from __future__ import annotations

from uuid import uuid4

from src.storage.models import CheckStatus, OverrideDecision


def build_override(result_id: str, status: CheckStatus, reason: str, reviewer: str) -> OverrideDecision:
    return OverrideDecision(
        override_id=f"ovr_{uuid4().hex}",
        result_id=result_id,
        status=status,
        reason=reason,
        reviewer=reviewer,
    )
