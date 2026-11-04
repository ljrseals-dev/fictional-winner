"""
ARTIFACT gate + write + post-anchor ceremony (Part 4).

Pre-write (blocking, fail-closed): chain + dual-TSA quorum.
Post-write (non-blocking, fail-alarming): run_anchor → Rekor v2 → monitor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .tsa.policy import Anchor, TsaPolicy, quorum_verdict, revocation_status, Interval


@dataclass
class CeremonyResult:
    terminal_state: str  # COMPLETE | AWAITING_INCLUSION | COMPLETE_UNANCHORED | HALTED
    run_id: str
    ledger_tail_hash: str
    tsa_verdict: str
    tlog_entry_id: str | None = None
    alarms: list[str] | None = None
    detail: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_ceremony(
    *,
    run_id: str,
    ledger_tail_hash: str,
    ledger_length: int,
    genesis_entry_hash: str,
    gate_decision: dict,
    tsa_anchors: list[Anchor],
    tsa_policy: TsaPolicy,
    revoked_at: datetime | None = None,
    frozen: bool = False,
    tlog_client: Any = None,  # production: Rekor v2 client
) -> CeremonyResult:
    """
    Ordered steps 1–9 of the design.
    Step 3 (TSA) is blocking; step 8 (inclusion) is not.
    """
    # 1. pre
    if frozen:
        return CeremonyResult(
            "HALTED", run_id, ledger_tail_hash, "SKIPPED",
            detail="harness FROZEN; refuse new run",
        )

    # 3. dual-TSA quorum (blocking)
    verdict = quorum_verdict(tsa_anchors, tsa_policy)
    if verdict.status in ("DISAGREEMENT", "INSUFFICIENT"):
        return CeremonyResult(
            "HALTED", run_id, ledger_tail_hash, verdict.status,
            detail=verdict.detail or verdict.status,
        )
    if verdict.status == "TOLERATED":
        # log TSA_SKEW; production increments skew_warnings_in_window
        pass

    # 4. revocation boundary
    if revoked_at and verdict.earliest and verdict.latest:
        iv = Interval(verdict.earliest, verdict.latest)
        status = revocation_status(iv, revoked_at)
        if status in ("after_revocation", "indeterminate"):
            return CeremonyResult(
                "HALTED", run_id, ledger_tail_hash, verdict.status,
                detail=f"revocation_status={status}",
            )

    # 5. write is outside this function (orchestrator responsibility)
    # 6–7. assemble + submit run_anchor
    run_anchor = {
        "schema_version": "1.0.0",
        "kind": "artifact.run_anchor.v1",
        "run_id": run_id,
        "ledger_tail_hash": ledger_tail_hash,
        "ledger_length": ledger_length,
        "genesis_entry_hash": genesis_entry_hash,
        "terminal_state": "COMPLETE",
        "gate_decisions": [gate_decision],
        "completed_at": _now().isoformat(),
    }
    # production: sign with orchestrator Ed25519, submit hashedRekordRequestV002

    if tlog_client is None:
        # sandbox / dead-log path → COMPLETE_UNANCHORED + alarm
        return CeremonyResult(
            "COMPLETE_UNANCHORED",
            run_id,
            ledger_tail_hash,
            verdict.status,
            detail="tlog submission skipped or failed; alarm + freeze",
            alarms=["ANCHOR_SUBMISSION_FAILED"],
        )

    # 8–9. inclusion check (non-blocking)
    # production: verify against latest witnessed checkpoint
    return CeremonyResult(
        "AWAITING_INCLUSION",  # or COMPLETE once inclusion proven
        run_id,
        ledger_tail_hash,
        verdict.status,
        tlog_entry_id="stub",
    )
