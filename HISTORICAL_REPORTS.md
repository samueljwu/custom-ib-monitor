# Historical IBKR reports

Create **three separate Activity Flex Queries** in IBKR Client Portal under **Performance & Reports → Flex Queries**. Use XML output, select only the account entered in the app, include every currency and instrument, and leave symbol filters empty. The app requests dated reports directly from IBKR Flex Web Service; no report file is uploaded to another service. Enter each query ID in **Settings**, then save one Flex token locally with `enter_flex_token.cmd`.

| Query / Settings field | Required sections and fields | Used for |
| --- | --- | --- |
| **Trades** / Trades Flex query ID | **Trades** at **Executions** detail: Account ID, Trade ID or IB Execution ID, Trade Date/Time, Buy/Sell, Quantity, Trade Price, Conid, Symbol, Asset Category, Currency, Multiplier, FX Rate to Base, IB Commission and Commission Currency. For options, also Local Symbol, Expiry, Put/Call, and Strike. Include **Corporate Actions**, **Option Exercises/Assignments/Expirations**, and **Transfers** with account, transaction ID, date, action/direction, asset class, contract ID, symbol, quantity, currency, cost or proceeds, multiplier and FX Rate to Base where offered. Include Base Currency or USD conversion evidence. | Completed executions, transferred opening lots, supported security events, and reconciliation review. Unsupported events stay flagged for review. |
| **Analytics** / Analytics Flex query ID | **Equity Summary in Base** with daily Report Date, Total NAV, and Cash; **Cash Transactions** with Report Date or Date/Time, Type, Amount, Currency, FX Rate to Base and Transaction ID; **Transfers** with date, direction, asset class, Position Amount in Base or cash amount, Currency, FX Rate to Base, and Transaction ID. Include Account Information with Base Currency, or a USD base declaration in each statement. | Completed daily NAV, cash balance, deposits/withdrawals, security transfers and flow-adjusted returns. Daily NAV rows and complete requested date coverage are needed. |
| **Cash** / Cash Flex query ID | **Cash Report** for every statement currency: Currency, From/To Date, Starting/Ending Cash, Net Trades Sales/Purchases, Commissions, Deposits/Withdrawals, Dividends, Payment in Lieu, Withholding Tax, Broker Interest and Other Fees. **Cash Transactions**: Account ID, Currency, Report Date or Date/Time, Type, Amount, Description, and Transaction ID. | Dated nontrade cash activity and per-currency opening-to-closing balance checks. Unsupported transaction types or a broken bridge stop that period's import. |

IBKR's field labels can vary by portal version. The required XML attributes are validated before a period is marked complete. The app currently expects a **USD base account** and one account per database. The Flex query must allow custom date requests and return the requested account and full date interval. Check the in-app sync status if IBKR cannot provide a section or older period. [IBKR Activity Flex reference](https://www.ibkrguides.com/reportingreference/reportguide/activity%20flex%20query%20reference.htm)

## Import and coverage

1. Start the app once, enter the account and three query IDs in Settings, and save the Flex token. Use a local, unsynchronized data folder if changing the default.
2. To fetch older history, close the app and run, for example:

   ```powershell
   python -m scripts.import_history --source all --from-date 2023-01-01 --to-date 2023-12-31
   ```

   You can use `--source trades`, `analytics`, or `cash` to import one report type. Use `--database C:\path\to\portfolio.sqlite3` only when you deliberately use a nondefault database. The command creates a local database backup before importing each source and processes short dated windows. Run cash periods in chronological order and choose dates that do not overlap existing imported cash periods.
3. Reopen the app and press **Sync IBKR** to catch up completed days through yesterday. Without an older import, the first automatic Trades and Cash sync starts with recent 30 day windows; Analytics starts at the beginning of the fourth previous calendar year. Review **Trades**, **Analytics**, **Cash**, and sync status for missing dates or events needing review.

IBKR controls the oldest available Flex history; an unavailable period cannot be reconstructed by this app. Live TWS/Gateway data supplies current positions, prices, FX, account values and recent executions, but not complete historical NAV or cash transactions. The app stores imported records in local SQLite, keeps backups and diagnostic logs locally, and does not save downloaded XML reports by default. SQLite files and backups are currently unencrypted; protect the local Windows account and backup folder.
