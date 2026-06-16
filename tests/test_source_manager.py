"""TDD: xcg.md Step 3-5 — SourceManager + include + preprocessor."""

import pytest
from pathlib import Path
from xcodegraph.core.source_manager import (
    SourceManager, MiniPreprocessor, SourceMap, SourceSegment,
)


# ── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def include_pkg_classes(tmp_path: Path):
    """xcg.md 14.1: package with `include'd class files."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "my_agent_pkg.sv").write_text("""\
package my_agent_pkg;
  import uvm_pkg::*;
  `include "my_item.svh"
  `include "my_driver.svh"
  `include "my_monitor.svh"
endpackage
""")
    (rtl / "my_item.svh").write_text("""\
class my_item extends uvm_sequence_item;
  rand bit [7:0] data;
endclass
""")
    (rtl / "my_driver.svh").write_text("""\
class my_driver extends uvm_driver #(my_item);
  task run_phase(uvm_phase phase); endtask
endclass
""")
    (rtl / "my_monitor.svh").write_text("""\
class my_monitor extends uvm_monitor;
  uvm_analysis_port #(my_item) ap;
endclass
""")
    return rtl


@pytest.fixture
def multi_pkg_same_header(tmp_path: Path):
    """xcg.md 14.2: same .svh included by two packages."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "a_pkg.sv").write_text("""\
package a_pkg;
  `include "common_seq.svh"
endpackage
""")
    (rtl / "b_pkg.sv").write_text("""\
package b_pkg;
  `include "common_seq.svh"
endpackage
""")
    (rtl / "common_seq.svh").write_text("""\
class common_seq extends uvm_sequence;
  task body(); endtask
endclass
""")
    return rtl


@pytest.fixture
def ifdef_include(tmp_path: Path):
    """xcg.md 14.3: ifdef-controlled include."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "my_pkg.sv").write_text("""\
package my_pkg;
  `ifdef USE_AXI
    `include "axi_driver.svh"
  `else
    `include "apb_driver.svh"
  `endif
