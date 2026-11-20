import pytest

from truck_tms.database import ValidationError
from truck_tms.ui.widgets import format_number, parse_number


@pytest.mark.parametrize("text, value", [
    ("", None), ("  ", None),
    ("1500", 1500), ("1500.75", 1500.75), ("1500,75", 1500.75),
    ("12,500", 12500), ("12.500", 12500), ("1,234,567", 1234567), ("1.234.567", 1234567),
    ("1,234.50", 1234.5), ("1.234,50", 1234.5),
    ("0,70", 0.7), ("0.650", 0.65), (".5", 0.5), ("2,5", 2.5), ("-1,250", -1250),
    ("1 500", 1500),
])
def test_parse_number(text, value):
    assert parse_number(text) == value


@pytest.mark.parametrize("text", ["abc", "1,2,3", "12..5", "1.2.3,4.5"])
def test_parse_number_rejects_garbage(text):
    with pytest.raises(ValidationError):
        parse_number(text)


def test_format_number_round_trip():
    for value in (0, 7, 12500, 0.65, 1234.5):
        assert parse_number(format_number(value)) == value
