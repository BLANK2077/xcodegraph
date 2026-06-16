"""MCP stdio CLI test — tests the MCP server as a subprocess via stdio transport.

Uses mcp.client.stdio_client to launch `xcodegraph serve` and call all tools.
No browser required — pure CLI.
"""

import asyncio
import os
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from xcodegraph.core.indexer import Indexer


@pytest.fixture
def indexed_db(tmp_path):
    """Create an indexed project for MCP server testing."""
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.sv").write_text("module top(input clk); sub u_sub(.clk(clk)); endmodule\n")
    (rtl / "sub.sv").write_text("module sub(input clk); endmodule\n")
    (rtl / "filelist.f").write_text("top.sv\nsub.sv")
    db_path = str(tmp_path / "index.sqlite")
    idx = Indexer(db_path)
    idx.index_filelist(str(rtl / "filelist.f"))
    idx.close()
    return db_path


def _run_mcp_call(db_path: str, tool: str, args: dict) -> str:
    """Sync wrapper: launch MCP server, call one tool, return text result."""
    async def _call():
        env = {**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..")}
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "xcodegraph.cli", "serve", "--db", db_path],
            env=env,
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, args)
                return result.content[0].text
    return asyncio.run(_call())


class TestMCPStdioTools:
    """Test each MCP tool via stdio subprocess."""

    def test_list_all_tools(self, indexed_db):
        async def _list():
            env = {**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(__file__), "..")}
            server_params = StdioServerParameters(
                command="python", args=["-m", "xcodegraph.cli", "serve", "--db", indexed_db], env=env,
            )
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return [t.name for t in tools.tools]
        names = asyncio.run(_list())
        assert "xcodegraph_search" in names
        assert "xcodegraph_status" in names
        assert "xcodegraph_hierarchy" in names

    def test_status(self, indexed_db):
        text = _run_mcp_call(indexed_db, "xcodegraph_status", {})
        assert "ok" in text.lower()

    def test_search(self, indexed_db):
        text = _run_mcp_call(indexed_db, "xcodegraph_search", {"query": "top"})
        assert "top" in text

    def test_node(self, indexed_db):
        text = _run_mcp_call(indexed_db, "xcodegraph_node", {"name": "top"})
        assert "ok" in text.lower() or "module" in text.lower()

    def test_definition(self, indexed_db):
        text = _run_mcp_call(indexed_db, "xcodegraph_definition", {"name": "top"})
        assert "top" in text

    def test_hierarchy(self, indexed_db):
        text = _run_mcp_call(indexed_db, "xcodegraph_hierarchy", {"name": "top"})
        assert "sub" in text

    def test_instantiated_by(self, indexed_db):
        text = _run_mcp_call(indexed_db, "xcodegraph_instantiated_by", {"name": "sub"})
        assert "top" in text

    def test_edge_queries(self, indexed_db):
        for tool in ["xcodegraph_imports", "xcodegraph_includes", "xcodegraph_extends"]:
            text = _run_mcp_call(indexed_db, tool, {"name": "top"})
            assert text