endpackage
""")
    (rtl / "axi_driver.svh").write_text("class axi_driver extends uvm_driver; endclass\n")
    (rtl / "apb_driver.svh").write_text("class apb_driver extends uvm_driver; endclass\n")
    return rtl


# ── MiniPreprocessor tests ────────────────────────────────────────────────

class TestMiniPreprocessor:
    def test_ifdef_active_branch(self):
        pp = MiniPreprocessor({"USE_AXI": "1"})
        lines = [
            "package p;\n",
            "`ifdef USE_AXI\n",
            "  axi_driver\n",
            "`else\n",
            "  apb_driver\n",
            "`endif\n",
            "endpackage\n",
        ]
        out, _ = pp.process_lines(lines, "test.sv")
        joined = "".join(out)
        assert "axi_driver" in joined
        assert "apb_driver" not in joined

    def test_ifndef_inactive_when_defined(self):
        pp = MiniPreprocessor({"SIM": "1"})
        lines = [
            "`ifndef SIM\n",
            "  no_sim\n",
            "`else\n",
            "  yes_sim\n",
            "`endif\n",
        ]
        out, _ = pp.process_lines(lines, "test.sv")
        joined = "".join(out)
        assert "no_sim" not in joined
        assert "yes_sim" in joined

    def test_elsif_selects_second(self):
        pp = MiniPreprocessor({"B": "1"})
        lines = [
            "`ifdef A\n",
            "  a\n",
            "`elsif B\n",
            "  b\n",
            "`else\n",
            "  c\n",
            "`endif\n",
        ]
        out, _ = pp.process_lines(lines, "test.sv")
        joined = "".join(out)
        assert "a" not in joined
        assert "b" in joined
        assert "c" not in joined

    def test_nested_ifdef(self):
        pp = MiniPreprocessor({"A": "1", "B": "1"})
        lines = [
            "`ifdef A\n",
            "  `ifdef B\n",
            "    nested_active\n",
            "  `endif\n",
            "  outer_active\n",
            "`endif\n",
            "always_on\n",  # outside any ifdef → always active
        ]
        out, _ = pp.process_lines(lines, "test.sv")
        joined = "".join(out)
        assert "nested_active" in joined
        assert "outer_active" in joined
        assert "always_on" in joined  # outside ifdef block → always active

    def test_undef_detection(self):
        pp = MiniPreprocessor({"X": "1"})
        lines = ["`ifdef X\n", "  active\n", "`endif\n"]
        out, _ = pp.process_lines(lines, "test.sv")
        assert "active" in "".join(out)

        pp2 = MiniPreprocessor({})
        out2, _ = pp2.process_lines(lines, "test.sv")
        assert "active" not in "".join(out2)


# ── SourceManager tests ───────────────────────────────────────────────────

class TestIncludeExpansion:
    """xcg.md 14.1: include_pkg_classes."""

    def test_expanded_source_contains_class(self, include_pkg_classes):
        sm = SourceManager(incdirs=[str(include_pkg_classes)])
        result = sm.build_compilation_unit(str(include_pkg_classes / "my_agent_pkg.sv"))
        assert "my_driver" in result.source_text
        assert "my_monitor" in result.source_text
        # The expanded source should have the full package with inlined classes
        assert "package my_agent_pkg" in result.source_text
        assert "endpackage" in result.source_text

    def test_source_map_segments_created(self, include_pkg_classes):
        sm = SourceManager(incdirs=[str(include_pkg_classes)])
        result = sm.build_compilation_unit(str(include_pkg_classes / "my_agent_pkg.sv"))
        # Should have segments for each included file
        origin_files = {seg.origin_file for seg in result.source_map.segments}
        assert any("my_item.svh" in f for f in origin_files)
        assert any("my_driver.svh" in f for f in origin_files)

    def test_include_edges_recorded(self, include_pkg_classes):
        sm = SourceManager(incdirs=[str(include_pkg_classes)])
        result = sm.build_compilation_unit(str(include_pkg_classes / "my_agent_pkg.sv"))
        assert len(result.include_edges) == 3
        assert all(e.resolved for e in result.include_edges)


class TestMultiPackageSameHeader:
    """xcg.md 14.2: same .svh in two packages."""

    def test_both_cus_expand(self, multi_pkg_same_header):
        sm = SourceManager(incdirs=[str(multi_pkg_same_header)])
        r1 = sm.build_compilation_unit(str(multi_pkg_same_header / "a_pkg.sv"))
        r2 = sm.build_compilation_unit(str(multi_pkg_same_header / "b_pkg.sv"))

        assert "common_seq" in r1.source_text
        assert "common_seq" in r2.source_text
        assert "a_pkg" in r1.source_text
        assert "b_pkg" in r2.source_text


class TestIfdefInclude:
    """xcg.md 14.3: ifdef-controlled include selection."""

    def test_active_branch_only(self, ifdef_include):
        sm = SourceManager(
            incdirs=[str(ifdef_include)],
            defines={"USE_AXI": "1"},
        )
        result = sm.build_compilation_unit(str(ifdef_include / "my_pkg.sv"))
        assert "axi_driver" in result.source_text
        assert "apb_driver" not in result.source_text

    def test_inactive_branch_excluded(self, ifdef_include):
        sm = SourceManager(
            incdirs=[str(ifdef_include)],
            defines={},  # USE_AXI not defined → else branch active
        )
        result = sm.build_compilation_unit(str(ifdef_include / "my_pkg.sv"))
        assert "axi_driver" not in result.source_text
        assert "apb_driver" in result.source_text


class TestCircularInclude:
    """xcg.md 14.8: circular include detection."""

    def test_circular_include_diagnostic(self, tmp_path):
        rtl = tmp_path / "rtl"
        rtl.mkdir()
        (rtl / "a.svh").write_text('`include "b.svh"\n')
        (rtl / "b.svh").write_text('`include "a.svh"\n')
        (rtl / "top.sv").write_text('`include "a.svh"\n')
        sm = SourceManager(incdirs=[str(rtl)])
        result = sm.build_compilation_unit(str(rtl / "top.sv"))
        assert any("circular" in d.message.lower() for d in result.diagnostics)


class TestUnresolvedInclude:
    """xcg.md 14.7: unresolved include diagnostic."""

    def test_unresolved_include_diagnostic(self, tmp_path):
        rtl = tmp_path / "rtl"
        rtl.mkdir()
        (rtl / "top.sv").write_text('`include "missing.svh"\n')
        sm = SourceManager(incdirs=[str(rtl)])
        result = sm.build_compilation_unit(str(rtl / "top.sv"))
        assert any("unresolved" in d.message.lower() for d in result.diagnostics)
        # Should not crash
        assert isinstance(result.source_text, str)
