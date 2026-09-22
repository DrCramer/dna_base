from app.protocol_exporters.base import ProtocolInstrumentExporter


_exporters: dict[str, ProtocolInstrumentExporter] = {}


def register_exporter(exporter: ProtocolInstrumentExporter) -> None:
    if exporter.key in _exporters:
        raise ValueError(f"Exporter {exporter.key!r} is already registered")
    _exporters[exporter.key] = exporter


def list_exporters() -> list[ProtocolInstrumentExporter]:
    return list(_exporters.values())


def get_exporter(key: str) -> ProtocolInstrumentExporter | None:
    return _exporters.get(key)
