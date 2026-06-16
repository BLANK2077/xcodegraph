"""Common pytest fixtures for xcodegraph tests."""

import os
import sys
import pytest

# Make xcodegraph package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sv_tmpdir(tmp_path):
    """Temporary directory with SV source files and filelists."""
    return tmp_path


@pytest.fixture
def make_filelist(sv_tmpdir):
    """Helper to create a .f filelist and supporting files."""
    def _make(name: str, lines: list[str], extra_files: dict[str, str] | None = None):
        """Create a filelist `name` with `lines`, plus optional extra source files."""
        filelist_path = sv_tmpdir / name
        filelist_path.parent.mkdir(parents=True, exist_ok=True)
        filelist_path.write_text("\n".join(lines))

        if extra_files:
            for fname, content in extra_files.items():
                fpath = sv_tmpdir / fname
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content)

        return str(filelist_path)
    return _make
