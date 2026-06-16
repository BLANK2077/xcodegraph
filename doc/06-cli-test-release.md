# 阶段 6: CLI、测试与发布

> 时间: 2-3 天 | 依赖: 阶段 1-5 | 优先级: P1

## 目标

实现命令行入口、完整测试覆盖、PyPI 发布。

## 交付物

### 6.1 CLI (`cli/main.py`)

```bash
# 初始化项目
xcodegraph init [--path /path/to/project]

# 索引文件/目录/filelist
xcodegraph index <path> [--filelist <filelist.f>] [--defines +define+MACRO=VAL]

# 搜索
xcodegraph search <query> [--kind module|interface|parameter|...]

# 查看节点详情
xcodegraph node <name> [--kind module]

# 启动 MCP server
xcodegraph serve --mcp

# 启动文件监听
xcodegraph watch [--path /path/to/project]

# 状态查看
xcodegraph status

# 安装/卸载 MCP
xcodegraph install <agent>
xcodegraph uninstall

# 清理索引数据
xcodegraph clean [--filelist]
```

### 6.2 CLI 实现

```python
# cli/main.py
import argparse
import sys
from xcodegraph import CodeGraph

def main():
    parser = argparse.ArgumentParser(
        prog='xcodegraph',
        description='Python SystemVerilog Code Intelligence'
    )
    subparsers = parser.add_subparsers(dest='command')

    # init
    p_init = subparsers.add_parser('init')
    p_init.add_argument('--path', default='.')

    # index
    p_index = subparsers.add_parser('index')
    p_index.add_argument('path')
    p_index.add_argument('--filelist', '-f', help='VCS .f filelist')
    p_index.add_argument('--defines', '-d', help='+define+MACRO=VAL')

    # search
    p_search = subparsers.add_parser('search')
    p_search.add_argument('query')
    p_search.add_argument('--kind', '-k')
    p_search.add_argument('--format', choices=['text', 'json'], default='text')

    # node
    p_node = subparsers.add_parser('node')
    p_node.add_argument('name')
    p_node.add_argument('--kind', '-k')

    # serve
    p_serve = subparsers.add_parser('serve')
    p_serve.add_argument('--mcp', action='store_true')
    p_serve.add_argument('--port', type=int, default=0)

    # watch
    p_watch = subparsers.add_parser('watch')
    p_watch.add_argument('--path', default='.')

    # install / uninstall
    p_install = subparsers.add_parser('install')
    p_install.add_argument('agent', choices=['claude', 'cursor', 'codex'])

    p_uninstall = subparsers.add_parser('uninstall')

    # status / clean
    subparsers.add_parser('status')
    subparsers.add_parser('clean')

    args = parser.parse_args()
    dispatch(args)

def dispatch(args):
    if args.command == 'init':
        cg = CodeGraph.init(args.path)
        print(f"Initialized XCodeGraph at {args.path}/.xcodegraph")
    elif args.command == 'index':
        ...
```

### 6.3 测试体系

对标 JS 版测试架构：

```
tests/
├── conftest.py              # 共享 fixtures
│   ├── parser fixture       # 预初始化的 Parser + Language
│   ├── tmp_project fixture  # 临时项目目录 + SQLite DB
│   └── filelist fixture     # 临时 .f + .sv 文件树
├── test_extraction.py       # 15 种 SV AST 节点类型
├── test_filelist.py         # filelist 解析参数化测试
├── test_storage.py          # SQLite CRUD + 事务
├── test_fts.py              # FTS5 全文搜索
├── test_resolution.py       # import/extends/instantiates 跨文件
├── test_watcher.py          # 文件变更监听
├── test_mcp.py              # MCP 工具
├── test_installer.py        # MCP 安装器参数化
├── test_integration.py      # 端到端管道
└── test_benchmark.py        # 真实项目质量评估
```

#### 测试模式对标

| CodeGraph (JS) 模式 | Python 版 | 示例 |
|---|---|---|
| `describe('SV Extraction')` + `it(...)` | `class TestSVExtraction` + `def test_*` | `test_extraction.py` |
| `for target of ALL_TARGETS` 参数化 | `@pytest.mark.parametrize` | `test_filelist.py` |
| `mkdtempSync` + `afterEach` 清理 | `tmp_path` fixture (自动清理) | 所有文件系统测试 |
| 真实 SQLite (无 mock) | `sqlite3` + `:memory:` 或 `tmp_path` | `test_storage.py` |
| Evaluation runner (独立 `tsx` 脚本) | `test_benchmark.py` + pytest-benchmark | `test_benchmark.py` |
| 无共享 helper 文件 | `conftest.py` 共享 fixtures | `conftest.py` |

#### 参数化测试示例 (filelist)

```python
FILECASES = [
    # (name, content_lines, expected_files)
    ("basic", ["top.sv", "sub.sv"], ["top.sv", "sub.sv"]),
    ("incdir", ["+incdir+/a", "top.sv"], ["top.sv"]),
    ("nested_f", ["-f sub.f"], ["a.sv", "b.sv"]),
    ("ifdef_true", ["+define+FPGA", "`ifdef FPGA", "fpga.sv", "`endif"], ["fpga.sv"]),
    ("ifdef_false", ["`ifdef ASIC", "asic.sv", "`endif"], []),
    ("nested_ifdef", ["+define+A", "`ifdef A", "`ifdef B", "b.sv", "`endif", "a.sv", "`endif"], ["a.sv"]),
]

@pytest.mark.parametrize("name,content,expected", FILECASES)
def test_filelist_expand(tmp_path, name, content, expected):
    f = tmp_path / f"{name}.f"
    f.write_text("\n".join(content))
    result = FilelistParser().parse(str(f))
    assert result.files == expected
```

### 6.4 PyPI 发布

```toml
# pyproject.toml
[project]
name = "xcodegraph"
version = "0.1.0"
description = "Python SystemVerilog Code Intelligence"
requires-python = ">=3.10"
dependencies = [
    "tree-sitter>=0.25",
    "tree-sitter-systemverilog>=0.3",
    "watchdog>=4.0",
]

[project.scripts]
xcodegraph = "xcodegraph.cli.main:main"

[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"
```

```bash
# 构建
python -m build

# 发布到 PyPI
twine upload dist/*
```

## 验证标准

```bash
# 全部测试
pytest tests/ -v

# CLI 端到端
xcodegraph init --path /tmp/test_project
xcodegraph index /tmp/test_project/rtl
xcodegraph search ADDR_WIDTH
xcodegraph serve --mcp &
```
