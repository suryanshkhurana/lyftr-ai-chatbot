"""Session and message persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.connection import Database


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class StoredSession:
    exists: bool
    system_prompt: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)  # [{"role","content"}], oldest first


class ChatRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def load_session(self, session_id: str) -> StoredSession:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return StoredSession(exists=False)
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return StoredSession(
            exists=True,
            system_prompt=row["system_prompt"],
            history=[{"role": r["role"], "content": r["content"]} for r in rows],
        )

    def save_turn(
        self,
        session_id: str,
        system_prompt_override: str | None,
        user_content: str,
        assistant_content: str,
        assistant_metadata: dict[str, Any],
    ) -> None:
        """Persist the session row (+ optional prompt override) and both messages in one transaction."""
        now = utc_now_iso()
        with self.db.connect() as conn:
            with conn:  # BEGIN ... COMMIT, ROLLBACK on error
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (session_id, system_prompt, created_at) VALUES (?, ?, ?)",
                    (session_id, system_prompt_override, now),
                )
                if system_prompt_override is not None:
                    conn.execute(
                        "UPDATE sessions SET system_prompt = ? WHERE session_id = ?",
                        (system_prompt_override, session_id),
                    )
                conn.executemany(
                    "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
                    [
                        (session_id, "user", user_content, None, now),
                        (session_id, "assistant", assistant_content, json.dumps(assistant_metadata), now),
                    ],
                )

    def get_messages(self, session_id: str) -> list[dict[str, Any]] | None:
        """Public history (no system prompt). None when the session is unknown."""
        with self.db.connect() as conn:
            if conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone() is None:
                return None
            rows = conn.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item: dict[str, Any] = {"role": r["role"], "content": r["content"]}
            if r["role"] == "assistant" and r["metadata"]:
                item["metadata"] = json.loads(r["metadata"])
            out.append(item)
        return out
