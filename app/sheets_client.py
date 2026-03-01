# app/sheets_client.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


SHEETS_ID_RE = re.compile(r"https?://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)")


def extract_sheet_id(url: str) -> Optional[str]:
    m = SHEETS_ID_RE.search(url or "")
    return m.group(1) if m else None


def _norm(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = s.replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(str(x).replace(",", ".").strip())
    except Exception:
        return None


def _col_to_a1(col: int) -> str:
    """1-based col index -> A1 column letters"""
    s = ""
    while col > 0:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


@dataclass(frozen=True)
class CourseCol:
    col_idx: int  # 1-based
    course_title: str
    course_id: Optional[int]
    teacher: Optional[str]
    credits: Optional[float]
    description_url: Optional[str]


class SheetsClient:
    """
    Google Sheets client adapted to your table layout.

    Worksheets:
      - "Таблица выбора"
      - "Расписание"

    Key rows in "Таблица выбора":
      Row 6: headers (A=ФИО, B=Табель, C..=courses)
      Row 5: teacher (C..)
      Row 3: course id (C..)
      Row 9: credits (C..)
      Row 12+: student rows (A,B + 0/1 in C..)

    "Расписание":
      Column C: course name
      Column S: google calendar link
    """

    WS_TABLE = "Таблица выбора"
    WS_SCHEDULE = "Расписание"

    ROW_COURSE_IDS = 3
    ROW_TEACHERS = 5
    ROW_HEADERS = 6
    ROW_CREDITS = 9
    ROW_FIRST_STUDENT = 12

    COL_FIO = 1
    COL_TABEL = 2
    COL_FIRST_COURSE = 3

    SCHED_COL_COURSE_NAME = 3   # C
    SCHED_COL_CALENDAR = 19     # S

    def __init__(self, sa_json_path: str):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(sa_json_path, scopes=scopes)
        self.svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    # ---------------- low-level helpers ----------------

    def _values_get(self, spreadsheet_id: str, a1_range: str) -> List[List[Any]]:
        resp = (
            self.svc.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=a1_range, valueRenderOption="UNFORMATTED_VALUE")
            .execute()
        )
        return resp.get("values", [])

    def _values_batch_get(self, spreadsheet_id: str, ranges: List[str]) -> Dict[str, List[List[Any]]]:
        resp = (
            self.svc.spreadsheets()
            .values()
            .batchGet(spreadsheetId=spreadsheet_id, ranges=ranges, valueRenderOption="UNFORMATTED_VALUE")
            .execute()
        )
        out: Dict[str, List[List[Any]]] = {}
        for vr in resp.get("valueRanges", []):
            out[vr["range"]] = vr.get("values", [])
        return out

    def _get_sheet_id_by_title(self, spreadsheet_id: str, title: str) -> int:
        meta = (
            self.svc.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets(properties(sheetId,title))")
            .execute()
        )
        for sh in meta.get("sheets", []):
            props = sh.get("properties", {})
            if props.get("title") == title:
                return int(props["sheetId"])
        raise ValueError(f"Worksheet not found: {title}")

    def _get_row_with_hyperlinks(
        self, spreadsheet_id: str, title: str, row_1based: int, col_start_1based: int, col_end_1based: int
    ) -> List[Tuple[Any, Optional[str]]]:
        """
        Returns list of (display_value, hyperlink_url) for a row segment.

        This works for:
        - hyperlinks set on the cell (CellData.hyperlink)
        - rich text links (textFormatRuns.link.uri)
        - HYPERLINK(...) formula (we try to parse it)
        """
        sheet_id = self._get_sheet_id_by_title(spreadsheet_id, title)

        # Convert to 0-based indexes for GridRange
        start_col = col_start_1based - 1
        end_col = col_end_1based  # end is exclusive in API (already 1-based -> ok)
        start_row = row_1based - 1
        end_row = row_1based

        resp = (
            self.svc.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                ranges=[
                    {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row,
                        "endRowIndex": end_row,
                        "startColumnIndex": start_col,
                        "endColumnIndex": end_col,
                    }
                ],
                includeGridData=True,
                fields=(
                    "sheets(data(rowData(values("
                    "formattedValue,userEnteredValue,hyperlink,textFormatRuns)))))"
                ),
            )
            .execute()
        )

        # Navigate response
        sheets = resp.get("sheets", [])
        if not sheets:
            return []

        data = sheets[0].get("data", [])
        if not data:
            return []

        row_data = data[0].get("rowData", [])
        if not row_data:
            return []

        values = row_data[0].get("values", [])
        out: List[Tuple[Any, Optional[str]]] = []

        for cell in values:
            display = cell.get("formattedValue")
            link = cell.get("hyperlink")

            # rich text link
            if not link:
                for run in cell.get("textFormatRuns", []) or []:
                    uri = (run.get("format", {}) or {}).get("link", {}) or {}
                    if uri.get("uri"):
                        link = uri["uri"]
                        break

            # HYPERLINK formula
            if not link:
                uev = cell.get("userEnteredValue", {})
                formula = uev.get("formulaValue")
                if formula and "HYPERLINK" in formula.upper():
                    # naive parse: =HYPERLINK("url","text")
                    m = re.search(r'HYPERLINK\(\s*"([^"]+)"', formula, flags=re.I)
                    if m:
                        link = m.group(1)

            out.append((display, link))

        return out

    # ---------------- public API ----------------

    def list_worksheets(self, sheet_url: str) -> List[str]:
        sid = extract_sheet_id(sheet_url)
        if not sid:
            raise ValueError("Invalid Google Sheets URL")
        meta = (
            self.svc.spreadsheets()
            .get(spreadsheetId=sid, fields="sheets(properties(title))")
            .execute()
        )
        return [s["properties"]["title"] for s in meta.get("sheets", [])]

    def read_courses(self, sheet_url: str) -> List[Dict[str, Any]]:
        spreadsheet_id = extract_sheet_id(sheet_url)
        if not spreadsheet_id:
            raise ValueError("Invalid Google Sheets URL")

        # We need to know how far columns go. We'll read header row 6 broadly.
        # Use a wide range; extra empty cells are fine.
        # If your sheet exceeds AZ, increase end column.
        header_a1 = f"'{self.WS_TABLE}'!A{self.ROW_HEADERS}:AZ{self.ROW_HEADERS}"
        header_vals = self._values_get(spreadsheet_id, header_a1)
        header_row = header_vals[0] if header_vals else []

        # Determine last non-empty header column
        last_col = 0
        for idx, v in enumerate(header_row, start=1):
            if v is not None and str(v).strip() != "":
                last_col = idx
        if last_col < self.COL_FIRST_COURSE:
            return []

        # Batch get teachers/ids/credits for C..last_col
        c_start = _col_to_a1(self.COL_FIRST_COURSE)
        c_end = _col_to_a1(last_col)

        ranges = [
            f"'{self.WS_TABLE}'!{c_start}{self.ROW_COURSE_IDS}:{c_end}{self.ROW_COURSE_IDS}",
            f"'{self.WS_TABLE}'!{c_start}{self.ROW_TEACHERS}:{c_end}{self.ROW_TEACHERS}",
            f"'{self.WS_TABLE}'!{c_start}{self.ROW_CREDITS}:{c_end}{self.ROW_CREDITS}",
        ]
        got = self._values_batch_get(spreadsheet_id, ranges)

        ids_row = (got[ranges[0]][0] if got.get(ranges[0]) else [])
        teachers_row = (got[ranges[1]][0] if got.get(ranges[1]) else [])
        credits_row = (got[ranges[2]][0] if got.get(ranges[2]) else [])

        # Hyperlinks from header row segment C..last_col
        header_with_links = self._get_row_with_hyperlinks(
            spreadsheet_id,
            self.WS_TABLE,
            self.ROW_HEADERS,
            self.COL_FIRST_COURSE,
            last_col,
        )

        courses: List[Dict[str, Any]] = []
        for offset, (title, link) in enumerate(header_with_links):
            col_idx = self.COL_FIRST_COURSE + offset

            if title is None or str(title).strip() == "":
                continue

            teacher = teachers_row[offset] if offset < len(teachers_row) else None
            teacher = str(teacher).strip() if teacher is not None and str(teacher).strip() != "" else None

            cid_val = ids_row[offset] if offset < len(ids_row) else None
            course_id: Optional[int] = None
            if cid_val is not None and str(cid_val).strip() != "":
                try:
                    course_id = int(str(cid_val).strip())
                except Exception:
                    course_id = None

            credits_val = credits_row[offset] if offset < len(credits_row) else None
            credits = _to_float(credits_val)

            courses.append(
                {
                    "name": str(title).strip(),
                    "credits": float(credits) if credits is not None else 0.0,
                    "teacher": teacher,
                    "description_url": link,
                    "course_id": course_id,
                    "col_idx": col_idx,
                }
            )

        return courses

    def get_course_by_name(self, sheet_url: str, course_name: str) -> Optional[Dict[str, Any]]:
        target = _norm(course_name)
        courses = self.read_courses(sheet_url)
        for c in courses:
            if _norm(c["name"]) == target:
                return c
        for c in courses:
            if target and target in _norm(c["name"]):
                return c
        return None

    def find_student(self, sheet_url: str, identity: str) -> Dict[str, Any]:
        spreadsheet_id = extract_sheet_id(sheet_url)
        if not spreadsheet_id:
            raise ValueError("Invalid Google Sheets URL")

        ident = _norm(identity)
        is_number = bool(re.fullmatch(r"\d{4,}", ident))

        # Read A,B columns from row 12 down (broad range; Google trims empties)
        rng = f"'{self.WS_TABLE}'!A{self.ROW_FIRST_STUDENT}:B"
        rows = self._values_get(spreadsheet_id, rng)

        matches: List[Tuple[int, str]] = []

        for i, row in enumerate(rows):
            r_index = self.ROW_FIRST_STUDENT + i  # 1-based row in sheet
            fio = row[0] if len(row) > 0 else None
            tab = row[1] if len(row) > 1 else None

            fio_s = str(fio).strip() if fio is not None else ""
            tab_s = str(tab).strip() if tab is not None else ""

            if is_number and tab_s and _norm(tab_s) == ident:
                return {"found": True, "display_name": fio_s, "row_index": r_index}

            if fio_s and ident and ident in _norm(fio_s):
                matches.append((r_index, fio_s))

        if len(matches) == 1:
            r, fio_s = matches[0]
            return {"found": True, "display_name": fio_s, "row_index": r}

        if len(matches) > 1:
            return {
                "found": False,
                "reason": "multiple_matches",
                "candidates": [fio for _, fio in matches[:8]],
            }

        return {"found": False, "reason": "not_found"}

    def get_student_selected_courses(self, sheet_url: str, student_row_index: int) -> List[str]:
        spreadsheet_id = extract_sheet_id(sheet_url)
        if not spreadsheet_id:
            raise ValueError("Invalid Google Sheets URL")

        # Need course columns extent
        courses = self.read_courses(sheet_url)
        if not courses:
            return []

        last_col = max(c["col_idx"] for c in courses)
        start_a1 = _col_to_a1(self.COL_FIRST_COURSE)
        end_a1 = _col_to_a1(last_col)
        rng = f"'{self.WS_TABLE}'!{start_a1}{student_row_index}:{end_a1}{student_row_index}"
        row_vals = self._values_get(spreadsheet_id, rng)
        vals = row_vals[0] if row_vals else []

        selected: List[str] = []
        # Map offsets to course titles
        # courses are sorted by col_idx (we assume monotonic)
        courses_sorted = sorted(courses, key=lambda x: x["col_idx"])

        for offset, c in enumerate(courses_sorted):
            v = vals[offset] if offset < len(vals) else None
            if str(v).strip().lower() in {"1", "1.0", "да", "yes", "true"}:
                selected.append(c["name"])

        return selected

    def write_selection(
        self,
        sheet_url: str,
        student_row_index: int,
        course_names: List[str],
        *,
        clear_others: bool = False,
    ) -> Dict[str, Any]:
        """
        Writes 1 for selected courses for a given student row in "Таблица выбора".
        If clear_others=True, sets 0 for all course columns, then sets 1 for selected.
        """
        spreadsheet_id = extract_sheet_id(sheet_url)
        if not spreadsheet_id:
            raise ValueError("Invalid Google Sheets URL")

        courses = self.read_courses(sheet_url)
        if not courses:
            return {"written": 0, "not_found_courses": course_names, "cleared": False}

        by_norm = {_norm(c["name"]): c for c in courses}

        targets: List[Dict[str, Any]] = []
        not_found: List[str] = []
        for name in course_names:
            key = _norm(name)
            c = by_norm.get(key)
            if not c:
                c = next((v for k, v in by_norm.items() if key and key in k), None)
            if c:
                targets.append(c)
            else:
                not_found.append(name)

        updates = []

        last_col = max(c["col_idx"] for c in courses)
        cleared = False

        if clear_others:
            # Set entire course range to 0
            start_a1 = _col_to_a1(self.COL_FIRST_COURSE)
            end_a1 = _col_to_a1(last_col)
            rng = f"'{self.WS_TABLE}'!{start_a1}{student_row_index}:{end_a1}{student_row_index}"
            zeros = [[0 for _ in range(self.COL_FIRST_COURSE, last_col + 1)]]
            updates.append({"range": rng, "values": zeros})
            cleared = True

        # Set selected to 1
        for c in targets:
            col_letter = _col_to_a1(int(c["col_idx"]))
            rng = f"'{self.WS_TABLE}'!{col_letter}{student_row_index}:{col_letter}{student_row_index}"
            updates.append({"range": rng, "values": [[1]]})

        if updates:
            body = {"valueInputOption": "USER_ENTERED", "data": updates}
            self.svc.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

        return {"written": len(targets), "not_found_courses": not_found, "cleared": cleared}

    def get_calendar_links_for_courses(self, sheet_url: str, course_names: List[str]) -> Dict[str, str]:
        spreadsheet_id = extract_sheet_id(sheet_url)
        if not spreadsheet_id:
            raise ValueError("Invalid Google Sheets URL")

        # Read columns C and S from schedule sheet
        # We'll fetch a wide range C:S and then pick [0] and [16] (since C is 1st in that range).
        rng = f"'{self.WS_SCHEDULE}'!C:S"
        rows = self._values_get(spreadsheet_id, rng)

        sched_map: Dict[str, str] = {}
        for row in rows:
            cname = row[0] if len(row) > 0 else None
            cal = row[16] if len(row) > 16 else None  # S is 17th column in C:S slice
            if not cname or not cal:
                continue
            cal_s = str(cal).strip()
            if "calendar.google.com" not in cal_s:
                continue
            sched_map[_norm(cname)] = cal_s

        wanted = { _norm(n): n for n in course_names if _norm(n) }
        result: Dict[str, str] = {}

        for nk, original in wanted.items():
            if nk in sched_map:
                result[original] = sched_map[nk]
                continue
            hit = next((cal for cn, cal in sched_map.items() if nk and nk in cn), None)
            if hit:
                result[original] = hit

        return result