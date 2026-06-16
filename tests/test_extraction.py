"""Test SystemVerilog AST extraction — RTL + verification structures."""

import pytest
from xcodegraph.core.parser import SVParser


@pytest.fixture(scope="module")
def parser():
    return SVParser()


def extract(parser, source):
    return parser.extract("test.sv", source)


class TestRTLStructures:
    """Module, interface, package, parameter, typedef, enum."""

    def test_module_declaration(self, parser):
        r = extract(parser, "module uart_tx(input logic clk); endmodule")
        nodes = {n.kind: n.name for n in r.nodes if n.kind == "module"}
        assert nodes.get("module") == "uart_tx"

    def test_interface_declaration(self, parser):
        r = extract(parser, "interface serial_if(input logic clk); endinterface")
        kinds = {n.kind for n in r.nodes}
        assert "interface" in kinds

    def test_package_declaration(self, parser):
        r = extract(parser, "package my_pkg; endpackage")
        kinds = {n.kind for n in r.nodes}
        assert "package" in kinds

    def test_parameter_extraction(self, parser):
        r = extract(parser, "module m #(parameter int W = 8, localparam int D = 16) (); endmodule")
        params = {n.name for n in r.nodes if n.kind == "parameter"}
        assert "W" in params
        assert "D" in params

    def test_typedef_extraction(self, parser):
        r = extract(parser, "package p; typedef enum { IDLE, RUN } st_e; endpackage")
        nodes = {(n.kind, n.name) for n in r.nodes}
        assert ("typedef", "st_e") in nodes

    def test_enum_member_extraction(self, parser):
        r = extract(parser, "package p; typedef enum { IDLE, RUN, DONE } st_e; endpackage")
        enum_names = {n.name for n in r.nodes if n.kind == "parameter" and n.name in ("IDLE", "RUN", "DONE")}
        assert enum_names == {"IDLE", "RUN", "DONE"}


