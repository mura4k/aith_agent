from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class Course(BaseModel):
    name: str
    credits: float
    teacher: Optional[str] = None
    description_url: Optional[str] = None
    is_required: bool = False

class StudentMatch(BaseModel):
    found: bool
    display_name: Optional[str] = None
    row_index: Optional[int] = None
    reason: Optional[str] = None
    candidates: List[str] = Field(default_factory=list)

class CreditsInfo(BaseModel):
    required_credits: float
    selected_credits: float
    max_credits: float
    remaining_credits: float
    ok: bool
    message: str

class WritePreview(BaseModel):
    sheet_url: str
    student_display_name: str
    selected_courses: List[str]
    action_summary: str

class ToolResult(BaseModel):
    ok: bool
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    