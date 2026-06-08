"""Module with example function unit test for description purposes."""

from tgedr_observability.example import dict2pd


def test_example() -> None:
    """Tests the conversion a list of dictionaries to a pandas DataFrame."""
    data = [
        {"Name": "Alice", "Age": 25, "City": "New York"},
        {"Name": "Bob", "Age": 30, "City": "Los Angeles"},
        {"Name": "Charlie", "Age": 35, "City": "Chicago"},
    ]
    dfx = dict2pd(data)
    assert dfx.iloc[0, 0] == "Alice"
    assert dfx.iloc[1, 1] == 30
    assert dfx.iloc[2, 2] == "Chicago"
