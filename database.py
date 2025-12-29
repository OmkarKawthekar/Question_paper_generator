"""
SQLite database utilities for Questify.

Schema: questions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit TEXT NOT NULL,
  question TEXT NOT NULL,
  marks INTEGER NOT NULL,
  difficulty TEXT NOT NULL CHECK(difficulty IN ('Easy','Medium','Hard'))
)

Exposed functions:
- set_db_path(path)
- initialize_database()
- reset_database()
- insert_questions(records)
- query_questions(units=None, difficulties=None, marks_filter=None)
- get_all_units()
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, List, Optional, Dict


_DB_PATH: str = "questify.db"


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit TEXT NOT NULL,
                question TEXT NOT NULL,
                marks INTEGER NOT NULL,
                difficulty TEXT NOT NULL CHECK (difficulty IN ('Easy','Medium','Hard'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def reset_database() -> None:
    conn = _connect()
    try:
        conn.execute("DROP TABLE IF EXISTS questions")
        conn.commit()
        initialize_database()
    finally:
        conn.close()


def insert_questions(records: Iterable[Dict]) -> int:
    """Insert a list of question dicts.
    Each record requires: unit:str, question:str, marks:int, difficulty:str('Easy'|'Medium'|'Hard')
    Returns number of inserted rows.
    """
    rows = [
        (
            str(r.get("unit", "Unknown")),
            str(r.get("question", "")),
            int(r.get("marks", 0)),
            str(r.get("difficulty", "Medium")),
        )
        for r in records
        if r.get("question")
    ]
    if not rows:
        return 0
    conn = _connect()
    try:
        conn.executemany(
            "INSERT INTO questions(unit, question, marks, difficulty) VALUES(?,?,?,?)",
            rows,
        )
        conn.commit()
        return conn.total_changes
    finally:
        conn.close()


def query_questions(
    units: Optional[List[str]] = None,
    difficulties: Optional[List[str]] = None,
    marks_filter: Optional[List[int]] = None,
) -> List[Dict]:
    """Query questions with optional filters."""
    sql = "SELECT id, unit, question, marks, difficulty FROM questions WHERE 1=1"
    params: List = []

    if units:
        placeholders = ",".join(["?"] * len(units))
        sql += f" AND unit IN ({placeholders})"
        params.extend(units)

    if difficulties:
        placeholders = ",".join(["?"] * len(difficulties))
        sql += f" AND difficulty IN ({placeholders})"
        params.extend(difficulties)

    if marks_filter:
        placeholders = ",".join(["?"] * len(marks_filter))
        sql += f" AND marks IN ({placeholders})"
        params.extend([int(m) for m in marks_filter])

    sql += " ORDER BY unit ASC, marks ASC"

    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_units() -> List[str]:
    conn = _connect()
    try:
        cur = conn.execute("SELECT DISTINCT unit FROM questions ORDER BY unit ASC")
        rows = [r[0] for r in cur.fetchall()]
        return rows
    finally:
        conn.close()


