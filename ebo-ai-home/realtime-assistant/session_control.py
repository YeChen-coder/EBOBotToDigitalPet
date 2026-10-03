"""Small file-based control channel for starting and closing voice sessions."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path


_ENGLISH_CLOSE = re.compile(
    r"(?:please\s+)?(?:can you\s+|could you\s+|would you\s+|i want (?:you )?to\s+)?"
    r"(?:end|close|stop)\s+(?:(?:this|the|our|current)\s+)?(?:conversation|session)"
    r"(?:\s+(?:now|please))?[.!?]?",
    re.IGNORECASE,
)
_CHINESE_CLOSE = re.compile(r"(?:请)?(?:结束|关闭)(?:这次|当前|这个)?(?:对话|会话)(?:吧|谢谢)?[。.!?]?")


class AssistantPreference:
    """Persist the user's AI switch independently of container lifecycle."""
    def __init__(self, path):
        self.path = Path(path)
        self.error = ''

    def load(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))['enabled']
            if not isinstance(value, bool):
                raise ValueError('invalid_enabled')
            return value
        except FileNotFoundError:
            return True
        except (OSError, ValueError, KeyError, TypeError):
            self.error = 'assistant_preference_unreadable'
            return False

    def save(self, enabled):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('w', encoding='utf-8') as handle:
                json.dump({'enabled': enabled}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.error = ''
        finally:
            temporary.unlink(missing_ok=True)


def explicit_close_phrase(text: str) -> bool:
    """Match a short, direct spoken request to end the current session."""
    text = text.strip()
    return bool(
        len(text) <= 120
        and (
            _ENGLISH_CLOSE.fullmatch(text)
            or _CHINESE_CLOSE.fullmatch(text)
            or text.casefold() in {"stop listening", "stop listening.", "别再听了", "别再听了。"}
        )
    )
