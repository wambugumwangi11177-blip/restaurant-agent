import json
from pathlib import Path

from integration.export_probe import profile_csv


def test_csv_probe_profiles_without_persisting_rows(tmp_path: Path):
    export = tmp_path / "sales.csv"
    export.write_text("id,when,cents,status\na,2026-09-15T08:00:00+03:00,1200,closed\na,not-a-date,1500,closed\nb,2026-09-15T09:00:00+03:00,nope,void\n")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"sale_id": "id", "sale_timestamp": "when", "sale_amount_minor": "cents", "sale_status": "status"}))
    result = profile_csv(export, mapping)
    assert result.rows == 3
    assert result.unique_sale_ids == 2
    assert result.duplicate_sale_ids == 1
    assert result.malformed_timestamps == 1
    assert result.malformed_amounts == 1
