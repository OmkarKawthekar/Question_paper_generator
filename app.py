"""
Streamlit frontend for Question Paper Generator.

Features:
- Upload a syllabus PDF and parse it into units
- Generate questions per unit using an LLM (OpenAI-compatible or Ollama LLaMA)
- Store and retrieve questions in SQLite
- Configure total marks, marks distribution, selected units, difficulty, and output format
- Generate a question paper as PDF or Word and download it

Environment/Setup:
- Set one of the following for LLM access before running:
  - OPENAI_API_KEY (and optionally OPENAI_BASE_URL for OpenAI-compatible endpoints)
  - or run Ollama locally and set OLLAMA_MODEL (e.g., "llama3.1"), OLLAMA_BASE_URL if not default

Run:
  pip install -r requirements.txt
  streamlit run app.py
"""

import io
import os
import random
from typing import Dict, List, Tuple

import streamlit as st

from database import (
    initialize_database,
    insert_questions,
    query_questions,
    get_all_units,
    reset_database,
    set_db_path,
)
from llm_utils import parse_syllabus_units, generate_questions_for_unit
from pdf_generator import (
    build_question_paper_pdf,
    build_question_paper_docx,
    generate_sample_syllabus_pdf_bytes,
)


# -----------------------------
# App Config
# -----------------------------
st.set_page_config(page_title="Questify - Question Paper Generator", page_icon="📝", layout="wide")

DEFAULT_DB_PATH = os.environ.get("QUESTIFY_DB_PATH", "questify.db")
set_db_path(DEFAULT_DB_PATH)
initialize_database()


# -----------------------------
# Helpers
# -----------------------------
def ensure_sample_syllabus() -> bytes:
    """Create a simple sample syllabus PDF on-the-fly for convenience."""
    return generate_sample_syllabus_pdf_bytes()


def sample_marks_distribution(total_marks: int, allowed_marks: List[int], pool: List[Dict]) -> Tuple[List[Dict], int]:
    """Greedy random sampler of questions until total marks are reached or exceeded.
    - allowed_marks: list like [2,4,6]
    - pool: list of question dicts containing 'marks'
    Returns (selected_questions, total_selected_marks)
    """
    # Group by marks
    marks_to_questions: Dict[int, List[Dict]] = {int(m): [] for m in allowed_marks}
    for q in pool:
        try:
            mval = int(q.get("marks", 0))
        except Exception:
            continue
        if mval in marks_to_questions:
            marks_to_questions[mval].append(q)

    selected: List[Dict] = []
    current = 0
    # Flatten selection order by shuffling within each marks bucket repeatedly
    order = []
    for m in allowed_marks:
        order.extend([m] * max(1, len(marks_to_questions.get(m, []))))
    random.shuffle(order)

    # Fallback simple loop if order is empty
    if not order:
        return [], 0

    idx = 0
    while current < total_marks and any(marks_to_questions[m] for m in allowed_marks):
        m = order[idx % len(order)]
        idx += 1
        if not marks_to_questions[m]:
            continue
        q = random.choice(marks_to_questions[m])
        marks_to_questions[m].remove(q)
        selected.append(q)
        current += m

    # If we exceeded, allow it; otherwise return whatever we could assemble
    return selected, current


def format_questions_to_sections(questions: List[Dict]) -> List[Tuple[str, List[Dict]]]:
    """Create simple sections by marks value, for nicer paper structure."""
    by_marks: Dict[int, List[Dict]] = {}
    for q in questions:
        by_marks.setdefault(int(q["marks"]), []).append(q)
    sections: List[Tuple[str, List[Dict]]] = []
    for marks in sorted(by_marks.keys()):
        title = f"Section: {marks} Mark Questions"
        sections.append((title, by_marks[marks]))
    return sections


# -----------------------------
# UI - Sidebar
# -----------------------------
with st.sidebar:
    st.header("Settings")

    st.caption("Database")
    if st.button("Reset Database", type="secondary"):
        reset_database()
        st.success("Database reset successfully.")

    st.caption("Sample Syllabus")
    if st.button("Download Sample Syllabus PDF"):
        pdf_bytes = ensure_sample_syllabus()
        st.download_button(
            label="Click to download sample_syllabus.pdf",
            data=pdf_bytes,
            file_name="sample_syllabus.pdf",
            mime="application/pdf",
        )


