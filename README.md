# Custom IB Monitor

A Windows desktop monitor for one Interactive Brokers account. It reads live account and market data through your local TWS or IB Gateway and builds historical trades, performance, and cash views from your own Activity Flex queries. It does not place orders.

## Start

Install Python 3.11 or newer, then run in PowerShell:

```powershell
python -m pip install -r requirements.txt
python main.py
```

The app starts in Mock mode. In TWS or IB Gateway, enable socket API access and **Read-Only API**, then sign in. In **Settings**, choose **Use IBKR**, enter the host (`127.0.0.1` for the same computer), the socket port shown in TWS/Gateway, a client ID, and your account ID; apply the settings. No IBKR login password is entered into this app. [IBKR API setup](https://interactivebrokers.github.io/tws-api/initial_setup.html)

For history, create three account-scoped **Activity Flex Queries** with XML output in IBKR Client Portal: Trades, Analytics, and Cash. Enter their query IDs in Settings. Enable Flex Web Service, generate a token, and run `enter_flex_token.cmd`; enter the same account ID and paste the token into the local dialog. Press **Sync IBKR**. See [Historical reports](HISTORICAL_REPORTS.md) for the required sections, fields, and coverage. [IBKR Flex Queries](https://www.ibkrguides.com/brokerportal/performanceandstatements/flex.htm) · [Flex Web Service](https://www.ibkrguides.com/clientportal/performanceandstatements/flex-web-service.htm)

## What it shows

| View | Purpose |
| --- | --- |
| Overview | Account totals, trade-derived holdings, prices, P&L, and differences from broker positions. |
| Trades and Lots | Executions, matched sale lots, open lots, and realized P&L. |
| Rebalance | Saved target weights, buy/sell size estimates, and price scenarios; no order submission. |
| Analytics | Historical NAV, flow-adjusted performance, capital deployment, cash ratio, and current market or delta-adjusted exposure. |
| Cash | Dated cash activity by currency and validated statement balance bridges. |

Data, settings, reports, backups, and diagnostic logs stay on your computer. New installs use `%LOCALAPPDATA%\CustomIBMonitor`; the Flex token is stored in Windows Credential Manager. The SQLite database and backups are **not encrypted**. Choose a local, unsynchronized data and backup folder in Settings if you change the defaults. Keep real reports, databases, exports, and credentials out of Git.
