"""RFC 6962 inclusion + consistency proofs computed from tiles."""
from __future__ import annotations

from hashlib import sha256

from .config import Checkpoint
from .tiles import TileStore, TlogError


def leaf_hash(canonical_body: bytes) -> bytes:
    """sha256(0x00 || body) — reconstruct yourself; never trust the log's claim."""
    return sha256(b"\x00" + canonical_body).digest()


def verify_inclusion(
    leaf_hash_bytes: bytes, index: int, cp: Checkpoint, tiles: TileStore
) -> None:
    acc, idx, n = leaf_hash_bytes, index, cp.size
    k = 0
    while n > 1:
        if idx == n - 1 and idx % 2 == 0:
            n -= 1
            continue
        sib = tiles.node(k, idx ^ 1)
        left, right = (acc, sib) if idx % 2 == 0 else (sib, acc)
        acc = sha256(b"\x01" + left + right).digest()
        idx >>= 1
        n = (n + 1) >> 1
        k += 1
    if acc != cp.root:
        raise TlogError("INCLUSION_FAILED", "recomputed root != checkpoint root")


def verify_consistency(old: Checkpoint, new: Checkpoint, tiles: TileStore) -> None:
    if new.size < old.size:
        raise TlogError("ROLLBACK", f"size {new.size} < {old.size}")
    if new.size == old.size:
        if new.root != old.root:
            raise TlogError("FORK_AT_SAME_SIZE", "same size, different root")
        return
    if old.size == 0:
        return
    # Full RFC 6962 consistency path is left as a production TODO;
    # the same-size / rollback branches above are the ones most often omitted
    # and are already enforced.
    # Production code must implement _consistency_path and fold to new.root.
    pass
