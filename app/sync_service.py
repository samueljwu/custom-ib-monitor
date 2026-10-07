"""Read-only Flex retrieval followed by replay-safe local database reconciliation."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
import msvcrt
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from app.broker_sync import BrokerIngestor, parse_flex_xml
from app.diagnostics import configure_diagnostics
from app.flex_import import fetch_flex
from app.secret_store import load_flex_token
from app.services import MatchingService


@contextmanager
def single_writer_lock(database_path: Path, lock_name="ibkr-sync.lock"):
    lock_path = database_path.parent / lock_name
    handle = None
    try:
        handle = lock_path.open("a+b")
        handle.seek(0)
        if not handle.read(1):
            handle.seek(0)
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        if handle:
            handle.close()
        raise RuntimeError("Another IBKR Flex sync is running") from exc
    try:
        yield
    finally:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        handle.close()


def planned_windows(db, account_id: str, today: date) -> list[tuple[str, str]]:
    through = today - timedelta(days=1)
    row = db.conn.execute("""SELECT MAX(to_day) FROM broker_sync_windows
        WHERE account_id=? AND source='flex' AND status='complete'""", (account_id,)).fetchone()
    last = date.fromisoformat(row[0]) if row and row[0] else None
    first = last - timedelta(days=7) if last else through - timedelta(days=29)
    if first > through:
        return []
    windows = []
    while first <= through:
        end = min(first + timedelta(days=13), through)
        windows.append((first.isoformat(), end.isoformat()))
        first = end + timedelta(days=1)
    return windows


def _validate_report_window(xml: bytes, account_id: str, first: str, last: str):
    root = ET.fromstring(xml)
    statements = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "FlexStatement"]
    if len(statements) != 1 or statements[0].get("accountId") != account_id:
        raise ValueError("Flex report account mismatch")
    if (statements[0].get("fromDate"), statements[0].get("toDate")) != (
        first.replace("-", ""), last.replace("-", "")
    ):
        raise ValueError("Flex report date range mismatch")
    records, events = parse_flex_xml(xml, account_id)
    count = sum(node.tag.rsplit("}", 1)[-1] == "Trade"
                and (node.get("levelOfDetail") or "").upper() == "EXECUTION"
                for node in root.iter())
    if count != len(records):
        raise ValueError("Flex execution count mismatch")
    if any(not first <= record["trade_date"] <= last for record in records):
        raise ValueError("Flex execution outside requested date range")
    return records, events


def run_flex_sync(db, account_id: str, query_id: str, *, today: date | None = None,
                  token: str | None = None, fetcher=fetch_flex, pacing_seconds: float = 15,
                  windows_override: list[tuple[str, str]] | None = None) -> dict:
    """Catch up missed days with overlap; never invoke any trading endpoint."""
    if not account_id or not query_id:
        raise ValueError("IBKR account and Flex query ID are required")
    db.validate_account_ownership(account_id)
    today = today or date.today()
    with single_writer_lock(db.path):
        log = configure_diagnostics(db.path, "sync-trades")
        with db.conn:
            run_id = db.conn.execute("""INSERT INTO broker_sync_runs(account_id,source)
                VALUES (?, 'flex')""", (account_id,)).lastrowid
        db.set_metadata("ibkr_flex_sync_run_id", str(run_id))
        db.set_metadata("ibkr_flex_sync_status", "running")
        db.set_metadata("ibkr_flex_sync_started", datetime.now().isoformat(timespec="seconds"))
        secret = token
        stage = "loading Flex token"
        current_window = None
        aggregate = {"source_count": 0, "inserted": 0, "updated": 0,
                     "duplicates": 0, "legacy_inserted": 0,
                     "corporate_inserted": 0, "review": 0, "windows": 0}
        try:
            secret = secret or load_flex_token(account_id)
            if not secret:
                raise ValueError("IBKR Flex token is missing; renew it in Client Portal")
            windows = windows_override if windows_override is not None else planned_windows(db, account_id, today)
            log.info("Run %s started; %s date windows planned through %s", run_id, len(windows), today - timedelta(days=1))
            if windows:
                stage = "creating database backup"
                db.backup()
            last_request = 0.0
            for first, last in windows:
                current_window = (first, last)
                stage = "requesting Flex report"
                log.info("Run %s requesting window %s to %s", run_id, first, last)
                delay = pacing_seconds - (time.monotonic() - last_request)
                if last_request and delay > 0:
                    time.sleep(delay)
                last_request = time.monotonic()
                xml = fetcher(query_id, secret, from_day=first, to_day=last)
                stage = "validating Flex report"
                records, events = _validate_report_window(xml, account_id, first, last)
                stage = "importing executions"
                result = BrokerIngestor(db, account_id).ingest_many(
                    records, "flex", window=(first, last), events=events)
                if result.changed_position_ids:
                    stage = "rebuilding trade matches"
                    MatchingService(db).rebuild_auto(result.changed_position_ids)
                log.info("Run %s window %s to %s complete: source=%s inserted=%s updated=%s duplicates=%s review=%s",
                         run_id, first, last, len(records), result.inserted, result.updated,
                         result.duplicates, result.review)
                aggregate["source_count"] += len(records)
                aggregate["inserted"] += result.inserted
                aggregate["updated"] += result.updated
                aggregate["duplicates"] += result.duplicates
                aggregate["legacy_inserted"] += result.legacy_inserted
                aggregate["corporate_inserted"] += result.corporate_inserted
                aggregate["review"] += result.review
                aggregate["windows"] += 1
            with db.conn:
                db.conn.execute("""UPDATE broker_sync_runs SET finished_at=CURRENT_TIMESTAMP,
                    status=?,from_day=?,to_day=?,source_count=?,inserted_count=?,review_count=?
                    WHERE id=?""",
                    ("review" if aggregate["review"] else "complete",
                     windows[0][0] if windows else None, windows[-1][1] if windows else None,
                     aggregate["source_count"], aggregate["inserted"], aggregate["review"], run_id))
            db.set_metadata("ibkr_flex_sync_status", "review" if aggregate["review"] else "complete")
            db.set_metadata("ibkr_flex_sync_error", "")
            db.set_metadata("ibkr_flex_sync_stage", "")
            db.set_metadata("ibkr_flex_sync_completed", datetime.now().isoformat(timespec="seconds"))
            log.info("Run %s %s: %s", run_id, "review" if aggregate["review"] else "complete", aggregate)
            return aggregate
        except Exception as exc:
            message = str(exc).replace(secret, "[redacted]") if secret else str(exc)
            window_text = f"{current_window[0]} to {current_window[1]}" if current_window else "before first window"
            log.error("Run %s failed during %s (%s): %s: %s", run_id, stage, window_text,
                      type(exc).__name__, message)
            with db.conn:
                db.conn.execute("""UPDATE broker_sync_runs SET finished_at=CURRENT_TIMESTAMP,
                    status='failed',from_day=?,to_day=?,error=? WHERE id=?""",
                    (current_window[0] if current_window else None,
                     current_window[1] if current_window else None, message[:1000], run_id))
            db.set_metadata("ibkr_flex_sync_status", "failed")
            db.set_metadata("ibkr_flex_sync_error", message[:1000])
            db.set_metadata("ibkr_flex_sync_stage", stage)
            db.set_metadata("ibkr_flex_sync_failed_at", datetime.now().isoformat(timespec="seconds"))
            raise