class TestFunctionAndTask:
    """Function/task declarations and calls."""

    def test_function_declaration(self, parser):
        r = extract(parser, """
module m;
  function int calc(int x); return x + 1; endfunction
endmodule""")
        funcs = {n.name for n in r.nodes if n.kind == "function"}
        assert "calc" in funcs

    def test_task_declaration(self, parser):
        r = extract(parser, """
module m;
  task run_phase(); endtask
endmodule""")
        tasks = {n.name for n in r.nodes if n.kind == "function"}
        assert "run_phase" in tasks

    def test_function_call_recorded(self, parser):
        r = extract(parser, """
module m;
  function int calc(int x); return helper(x); endfunction
endmodule""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("CALLS", "helper") in refs


class TestInstantiations:
    """Module/interface instantiation."""

    def test_module_instantiation(self, parser):
        r = extract(parser, """
module top; sub u_sub(.clk(clk)); endmodule""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("INSTANTIATES", "sub") in refs

    def test_instantiation_walks_children_for_calls(self, parser):
        r = extract(parser, """
module top;
  sub #(.W(helper(8))) u_sub(.clk(clk));
endmodule""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("CALLS", "helper") in refs
        assert ("INSTANTIATES", "sub") in refs


class TestImports:
    """Package import."""

    def test_package_import(self, parser):
        r = extract(parser, """
module m; import uvm_pkg::*; endmodule""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("IMPORTS", "uvm_pkg") in refs

    def test_import_creates_node(self, parser):
        r = extract(parser, """
module m; import my_pkg::*; endmodule""")
        imports = {n.name for n in r.nodes if n.kind == "import"}
        assert any("my_pkg" in imp for imp in imports)


class TestClassExtends:
    """Class declarations and inheritance."""

    def test_class_declaration(self, parser):
        r = extract(parser, """
package p;
  class my_driver extends uvm_driver; endclass
endpackage""")
        kinds = {n.kind for n in r.nodes}
        assert "class" in kinds

    def test_extends_reference(self, parser):
        r = extract(parser, """
package p;
  class my_driver extends uvm_driver; endclass
endpackage""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("EXTENDS", "uvm_driver") in refs

    def test_class_contains_method(self, parser):
        r = extract(parser, """
package p;
  class my_driver extends uvm_driver;
    function void build_phase(uvm_phase phase); endfunction
    task run_phase(uvm_phase phase); endtask
  endclass
endpackage""")
        edges = {(e.src_name, e.kind, e.dst_name) for e in r.edges}
        assert ("my_driver", "CONTAINS", "build_phase") in edges
        assert ("my_driver", "CONTAINS", "run_phase") in edges


class TestVerificationSVA:
    """SVA property/sequence/assert/assume."""

    def test_property_declaration(self, parser):
        r = extract(parser, """
module m(input clk, input push);
  property push_no_overflow; @(posedge clk) push |-> !overflow; endproperty
endmodule""")
        props = {n.name for n in r.nodes if n.kind == "property"}
        assert "push_no_overflow" in props

    def test_sequence_declaration(self, parser):
        r = extract(parser, """
module m;
  sequence fifo_full_seq; cnt == DEPTH; endsequence
endmodule""")
        seqs = {n.name for n in r.nodes if n.kind == "sequence"}
        assert "fifo_full_seq" in seqs

    def test_assert_statement(self, parser):
        r = extract(parser, """
module m(input clk);
  assert property (@(posedge clk) a |-> b) else $error("fail");
endmodule""")
        kinds = {n.kind for n in r.nodes}
        assert "assert" in kinds

    def test_checker_extraction(self, parser):
        r = extract(parser, """
checker my_checker(input clk); endchecker""")
        kinds = {n.kind for n in r.nodes}
        assert "checker" in kinds


class TestVerificationConstraints:
    """Constraint blocks and rand fields."""

    def test_rand_field_detected(self, parser):
        r = extract(parser, """
package p;
  class my_item;
    rand bit [7:0] addr;
  endclass
endpackage""")
        rand_fields = {n.name for n in r.nodes if n.kind == "rand_field"}
        assert "addr" in rand_fields

    def test_constraint_block(self, parser):
        r = extract(parser, """
package p;
  class my_item;
    rand bit [7:0] addr;
    constraint addr_align { addr[1:0] == 2'b00; }
  endclass
endpackage""")
        constraints = {n.kind for n in r.nodes if n.kind == "constraint"}
        assert len(constraints) > 0


class TestVerificationCoverage:
    """Covergroups, coverpoints, crosses."""

    def test_covergroup(self, parser):
        r = extract(parser, """
module m(input clk);
  covergroup cg @(posedge clk);
    cp: coverpoint sig;
  endgroup
endmodule""")
        kinds = {n.kind for n in r.nodes}
        assert "covergroup" in kinds

    def test_coverpoint(self, parser):
        r = extract(parser, """
module m(input clk, input logic [7:0] data);
  covergroup cg @(posedge clk);
    data_cp: coverpoint data;
  endgroup
endmodule""")
        kinds = {n.kind for n in r.nodes}
        assert "coverpoint" in kinds

    def test_cross(self, parser):
        r = extract(parser, """
module m(input clk);
  covergroup cg @(posedge clk);
    cp_a: coverpoint a;
    cp_b: coverpoint b;
    axb: cross cp_a, cp_b;
  endgroup
endmodule""")
        kinds = {n.kind for n in r.nodes}
        assert "cross" in kinds


class TestTLMAndVirtualIf:
    """TLM port detection and virtual interface bindings."""

    def test_tlminitf_detected(self, parser):
        r = extract(parser, """
package p;
  class my_monitor;
    uvm_analysis_port #(item) ap;
  endclass
endpackage""")
        tlm_nodes = {n.kind for n in r.nodes if n.kind == "tlminitf"}
        assert len(tlm_nodes) > 0

    def test_virtual_interface_reference(self, parser):
        r = extract(parser, """
package p;
  class my_driver extends uvm_driver;
    virtual my_if vif;
  endclass
endpackage""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("REFERENCES", "my_if") in refs


class TestEdges:
    """Edge creation validation."""

    def test_contains_edges(self, parser):
        r = extract(parser, "module top; endmodule")
        contains = [e for e in r.edges if e.kind == "CONTAINS"]
        assert len(contains) >= 1  # file → module

    def test_instantiation_edge(self, parser):
        r = extract(parser, """
module top; sub u_sub(); endmodule""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("INSTANTIATES", "sub") in refs

    def test_error_handling_on_parse_failure(self, parser):
        """Malformed SV should not crash; errors stored but nodes may be empty."""
        r = extract(parser, "@@@ not valid SV @@@")
        # Should not throw; errors may be present
        assert isinstance(r.errors, list)
