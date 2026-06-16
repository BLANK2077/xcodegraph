"""TDD: Phase 6 — AI-oriented module summary + advanced extraction."""

import pytest
from xcodegraph.core.parser import SVParser
from xcodegraph.core.storage import Storage
from xcodegraph.core.indexer import Indexer


@pytest.fixture
def indexed_uvm_project(tmp_path):
    """Index a UVM-style project and return the DB path."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()

    (rtl / "env.sv").write_text("""\
package my_env_pkg;
  import uvm_pkg::*;

  class my_driver extends uvm_driver #(axi_item);
    virtual axi_if vif;
    task run_phase(uvm_phase phase);
      seq_item_port.get_next_item(req);
      vif.drv_cb.data <= req.data;
      seq_item_port.item_done();
    endtask
  endclass

  class my_monitor extends uvm_monitor;
    uvm_analysis_port #(axi_item) ap;
    task run_phase(uvm_phase phase);
      forever begin
        axi_item item;
        ap.write(item);
      end
    endtask
  endclass

  class axi_item extends uvm_sequence_item;
    rand bit [7:0] addr;
    rand bit [31:0] data;
    constraint addr_align { addr[1:0] == 2'b00; }
  endclass

  covergroup cg_transfer @(posedge clk);
    addr_cp: coverpoint vif.mon_cb.addr;
    data_cp: coverpoint vif.mon_cb.data;
    addr_x_data: cross addr_cp, data_cp;
  endgroup
endpackage
""")

    (rtl / "top.sv").write_text("""\
module tb_top;
  axi_if u_if();
  initial run_test("my_test");
endmodule
""")

    (rtl / "filelist.f").write_text("env.sv\ntop.sv")

    db_path = str(tmp_path / "index.sqlite")
    idx = Indexer(db_path)
    idx.index_filelist(str(rtl / "filelist.f"))
    idx.close()
    return db_path


class TestModuleSummary:
    """TDD: generate a summary for a module/package."""

    def test_summary_has_structure(self, indexed_uvm_project):
        s = Storage(indexed_uvm_project)
        assert s.stats()["node_count"] > 0

    def test_driver_has_run_phase(self, indexed_uvm_project):
        s = Storage(indexed_uvm_project)
        node = s.get_node("my_driver")
        s.close()
        assert node is not None
        assert node["kind"] == "class"

    def test_coverage_extracted(self, indexed_uvm_project):
        s = Storage(indexed_uvm_project)
        nodes = s.search_nodes("cg_transfer")
        s.close()
        assert len(nodes) >= 1

    def test_tlm_port_detected(self, indexed_uvm_project):
        s = Storage(indexed_uvm_project)
        nodes = s.search_nodes("ap", kind="tlminitf")
        s.close()
        assert len(nodes) >= 1

    def test_constraint_detected(self, indexed_uvm_project):
        s = Storage(indexed_uvm_project)
        nodes = s.search_nodes("addr_align")
        s.close()
        assert len(nodes) >= 1


class TestGenerateSummary:
    """TDD: generate_summary() function."""

    def test_generate_summary_for_module(self, indexed_uvm_project):
        from xcodegraph.core.summary import generate_summary
        s = Storage(indexed_uvm_project)
        summary = generate_summary(s, "my_driver")
        s.close()
        assert "my_driver" in summary
        assert "class" in summary.lower() or "uvm" in summary.lower()

    def test_generate_summary_handles_missing(self, indexed_uvm_project):
        from xcodegraph.core.summary import generate_summary
        s = Storage(indexed_uvm_project)
        summary = generate_summary(s, "nonexistent")
        s.close()
        assert "not found" in summary.lower()
