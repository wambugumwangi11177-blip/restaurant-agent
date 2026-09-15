"""Validation-only tracer for a vendor CSV export.

It reads a supplied file, profiles required fields, and emits aggregate
evidence. It never writes to the application database, calls a vendor, or
prints raw rows/PII. Use it only after the vendor has approved the export.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


REQUIRED_MAPPING_KEYS = frozenset({"sale_id", "sale_timestamp", "sale_amount_minor", "sale_status"})


class ExportProbeError(ValueError):
    pass


@dataclass(frozen=True)
class ExportProfile:
    rows: int
    unique_sale_ids: int
    duplicate_sale_ids: int
    malformed_timestamps: int
    malformed_amounts: int
    statuses: dict[str, int]
    mapped_columns: dict[str, str]


def _load_mapping(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportProbeError(f"cannot read mapping: {exc}") from exc
    if not isinstance(data, dict) or not REQUIRED_MAPPING_KEYS <= data.keys():
        missing = sorted(REQUIRED_MAPPING_KEYS - set(data) if isinstance(data, dict) else REQUIRED_MAPPING_KEYS)
        raise ExportProbeError(f"mapping must contain: {', '.join(missing)}")
    if not all(isinstance(data[key], str) and data[key].strip() for key in REQUIRED_MAPPING_KEYS):
        raise ExportProbeError("mapped column names must be non-empty strings")
    return {key: value.strip() for key, value in data.items() if isinstance(value, str)}


def profile_csv(export_path: Path, mapping_path: Path) -> ExportProfile:
    mapping = _load_mapping(mapping_path)
    try:
        stream = export_path.open(newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise ExportProbeError(f"cannot read export: {exc}") from exc
    with stream:
        reader = csv.DictReader(stream)
        headers = set(reader.fieldnames or [])
        absent = sorted(set(mapping.values()) - headers)
        if absent:
            raise ExportProbeError("mapped columns not found: " + ", ".join(absent))
        ids: Counter[str] = Counter()
        statuses: Counter[str] = Counter()
        malformed_timestamps = malformed_amounts = rows = 0
        for row in reader:
            rows += 1
            ids[(row.get(mapping["sale_id"]) or "").strip()] += 1
            statuses[(row.get(mapping["sale_status"]) or "<blank>").strip() or "<blank>"] += 1
            try:
                datetime.fromisoformat((row.get(mapping["sale_timestamp"]) or "").strip().replace("Z", "+00:00"))
            except ValueError:
                malformed_timestamps += 1
            try:
                int((row.get(mapping["sale_amount_minor"]) or "").strip())
            except ValueError:
                malformed_amounts += 1
    empty_id_count = ids.pop("", 0)
    return ExportProfile(
        rows=rows,
        unique_sale_ids=len(ids),
        duplicate_sale_ids=sum(count - 1 for count in ids.values() if count > 1),
        malformed_timestamps=malformed_timestamps,
        malformed_amounts=malformed_amounts,
        statuses=dict(sorted(statuses.items())),
        mapped_columns=mapping,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a Macsoft/vendor CSV without persisting data.")
    parser.add_argument("export", type=Path, help="path to the vendor-approved CSV")
    parser.add_argument("--mapping", required=True, type=Path, help="JSON mapping from canonical fields to CSV columns")
    args = parser.parse_args()
    try:
        print(json.dumps(asdict(profile_csv(args.export, args.mapping)), indent=2, sort_keys=True))
    except ExportProbeError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
