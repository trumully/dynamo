import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from dynamo.utils import helper


@pytest.fixture
def temp_dir() -> Generator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def test_existing_file(temp_dir: Path) -> None:
    file_path = temp_dir / "existing_file.txt"
    file_path.touch()
    assert helper.resolve_file_with_links(file_path) == file_path.resolve()


def test_existing_folder(temp_dir: Path) -> None:
    folder_path = temp_dir / "existing_folder"
    folder_path.mkdir()
    assert helper.resolve_folder_with_links(folder_path) == folder_path.resolve()


def test_non_existing_file(temp_dir: Path) -> None:
    file_path = temp_dir / "non_existing_file.txt"
    resolved_path = helper.resolve_file_with_links(file_path)
    assert resolved_path.exists()
    assert resolved_path.is_file()


def test_non_existing_folder(temp_dir: Path) -> None:
    folder_path = temp_dir / "non_existing_folder"
    resolved_path = helper.resolve_folder_with_links(folder_path)
    assert resolved_path.exists()
    assert resolved_path.is_dir()


def test_nested_non_existing_path(temp_dir: Path) -> None:
    nested_path = temp_dir / "a" / "b" / "c" / "file.txt"
    resolved_path = helper.resolve_file_with_links(nested_path)
    assert resolved_path.exists()
    assert resolved_path.is_file()
    assert all(p.exists() for p in resolved_path.parents if str(p) != resolved_path.root)
