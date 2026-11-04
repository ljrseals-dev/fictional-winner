"""TSA registry, interval algebra, dual-TSA quorum, revocation status."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class TsaEntry:
    tsa_id: str
    role: str  # "primary" | "witness"
    url: str
    operator_id: str  # REQUIRED, distinct from tsa_id; two tsa_ids with one operator_id are ONE TSA (enforced in Phase 5)
    policy_oid: str
    root_pem_path: str
    root_fingerprint_sha256: str
    max_accuracy_s: float
    distrust_after: str | None  # REQUIRED, ISO-8601 or an explicit None meaning "no known distrust"
    not_after: str | None = None
    allow_ess_v1: bool = False
    jurisdiction: str = ""
    time_source: str = ""


@dataclass(frozen=True)
class TsaPolicy:
    registry: dict[str, TsaEntry]
    quorum: int = 2
    max_skew_s: float = 2.0
    require_distinct_operators: bool = True
    require_distinct_jurisdictions: bool = False
    max_accuracy_s: float = 1.0


@dataclass(frozen=True)
class Interval:
    lo: datetime
    hi: datetime

    def intersects(self, other: "Interval") -> bool:
        return self.lo <= other.hi and other.lo <= self.hi


@dataclass(frozen=True)
class Anchor:
    tsa_id: str
    gen_time: datetime
    accuracy_s: float
    token_bytes: bytes = b""

    @property
    def interval(self) -> Interval:
        delta = timedelta(seconds=self.accuracy_s)
        return Interval(self.gen_time - delta, self.gen_time + delta)


@dataclass(frozen=True)
class Verdict:
    status: str  # CONFIRMED | TOLERATED | DISAGREEMENT | INSUFFICIENT
    earliest: datetime | None = None
    latest: datetime | None = None
    gap: timedelta | None = None
    anchors: list[Anchor] = field(default_factory=list)
    detail: str = ""


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _accept(anchor: Anchor, policy: TsaPolicy) -> bool:
    entry = policy.registry.get(anchor.tsa_id)
    if entry is None:
        return False
    if anchor.accuracy_s > min(entry.max_accuracy_s, policy.max_accuracy_s):
        return False
    distrust = _parse_iso(entry.distrust_after)
    if distrust and anchor.gen_time >= distrust:
        return False
    not_after = _parse_iso(entry.not_after)
    if not_after and anchor.gen_time > not_after:
        return False
    return True


def quorum_verdict(anchors: list[Anchor], policy: TsaPolicy) -> Verdict:
    eligible = [a for a in anchors if _accept(a, policy)]
    if len(eligible) < policy.quorum:
        return Verdict(
            "INSUFFICIENT",
            detail=f"{len(eligible)} usable of {policy.quorum} required",
        )

    if policy.require_distinct_operators:
        # simplistic: distinct tsa_id is treated as distinct operator
        if len({a.tsa_id for a in eligible}) < policy.quorum:
            return Verdict("INSUFFICIENT", detail="operators not distinct")

    lo = max(a.interval.lo for a in eligible)
    hi = min(a.interval.hi for a in eligible)

    if lo <= hi:
        return Verdict("CONFIRMED", earliest=lo, latest=hi, anchors=eligible)

    gap = lo - hi
    if gap <= timedelta(seconds=policy.max_skew_s):
        return Verdict(
            "TOLERATED",
            earliest=hi,
            latest=lo,
            gap=gap,
            anchors=eligible,
            detail="TSA_SKEW within tolerance",
        )
    return Verdict(
        "DISAGREEMENT",
        earliest=hi,
        latest=lo,
        gap=gap,
        anchors=eligible,
        detail="gap exceeds max_skew_s; halt",
    )


def revocation_status(sig_interval: Interval, revoked_at: datetime) -> str:
    """Three-valued: before_revocation | after_revocation | indeterminate."""
    if sig_interval.hi < revoked_at:
        return "before_revocation"
    if sig_interval.lo > revoked_at:
        return "after_revocation"
    return "indeterminate"
