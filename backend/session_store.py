"""SQLite-backed chat session store for the conversational generate/refine flow.

Mirrors the session-management concept from the ocdp-data-integration-ai-automation
repo (chat_session + chat_message tables) but scoped down for this single-user,
local tool: no auth/user_email column, one SQLite file on disk so sessions and
their chat history survive server restarts (the old in-memory SESSIONS dict did not).
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "modeliq_sessions.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_session (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                industry TEXT NOT NULL,
                standard TEXT NOT NULL,
                dialect TEXT NOT NULL,
                requirement TEXT NOT NULL,
                llm_context TEXT,
                model_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_session(session_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_message_session ON chat_message(session_id, id)")

        # Governance approval state on each model. Added via migration so existing
        # DBs pick it up without being recreated.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chat_session)")}
        if "status" not in cols:
            conn.execute("ALTER TABLE chat_session ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'")

        # Governance audit trail: an append-only log of who did what to a model.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                action TEXT NOT NULL,
                detail TEXT,
                actor TEXT NOT NULL DEFAULT 'You',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_event_session ON audit_event(session_id, id)")

        # Human-in-the-loop sign-off on design-review findings: one row per
        # resolved finding, so the decision + reason survive reloads and feed
        # the governance audit trail / exported governance document.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_resolution (
                session_id TEXT NOT NULL,
                finding_id TEXT NOT NULL,
                finding_title TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL DEFAULT 'You',
                created_at TEXT NOT NULL,
                PRIMARY KEY (session_id, finding_id),
                FOREIGN KEY (session_id) REFERENCES chat_session(session_id) ON DELETE CASCADE
            )
            """
        )

        # User-added reference standards (Catalog tab). Built-in standards live in
        # standards_library.py; these are merged on top of them at read time.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_standard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                industry TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )


def _derive_title(requirement: str) -> str:
    clean = " ".join(requirement.split())
    return clean[:48] + "\u2026" if len(clean) > 48 else clean


def create_session(industry: str, standard: str, dialect: str, requirement: str, llm_context: list) -> str:
    session_id = uuid.uuid4().hex
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_session
                (session_id, title, industry, standard, dialect, requirement, llm_context, model_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (session_id, _derive_title(requirement), industry, standard, dialect, requirement,
             json.dumps(llm_context), now, now),
        )
    return session_id


def list_sessions() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT session_id, title, created_at, updated_at FROM chat_session ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_session(session_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM chat_session WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        messages = conn.execute(
            "SELECT role, text, created_at FROM chat_message WHERE session_id = ? ORDER BY id ASC", (session_id,)
        ).fetchall()
    session = dict(row)
    session["llm_context"] = json.loads(session["llm_context"]) if session["llm_context"] else []
    session["model"] = json.loads(session["model_json"]) if session["model_json"] else None
    session["chat"] = [dict(m) for m in messages]
    return session


def update_session(session_id: str, *, llm_context: list, dialect: str, model_json: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE chat_session SET llm_context = ?, dialect = ?, model_json = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(llm_context), dialect, json.dumps(model_json), _now(), session_id),
        )


def rename_session(session_id: str, title: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE chat_session SET title = ?, updated_at = ? WHERE session_id = ?", (title.strip(), _now(), session_id)
        )
    return cur.rowcount > 0


def delete_session(session_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM chat_session WHERE session_id = ?", (session_id,))
    return cur.rowcount > 0


def add_message(session_id: str, role: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO chat_message (session_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, text, _now()),
        )


# --- Governance: model list, approval status, audit trail --------------------

def list_models() -> list[dict]:
    """Sessions that actually produced a model, with their governance status —
    the source list for the Governance tab."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT session_id, title, industry, standard, dialect, status,
                   model_json, created_at, updated_at
            FROM chat_session
            WHERE model_json IS NOT NULL
            ORDER BY updated_at DESC
            """
        ).fetchall()
    models = []
    for row in rows:
        item = dict(row)
        item["model"] = json.loads(item.pop("model_json")) if item.get("model_json") else None
        models.append(item)
    return models


def set_status(session_id: str, status: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE chat_session SET status = ?, updated_at = ? WHERE session_id = ?",
            (status, _now(), session_id),
        )
    return cur.rowcount > 0


def add_audit(session_id: str | None, action: str, detail: str = "", actor: str = "You") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_event (session_id, action, detail, actor, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, action, detail, actor, _now()),
        )


def list_audit(session_id: str | None = None, limit: int = 200) -> list[dict]:
    with _connect() as conn:
        if session_id:
            rows = conn.execute(
                """
                SELECT a.id, a.session_id, a.action, a.detail, a.actor, a.created_at, s.title
                FROM audit_event a LEFT JOIN chat_session s ON a.session_id = s.session_id
                WHERE a.session_id = ? ORDER BY a.id DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT a.id, a.session_id, a.action, a.detail, a.actor, a.created_at, s.title
                FROM audit_event a LEFT JOIN chat_session s ON a.session_id = s.session_id
                ORDER BY a.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


# --- Human-in-the-loop review resolutions ------------------------------------

def set_review_resolution(session_id: str, finding_id: str, finding_title: str,
                          decision: str, reason: str = "", actor: str = "You") -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO review_resolution
                (session_id, finding_id, finding_title, decision, reason, actor, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, finding_id) DO UPDATE SET
                finding_title = excluded.finding_title,
                decision = excluded.decision,
                reason = excluded.reason,
                actor = excluded.actor,
                created_at = excluded.created_at
            """,
            (session_id, finding_id, finding_title, decision, reason, actor, _now()),
        )


def list_review_resolutions(session_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT finding_id, finding_title, decision, reason, actor, created_at "
            "FROM review_resolution WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


# --- Catalog: user-added reference standards ---------------------------------
def add_standard(industry: str, name: str, description: str = "") -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO custom_standard (industry, name, description, created_at) VALUES (?, ?, ?, ?)",
            (industry, name, description, _now()),
        )
    return cur.lastrowid


def list_custom_standards(industry: str | None = None) -> list[dict]:
    with _connect() as conn:
        if industry:
            rows = conn.execute(
                "SELECT id, industry, name, description, created_at FROM custom_standard WHERE industry = ? ORDER BY id",
                (industry,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, industry, name, description, created_at FROM custom_standard ORDER BY industry, id"
            ).fetchall()
    return [dict(row) for row in rows]


def delete_standard(standard_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM custom_standard WHERE id = ?", (standard_id,))
    return cur.rowcount > 0
