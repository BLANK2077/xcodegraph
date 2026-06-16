# 项目总览与架构

## 目标

构建一个 Python 版的 SystemVerilog 代码知识图谱 (CodeGraph)，功能对标 JS 版 `colbymchenry/codegraph`，但仅针对 SystemVerilog 语言，并增加 VCS-style filelist 支持。

## 为什么 Python

- 芯片验证工程师的日常工作以 Python 为主（UVM 仿真脚本、cocotb、回归自动化）
- 无需安装 Node.js 工具链
- `pip install` 一键部署
- 易于集成到现有验证流程

## 架构总览

```
                    ┌──────────────────┐
                    │   CLI / MCP Server │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Filelist     │  │  Extraction     │  │  FileWatcher    │
│  Parser       │  │  Pipeline       │  │  (watchdog)     │
│               │  │                 │  │                 │
│ -f 递归展开   │  │ TreeSitterCore  │  │ 增量自动重索引  │
│ +incdir+      │  │ SVVisitor       │  │                 │
│ +define+      │  │                 │  │                 │
│ `ifdef 条件栈 │  │ py-tree-sitter  │  │                 │
└───────┬───────┘  └───────┬─────────┘  └─────────────────┘
        │                  │
        └────────┬─────────┘
                 │
                 ▼
        ┌────────────────┐
        │  SQLite DB     │
        │                │
        │  nodes         │
        │  edges         │
        │  files         │
        │  unresolved_   │
        │  refs          │
        │  nodes_fts     │
        └───────┬────────┘
                │
                ▼
        ┌────────────────┐
        │  Reference     │
        │  Resolver      │
        │                │
        │  跨文件引用解析│
        │  import/extends│
        │  /instantiates │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  Search API    │
        │                │
        │  search_nodes  │
        │  get_callers   │
        │  get_callees   │
        └────────────────┘
```

## 模块依赖关系

```
models.py          ← 数据类定义 (Node, Edge, ExtractionResult)
helpers.py         ← 工具函数 (generateNodeId, getNodeText 等)
extraction/
  context.py       ← ExtractionContext 状态管理
  core.py          ← TreeSitterCore 提取管道
  visitor.py       ← SVVisitor — visit_node 主体逻辑
filelist/
  parser.py        ← FilelistParser — 递归展开 + 条件编译
  preprocess.py    ← VerilogPreprocessor (借鉴自 VeribleVCSFilelist)
storage/
  schema.py        ← SQLite schema DDL
  queries.py       ← CRUD 操作封装
  fts.py           ← FTS5 全文搜索
resolution/
  resolver.py      ← 跨文件引用解析
watcher/
  watcher.py       ← 文件变更监听 + 增量索引
cli/
  main.py          ← 命令行入口
mcp/
  server.py        ← MCP server 实现
```

## 开发阶段

| 阶段 | 内容 | 预估时间 | 依赖 |
|---|---|---|---|
| 1 | 核心提取器 | 4-5 天 | — |
| 2 | Filelist 解析器 | 2-3 天 | — (可与阶段1并行) |
| 3 | 存储与搜索 | 2-3 天 | 阶段 1 |
| 4 | 引用解析 + 文件监听 | 3-4 天 | 阶段 1, 3 |
| 5 | MCP Server | 2-3 天 | 阶段 3, 4 |
| 6 | CLI、测试、发布 | 2-3 天 | 阶段 1-5 |

**总计**: 15-21 天（串行），可压缩至 11-16 天（阶段 1/2 并行）。

## 关键设计决策

1. **py-tree-sitter 而非 Verible**：tree-sitter 是成熟生态，Python 绑定完善，与 JS 版 CodeGraph 同架构
2. **SQLite 而非 pickle**：对标 JS 版 schema，支持增量更新和并发查询
3. **自建 Filelist 解析器**：无现成库，但语法简单，借鉴 VeribleVCSFilelist 的 preprocess.py
4. **仅支持 SystemVerilog**：不支持其他语言，大幅简化代码和测试

## 参考仓库

| 仓库 | 用途 |
|---|---|
| `colbymchenry/codegraph` | JS 版架构参考，schema 对标 |
| `tree-sitter/py-tree-sitter` | 核心解析依赖 |
| `ColsonZhang/VeribleVCSFilelist` | preprocess.py 宏处理逻辑参考 |
| `sgherbst/pysvinst` | SV 结构提取参考 |
