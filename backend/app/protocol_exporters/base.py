from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ExportedFile:
    filename: str
    mime_type: str
    content: bytes


class ProtocolInstrumentExporter(Protocol):
    key: str
    stage_type: str

    def validate(self, protocol_snapshot: dict[str, Any]) -> list[ValidationIssue]: ...

    def export(self, protocol_snapshot: dict[str, Any]) -> ExportedFile: ...
