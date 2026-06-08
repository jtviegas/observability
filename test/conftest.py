"""test configurations."""

from pathlib import Path
import sys
import tempfile
import pytest


sys.path.insert(0, Path(__file__).parent.parent.joinpath("src").absolute())  # isort:skip


@pytest.fixture(scope="session")
def resources_folder() -> str:
    """Provides the location of test respource folder.

    Returns:
        test resources folder path

    """
    return Path(__file__).parent.joinpath("resources").absolute()


@pytest.fixture(scope="session")
def temporary_folder() -> str:
    """Provides a temporary folder for testing purposes.

    Returns:
        temporary folder

    """
    # pylint: disable=consider-using-with
    _folder = tempfile.TemporaryDirectory("+wb").name
    _path = Path(_folder)
    if not _path.exists():
        _path.mkdir(parents=True)
    return _folder
