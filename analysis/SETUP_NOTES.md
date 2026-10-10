1. Get to Google Cloud Console

Go to https://console.cloud.google.com and sign in with the same Google account that owns (or can access) your spreadsheet. If it’s your first time, you’ll be asked to accept the terms of service. You don’t need to pay for anything: the Sheets and Drive APIs are free at normal usage levels, and you won’t be asked for a card for this.

2. Create a project
At the top of the page, click the project selector (it sits next to the Google Cloud logo and may say “Select a project”).
Click New Project.
Give it a name like sheets-python and click Create.
Make sure the new project is selected in the project selector before moving on.
3. Enable the APIs
Open the left-hand menu (☰) and go to APIs & Services → Library.
Search for Google Sheets API, click it, then click Enable.
Go back to the Library, search for Google Drive API, and enable that too. (gspread uses Drive to find spreadsheets by name.)
4. Create a service account

A service account is a robot Google identity that your Python script logs in as.

Go to APIs & Services → Credentials.
Click Create Credentials → Service account.
Enter a name (e.g. sheets-reader) and click Create and continue.
You can skip the optional role and user-access steps. Click Done.
5. Download the key file
On the Credentials page, under Service Accounts, click the account you just created.
Open the Keys tab.
Click Add key → Create new key, choose JSON, and click Create.
A .json file downloads automatically. Move it into your project folder and rename it to something like service_account.json.

If key creation is blocked with a message about an organization policy, you’re probably on a work or school account. In that case, use a personal Google account for the Cloud project instead, or ask your admin.

6. Share the spreadsheet with the service account

This step trips people up. The service account is its own identity, so it can’t see your sheet until you share it.

Open the JSON file and find the client_email field. It looks like sheets-reader@sheets-python-123456.iam.gserviceaccount.com.
Open your Google Sheet and click Share.
Paste that email address, set the role to Viewer, and click Send (untick “Notify people” if it appears).
7. Install and run
bash
pip install gspread pandas matplotlib
python
import gspread
import pandas as pd

gc = gspread.service_account(filename="service_account.json")
sh = gc.open_by_key("YOUR_SHEET_ID")   # the long string in the sheet's URL
ws = sh.sheet1                          # first tab

df = pd.DataFrame(ws.get_all_records())
print(df.head())

You can find the sheet ID in the URL: https://docs.google.com/spreadsheets/d/THIS_PART/edit.

Common errors
APIError 403: The caller does not have permission: you haven’t shared the sheet with the service account’s email.
APIError 403: ... API has not been used in project: one of the two APIs isn’t enabled yet (or you enabled it on a different project).
SpreadsheetNotFound: same cause as the first one, or a typo in the name or ID. Using open_by_key avoids name mix-ups.

Once that prints your data, the plotting code from my earlier message will work as is. If you hit a snag at any step, tell me what the screen shows and I’ll help you through it.