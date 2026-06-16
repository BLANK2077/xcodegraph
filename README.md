# XCodeGraph

Python 版 SystemVerilog 代码知识图谱。

基于 `py-tree-sitter` 实现，为芯片验证工程师提供本地优先的 SV 代码索引、搜索和 AI 上下文构建能力。

## 为什么需要 XCodeGraph

原版 [CodeGraph](https://github.com/colbymchenry/codegraph) 基于 Node.js/TypeScript 构建，功能强大但部署在 IC 服务器上有诸多现实困难：

- **Node.js 版本不匹配** — IC 服务器通常运行 RHEL/CentOS 7/8，系统包管理器提供的 Node.js 版本过旧，而 CodeGraph 要求 Node ≥ 18
- **内网隔离无法联网** — 绝大多数 IC 服务器处于封闭网络环境，`npm install` 无法拉取依赖，离线安装 Node 工具链繁琐
- **WASM 运行时依赖** — CodeGraph 依赖 `web-tree-sitter` 的 WASM 加载，在某些旧内核（如 Linux 4.18）上可能存在兼容性问题
- **多语言包袱过重** — CodeGraph 支持 20+ 编程语言，但对于芯片验证工程师只需要 SystemVerilog

XCodeGraph 的设计目标：

```
pip install xcodegraph              # 一个命令，纯 Python wheel，无网络依赖
xcodegraph index my_project/        # 索引 RTL 代码
xcodegraph search ADDR_WIDTH        # 搜索参数/信号/模块
```

- **最小依赖** — 仅需 `tree-sitter` + `tree-sitter-systemverilog` + `watchdog`，均为预编译 wheel
- **Python only** — 芯片验证工程师的默认语言，无需安装 Node.js
- **离线友好** — 下载 wheel 文件后用 `pip install --no-index *.whl` 即可部署
- **仅支持 SystemVerilog** — 不做多语言，专注 SV/RTL 代码结构，代码量控制在 ~2000 行

## 架构来源

XCodeGraph 的总体架构（提取器 → 存储 → 引用解析 → 搜索 → MCP Server 的分层设计）学习自原版 [CodeGraph](https://github.com/colbymchenry/codegraph)，一个优秀的本地优先代码知识图谱项目。我们借鉴了它的：

- `NodeKind`/`EdgeKind` 类型体系
- `ExtractionContext` 作用域栈 + `createNode`/`addUnresolvedReference` 的提取上下文模式
- `LanguageExtractor` 接口 + `visitNode` 钩子的自定义 visitor 设计
- SQLite FTS5 存储 schema 和增量索引策略
- MCP Server 工具设计（`search` / `explore` / `node` 等）

在此基础上，XCodeGraph 针对芯片验证场景做了适配：用 Python 替代 Node.js、增加 VCS filelist 支持、移除多语言泛化逻辑、使用 `py-tree-sitter` 替代 `web-tree-sitter`。

## 快速开始

```
pip install xcodegraph
xcodegraph index my_project/ --filelist my_project/rtl.f
xcodegraph search ADDR_WIDTH
```

## AI 集成 (MCP Server)

XCodeGraph 提供 MCP Server，可接入 Claude Code、Codex CLI 等 AI 工具。

### 启动 MCP Server

```bash
# stdio 传输 (AI 工具直接调用)
xcodegraph serve --db .xcodegraph/index.sqlite
```

### 配置 Claude Code

在**项目根目录**创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "xcodegraph": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "xcodegraph.cli", "serve", "--db", ".xcodegraph/index.sqlite"]
    }
  }
}
```

或通过 Claude Code CLI 添加：

```bash
claude mcp add --scope project xcodegraph -- python -m xcodegraph.cli serve --db .xcodegraph/index.sqlite
```

**全局配置** (所有项目可用): 编辑 `~/.claude.json`，插入相同的 `mcpServers` 块。

### 配置 Codex CLI

编辑 `~/.codex/config.toml`：

```toml
[mcp_servers.xcodegraph]
command = "python"
args = ["-m", "xcodegraph.cli", "serve", "--db", "/absolute/path/to/.xcodegraph/index.sqlite"]
```

> **注意**: TOML 格式中路径必须使用绝对路径。Codex 不支持 `~` 展开，请使用完整路径如 `/home/user/project/.xcodegraph/index.sqlite`。

### 验证连接

在 Claude Code 中输入 `/mcp` 查看已连接的 MCP server，或直接调用：

```
xcodegraph_status()
```

如果返回索引统计信息，说明连接成功。

### MCP 工具清单

| 工具 | 用途 |
|------|------|
| `xcodegraph_search` | 搜索符号 |
| `xcodegraph_node` | 符号详情 + 关系 |
| `xcodegraph_definition` | 跳转定义 |
| `xcodegraph_file_symbols` | 文件符号列表 |
| `xcodegraph_hierarchy` | 模块层次树 |
| `xcodegraph_instantiated_by` | 反向实例化 |
| `xcodegraph_extends` | 类继承链 |
| `xcodegraph_imports` | Package 导入 |
| `xcodegraph_includes` | `` `include `` 追踪 |
| `xcodegraph_status` | 索引状态 |
| `xcodegraph_reindex_file` | 单文件重索引 |

详见 [AI 使用指南](skill/xcodegraph-sv-skill.md)。

## 文档

- [AI 使用指南](skill/xcodegraph-sv-skill.md) ⭐
- [OpenTitan Benchmark 报告](doc/opentitan-results.md)
- [OpenTitan 实时输出](doc/opentitan-live-output.md)
- [修正开发计划](doc/01-revised-plan.md)
- [可行性报告](doc/py-codegraph-sv-feasibility.md)
