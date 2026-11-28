from services.inventory_units import ALLOWED_UNITS, is_allowed_unit, normalize_unit


def test_normalize_aliases():
    assert normalize_unit("KGS") == "kg"
    assert normalize_unit("litre") == "L"
    assert normalize_unit("pieces") == "pcs"
    assert normalize_unit("L") == "L"


def test_allowed_list():
    for unit in ALLOWED_UNITS:
        assert is_allowed_unit(unit)