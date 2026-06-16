"""TDD: MCP server — thin adapter over core API."""

import pytest
from xcodegraph.mcp_server import XCodeGraphMCPServer
from xcodegraph.core.indexer import Indexer


@pytest.fixture
def mcp_server(tmp_path):
    """Create an indexed project and return an MCP server instance."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()

    (rtl / "top.sv").write_text("""\
module top(input clk);
  sub u_sub(.clk(clk));
endmodule
""")

    (rtl / "sub.sv").write_text("""\
module sub(input clk);
endmodule
""")

    (rtl / "filelist.f").write_text("top.sv\nsub.sv")

    db_path = str(tmp_path / "index.sqlite")
    idx = Indexer(db_path)
    idx.index_filelist(str(rtl / "filelist.f"))
    idx.close()
    return XCodeGraphMCPServer(db_path)


class TestMCPStatus:
    """TDD: status tool."""

    def test_status_returns_ok(self, mcp_server):
        result = mcp_server.tool_status()
        assert result["status"] == "ok"
        assert result["node_count"] > 0
        assert result["edge_count"] > 0


class TestMCPSearch:
    """TDD: search tool."""

    def test_search_finds_module(self, mcp_server):
        result = mcp_server.tool_search("top")
        assert result["status"] == "ok"
        assert result["count"] >= 1
        names = [r["name"] for r in result["results"]]
        assert "top" in names

    def test_search_with_kind_filter(self, mcp_server):
        result = mcp_server.tool_search("sub", kind="module")
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestMCPNode:
    """TDD: node detail tool."""

    def test_node_returns_details(self, mcp_server):
        result = mcp_server.tool_node("top")
        assert result["status"] == "ok"
        assert result["node"]["kind"] == "module"
        assert result["node"]["name"] == "top"
        assert "file" in result["node"]

    def test_node_not_found(self, mcp_server):
        result = mcp_server.tool_node("nonexistent")
        assert result["status"] == "not_found"


class TestMCPDefinition:
    """TDD: definition jump tool."""

    def test_definition_returns_location(self, mcp_server):
        result = mcp_server.tool_definition("top")
        assert result["status"] == "ok"
        assert result["name"] == "top"
        assert "line" in result


class TestMCPFileSymbols:
    """TDD: file symbols tool."""

    def test_file_symbols_lists_all(self, mcp_server):
        result = mcp_server.tool_definition("top")
        result = mcp_server.tool_file_symbols(result["file"])
        assert result["status"] == "ok"
        assert result["count"] >= 1


class TestMCPHierarchy:
    """TDD: hierarchy tool."""

    def test_hierarchy_from_top(self, mcp_server):
        result = mcp_server.tool_hierarchy("top")
        assert result["status"] == "ok"
        names = [h["name"] for h in result["hierarchy"]]
        assert "top" in names
        assert "sub" in names

    def test_hierarchy_depth(self, mcp_server):
        result = mcp_server.tool_hierarchy("top", depth=0)
        assert len(result["hierarchy"]) == 1


class TestMCPInstantiatedBy:
    """TDD: instantiated-by tool."""

    def test_sub_instantiated_by_top(self, mcp_server):
        result = mcp_server.tool_instantiated_by("sub")
        assert result["status"] == "ok"
        names = [r["name"] for r in result["instantiated_by"]]
        assert "top" in names


class TestMCPEdgeTools:
    """TDD: imports/includes/extends edge query tools."""

    def test_imports_smoke(self, mcp_server):
        result = mcp_server.tool_imports("top")
        assert result["status"] == "ok"
        assert result["kind"] == "IMPORTS"

    def test_includes_smoke(self, mcp_server):
        result = mcp_server.tool_includes("top")
        assert result["status"] == "ok"

    def test_extends_smoke(self, mcp_server):
        result = mcp_server.tool_extends("top")
        assert result["status"] == "ok"


class TestMCPNotFound:
    """TDD: error handling for missing index."""

    def test_missing_db_raises(self):
        with pytest.raises(FileNotFoundError):
            XCodeGraphMCPServer("/tmp/nonexistent_db.sqlite")
