"""Fetch dated Activity Flex history into the local portfolio database."""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from app.analytics_flex import run_analytics_flex_sync
from app.cash_flex import run_cash_flex_sync
from app.database import Database
from app.sync_service import run_flex_sync


WINDOW_DAYS = {"trades": 14, "analytics": 180, "cash": 30}
QUERY_KEYS = {"trades": "flex_query_id", "analytics": "analytics_flex_query_id",
              "cash": "cash_flex_query_id"}
RUNNERS = {"trades": run_flex_sync, "analytics": run_analytics_flex_sync,
           "cash": run_cash_flex_sync}


def windows(first: date, last: date, days: int) -> list[tuple[str, str]]:
    result = []
    while first <= last:
        end = min(first + timedelta(days=days - 1), last)
        result.append((first.isoformat(), end.isoformat()))
        first = end + timedelta(days=1)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=(*WINDOW_DAYS, "all"), required=True)
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--database", help="Optional path to an existing local portfolio SQLite file")
    args = parser.parse_args(argv)
    if args.from_date > args.to_date or args.to_date >= date.today():
        parser.error("Choose an ordered date range ending before today")
    if args.database:
        from pathlib import Path
        if not Path(args.database).is_file():
            parser.error("The selected database does not exist")
    db = Database(args.database)
    try:
        account = db.setting("ib_account_id")
        if not account:
            parser.error("Set the IBKR account in the app before importing history")
        sources = list(WINDOW_DAYS) if args.source == "all" else [args.source]
        for source in sources:
            query = db.setting(QUERY_KEYS[source])
            if not query:
                parser.error(f"Set the {source} Flex query ID in the app first")
        for source in sources:
            if source == "cash":
                overlap = db.conn.execute("""SELECT 1 FROM cash_reconciliations
                    WHERE portfolio_id=1 AND NOT (period_to<? OR period_from>?) LIMIT 1""",
                    (args.from_date.isoformat(), args.to_date.isoformat())).fetchone()
                if overlap:
                    parser.error("Cash history overlaps an imported period; choose missing dates only")
            spans = windows(args.from_date, args.to_date, WINDOW_DAYS[source])
            result = RUNNERS[source](db, account, db.setting(QUERY_KEYS[source]),
                                     windows_override=spans)
            print(f"{source}: {result['windows']} report windows processed")
        return 0
    finally:
        db.conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
