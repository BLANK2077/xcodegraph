# XCodeGraph

Python 版 SystemVerilog 代码知识图谱。

基于 `py-tree-sitter` 实现，为芯片验证工程师提供本地优先的 SV 代码索引、搜索和 AI 上下文构建能力。

## 快速开始

```
pip install xcodegraph
xcodegraph index my_project/ --filelist my_project/rtl.f
xcodegraph search ADDR_WIDTH
```

## 文档

- [项目总览与架构](doc/00-overview.md)
- [阶段 1: 核心提取器](doc/01-core-extraction.md)
- [阶段 2: Filelist 解析器](doc/02-filelist-parser.md)
- [阶段 3: 存储与搜索](doc/03-storage-search.md)
- [阶段 4: 引用解析与文件监听](doc/04-resolution-watcher.md)
- [阶段 5: MCP Server](doc/05-mcp-server.md)
- [阶段 6: CLI、测试与发布](doc/06-cli-test-release.md)
- [可行性报告](doc/py-codegraph-sv-feasibility.md)
