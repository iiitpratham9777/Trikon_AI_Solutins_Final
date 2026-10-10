"""In-memory, per-session conversation history. Resets when the backend restarts."""
import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from ..config import Settings
from ..errors import BadRequest, SessionNotFound

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass
class Session:
    id: str
    messages: list = field(default_factory=list)  # [{"role": "user"|"assistant", "content": str}]
    last_used: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ConversationService:
    def __init__(self, settings: Settings):
        self.s = settings
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, session_id: Optional[str]) -> Session:
        self._evict()
        if session_id is not None and not _ID_RE.match(session_id):
            raise BadRequest("Invalid session id.")
        sid = session_id or uuid.uuid4().hex
        session = self._sessions.get(sid)
        if session is None:
            session = Session(id=sid)
            self._sessions[sid] = session
        session.last_used = time.monotonic()
        return session

    def history(self, session: Session) -> list[dict]:
        return [dict(m) for m in session.messages]

    def append_turn(self, session: Session, user: str, assistant: str) -> None:
        session.messages.append({"role": "user", "content": user})
        session.messages.append({"role": "assistant", "content": assistant})
        keep = self.s.max_history_turns * 2
        if len(session.messages) > keep:
            session.messages = session.messages[-keep:]
        session.last_used = time.monotonic()

    def delete(self, session_id: str) -> None:
        if self._sessions.pop(session_id, None) is None:
            raise SessionNotFound("Session not found.")

    def count(self) -> int:
        return len(self._sessions)

    def _evict(self) -> None:
        now = time.monotonic()
        for sid in [k for k, v in self._sessions.items() if now - v.last_used > self.s.session_ttl_s]:
            self._sessions.pop(sid, None)
        while len(self._sessions) >= self.s.max_sessions:
            oldest = min(self._sessions.values(), key=lambda v: v.last_used)
            self._sessions.pop(oldest.id, None)
