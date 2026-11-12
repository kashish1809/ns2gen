"""Undo / redo over opaque snapshots (JSON strings)."""
from __future__ import annotations

from typing import List, Optional


class History:
    def __init__(self, limit: int = 200):
        self.limit = limit
        self._undo: List[str] = []
        self._redo: List[str] = []

    def push(self, snap: str) -> None:
        """Record the state *before* a change."""
        if self._undo and self._undo[-1] == snap:
            return
        self._undo.append(snap)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self, current: str) -> Optional[str]:
        if not self._undo:
            return None
        self._redo.append(current)
        return self._undo.pop()

    def redo(self, current: str) -> Optional[str]:
        if not self._redo:
            return None
        self._undo.append(current)
        return self._redo.pop()

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
