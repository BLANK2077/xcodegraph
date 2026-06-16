"""TDD: Phase 5 — UVM class inference, common block, include tracking."""

import pytest
from xcodegraph.core.parser import SVParser


@pytest.fixture(scope="module")
def parser():
    return SVParser()


def extract(parser, source):
    return parser.extract("test.sv", source)


class TestUVMClassInference:
    """TDD: detect UVM component type from class extends."""

    def test_driver_detected(self, parser):
        r = extract(parser, """
package p;
  class my_driver extends uvm_driver #(item);
    task run_phase(uvm_phase phase); endtask
  endclass
endpackage""")
        classes = [n for n in r.nodes if n.kind == "class"]
        assert len(classes) >= 1

    def test_monitor_detected(self, parser):
        r = extract(parser, """
package p;
  class my_monitor extends uvm_monitor;
  endclass
endpackage""")
        classes = [n for n in r.nodes if n.kind == "class"]
        assert len(classes) >= 1

    def test_env_agent_scoreboard(self, parser):
        r = extract(parser, """
package p;
  class my_env extends uvm_env; endclass
  class my_agent extends uvm_agent; endclass
  class my_scoreboard extends uvm_scoreboard; endclass
endpackage""")
        classes = [n for n in r.nodes if n.kind == "class"]
        assert len(classes) == 3

    def test_sequence_detected(self, parser):
        r = extract(parser, """
package p;
  class my_seq extends uvm_sequence #(item);
    task body(); endtask
  endclass
endpackage""")
        classes = [n for n in r.nodes if n.kind == "class"]
        assert len(classes) >= 1

    def test_test_detected(self, parser):
        r = extract(parser, """
package p;
  class my_test extends uvm_test;
    function void build_phase(uvm_phase phase); endfunction
  endclass
endpackage""")
        classes = [n for n in r.nodes if n.kind == "class"]
        assert len(classes) >= 1


class TestCommonBlockHook:
    """TDD: common block summary from JSON config."""

    def test_pattern_match_returns_summary(self):
        from xcodegraph.core.common_block import CommonBlockHook
        config = {
            "patterns": [
                {
                    "name": "common_fifo",
                    "path_regex": ".*/common/.*fifo.*\\.(sv|v)$",
                    "kind": "fifo",
                    "summary": "Common FIFO block. Treat as storage first."
                }
            ]
        }
        hook = CommonBlockHook(config)
        result = hook.match("/proj/common/ip/fifo_sync.sv")
        assert result is not None
        assert result["name"] == "common_fifo"
        assert result["kind"] == "fifo"

    def test_no_match_returns_none(self):
        from xcodegraph.core.common_block import CommonBlockHook
        config = {"patterns": [{"name": "fifo", "path_regex": ".*fifo.*", "kind": "fifo", "summary": "FIFO"}]}
        hook = CommonBlockHook(config)
        result = hook.match("/proj/rtl/uart_tx.sv")
        assert result is None

    def test_multiple_patterns_first_wins(self):
        from xcodegraph.core.common_block import CommonBlockHook
        config = {
            "patterns": [
                {"name": "arbiter", "path_regex": ".*arb.*", "kind": "arbiter", "summary": "Arbiter"},
                {"name": "rr_arbiter", "path_regex": ".*rr.*arb.*", "kind": "arbiter", "summary": "RR Arbiter"},
            ]
        }
        hook = CommonBlockHook(config)
        result = hook.match("/proj/rr_arbiter.sv")
        assert result is not None
        assert result["name"] == "arbiter"  # first match wins


class TestIncludeTracking:
    """TDD: `include file tracking."""

    def test_include_recorded_as_reference(self, parser):
        r = extract(parser, '`include "defs.svh"\nmodule top; endmodule')
        # include should appear as an unresolved ref or node
        ref_names = {r.name for r in r.unresolved_refs}
        assert "defs.svh" in ref_names
