from __future__ import annotations

import inspect
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar, Literal, Mapping

Severity = Literal["low", "medium", "high", "critical"]
EntityPayload = Mapping[str, Any]
EvidencePayload = Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class DriftRuleContext:
    document_id: uuid.UUID | None
    entities: tuple[EntityPayload, ...] = field(default_factory=tuple)
    evidence: EvidencePayload = field(default_factory=dict)

    def __post_init__(self) -> None:
        frozen_entities = tuple(
            MappingProxyType(dict(entity)) for entity in self.entities
        )
        frozen_evidence = MappingProxyType(dict(self.evidence))
        object.__setattr__(self, "entities", frozen_entities)
        object.__setattr__(self, "evidence", frozen_evidence)


@dataclass(slots=True)
class DriftAlertDraft:
    rule_type: str
    severity: Severity
    message: str
    document_id: uuid.UUID | None = None
    evidence: dict = field(default_factory=dict)


class BaseDriftRule(ABC):
    _VALID_SEVERITIES: ClassVar[set[str]] = {"low", "medium", "high", "critical"}
    rule_type: ClassVar[str]
    severity: ClassVar[Severity]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return

        rule_type = getattr(cls, "rule_type", None)
        severity = getattr(cls, "severity", None)

        if not isinstance(rule_type, str) or not rule_type.strip():
            raise TypeError(
                f"{cls.__name__} must define non-empty class attr: rule_type"
            )

        if severity not in cls._VALID_SEVERITIES:
            allowed = ", ".join(sorted(cls._VALID_SEVERITIES))
            raise TypeError(
                f"{cls.__name__} must define class attr severity in {{{allowed}}}"
            )

    @abstractmethod
    def evaluate(self, context: DriftRuleContext) -> list[DriftAlertDraft]:
        """Return draft alerts for a single rule evaluation pass."""
