"""TDD: reindex and stale detection (Phase 4)."""

import os
import pytest
from xcodegraph.core.indexer import Indexer
from xcodegraph.core.storage import Storage


@pytest.fixture
def indexed_db(tmp_path):
    """Create a mini project with git repo and indexed data."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()

    (rtl / "top.sv").write_text("module top(input clk); endmodule\n")
    (rtl / "filelist.f").write_text("top.sv\n")

    # Initialize git repo
    repo_dir = str(tmp_path)
    os.system(f"cd {repo_dir} && git init && git add -A && git commit -m init 2>/dev/null")

    db_path = str(tmp_path / "index.sqlite")
    idx = Indexer(db_path)
    idx.index_filelist(str(rtl / "filelist.f"))
    idx.close()
    return tmp_path, db_path


class TestStatusStale:
    """TDD: stale detection via Git HEAD and file hash."""

    def test_status_ok_after_index(self, indexed_db):
        tmp_path, db_path = indexed_db
        s = Storage(db_path)
        stats = s.stats()
        s.close()
        assert stats["node_count"] > 0

    def test_file_hash_tracking(self, indexed_db):
        tmp_path, db_path = indexed_db
        s = Storage(db_path)
        # Verify files table has sha256
        row = s.conn.execute("SELECT sha256 FROM files LIMIT 1").fetchone()
        s.close()
        assert row["sha256"] and len(row["sha256"]) == 64  # SHA256 hex

    def test_meta_stores_index_info(self, indexed_db):
        tmp_path, db_path = indexed_db
        s = Storage(db_path)
        backend = s.get_meta("backend")
        s.close()
        assert backend == "tree-sitter"

    def test_upsert_unchanged_file_skips(self, indexed_db):
        """Re-indexing unchanged file should be no-op (sha256 match)."""
        tmp_path, db_path = indexed_db
        s = Storage(db_path)
        before = s.stats()["node_count"]

        # Re-insert same file content
        top_sv = tmp_path / "rtl" / "top.sv"
        content = top_sv.read_bytes()
        s.upsert_file(str(top_sv), content)
        after = s.stats()["node_count"]
        s.close()

        # Node count should be unchanged (no new nodes added)
        assert before == after


class TestReindex:
    """TDD: reindex --file / --changed / --full."""

    def test_reindex_full_rebuilds(self, indexed_db):
        tmp_path, db_path = indexed_db
        idx = Indexer(db_path)
        result = idx.index_filelist(str(tmp_path / "rtl" / "filelist.f"))
        idx.close()
        assert result["indexed_files"] == 1

    def test_reindex_detects_modified_file(self, indexed_db):
        tmp_path, db_path = indexed_db
        s = Storage(db_path)
        before = s.stats()["file_count"]

        # Modify file
        top_sv = tmp_path / "rtl" / "top.sv"
        top_sv.write_text("module top(input clk, input rst_n); endmodule\n")

        # Re-index
        s.close()
        idx = Indexer(db_path)
        idx.index_filelist(str(tmp_path / "rtl" / "filelist.f"))
        idx.close()

        s2 = Storage(db_path)
        after = s2.stats()
        s2.close()

        # Should still have same file count
        assert after["file_count"] == before
