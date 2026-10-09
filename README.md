# Custom IB Monitor

A read-only Python desktop app for one Interactive Brokers account with a USD base currency. Monitor holdings, trades, performance, cash, and exposure, and plan rebalancing scenarios. The app cannot place orders.

## Features

| View | Functions |
| --- | --- |
| Overview | Account totals, live prices, holdings, P&L, and position reconciliation. |
| Trades and Lots | Execution history, lot matching, and realized/open P&L including fees and FX. |
| Analytics | NAV, flow-adjusted performance, S&P 500 comparison, daily gain/loss rankings, Sharpe, and capital deployment. |
| Returns | Lifetime trading P&L and return on purchase cost, with contributing lots. |
| Exposure | Market-value or option-adjusted exposure by sector or custom categories. |
| Cash | Cash activity by currency and balance checks. |
| Rebalance | Holding and cash targets, estimated trades, stock ideas, and upside/downside scenarios. |

Returns and Exposure are inside Analytics. Tables support sorting, filtering, copying, custom decimals, and saved views. Switch themes, reorder tabs, export a workbook, or create a backup. Press **F1** for the in-app guide.

## Run

Install Python 3.11, then run from this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

The app starts in **Demo** mode until you configure IBKR. After code changes, close and rerun it.

Use `--database` to select a SQLite file for this launch. The path must be in a subfolder under the repo's `data/` directory; it does not change the default selection:

```powershell
.\.venv\Scripts\python.exe main.py --database data\my-portfolio\portfolio.sqlite3
```

## Connect IBKR

1. Sign in to TWS or IB Gateway. Enable socket API access and **Read-Only API**.
2. Open the app's **Settings**, select **IBKR** as the data source, and enter your account. Under **Connection options**, set the host (`127.0.0.1` for the same computer), matching API port, and an unused client ID. Click **Save settings**.
3. Create three Activity Flex Queries with XML output: **Trades**, **Analytics**, and **Cash**. Follow the [historical reports setup guide](HISTORICAL_REPORTS.md).
4. Enable Flex Web Service in IBKR Client Portal. Enter the three query IDs in **Settings → History & Flex**, save settings, then choose **Save Flex token**.
5. Click **Sync IBKR** for updates or **Import history** for an earlier date range. Imports support pause/resume and show coverage gaps. **Import older trades** supports an English Activity Statement CSV when Flex history is unavailable.

The app does not need your IBKR login password. Live prices depend on market-data permissions; delayed and cached quotes are labelled. See [SECURITY_DESIGN.md](SECURITY_DESIGN.md) for credential handling and security constraints.

## Development

Install test dependencies and run the synthetic test suite:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```
