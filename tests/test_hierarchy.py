"""TDD: hierarchy and instantiated-by queries (Phase 2)."""

import os
import pytest
from xcodegraph.core.indexer import Indexer
from xcodegraph.core.storage import Storage


@pytest.fixture
def indexed_db(tmp_path):
    """Create a mini project with module hierarchy and index it.

    top
    ├── u_fifo  (fifo)
    └── u_uart  (uart_tx)
          └── u_baud (baud_gen)
    """
    rtl = tmp_path / "rtl"
    rtl.mkdir()

    (rtl / "fifo.sv").write_text("""
module fifo(input clk, input rst_n);
endmodule
""")

    (rtl / "baud_gen.sv").write_text("""
module baud_gen(input clk);
endmodule
""")

    (rtl / "uart_tx.sv").write_text("""
module uart_tx(input clk);
  baud_gen u_baud(.clk(clk));
endmodule
""")

    (rtl / "top.sv").write_text("""
module top(input clk);
  fifo u_fifo(.clk(clk), .rst_n(1'b0));
  uart_tx u_uart(.clk(clk));
endmodule
""")

    (rtl / "filelist.f").write_text("""\
fifo.sv
baud_gen.sv
uart_tx.sv
top.sv
""")

    db_path = str(tmp_path / "index.sqlite")
    idx = Indexer(db_path)
    idx.index_filelist(str(rtl / "filelist.f"))
    idx.close()
    return db_path


class TestHierarchy:
    """TDD: hierarchy (BFS following INSTANTIATES edges)."""

    def test_hierarchy_from_top(self, indexed_db):
        s = Storage(indexed_db)
        hierarchy = s.get_hierarchy("top", depth=5)
        s.close()

        names = [h["name"] for h in hierarchy]
        assert "top" in names
        assert "fifo" in names
        assert "uart_tx" in names
        assert "baud_gen" in names

    def test_hierarchy_depth_limit(self, indexed_db):
        s = Storage(indexed_db)
        hierarchy = s.get_hierarchy("top", depth=0)
        s.close()
        # depth 0: only top itself
        assert len(hierarchy) == 1

    def test_hierarchy_depth_1(self, indexed_db):
        s = Storage(indexed_db)
        hierarchy = s.get_hierarchy("top", depth=1)
        s.close()
        # top + direct children (fifo + uart_tx)
        names = {h["name"] for h in hierarchy}
        assert "top" in names
        assert "fifo" in names
        assert "uart_tx" in names
        assert "baud_gen" not in names  # depth 2


class TestInstantiatedBy:
    """TDD: reverse INSTANTIATES lookup."""

    def test_fifo_instantiated_by_top(self, indexed_db):
        s = Storage(indexed_db)
        result = s.get_instantiated_by("fifo")
        s.close()

        instantiators = [r["name"] for r in result]
        assert "top" in instantiators

    def test_baud_gen_instantiated_by_uart(self, indexed_db):
        s = Storage(indexed_db)
        result = s.get_instantiated_by("baud_gen")
        s.close()

        instantiators = [r["name"] for r in result]
        assert "uart_tx" in instantiators


class TestExtendsImports:
    """TDD: extends and imports edge queries."""

    def test_extends_query(self, indexed_db):
        s = Storage(indexed_db)
        # Our test project has no extends, just verify the API works
        result = s.get_edges_by_kind("top", "EXTENDS")
        s.close()
        assert isinstance(result, list)

    def test_imports_query(self, indexed_db):
        s = Storage(indexed_db)
        result = s.get_edges_by_kind("top", "IMPORTS")
        s.close()
        assert isinstance(result, list)
