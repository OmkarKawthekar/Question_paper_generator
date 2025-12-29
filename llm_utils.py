"""
LLM utilities:
- parse_syllabus_units(pdf_bytes): extract text and split into units using headings
- generate_questions_for_unit(unit): call LLM to produce exactly 2x4M and 2x6M questions

Backends supported:
- OpenAI-compatible via environment OPENAI_API_KEY and optional OPENAI_BASE_URL
- Ollama via local server; set OLLAMA_MODEL (e.g., "llama3.1") and optional OLLAMA_BASE_URL

Returned question format per question:
  { "unit": str, "question": str, "marks": int, "difficulty": "Easy"|"Medium"|"Hard" }
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List

import requests
from pypdf import PdfReader
import io as _io


SYSTEM_PROMPT = (
    "You are an expert teacher. Generate concise, clear exam questions strictly based on the provided unit content. "
    "Return ONLY valid JSON matching the required schema with no extra text."
)


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    reader = PdfReader(_io.BytesIO(pdf_bytes))
    text_parts: List[str] = []
    for page in reader.pages:
        try:
            text_parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(text_parts)


def bytes_to_io(data: bytes):
    # Late import to avoid global dependency
    import io as _io

    return _io.BytesIO(data)


def parse_syllabus_units(pdf_bytes: bytes) -> List[Dict]:
    """Parse syllabus PDF into units.
    Heuristic: split on headings like 'Unit 1', 'UNIT - 2', 'Module 3', etc.
    Fallback: single unit with full text.
    Returns list of {title, content}.
    """
    raw = _extract_text_from_pdf(pdf_bytes)
    if not raw.strip():
        return []

    # Normalize
    text = re.sub(r"\r", "\n", raw)
    text = re.sub(r"\n{2,}", "\n\n", text)

    # Split on unit/module headers
    pattern = re.compile(r"(?i)(?:^|\n)(unit|module)\s*[-:]?\s*(\d+)\b[\s\S]*?(?=(?:\n(?:unit|module)\s*[-:]?\s*\d+\b)|\Z)")

    matches = list(pattern.finditer(text))
    units: List[Dict] = []
    if matches:
        for m in matches:
            header_word = m.group(1)
            unit_num = m.group(2)
            block = m.group(0)
            # Remove the heading line for content readability
            content = re.sub(r"(?i)^(unit|module)\s*[-:]?\s*\d+\b\s*", "", block.strip())
            units.append({
                "title": f"{header_word.title()} {unit_num}",
                "content": content.strip(),
            })
    else:
        # Fallback: try splitting by major headings
        chunks = re.split(r"\n\n+", text)
        if len(chunks) > 1:
            for i, c in enumerate(chunks, start=1):
                units.append({"title": f"Unit {i}", "content": c.strip()})
        else:
            units.append({"title": "Unit 1", "content": text.strip()})

    # Trim overly short/empty units
    units = [u for u in units if len(u.get("content", "").strip()) >= 20]
    return units


def _call_openai_chat(messages: List[Dict]) -> str:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    base = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key, base_url=base) if base else OpenAI(api_key=api_key)
    resp = client.chat.completions.create(model=model, messages=messages, temperature=0.3)
    return resp.choices[0].message.content or ""


def _call_ollama(messages: List[Dict]) -> str:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    url = f"{base.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "options": {"temperature": 0.3},
        "stream": False,
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    # Ollama returns {'message': {'content': '...'}} or aggregated content
    if isinstance(data, dict):
        msg = data.get("message") or {}
        content = msg.get("content") or data.get("content") or ""
        return content
    return ""


def _choose_backend() -> str:
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "ollama"  # default


def generate_questions_for_unit(unit: Dict) -> List[Dict]:
    """Generate exactly 2x4M and 2x6M questions for a unit via LLM.
    Returns a list of 4 question dicts.
    """
    unit_title = unit.get("title", "Unit")
    unit_content = unit.get("content", "")
    user_prompt = f"""
You are given a course unit titled "{unit_title}" with the following content. Generate exam questions strictly based on this content.

Requirements:
- Exactly 4 questions total
- Exactly two questions of 4 marks and two questions of 6 marks
- Balance concepts across the unit; avoid duplication
- Difficulty: mix of Easy, Medium, Hard but ensure overall balance
- Return ONLY JSON matching this schema:
{{
  "questions": [
    {{"question": str, "marks": 4|6, "difficulty": "Easy"|"Medium"|"Hard"}},
    ... exactly 4 entries ...
  ]
}}

UNIT CONTENT:
"""
    # Limit content size for prompt safety
    unit_excerpt = unit_content.strip()
    if len(unit_excerpt) > 4000:
        unit_excerpt = unit_excerpt[:4000] + "..."
    user_prompt += unit_excerpt

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    backend = _choose_backend()
    if backend == "openai":
        content = _call_openai_chat(messages)
    else:
        content = _call_ollama(messages)

    # Parse JSON
    json_str = _extract_json_block(content)
    data = json.loads(json_str)
    out: List[Dict] = []
    for item in data.get("questions", [])[:4]:
        q = str(item.get("question", "")).strip()
        if not q:
            continue
        marks = int(item.get("marks", 4))
        if marks not in (4, 6):
            # Coerce to allowed
            marks = 4 if marks < 5 else 6
        difficulty = str(item.get("difficulty", "Medium"))
        if difficulty not in ("Easy", "Medium", "Hard"):
            difficulty = "Medium"
        out.append({
            "unit": unit_title,
            "question": q,
            "marks": marks,
            "difficulty": difficulty,
        })

    # Ensure exactly two 4M and two 6M by adjustments if needed
    four = [q for q in out if q["marks"] == 4]
    six = [q for q in out if q["marks"] == 6]
    # Simple balancing: trim/expend by converting extra items
    while len(four) > 2 and len(six) < 2:
        x = four.pop()
        x["marks"] = 6
        six.append(x)
    while len(six) > 2 and len(four) < 2:
        x = six.pop()
        x["marks"] = 4
        four.append(x)
    balanced = (four + six)[:4]
    # If still short, duplicate with safe tweaks
    while len(balanced) < 4 and (four or six):
        src = four if len(four) < 2 else six
        if not src:
            src = six if len(six) > 0 else four
        if not src:
            break
        dup = dict(src[0])
        dup["question"] = dup["question"] + " (variation)"
        balanced.append(dup)
    return balanced[:4]


def _extract_json_block(text: str) -> str:
    """Extract JSON block from LLM output. If not found, attempt to coerce."""
    text = text.strip()
    # If wrapped in code fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    # Find first { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    # Fallback minimal JSON
    return json.dumps({"questions": []})


