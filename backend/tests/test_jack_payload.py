from services.jack_payload import strip_money_fields


def test_strip_money_fields_removes_kes_recursive():
    raw = {"item": "Rice", "kes": 900, "nested": {"amount_cents": 100, "qty": 8, "unit": "kg"}}
    out = strip_money_fields(raw)
    assert "kes" not in out
    assert "amount_cents" not in out["nested"]
    assert out["nested"]["qty"] == 8