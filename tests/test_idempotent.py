"""TDD: xcg.md Step 1 — DB idempotency (repeated index = same counts)."""

import pytest
from xcodegraph.core.indexer import Indexer
from xcodegraph.core.storage import Storage


@pytest.fixture
def indexed_db(tmp_path):
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.sv").write_text("module top; sub u_sub(); endmodule\n")
    (rtl / "sub.sv").write_text("module sub; endmodule\n")
    (rtl / "filelist.f").write_text("top.sv\nsub.sv\n")

    db_path = str(tmp_path / "index.sqlite")
    return db_path, rtl


class TestReIndexIdempotent:
    """Index twice → same node/edge/unresolved_ref counts."""

    def test_double_index_same_counts(self, indexed_db):
        db_path, rtl = indexed_db

        # First index
        idx1 = Indexer(db_path)
        idx1.index_filelist(str(rtl / "filelist.f"))
        idx1.close()
        s1 = Storage(db_path)
        n1 = s1.stats()["node_count"]
        e1 = s1.stats()["edge_count"]
        u1 = s1.stats()["unresolved_ref_count"]
        s1.close()

        # Second index (same filelist)
        idx2 = Indexer(db_path)
        idx2.index_filelist(str(rtl / "filelist.f"))
        idx2.close()
        s2 = Storage(db_path)
        n2 = s2.stats()["node_count"]
        e2 = s2.stats()["edge_count"]
        u2 = s2.stats()["unresolved_ref_count"]
        s2.close()

        assert n1 == n2, f"node count: {n1} vs {n2}"
        assert e1 == e2, f"edge count: {e1} vs {e2}"
        assert u1 == u2, f"unresolved_ref count: {u1} vs {u2}"

    def test_triple_index_stable(self, indexed_db):
        db_path, rtl = indexed_db
        counts = []
        for _ in range(3):
            idx = Indexer(db_path)
            idx.index_filelist(str(rtl / "filelist.f"))
            idx.close()
            s = Storage(db_path)
            counts.append(s.stats()["node_count"])
            s.close()

        assert counts[0] == counts[1] == counts[2], f"counts: {counts}"

    def test_reindex_single_file_no_duplicate(self, indexed_db):
        db_path, rtl = indexed_db

        idx = Indexer(db_path)
        idx.index_filelist(str(rtl / "filelist.f"))
        idx.close()
        s = Storage(db_path)
        before = s.stats()["node_count"]
        s.close()

        # Modify and reindex single file
        (rtl / "top.sv").write_text("module top; sub u_sub(); endmodule\n// modified\n")
        idx2 = Indexer(db_path)
        idx2.index_filelist(str(rtl / "filelist.f"))
        idx2.close()
        s2 = Storage(db_path)
        after = s2.stats()["node_count"]
        s2.close()

        # Counts should be stable (same number of modules)
        assert after == before, f"before={before}, after={after}"
