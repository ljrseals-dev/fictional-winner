"""C2SP tlog-tiles fetch + node derivation (Rekor v2 tile layout)."""
from __future__ import annotations

from hashlib import sha256
from typing import Any


class TlogError(Exception):
    def __init__(self, code: str, msg: str = ""):
        self.code = code
        super().__init__(f"{code}: {msg}" if msg else code)


class TileStore:
    """Fetches and caches C2SP tlog-tiles; derives node hashes on demand."""

    def __init__(self, base_url: str, session: Any = None, cache: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.cache: dict[tuple[int, int], list[bytes]] = cache or {}

    def _tile(self, level: int, number: int) -> list[bytes]:
        key = (level, number)
        if key not in self.cache:
            if self.session is None:
                raise TlogError("NO_SESSION", "live fetch requires an HTTP session")
            url = f"{self.base_url}/tile/{level}/{number}"
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            raw = r.content
            if len(raw) % 32:
                raise TlogError("TILE_MALFORMED", f"tile {level}/{number}")
            self.cache[key] = [raw[i : i + 32] for i in range(0, len(raw), 32)]
        return self.cache[key]

    def node(self, k: int, idx: int) -> bytes:
        """
        Hash of node at tree-level k, index idx.
        Tile level = k // 8; tile stores level-8L hashes.
        """
        L, r = divmod(k, 8)
        base = idx >> r
        hashes = self._tile(L, base >> 8)
        sib = base & 0xFF
        acc, pos = hashes[sib], sib
        for _ in range(1, r + 1):
            sib2 = pos ^ 1
            left, right = (acc, hashes[sib2]) if pos % 2 == 0 else (hashes[sib2], acc)
            acc = sha256(b"\x01" + left + right).digest()
            pos >>= 1
        return acc
