from __future__ import annotations
from typing import Any, Dict, List, Optional
from app.sheets_client import SheetsClient, extract_sheet_id
from app.content_fetch import fetch_description
from app.domain import ToolResult

def tool_schemas() -> List[Dict[str, Any]]:
    """
    OpenAI-style tool schema.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "extract_sheet_link",
                "description": "Extract a Google Sheets URL from user text. Returns url if found.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "confirm_sheet_link",
                "description": "Store confirmed sheet URL in session state.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_url": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                    },
                    "required": ["sheet_url", "confirmed"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_student",
                "description": "Verify that a student identity exists in the sheet. Identity can be name or tab number.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_url": {"type": "string"},
                        "identity": {"type": "string"},
                    },
                    "required": ["sheet_url", "identity"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_courses",
                "description": "List available courses from the sheet with credits and teacher and description links (if any).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_url": {"type": "string"},
                    },
                    "required": ["sheet_url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_course_description",
                "description": "Fetch course description by URL (Google Docs or Notion public page).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compute_credits",
                "description": "Compute remaining credits based on required credits, selected credits, and max limit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "required_credits": {"type": "number"},
                        "selected_credits": {"type": "number"},
                        "max_credits": {"type": "number"},
                    },
                    "required": ["required_credits", "selected_credits", "max_credits"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "prepare_write_preview",
                "description": "Prepare a preview of what will be written to the sheet, but do not write yet.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_url": {"type": "string"},
                        "student_display_name": {"type": "string"},
                        "selected_courses": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["sheet_url", "student_display_name", "selected_courses"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_selection",
                "description": "Write selected courses to Google Sheet for the verified student. Requires explicit confirmation flag.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_url": {"type": "string"},
                        "student_row_index": {"type": "integer"},
                        "selected_courses": {"type": "array", "items": {"type": "string"}},
                        "user_confirmed": {"type": "boolean"},
                    },
                    "required": ["sheet_url", "student_row_index", "selected_courses", "user_confirmed"],
                },
            },
        },
    ]

def extract_sheet_link_from_text(text: str) -> Optional[str]:
    # simple: look for docs.google.com/spreadsheets
    import re
    m = re.search(r"https?://docs\.google\.com/spreadsheets/[^\s)]+", text)
    return m.group(0) if m else None

class ToolExecutor:
    def __init__(self, sheets: SheetsClient):
        self.sheets = sheets

    async def run(self, name: str, args: Dict[str, Any], session_state: Dict[str, Any]) -> ToolResult:
        try:
            if name == "extract_sheet_link":
                url = extract_sheet_link_from_text(args["text"])
                return ToolResult(ok=True, data={"sheet_url": url})

            if name == "confirm_sheet_link":
                # state update happens outside (in orchestrator), this tool just validates
                sheet_url = args["sheet_url"]
                if not extract_sheet_id(sheet_url):
                    return ToolResult(ok=False, error="Not a valid Google Sheets URL.")
                return ToolResult(ok=True, data={"confirmed": bool(args["confirmed"]), "sheet_url": sheet_url})

            if name == "verify_student":
                sheet_url = args["sheet_url"]
                identity = args["identity"]
                res = self.sheets.find_student(sheet_url, identity)
                return ToolResult(ok=True, data=res)

            if name == "list_courses":
                sheet_url = args["sheet_url"]
                courses = self.sheets.read_courses(sheet_url)
                return ToolResult(ok=True, data={"courses": courses})

            if name == "get_course_description":
                url = args["url"]
                text = await fetch_description(url)
                return ToolResult(ok=True, data={"text": text, "url": url})

            if name == "compute_credits":
                req = float(args["required_credits"])
                sel = float(args["selected_credits"])
                mx = float(args["max_credits"])
                remaining = mx - (req + sel)
                ok = remaining >= 0
                msg = "Ок по лимиту." if ok else "Превышен лимит зачётных единиц."
                return ToolResult(ok=True, data={
                    "required_credits": req,
                    "selected_credits": sel,
                    "max_credits": mx,
                    "remaining_credits": remaining,
                    "ok": ok,
                    "message": msg,
                })

            if name == "prepare_write_preview":
                sheet_url = args["sheet_url"]
                student = args["student_display_name"]
                selected = args["selected_courses"]
                summary = f"Будет записано для {student}: " + ", ".join(selected)
                return ToolResult(ok=True, data={
                    "sheet_url": sheet_url,
                    "student_display_name": student,
                    "selected_courses": selected,
                    "action_summary": summary,
                })

            if name == "write_selection":
                if not args.get("user_confirmed"):
                    return ToolResult(ok=False, error="User confirmation is required before writing.")
                sheet_url = args["sheet_url"]
                row = int(args["student_row_index"])
                selected = args["selected_courses"]
                res = self.sheets.write_selection(sheet_url, row, selected)
                return ToolResult(ok=True, data=res)

            return ToolResult(ok=False, error=f"Unknown tool: {name}")

        except Exception as e:
            return ToolResult(ok=False, error=str(e))