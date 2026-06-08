"""Module with example function for description purposes."""

import pandas as pd


def dict2pd(data: list[dict]) -> pd.DataFrame:
    """Convert a list of dictionaries to a pandas DataFrame."""
    return pd.DataFrame.from_dict(data)


def dummy_calculation(value: int) -> int:
    """The dummy function."""
    return value
