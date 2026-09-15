from pathlib import Path


def test_synthetic_seed_is_explicitly_gated_and_two_months():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "seed_vibanda_synthetic.py").read_text()
    assert "SYNTHETIC_DATA_ALLOWED" in source
    assert "--yes-synthetic-data" in source
    assert "Vibanda Village — Synthetic" in source
    assert "HISTORY_DAYS = 60" in source
