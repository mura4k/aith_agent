import re
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

def get_sheets_service(credentials_path: str | None = None):
    """Return an authorized Sheets API client.

    Credentials are loaded from a service account JSON file. The path can be
    provided explicitly or via the environment variable
    ``GOOGLE_CREDENTIALS_FILE``. Raises ``ValueError`` if the path is missing.
    """

    if credentials_path is None:
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_FILE")

    if not credentials_path:
        raise ValueError("Path to Google service account JSON file is required")

    creds = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    return build("sheets", "v4", credentials=creds)

def extract_sheet_id(url):
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def get_sheet_data(sheet_id, range_name):
    service = get_sheets_service()
    result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_name).execute()
    return result.get('values', [])

def update_sheet_data(sheet_id, range_name, values):
    service = get_sheets_service()
    body = {'values': values}
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=range_name,
        valueInputOption='USER_ENTERED', body=body).execute()

def get_spreadsheet_metadata(sheet_id):
    service = get_sheets_service()
    return service.spreadsheets().get(spreadsheetId=sheet_id).execute()
