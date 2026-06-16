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
