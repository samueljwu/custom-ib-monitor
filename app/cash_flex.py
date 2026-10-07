"""Validated, replay-safe Cash history from an Activity Flex query."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import time
import xml.etree.ElementTree as ET

from app.flex_import import fetch_flex
from app.secret_store import load_flex_token
from app.sync_service import single_writer_lock


CENT = Decimal("0.01")


def _tag(node):
    return node.tag.rsplit("}", 1)[-1]


def _day(value):
    try:
        return datetime.strptime((value or "")[:10].replace("-", "")[:8], "%Y%m%d").date().isoformat()
    except ValueError:
        raise ValueError("Invalid Cash Flex date") from None


def _amount(value, label, *, required=False):
    if value in (None, ""):
        if required:
            raise ValueError(f"Cash Flex is missing {label}")
        return Decimal(0)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid Cash Flex {label}") from None
    if not number.is_finite():
        raise ValueError(f"Invalid Cash Flex {label}")
    return number


def _kind(raw, amount):
    name = (raw or "").strip().lower().replace("&", "and")
    if name in ("deposits/withdrawals", "deposits and withdrawals", "deposit", "withdrawal"):
        return "Deposit" if amount >= 0 else "Withdrawal"
    if "payment in lieu" in name:
        return "Payment in lieu"
    if "dividend" in name:
        return "Dividend"
    if "withholding" in name or "transaction tax" in name:
        return "Withholding tax"
    if "stock lending" in name or "syep" in name:
        return "Stock lending interest"
    if "interest" in name:
        return "Debit interest" if amount < 0 else "Credit interest"
    if name in ("other fee", "other fees", "fee", "fees"):
        return "Other fee"
    raise ValueError(f"Unsupported Cash Flex transaction type: {raw or '(blank)'}")


def parse_cash_flex(xml, account_id, first, last):
    """Return one complete, currency-specific cash bridge and its transactions."""
    root = ET.fromstring(xml)
    statements = [node for node in root.iter() if _tag(node) == "FlexStatement"]
    if len(statements) != 1:
        raise ValueError("Cash Flex query must return exactly one account statement")
    statement = statements[0]
    if (statement.get("accountId") != account_id or
            _day(statement.get("fromDate")) != first or _day(statement.get("toDate")) != last):
        raise ValueError("Cash Flex account or date range mismatch")
    sections = {_tag(node): node for node in statement}
    if not {"CashReport", "CashTransactions"}.issubset(sections):
        raise ValueError("Cash Flex query needs Cash Report and Cash Transactions sections")
    reports = {}
    for node in sections["CashReport"]:
        if _tag(node) != "CashReportCurrency":
            continue
        code = (node.get("currency") or "").upper()
        if code in ("BASE_SUMMARY", "BASE", "BASE CURRENCY SUMMARY"):
            continue
        if not code or code in reports or node.get("accountId", account_id) != account_id:
            raise ValueError("Invalid or duplicate Cash Flex currency bridge")
        if (node.get("fromDate") and _day(node.get("fromDate")) != first or
                node.get("toDate") and _day(node.get("toDate")) != last):
            raise ValueError("Cash Flex currency bridge date mismatch")
        reports[code] = node
    if "USD" not in reports:
        raise ValueError("Cash Flex query needs a USD Cash Report row")

    movements = defaultdict(list)
    occurrences = Counter()
    for node in sections["CashTransactions"]:
        if _tag(node) != "CashTransaction":
            continue
        if node.get("accountId", account_id) != account_id:
            raise ValueError("Cash Flex transaction account mismatch")
        code = (node.get("currency") or "").upper()
        if code not in reports:
            raise ValueError(f"Cash Flex transaction has no {code or 'currency'} bridge")
        amount = _amount(node.get("amount"), "transaction amount", required=True)
        kind = _kind(node.get("type"), amount)
        reported_day = _day(node.get("reportDate") or node.get("dateTime"))
        if not first <= reported_day <= last:
            raise ValueError("Cash Flex transaction date is outside its statement; review posting date before importing")
        identity = (account_id, code, reported_day, kind, str(amount),
                    node.get("description") or "", node.get("transactionID") or "")
        occurrences[identity] += 1
        key = sha256(json.dumps((*identity, occurrences[identity]),
                                separators=(",", ":")).encode()).hexdigest()
        movements[code].append({
            "source_key": "cash-flex:" + key, "reported_day": reported_day,
            "kind": kind, "currency": code, "amount": str(amount),
            "description": node.get("description") or kind,
        })

    bridges = []
    for code, node in sorted(reports.items()):
        opening = _amount(node.get("startingCash"), "starting cash", required=True)
        closing = _amount(node.get("endingCash"), "ending cash", required=True)
        sales = _amount(node.get("netTradesSales"), "trade sales")
        purchases = _amount(node.get("netTradesPurchases"), "trade purchases")
        commissions = _amount(node.get("commissions"), "commissions")
        rows = movements[code]
        totals = defaultdict(Decimal)
        for row in rows:
            totals[row["kind"]] += Decimal(row["amount"])
        nontrade = sum(totals.values(), Decimal(0))
        difference = opening + sales + purchases + commissions + nontrade - closing
        if abs(difference) > CENT:
            raise ValueError(f"Cash Flex {code} bridge differs by {difference}; check missing transaction types or report fields")
        checks = (
            ("depositWithdrawals", totals["Deposit"] + totals["Withdrawal"]),
            ("dividends", totals["Dividend"]),
            ("paymentInLieu", totals["Payment in lieu"]),
            ("withholdingTax", totals["Withholding tax"]),
            ("otherFees", totals["Other fee"]),
            ("brokerInterest", totals["Credit interest"] + totals["Debit interest"] +
             totals["Stock lending interest"]),
        )
        for field, actual in checks:
            if node.get(field) not in (None, "") and abs(_amount(node.get(field), field) - actual) > CENT:
                raise ValueError(f"Cash Flex {code} {field} does not match transactions")
        bridges.append({
            "currency": code, "period_from": first, "period_to": last,
            "opening_cash": str(opening), "trade_sales": str(sales),
            "trade_purchases": str(purchases), "trade_commissions": str(commissions),
            "nontrade_cash": str(nontrade), "closing_cash": str(closing),
            "difference": str(difference), "movements": rows,
        })
    return bridges


def planned_cash_windows(db, portfolio_id, today):
    latest = db.cash_reconciliation(portfolio_id)
    through = today - timedelta(days=1)
    first = (date.fromisoformat(latest["period_to"]) + timedelta(days=1)
             if latest else through - timedelta(days=29))
    windows = []
    while first <= through:
        end = min(first + timedelta(days=29), through)
        windows.append((first.isoformat(), end.isoformat()))
        first = end + timedelta(days=1)
    return windows


def run_cash_flex_sync(db, account_id, query_id, *, portfolio_id=1, today=None,
                       token=None, fetcher=fetch_flex, pacing_seconds=15, windows_override=None):
    """Fetch completed cash statements; commit only windows whose bridges close."""
    if not account_id or not query_id:
        raise ValueError("IBKR account and Cash Flex query ID are required")
    db.validate_account_ownership(account_id)
    today = today or date.today()
    windows = windows_override if windows_override is not None else planned_cash_windows(db, portfolio_id, today)
    if not windows:
        return {"windows": 0, "movements": 0}
    secret = token or load_flex_token(account_id)
    if not secret:
        raise ValueError("IBKR Flex token is missing; renew it in Client Portal")
    count = 0
    with single_writer_lock(db.path, "ibkr-cash-sync.lock"):
        db.backup()
        last_request = 0.0
        for first, last in windows:
            delay = pacing_seconds - (time.monotonic() - last_request)
            if last_request and delay > 0:
                time.sleep(delay)
            last_request = time.monotonic()
            xml = fetcher(query_id, secret, from_day=first, to_day=last)
            bridges = parse_cash_flex(xml, account_id, first, last)
            digest = sha256(xml).hexdigest()
            with db.conn:
                for bridge in bridges:
                    prior = db.conn.execute("""SELECT closing_cash FROM cash_reconciliations
                        WHERE portfolio_id=? AND account_id=? AND currency=? AND period_to<?
                        ORDER BY period_to DESC LIMIT 1""",
                        (portfolio_id, account_id, bridge["currency"], first)).fetchone()
                    if prior and abs(Decimal(prior[0]) - Decimal(bridge["opening_cash"])) > CENT:
                        raise ValueError(f"Cash Flex {bridge['currency']} opening does not match prior close")
                    following = db.conn.execute("""SELECT period_from,opening_cash FROM cash_reconciliations
                        WHERE portfolio_id=? AND account_id=? AND currency=? AND period_from>?
                        ORDER BY period_from LIMIT 1""",
                        (portfolio_id, account_id, bridge["currency"], last)).fetchone()
                    if (following and date.fromisoformat(following[0]) ==
                            date.fromisoformat(last) + timedelta(days=1) and
                            abs(Decimal(following[1]) - Decimal(bridge["closing_cash"])) > CENT):
                        raise ValueError(f"Cash Flex {bridge['currency']} closing does not match next opening")
                    for row in bridge["movements"]:
                        db.conn.execute("""INSERT INTO cash_movements
                            (portfolio_id,account_id,source_key,reported_day,period_from,period_to,
                             kind,currency,amount,description,source_section,source_hash)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(portfolio_id,account_id,source_key) DO UPDATE SET
                            kind=excluded.kind,amount=excluded.amount,description=excluded.description,
                            source_hash=excluded.source_hash""",
                            (portfolio_id, account_id, row["source_key"], row["reported_day"],
                             first, last, row["kind"], row["currency"], row["amount"],
                             row["description"], "Cash Transactions", digest))
                    db.conn.execute("""INSERT INTO cash_reconciliations
                        (portfolio_id,account_id,period_from,period_to,currency,opening_cash,
                         trade_sales,trade_purchases,trade_commissions,nontrade_cash,
                         closing_cash,difference,source_hash)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (portfolio_id, account_id, first, last, bridge["currency"],
                         bridge["opening_cash"], bridge["trade_sales"],
                         bridge["trade_purchases"], bridge["trade_commissions"],
                         bridge["nontrade_cash"], bridge["closing_cash"],
                         bridge["difference"], digest))
                    count += len(bridge["movements"])
        db.set_metadata("ibkr_cash_sync_completed", datetime.now().isoformat(timespec="seconds"))
    return {"windows": len(windows), "movements": count}
