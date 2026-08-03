from __future__ import annotations

import hashlib
from typing import BinaryIO


class DuplicateDetector:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def fingerprint(self, stream: BinaryIO) -> str:
        current_position = None
        try:
            current_position = stream.tell()
        except (AttributeError, OSError):
            pass

        hasher = hashlib.sha256()
        try:
            stream.seek(0)
        except (AttributeError, OSError):
            pass

        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8", errors="ignore")
            hasher.update(chunk)

        try:
            stream.seek(current_position or 0)
        except (AttributeError, OSError):
            pass

        return hasher.hexdigest()

    def register(self, stream: BinaryIO) -> bool:
        fingerprint = self.fingerprint(stream)
        is_duplicate = fingerprint in self._seen
        if not is_duplicate:
            self._seen.add(fingerprint)
        return is_duplicate

    def clear(self) -> None:
        self._seen.clear()


duplicate_detector = DuplicateDetector()
