"""TDD: MCP tools return Markdown strings (not JSON dicts)."""

import pytest
from xcodegraph.mcp_server import create_server
from xcodegraph.core.indexer import Indexer


@pytest.fixture
def mcp_server(tmp_path):
    """Create an indexed project and return a FastMCP server instance."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.sv").write_text("module top(input clk);\n  sub u_sub(.clk(clk));\nendmodule\n")
    (rtl / "sub.sv").write_text("module sub(input clk);\nendmodule\n")
    (rtl / "filelist.f").write_text("top.sv\nsub.sv")
    db_path = str(tmp_path / "index.sqlite")
    idx = Indexer(db_path)
    idx.index_filelist(str(rtl / "filelist.f"))
    idx.close()
    return create_server(db_path)


def _call(mcp, tool, args=None):
    """Sync wrapper for async FastMCP.call_tool. Returns text string."""
    import asyncio
    result, extra = asyncio.run(mcp.call_tool(tool, args or {}))
    return result[0].text


class TestMCPStatus:
    def test_status_returns_md(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_status")
        assert "## XCodeGraph Status" in text
        assert "Files" in text
        assert "Nodes" in text


class TestMCPSearch:
    def test_search_returns_table(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_search", {"query": "top"})
        assert "## Search" in text
        assert "top" in text
        # Should be MD table, not JSON
        assert "|" in text

    def test_search_not_found(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_search", {"query": "zzz_nonexistent"})
        assert "No results" in text


class TestMCPNode:
    def test_node_returns_details(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_node", {"name": "top"})
        assert "## top (module)" in text
        assert "Location" in text
        # Should NOT contain DB internal fields
        assert '"id"' not in text

    def test_node_not_found(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_node", {"name": "nonexistent"})
        assert "Not found" in text


class TestMCPDefinition:
    def test_definition_returns_location(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_definition", {"name": "top"})
        assert "top" in text
        assert "Location" in text


class TestMCPFileSymbols:
    def test_file_symbols(self, mcp_server):
        # Get the file path from definition
        def_text = _call(mcp_server, "xcodegraph_definition", {"name": "top"})
        import re
        m = re.search(r"Location:\*\* (\S+):", def_text)
        if m:
            text = _call(mcp_server, "xcodegraph_file_symbols", {"file_path": m.group(1)})
            assert "Symbols" in text


class TestMCPHierarchy:
    def test_hierarchy_returns_tree(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_hierarchy", {"name": "top"})
        assert "Hierarchy" in text
        assert "sub" in text


class TestMCPInstantiatedBy:
    def test_inst_by(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_instantiated_by", {"name": "sub"})
        assert "top" in text


class TestMCPEdgeTools:
    def test_imports(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_imports", {"name": "top"})
        assert isinstance(text, str)
        assert len(text) > 10

    def test_includes(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_includes", {"name": "top"})
        assert isinstance(text, str)

    def test_extends(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_extends", {"name": "top"})
        assert isinstance(text, str)


class TestMCPReindex:
    def test_reindex_existing(self, mcp_server, tmp_path):
        text = _call(mcp_server, "xcodegraph_reindex_file",
                     {"file_path": str(tmp_path / "rtl" / "top.sv")})
        assert "Reindex" in text

    def test_reindex_missing(self, mcp_server):
        text = _call(mcp_server, "xcodegraph_reindex_file",
                     {"file_path": "/nonexistent.sv"})
        assert "not found" in text.lower()


class TestMCPNotFound:
    def test_missing_db_raises(self):
        with pytest.raises(FileNotFoundError):
            create_server("/tmp/nonexistent_db.sqlite")
