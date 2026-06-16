# 阶段 5: MCP Server

> 时间: 2-3 天 | 依赖: 阶段 3 (存储), 阶段 4 (搜索/解析) | 优先级: P1

## 目标

实现 Model Context Protocol (MCP) server，让 AI 工具（Claude Code、Cursor、Codex 等）能够查询 XCodeGraph 索引。

## 交付物

### 5.1 MCP Server (`mcp/server.py`)

对标 JS 版 `src/mcp/`：

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

class XCodeGraphMCPServer:
    def __init__(self, codegraph: CodeGraph):
        self.cg = codegraph
        self.server = Server("xcodegraph")

    def register_tools(self) -> None:
        """注册 MCP 工具"""

    async def serve(self, transport: str = 'stdio') -> None:
        """启动 MCP server"""
```

### 5.2 MCP 工具清单

对标 JS 版的工具设计：

| 工具名 | 功能 | 输入 | 输出 |
|---|---|---|---|
| `xcodegraph_search` | 搜索节点 | `query: str`, `kind: str?` | 匹配的节点列表 |
| `xcodegraph_node` | 查看节点详情 | `name: str` 或 `id: str` | 节点信息 + caller/callee 链路 |
| `xcodegraph_explore` | 探索代码流 | `symbols: list[str]` | 调用路径 + 限定名消歧 |
| `xcodegraph_callers` | 查找调用者 | `name: str` | 所有调用该节点的节点列表 |
| `xcodegraph_callees` | 查找被调用者 | `name: str` | 该节点调用的所有节点列表 |
| `xcodegraph_instantiation` | 查找实例化 | `name: str` | 模块/接口的所有实例 |
| `xcodegraph_hierarchy` | 层级结构 | `name: str` | class 继承链，module 包含树 |

### 5.3 Server 指令 (`mcp/instructions.py`)

对标 JS 版 `src/mcp/server-instructions.ts`：

```python
SERVER_INSTRUCTIONS = """
## XCodeGraph — SystemVerilog Code Intelligence

XCodeGraph provides structural understanding of SystemVerilog codebases.
Use these tools to answer questions about RTL module hierarchy, signal flow,
parameter dependencies, and class inheritance.

### Best practices:
- Start with `xcodegraph_search` for keyword-based queries
- Use `xcodegraph_explore` with specific symbol names for flow tracing
- Use `xcodegraph_node` when you need full context about a symbol
- For "how does X reach Y" questions, prefer explore over multiple callers/callees calls

### Tool reference:
...
"""
```

### 5.4 安装器 (`installer.py`)

对标 JS 版 `src/installer/`：

```python
class MCPInstaller:
    """为各 AI 工具配置 MCP server 连接"""

    def install_claude(self) -> None:
        """写入 ~/.claude/mcp.json"""
        ...

    def install_cursor(self) -> None:
        """写入 .cursor/mcp.json"""
        ...

    def uninstall(self) -> None:
        """移除 MCP 配置"""
        ...
```

### 5.5 MCP JSON 配置模板

```json
{
  "mcpServers": {
    "xcodegraph": {
      "command": "xcodegraph",
      "args": ["serve", "--mcp"],
      "env": {}
    }
  }
}
```

## CLI 子命令

```bash
# 启动 MCP server (stdio 传输)
xcodegraph serve --mcp

# 安装到 Claude Code
xcodegraph install claude

# 安装到 Cursor
xcodegraph install cursor

# 卸载
xcodegraph uninstall

# 查看状态
xcodegraph status
```

## 验证标准

```bash
# MCP 工具单元测试
pytest tests/test_mcp.py -v

# MCP 安装器参数化测试 (对标 JS 版 installer-targets.test.ts)
pytest tests/test_installer.py -v

# 端到端: 启动 server → 调用工具 → 验证返回
pytest tests/test_mcp_integration.py -v
```
