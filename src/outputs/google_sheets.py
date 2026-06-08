"""
Google Sheets integration via gspread + service account.

Setup (one-time):
1. Go to https://console.cloud.google.com
2. Create a project → Enable "Google Sheets API" and "Google Drive API"
3. Create a Service Account → Download JSON key → save as credentials/google_service_account.json
4. Share your target Google Sheet with the service account email (editor access)
5. Copy the Sheet ID from the URL and set GOOGLE_SPREADSHEET_ID in .env
"""
import os
from datetime import date
from typing import List

import gspread
from google.oauth2.service_account import Credentials

from src.storage.models import Listing
from src.utils.logger import get_logger
from src.utils.retry import sheets_retry

_SETUP_MISSING = FileNotFoundError  # do not retry on missing credentials file

log = get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "ID", "Title", "Equipment Type", "Brand", "Model", "Year",
    "Price", "Location", "Seller Name", "Seller Type", "Phone",
    "Description", "Photos", "Listing URL", "Date Listed",
    "Date Found", "Last Checked", "Status", "Priority", "Score",
    "Source", "Search Keyword", "Search City", "Notes",
]

PRIORITY_COLORS = {
    "high": {"red": 0.56, "green": 0.93, "blue": 0.56},
    "medium": {"red": 1.0, "green": 0.95, "blue": 0.6},
    "low": {"red": 0.9, "green": 0.9, "blue": 0.9},
    "rejected": {"red": 1.0, "green": 0.8, "blue": 0.8},
}


class GoogleSheetsExporter:
    def __init__(self):
        self.creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/google_service_account.json")
        self.spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", "")
        self._client = None
        self._spreadsheet = None

    def _connect(self):
        if self._client:
            return
        if not os.path.exists(self.creds_file):
            raise FileNotFoundError(
                f"Google service account file not found: {self.creds_file}\n"
                "See credentials/google_service_account.json — follow setup in src/outputs/google_sheets.py"
            )
        creds = Credentials.from_service_account_file(self.creds_file, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)
        log.info("Connected to Google Sheets")

    def _get_or_create_sheet(self, title: str):
        try:
            return self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            sheet = self._spreadsheet.add_worksheet(title=title, rows=5000, cols=30)
            log.info(f"Created worksheet: {title}")
            return sheet

    def sync_all_leads(self, listings: List[Listing]) -> None:
        self._connect()
        sheet = self._get_or_create_sheet("All Leads")
        self._write_listings(sheet, listings)
        log.info(f"Synced {len(listings)} listings to 'All Leads' tab")

    def sync_high_priority(self, listings: List[Listing]) -> None:
        self._connect()
        high = [l for l in listings if l.lead_priority == "high"]
        sheet = self._get_or_create_sheet("High Priority")
        self._write_listings(sheet, high)
        log.info(f"Synced {len(high)} high-priority listings")

    def write_daily_summary(self, stats: dict) -> None:
        self._connect()
        sheet = self._get_or_create_sheet("Daily Summary")

        row = [
            stats.get("date", str(date.today())),
            stats.get("total", 0),
            stats.get("high_priority", 0),
            stats.get("medium_priority", 0),
            stats.get("low_priority", 0),
            stats.get("rejected", 0),
        ]
        all_rows = sheet.get_all_values()
        if not all_rows:
            sheet.append_row(["Date", "Total", "High", "Medium", "Low", "Rejected"])
        sheet.append_row(row)
        log.info("Daily summary written to Google Sheets")

    def _write_listings(self, sheet, listings: List[Listing]) -> None:
        sheet.clear()
        rows = [HEADERS]
        for listing in listings:
            rows.append([
                listing.id,
                listing.listing_title or "",
                listing.equipment_type or "",
                listing.brand or "",
                listing.model or "",
                listing.year or "",
                listing.price or "",
                listing.location_full or "",
                listing.seller_name or "",
                listing.seller_type or "",
                listing.seller_phone or "",
                (listing.description or "")[:300],
                listing.photos_count or 0,
                listing.listing_url or "",
                str(listing.date_listed) if listing.date_listed else "",
                str(listing.date_found) if listing.date_found else "",
                str(listing.last_checked) if listing.last_checked else "",
                listing.status or "",
                listing.lead_priority or "",
                listing.lead_score or 0,
                listing.source or "",
                listing.search_keyword or "",
                listing.search_city or "",
                listing.notes or "",
            ])

        sheet.update(rows, "A1")
        self._apply_priority_colors(sheet, listings)

    def _apply_priority_colors(self, sheet, listings: List[Listing]) -> None:
        requests = []
        for i, listing in enumerate(listings):
            row_index = i + 1  # 0=header
            color = PRIORITY_COLORS.get(listing.lead_priority or "low", PRIORITY_COLORS["low"])
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet.id,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(HEADERS),
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": color}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            })
        if requests:
            self._spreadsheet.batch_update({"requests": requests})
