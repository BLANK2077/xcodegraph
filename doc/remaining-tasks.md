# XCodeGraph 未完成目标清单

> 日期: 2026-06-16 | 状态: 86 tests green, 14 integration checks pass

## 已完成

| Phase | 内容 | 状态 |
|---|---|---|
| 1 | 核心索引 (filelist + SQLite + tree-sitter + 30+ AST types) | ✅ |
| 2 | 实例化层次 (hierarchy + instantiated-by + lightweight resolve) | ✅ |
| 3 | MCP Server (FastMCP SDK, 12 tools, serve --mcp) | ✅ |
| 4 | Reindex + stale 检测 (sha256 track + reindex_file) | ✅ |
| 5 | 验证增强 (UVM class + common block hook + include track) | ✅ |
| 6 | AI Summary (generate_summary) | ✅ |
| — | CLI 补齐 (hierarchy/instantiated-by/imports/includes/extends) | ✅ |
| — | CLI reindex + summary 命令 | ✅ |
| — | FTS5 全文搜索 | ✅ |
| — | Git HEAD stale 检测 | ✅ |
| — | 跨文件 Reference Resolver | ✅ |
| — | MCP stdio CLI 测试 (8 tests) | ✅ |

> **全部完成 — 96 tests green**

---

## 🔴 P0 — 影响功能闭环

### 1. CLI 补齐 5 个查询命令

| storage 方法 | MCP tool | CLI |
|---|---|---|
| `get_hierarchy` | ✅ | ❌ |
| `get_instantiated_by` | ✅ | ❌ |
| `get_edges_by_kind("IMPORTS")` | ✅ | ❌ |
| `get_edges_by_kind("INCLUDES")` | ✅ | ❌ |
| `get_edges_by_kind("EXTENDS")` | ✅ | ❌ |

**工作量**: ~0.5h，在 `cli.py` 中新增 5 个 `sub.add_parser` + `cmd_*` 函数。

### 2. CLI `reindex` 命令

storage + indexer 已有 `index_filelist`/`index_directory`/`upsert_file` 能力，CLI 未暴露 reindex 入口。

**工作量**: ~0.5h，新增 `xcodegraph reindex --file <path>` / `--full`。

### 3. FTS5 全文搜索

`schema.sql` 中定义了 FTS5 虚拟表，但 `search_nodes()` 实际使用 `name LIKE '%query%'`。

```sql
-- schema.sql 中已定义但未启用
CREATE VIRTUAL TABLE nodes_fts USING fts5(name, full_name, signature, ...);
```

**工作量**: ~2h
- 在 `search_nodes` 中接入 FTS5 MATCH 查询
- 添加触发器保持 FTS 索引同步
- 保留 LIKE 作为 fallback

---

## 🟡 P1 — 增强差异化价值

### 4. Git HEAD stale 检测

`meta` 表已有 `git_head`/`git_branch` 字段，但 `status` 命令不读取 `.git/HEAD` 进行比较。

**目标**: `xcodegraph status` 输出 `{"status": "stale", "indexed_head": "abc", "current_head": "def"}`

**工作量**: ~2h
- 新增 `core/status.py` 中的 git HEAD 读取逻辑
- 索引时自动记录 git HEAD 到 meta 表
- `status` 命令比较并报告 stale

### 5. Common block hook 集成

`core/common_block.py` 已实现 `CommonBlockHook` 类（正则匹配 + JSON 配置），但未接入索引管道。

**目标**: 索引时自动匹配 common block 并附加 summary 到响应中。

**工作量**: ~1h
- 在 `indexer.py` 中加载 common block 配置
- MCP 工具返回时附加 `common_block` 字段

### 6. 跨文件 Reference Resolver

当前仅 lightweight resolve —— 查询时通过 `unresolved_refs` 表做 name 匹配。没有批处理创建持久 `edges` 的机制。

**现状**: 36 unresolved refs (UART) 中 UVM 基类已在索引内但未解析为边。

**目标**: 批处理 `unresolved_refs` → 匹配 `nodes` 表 → 创建 `edges`。

**工作量**: ~4h
- 新增 `core/resolver.py`
- 在 indexer 中调用 resolver
- 支持 import/extends/instantiates 三种跨文件解析

### 7. MCP stdio CLI 测试

官方 MCP SDK 提供 `mcp.client.stdio` 模块，可以在纯 CLI 环境下通过 stdio 子进程自动化测试 MCP server，无需浏览器。

**安装**:
```bash
pip install "mcp[cli]"
```

**测试方案** — 使用 `mcp.client.stdio.stdio_client` 编写自动化 test harness:

```python
# tests/test_mcp_cli.py 的模式
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def test_mcp_server():
    server_params = StdioServerParameters(
        command="python", args=["-m", "xcodegraph.cli", "serve", "--db", "test.sqlite"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List all tools
            tools = await session.list_tools()
            assert len(tools.tools) == 12

            # Call each tool and validate response
            result = await session.call_tool("xcodegraph_status", {})
            assert result.content[0].text  # has output
```

**运行**:
```bash
pytest tests/test_mcp_cli.py -v   # 纯 CLI，无浏览器
```

**目标**: 编写 `tests/test_mcp_cli.py`，通过 stdio subprocess 启动 `xcodegraph serve`，用 `mcp.client` 调用全部 12 个 tool 并验证响应格式。

**工作量**: ~2h

### 8. `` `include `` 文件独立索引

`include "defs.svh"` 被追踪为 `INCLUDES` unresolved ref，但头文件不作为独立编译单元索引。例如 `uart_state_e` typedef 在 `include/uart_defs.svh` 中定义，但未出现在节点表中。

**工作量**: ~2h
- filelist parser 支持 `+incdir+` 路径下的 `.svh` 文件索引
- 或 indexer 提供 `--include-dirs` 选项

---

## 🟢 P2 — 锦上添花

### 9. MCP tool description 完善

当前 FastMCP 工具有基础描述，可增强以提升 AI Agent 的可发现性。

**工作量**: ~0.5h

### 10. `generate_summary` 集成到 CLI/MCP

`core/summary.py` 已实现但无 CLI 子命令和 MCP tool。

**工作量**: ~0.5h

---

## 统计

| 优先级 | 数量 | 预估工时 |
|---|---|---|
| P0 | 3 | ~3h |
| P1 | 5 | ~11h |
| P2 | 2 | ~1h |
| **合计** | **10** | **~15h** |
