"""TDD: ClassName.method / ClassName.field 精确调用点追踪."""

import pytest
from xcodegraph.core.parser import SVParser


@pytest.fixture(scope="module")
def parser():
    return SVParser()


def extract(parser, source):
    return parser.extract("test.sv", source)


class TestVarTypeMapping:
    """_data_decl 建立 var→type 映射."""

    def test_class_type_variable_mapped(self, parser):
        r = extract(parser, """
class my_env extends uvm_env;
  my_agent u_agent;
endclass
""")
        # 通过检查 unresolved_refs 验证映射生效：my_agent 类型已记录
        ref_names = {r.name for r in r.unresolved_refs}
        assert "my_agent" in ref_names

    def test_virtual_if_variable_mapped(self, parser):
        r = extract(parser, """
class my_driver extends uvm_driver;
  virtual my_if vif;
endclass
""")
        ref_names = {r.name for r in r.unresolved_refs}
        assert "my_if" in ref_names


class TestQualifiedMethodCalls:
    """method_call 的 receiver 解析为 ClassName.method."""

    def test_drv_run_phase_resolved(self, parser):
        r = extract(parser, """
class my_env extends uvm_env;
  uart_driver drv;
  function void build_phase(uvm_phase phase);
    drv.run_phase(phase);
  endfunction
endclass
""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("CALLS", "uart_driver.run_phase") in refs

    def test_tlm_port_write_resolved(self, parser):
        r = extract(parser, """
class my_monitor extends uvm_monitor;
  uvm_analysis_port #(item) ap;
  task run_phase(uvm_phase phase);
    ap.write(item);
  endtask
endclass
""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("CALLS", "uvm_analysis_port.write") in refs

    def test_tf_call_without_receiver_not_affected(self, parser):
        """普通的 tf_call (helper(x)) 不应被影响."""
        r = extract(parser, """
module m;
  function int calc(int x);
    return helper(x);
  endfunction
endmodule
""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("CALLS", "helper") in refs
        # 不应该有带点的 qualified name
        assert not any("." in name for _, name in refs)


class TestQualifiedFieldAccess:
    """hierarchical_identifier 的 field 访问解析为 TypeName.field."""

    def test_pkt_lcr_resolved_to_type(self, parser):
        r = extract(parser, """
class uart_driver extends uvm_driver;
  uart_seq_item pkt;
  task run_phase();
    pkt.lcr = 8'h00;
  endtask
endclass
""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("REFERENCES", "uart_seq_item.lcr") in refs

    def test_vif_field_resolved(self, parser):
        r = extract(parser, """
class my_driver extends uvm_driver;
  virtual my_if vif;
  task run_phase();
    vif.drv_cb.data <= req.data;
  endtask
endclass
""")
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("REFERENCES", "my_if.drv_cb") in refs or ("REFERENCES", "my_if.drv_cb.data") in refs

    def test_simple_identifier_not_qualified(self, parser):
        """普通变量引用不应用映射."""
        r = extract(parser, """
module m;
  int count;
  always_ff @(posedge clk) count <= count + 1;
endmodule
""")
        # count 是 int 类型，不应产生 "int.count" 这样的 REFERENCES
        refs = {(r.kind, r.name) for r in r.unresolved_refs}
        assert ("REFERENCES", "int.count") not in refs
