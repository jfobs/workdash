from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    UNREVIEWED = "UNREVIEWED"
    OVERRIDDEN = "OVERRIDDEN"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


@dataclass(slots=True)
class Serializable:
    def model_dump(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), default=str)


@dataclass(slots=True)
class Document(Serializable):
    document_id: str
    filename: str
    content_hash: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class Page(Serializable):
    page_id: str
    document_id: str
    page_number: int
    width: float
    height: float


@dataclass(slots=True)
class NumericFact(Serializable):
    fact_id: str
    document_id: str
    page_number: int
    statement_name: str
    table_name: str | None = None
    row_label: str | None = None
    column_label: str | None = None
    period_label: str | None = None
    raw_text: str = ""
    normalized_value: float | None = None
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    extraction_confidence: float = 0.0
    source_type: str = "unknown"


@dataclass(slots=True)
class TableCell(Serializable):
    cell_id: str
    fact_id: str | None
    document_id: str
    page_number: int
    row_index: int
    col_index: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(slots=True)
class CheckDefinition(Serializable):
    check_id: str
    category: str
    description: str
    tolerance: float = 1.0


@dataclass(slots=True)
class CheckResult(Serializable):
    result_id: str
    check_id: str
    status: CheckStatus
    formula: str
    narrative: str
    source_fact_ids: list[str] = field(default_factory=list)
    target_fact_ids: list[str] = field(default_factory=list)
    tolerance: float = 1.0
    calculated_difference: float | None = None
    explanation: str = ""

    @classmethod
    def model_validate_json(cls, payload: str) -> "CheckResult":
        data = json.loads(payload)
        data["status"] = CheckStatus(data["status"])
        return cls(**data)


@dataclass(slots=True)
class LinkEdge(Serializable):
    edge_id: str
    source_fact_id: str
    target_fact_id: str
    relation_type: str
    confidence: float


@dataclass(slots=True)
class OverrideDecision(Serializable):
    override_id: str
    result_id: str
    status: CheckStatus
    reason: str
    reviewer: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def model_validate_json(cls, payload: str) -> "OverrideDecision":
        data = json.loads(payload)
        data["status"] = CheckStatus(data["status"])
        return cls(**data)


@dataclass(slots=True)
class CalculatorSelection(Serializable):
    selection_id: str
    document_id: str
    page_number: int
    bbox: tuple[float, float, float, float]
    ordered_fact_ids: list[str]
    signs: list[int]
    result_value: float
    reviewer: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class VersionComparison(Serializable):
    comparison_id: str
    left_document_id: str
    right_document_id: str
    threshold: float
    changed_facts: list[dict[str, Any]] = field(default_factory=list)
