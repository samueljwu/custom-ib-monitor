"""Import non-trade cash activity from an IBKR Activity Statement CSV.

Statement cash sections are checked against the trade ledger before any write.
Trade commissions remain on executions; later refunds are linked to those
executions and applied when deriving their effective fee.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re

from scripts.audit_activity_cash import audit, amount, cash_values, close, one_value, section, statement_rows


CASH_SECTIONS = (
    "Deposits & Withdrawals", "Dividends", "Withholding Tax", "Interest", "Fees"
)
REFUND = re.compile(r"^Refund \(([^,]+),\s*([+-]?\d+(?:\.\d+)?),\s*(\d{4}-\d{2}-\d{2})\)$")


def _kind(section_name, description, value):
    if section_name == "Deposits & Withdrawals":
        if "Electronic Fund Transfer" in description:
            return "Deposit" if value >= 0 else "Withdrawal"
        return "Cash adjustment"
    if section_name == "Dividends":
        return "Payment in lieu" if "Payment in Lieu" in description else "Dividend"
    if section_name == "Withholding Tax":
        return "Withholding tax"
    if section_name == "Interest":
        return "Stock lending interest" if "SYEP" in description else (
            "Debit interest" if value < 0 else "Credit interest")
    if section_name == "Fees":
        return "Other fee"
    raise ValueError(f"Unsupported cash section {section_name}")


def _source_key(account, section_name, currency, day, description, value, occurrence):
    identity = [account, section_name, currency, day, description, str(value), occurrence]
    return sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def _parse_movements(rows, account, first, last, source_hash):
    movements = []
    occurrence = Counter()
    for section_name in CASH_SECTIONS:
        for row in section(rows, section_name):
            if row[2] == "Total":
                continue
            if section_name == "Fees":
                currency, day, description, raw_amount = row[3], row[4], row[5], row[6]
            else:
                currency, day, description, raw_amount = row[2], row[3], row[4], row[5]
            date.fromisoformat(day)
            if currency != "USD":
                raise ValueError(f"Non-USD {section_name} needs a currency cash bridge")
            value = amount(raw_amount)
            marker = (section_name, currency, day, description, str(value))
            occurrence[marker] += 1
            movements.append({
                "source_key": _source_key(account, *marker, occurrence[marker]),
                "reported_day": day, "period_from": first, "period_to": last,
                "kind": _kind(section_name, description, value), "currency": currency,
                "amount": str(value), "description": description,
                "source_section": section_name, "source_hash": source_hash,
            })
    return movements


def _match_refunds(conn, rows, account, source_hash):
    refunds = []
    occurrence = Counter()
    by_trade = defaultdict(Decimal)
    for row in section(rows, "Commission Adjustments"):
        if row[2] == "Total":
            continue
        if row[2] != "USD":
            raise ValueError("Non-USD commission refund needs FX conversion")
        reported_day, description, refund = row[3], row[4], amount(row[5])
        date.fromisoformat(reported_day)
        match = REFUND.fullmatch(description)
        if not match or refund < 0:
            raise ValueError(f"Commission adjustment cannot be assigned to a trade: {description}")
        ticker, signed_qty, trade_day = match.groups()
        qty = amount(signed_qty)
        side = "BUY" if qty > 0 else "SELL"
        candidates = conn.execute("""SELECT id,quantity,commission_usd FROM trades
            WHERE portfolio_id=1 AND display_ticker=? AND trade_date=? AND side=?
            AND quantity>=?""", (ticker, trade_day, side, float(abs(qty)))).fetchall()
        eligible = [trade for trade in candidates if abs(
            amount(trade["commission_usd"]) * abs(qty) / amount(trade["quantity"]) - refund
        ) <= Decimal("0.0001")]
        exact_quantity = [trade for trade in eligible if
                          abs(amount(trade["quantity"]) - abs(qty)) <= Decimal("0.00000001")]
        if exact_quantity:
            eligible = exact_quantity
        if len(eligible) != 1:
            raise ValueError(f"Commission refund has {len(eligible)} matching trades: {description}")
        trade = eligible[0]
        by_trade[trade["id"]] += refund
        marker = ("Commission Adjustments", "USD", reported_day, description, str(refund))
        occurrence[marker] += 1
        refunds.append({
            "source_key": _source_key(account, *marker, occurrence[marker]),
            "trade_row_id": trade["id"], "reported_day": reported_day,
            "refund_usd": str(refund), "description": description,
            "source_hash": source_hash,
        })
    for trade_id, total in by_trade.items():
        raw = conn.execute("SELECT commission_usd FROM trades WHERE id=?", (trade_id,)).fetchone()
        if total - amount(raw[0]) > Decimal("0.0001"):
            raise ValueError(f"Refunds exceed the original commission for trade {trade_id}")
    return refunds


def _check_categories(movements, refunds, cash):
    totals = defaultdict(Decimal)
    for row in movements:
        totals[row["kind"]] += amount(row["amount"])
    close(totals["Deposit"] + totals["Withdrawal"] + totals["Cash adjustment"],
          cash["Deposits"], "Deposits and cash adjustments")
    close(totals["Dividend"], cash["Dividends"], "Dividends")
    close(totals["Payment in lieu"], cash["Payment In Lieu of Dividends"], "Payments in lieu")
    close(totals["Withholding tax"], cash["Withholding Tax"], "Withholding tax")
    close(totals["Credit interest"] + totals["Debit interest"] +
          totals["Stock lending interest"], cash["Broker Interest Paid and Received"], "Interest")
    close(totals["Other fee"], cash["Other Fees"], "Other fees")
    nontrade = sum(totals.values(), Decimal(0))
    if len(refunds) != len({row["source_key"] for row in refunds}):
        raise ValueError("Duplicate commission refund source IDs")
    return nontrade


def import_activity_cash(db, path, portfolio_id=1):
    """Validate and replay a complete statement into the selected local portfolio."""
    path = Path(path)
    account = db.setting("ib_account_id")
    if not account or portfolio_id != 1:
        raise ValueError("Select the configured IBKR portfolio")
    audit(path, db.path)  # Read-only full statement, trade, cash, NAV and quantity checks.
    rows = statement_rows(path)
    if one_value(rows, "Account Information", "Account") != account:
        raise ValueError("Statement account mismatch")
    period = one_value(rows, "Statement", "Period")
    start_text, end_text = period.split(" - ", 1)
    first = datetime.strptime(start_text, "%B %d, %Y").date()
    last = datetime.strptime(end_text, "%B %d, %Y").date()
    first_day, last_day = first.isoformat(), last.isoformat()
    source_hash = sha256(path.read_bytes()).hexdigest()
    cash_currencies = {row[3] for row in section(rows, "Cash Report") if len(row) > 4}
    unsupported = cash_currencies - {"USD", "AUD", "Base Currency Summary"}
    if unsupported:
        raise ValueError(f"Currency cash bridge needs review: {', '.join(sorted(unsupported))}")
    cash = cash_values(rows, "USD")
    aud = cash_values(rows, "AUD")
    base = cash_values(rows, "Base Currency Summary")
    movements = _parse_movements(rows, account, first_day, last_day, source_hash)
    refunds = _match_refunds(db.conn, rows, account, source_hash)
    nontrade = _check_categories(movements, refunds, cash)
    trade_commissions = cash["Commissions"]
    expected = (cash["Starting Cash"] + cash["Trades (Sales)"] +
                cash["Trades (Purchase)"] + trade_commissions + nontrade)
    difference = expected - cash["Ending Cash"]
    close(difference, Decimal(0), "Imported cash bridge")
    if aud:
        aud_expected = (aud["Starting Cash"] + aud["Trades (Sales)"] +
                        aud["Trades (Purchase)"] + aud["Commissions"])
        aud_difference = aud_expected - aud["Ending Cash"]
        close(aud_difference, Decimal(0), "AUD cash bridge")
    nav_rows = {row[2].strip(): amount(row[6]) for row in section(rows, "Net Asset Value")
                if len(row) > 6}
    prior_nav_rows = [row for row in section(rows, "Net Asset Value")
                      if len(row) > 6 and row[2].strip() == "Total"]
    prior_nav = amount(prior_nav_rows[0][3])
    prior_import = db.conn.execute("""SELECT source_hash FROM cash_reconciliations
        WHERE portfolio_id=? AND account_id=? AND period_from=? AND period_to=?
          AND currency='USD'""", (portfolio_id, account, first_day, last_day)).fetchone()
    if prior_import and prior_import[0] != source_hash:
        raise ValueError("A different statement for this period was already imported; review it before replacing")
    with db.conn:
        for row in movements:
            db.conn.execute("""INSERT INTO cash_movements
                (portfolio_id,account_id,source_key,reported_day,period_from,period_to,
                 kind,currency,amount,description,source_section,source_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(portfolio_id,account_id,source_key)
                DO UPDATE SET kind=excluded.kind,amount=excluded.amount,
                description=excluded.description,source_hash=excluded.source_hash""",
                (portfolio_id, account, row["source_key"], row["reported_day"],
                 first_day, last_day, row["kind"], row["currency"], row["amount"],
                 row["description"], row["source_section"], source_hash))
            if row["kind"] in {"Deposit", "Withdrawal"}:
                db.conn.execute("""INSERT INTO external_flows
                    (portfolio_id,source_id,day,amount_usd,kind) VALUES (?,?,?,?,?)
                    ON CONFLICT(portfolio_id,source_id) DO UPDATE SET
                    day=excluded.day,amount_usd=excluded.amount_usd,kind=excluded.kind""",
                    (portfolio_id, "cash:" + row["source_key"], row["reported_day"],
                     float(row["amount"]), row["kind"].lower()))
        for row in refunds:
            db.conn.execute("""INSERT INTO trade_fee_adjustments
                (portfolio_id,account_id,source_key,trade_row_id,reported_day,refund_usd,
                 description,source_hash) VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(portfolio_id,account_id,source_key) DO UPDATE SET
                trade_row_id=excluded.trade_row_id,refund_usd=excluded.refund_usd,
                source_hash=excluded.source_hash""",
                (portfolio_id, account, row["source_key"], row["trade_row_id"],
                 row["reported_day"], row["refund_usd"], row["description"], source_hash))
        for trade_id in {row["trade_row_id"] for row in refunds}:
            total = sum((amount(item[0]) for item in db.conn.execute(
                "SELECT refund_usd FROM trade_fee_adjustments WHERE trade_row_id=?",
                (trade_id,))), Decimal(0))
            original = amount(db.conn.execute(
                "SELECT commission_usd FROM trades WHERE id=?", (trade_id,)).fetchone()[0])
            if total - original > Decimal("0.0001"):
                raise ValueError(f"Refunds exceed original trade commission for {trade_id}")
        db.conn.execute("""INSERT INTO cash_reconciliations
            (portfolio_id,account_id,period_from,period_to,currency,opening_cash,trade_sales,
             trade_purchases,trade_commissions,nontrade_cash,closing_cash,difference,nav_usd,source_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(portfolio_id,account_id,period_from,period_to,currency) DO UPDATE SET
            opening_cash=excluded.opening_cash,trade_sales=excluded.trade_sales,
            trade_purchases=excluded.trade_purchases,trade_commissions=excluded.trade_commissions,
            nontrade_cash=excluded.nontrade_cash,closing_cash=excluded.closing_cash,
            difference=excluded.difference,nav_usd=excluded.nav_usd,
            source_hash=excluded.source_hash,checked_at=CURRENT_TIMESTAMP""",
            (portfolio_id, account, first_day, last_day, "USD", str(cash["Starting Cash"]),
             str(cash["Trades (Sales)"]), str(cash["Trades (Purchase)"]),
             str(trade_commissions), str(nontrade), str(cash["Ending Cash"]),
             str(difference), str(nav_rows["Total"]), source_hash))
        if aud:
            db.conn.execute("""INSERT INTO cash_reconciliations
                (portfolio_id,account_id,period_from,period_to,currency,opening_cash,trade_sales,
                 trade_purchases,trade_commissions,nontrade_cash,closing_cash,difference,nav_usd,source_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(portfolio_id,account_id,period_from,period_to,currency) DO UPDATE SET
                source_hash=excluded.source_hash,checked_at=CURRENT_TIMESTAMP""",
                (portfolio_id, account, first_day, last_day, "AUD", str(aud["Starting Cash"]),
                 str(aud["Trades (Sales)"]), str(aud["Trades (Purchase)"]),
                 str(aud["Commissions"]), "0", str(aud["Ending Cash"]),
                 str(aud_difference), None, source_hash))
        for day, nav, balance in ((first - timedelta(days=1), prior_nav, cash["Starting Cash"]),
                                  (last, nav_rows["Total"], base["Ending Cash"])):
            db.conn.execute("""INSERT INTO account_history
                (portfolio_id,day,nav_usd,cash_usd,source,flow_covered)
                VALUES (?,?,?,?,'activity_statement',0)
                ON CONFLICT(portfolio_id,day) DO UPDATE SET
                nav_usd=excluded.nav_usd,cash_usd=excluded.cash_usd,
                source=excluded.source,flow_covered=0
                WHERE account_history.source!='flex'""",
                (portfolio_id, day.isoformat(), float(nav), float(balance)))
    return {"movements": len(movements), "fee_refunds": len(refunds),
            "nontrade_usd": str(nontrade), "closing_cash_usd": str(cash["Ending Cash"]),
            "nav_usd": str(nav_rows["Total"]), "difference_usd": str(difference)}
