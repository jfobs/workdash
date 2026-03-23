from __future__ import annotations

from src.storage.models import CheckResult, CheckStatus


def tickmark_for_status(result: CheckResult) -> str:
    if result.status == CheckStatus.PASS:
        return "✅"
    if result.status == CheckStatus.FAIL:
        return "⚠️"
    if result.status == CheckStatus.OVERRIDDEN:
        return "📝"
    if result.status == CheckStatus.WARNING:
        return "⚠️"
    return "⬜"
