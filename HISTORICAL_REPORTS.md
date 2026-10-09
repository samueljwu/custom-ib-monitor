# Set up IBKR history

Create three **Activity Flex Queries**: **Trades**, **Analytics** and **Cash**. The app supports one **USD base account** per database.

## 1. Open Flex Queries

1. Sign in to IBKR Client Portal.
2. Click **Performance & Reports > Flex Queries**. Another route is **Menu > Reporting > Flex Queries**.
3. Find **Activity Flex Query** and click its **+** button.

[IBKR's query setup instructions](https://www.ibkrguides.com/clientportal/performanceandstatements/activityflex.htm)

## 2. Create Trades

1. Enter **Trades** in **Query Name**.
2. Click **Account Information**. Tick **Account ID**, **Currency** and **Date Opened**, then click **Save**. Leave the other fields unticked. **Currency** means your account's base currency.
3. Click **Trades**. Click **Select All** for the fields. Under **Level of Detail**, select **Executions** and **Closed Lots**. Click **Save**.
4. Click **Open Positions**. Click **Select All** for the fields, select both **Summary** and **Lot** detail, then **Save**.
5. Click **Corporate Actions > Select All > Save**.
6. Click **Option Exercises, Assignments and Expirations > Select All > Save**.
7. Click **Transfers > Select All > Save**.
8. Follow **Save each query** below before creating Analytics.

Use **Select All** inside these section pop-ups, not across the whole page. Other sections can stay unselected. The detail choices are separate from the field checkboxes.

[Account Information fields](https://www.ibkrguides.com/reportingreference/reportguide/account%20information%20activity%20flex.htm) | [Trades detail](https://www.ibkrguides.com/reportingreference/reportguide/tradesfq.htm) | [Open Positions detail](https://www.ibkrguides.com/reportingreference/reportguide/open%20positionsfq.htm)

## 3. Create Analytics

1. Return to **Flex Queries**, click **+** under **Activity Flex Query**, and name it **Analytics**.
2. Click **Account Information**. Tick **Account ID**, **Currency** and **Date Opened**, then **Save**.
3. Click **Net Asset Value (NAV) in Base > Select All > Save**. This includes **Report Date**, **Total** and **Cash**.
4. Click **Cash Transactions > Select All > Save**.
5. Click **Transfers > Select All > Save**.
6. Follow **Save each query** below. Set **Breakout by Day** to **Yes** for Analytics.

The NAV section may also be labelled **Net Asset Value (NAV) Summary in Base**. It supplies daily account values. [IBKR NAV fields](https://www.ibkrguides.com/reportingreference/reportguide/net%20asset%20value%20(nav)%20summary%20in%20base.htm)

## 4. Create Cash

1. Return to **Flex Queries**, click **+** under **Activity Flex Query**, and name it **Cash**.
2. Click **Account Information**. Tick **Account ID**, **Currency** and **Date Opened**, then **Save**.
3. Click **Cash Report > Select All > Save**.
4. Click **Cash Transactions > Select All > Save**. Keep every transaction type included if a type filter is offered.
5. Follow **Save each query** below. Set **Breakout by Day** to **No** for Cash.

Commission adjustments come through **Cash Transactions**; you do not need a separate Commission Details query. [IBKR explanation](https://www.interactivebrokers.com/en/?f=%2Fen%2Faccounts%2FreleaseNotes%2FStatement_Notes_Feb2013.php)

## 5. Save each query

Do this for **Trades**, **Analytics** and **Cash**:

1. Leave **Filters > Symbols** empty.
2. Under **Delivery Configuration**, click **Accounts > Add/Edit Accounts** and select only your app's account. Set **Format** to **XML** and **Period** to **Last 30 Calendar Days**. The app chooses its own dates when importing history.
3. Under **General Configuration**, use these settings:

   | Setting | Choose |
   | --- | --- |
   | Date Format | **yyyyMMdd** |
   | Time Format | **HHmmss** |
   | Date/Time Separator | **;** (semicolon) |
   | Include Currency Rates | **Yes** |
   | Display Account Alias in Place of Account ID | **No** |
   | Breakout by Day | **Analytics: Yes. Trades and Cash: No.** |

4. Click **Continue > Create**. Note the saved query's **Query ID**; reopen its details if needed.

[IBKR configuration reference](https://www.ibkrguides.com/reportingreference/reportguide/delivery%20configuration%20and%20general%20configuration.htm)

## 6. Connect the app

1. In Client Portal, find **Flex Web Service Configuration** and click its **gear**.
2. Turn **Flex Web Service** on. Copy the token shown. If it is expired, use **Generate A New Token**.
3. In the app, open **Settings > History & Flex**. Paste each Query ID into its matching **Trades**, **Analytics** or **Cash** field.
4. Click **Save settings**, then **Save Flex token**, and paste the token.
5. Click **Import history**. First try a short past range with known activity; then import the older range you need.

[IBKR token setup](https://www.ibkrguides.com/clientportal/performanceandstatements/flex-web-service.htm)

Use **Sync IBKR** for later updates. **Pause import** saves the current report before stopping; **Resume import** skips history already saved.

If dates are missing, open **Settings > History & Flex > Show all date ranges**. IBKR may not supply older periods. Use **Import older trades** for an older Activity Statement CSV; follow its instructions. This adds trades and verified transferred holdings only.
