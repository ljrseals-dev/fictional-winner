"""Rekor v2 / C2SP tlog configuration and checkpoint primitives."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TlogConfig:
    base_url: str  # e.g. https://log2025-1.rekor.sigstore.dev
    origin: str  # checkpoint key name == log origin
    log_public_key_pem: str
    witness_keys: dict[str, bytes]  # name -> ed25519 pubkey (from WITNESS operators)
    witnesses_required: int = 2
    max_checkpoint_age_s: int = 3600


@dataclass(frozen=True)
class Checkpoint:
    size: int
    root: bytes  # 32-byte root hash
    origin: str = ""
    note: str = ""  # raw signed note for audit