# -----------------------------
# UI - Main
# -----------------------------
st.title("📝 Questify - Question Paper Generator")
st.write("Upload a syllabus PDF, generate questions with LLM, and assemble a question paper.")

uploaded = st.file_uploader("Upload syllabus PDF", type=["pdf"]) 

col1, col2 = st.columns(2)
with col1:
    total_marks = st.number_input("Total Marks", min_value=10, max_value=200, value=70, step=5)
    allowed_marks = st.multiselect("Allowed Question Marks", options=[2, 4, 6], default=[4, 6])
    difficulty = st.selectbox("Difficulty", options=["All", "Easy", "Medium", "Hard"], index=0)
with col2:
    output_format = st.selectbox("Output Format", options=["PDF", "Word"], index=0)
    units_available = get_all_units()
    selected_units = st.multiselect("Select Units (optional)", options=units_available, default=units_available)

st.divider()


# -----------------------------
# Parse syllabus and generate questions
# -----------------------------
units: List[Dict] = []
if uploaded is not None:
    try:
        units = parse_syllabus_units(uploaded.read())
        if not units:
            st.warning("No units detected in the syllabus. Ensure the PDF contains headings like 'Unit 1', 'Unit 2', etc.")
        else:
            st.success(f"Detected {len(units)} units from the uploaded syllabus.")
            with st.expander("Preview Parsed Units"):
                for i, u in enumerate(units, start=1):
                    st.markdown(f"**Unit {i}:** {u.get('title','Untitled')}")
                    st.write(u.get("content", ""))
    except Exception as e:
        st.error(f"Failed to parse syllabus: {e}")

if uploaded is not None and units:
    if st.button("Generate Questions with LLM and Save to DB", type="primary"):
        with st.spinner("Generating questions for each unit using LLM..."):
            all_generated: List[Dict] = []
            for unit in units:
                # Generate exactly 2x4M and 2x6M per unit
                try:
                    generated = generate_questions_for_unit(unit)
                    all_generated.extend(generated)
                except Exception as e:
                    st.error(f"LLM generation failed for unit '{unit.get('title','')}'. Error: {e}")
            if all_generated:
                inserted = insert_questions(all_generated)
                st.success(f"Inserted {inserted} questions into the database.")


st.divider()


# -----------------------------
# Paper generation
# -----------------------------
if st.button("Generate Paper", type="primary"):
    with st.spinner("Assembling question paper from database..."):
        # Fetch question pool
        try:
            pool = query_questions(
                units=selected_units if selected_units else None,
                difficulties=None if difficulty == "All" else [difficulty],
                marks_filter=allowed_marks if allowed_marks else None,
            )
        except Exception as e:
            st.error(f"DB query failed: {e}")
            pool = []

        if not pool:
            st.warning("No questions available in DB matching your filters. Generate with LLM first or relax filters.")
        else:
            selected_questions, achieved_marks = sample_marks_distribution(
                total_marks=total_marks,
                allowed_marks=allowed_marks if allowed_marks else [2, 4, 6],
                pool=pool,
            )
            if not selected_questions:
                st.warning("Could not assemble any questions with the given constraints.")
            else:
                st.success(f"Assembled {len(selected_questions)} questions for ~{achieved_marks} marks.")
                sections = format_questions_to_sections(selected_questions)

                if output_format == "PDF":
                    pdf_bytes = build_question_paper_pdf(sections)
                    st.download_button(
                        label="Download Question Paper (PDF)",
                        data=pdf_bytes,
                        file_name="question_paper.pdf",
                        mime="application/pdf",
                    )
                else:
                    docx_bytes = build_question_paper_docx(sections)
                    st.download_button(
                        label="Download Question Paper (Word)",
                        data=docx_bytes,
                        file_name="question_paper.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )


