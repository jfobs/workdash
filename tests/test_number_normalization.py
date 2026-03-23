from src.parsing.number_normalization import normalize_numeric


def test_normalize_parentheses_and_percent():
    assert normalize_numeric("(1,234)") == -1234.0
    assert normalize_numeric("25%") == 0.25


def test_normalize_blank_dash():
    assert normalize_numeric("—") is None
