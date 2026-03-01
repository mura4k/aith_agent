from __future__ import annotations
import re
from typing import Optional
import httpx

GOOGLE_DOC_RE = re.compile(r"https?://docs\.google\.com/document/d/([a-zA-Z0-9-_]+)")
NOTION_RE = re.compile(r"https?://(www\.)?notion\.so/")

def _strip_html(html: str) -> str:
    # super simple
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

async def fetch_public_text(url: str, max_chars: int = 3500) -> str:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        txt = _strip_html(r.text)
        return txt[:max_chars]

async def fetch_description(url: str) -> str:
    # try public fetch for both docs & notion
    # TODO: add Drive API / Notion API for private pages.
    return await fetch_public_text(url)