"""IMAP sync type definitions."""

from __future__ import annotations

from typing import Any, Protocol


class SyncResult:
    """Result of a folder/account sync operation."""

    def __init__(self) -> None:
        self.total = 0
        self.new = 0
        self.updated = 0
        self.errors: list[str] = []

    def __repr__(self) -> str:
        return (
            f"SyncResult(total={self.total}, new={self.new}, "
            f"updated={self.updated}, errors={len(self.errors)})"
        )


class MessageStore(Protocol):
    """Interface for message persistence during IMAP sync."""

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[int]:
        ...

    def store_message(self, data: dict[str, Any], force: bool = False) -> str:
        ...
