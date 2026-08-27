"""test configurations."""

from pathlib import Path
import sys
import tempfile
from typing import Generator
import pytest


sys.path.insert(0, str(Path(__file__).parent.parent.joinpath("src").absolute()))  # isort:skip


@pytest.fixture(scope="session")
def resources_folder() -> str:
    """Provides the location of test respource folder.

    Returns:
        test resources folder path

    """
    return str(Path(__file__).parent.joinpath("resources").absolute())


@pytest.fixture(scope="session")
def temporary_folder() -> Generator[str, None, None]:
    """Provides a temporary folder for testing purposes.

    Yields:
        temporary folder path

    """
    _tmpdir = tempfile.TemporaryDirectory()
    _path = Path(_tmpdir.name)
    if not _path.exists():
        _path.mkdir(parents=True)
    yield _tmpdir.name
    _tmpdir.cleanup()
