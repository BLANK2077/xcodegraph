# Python 版 CodeGraph (SystemVerilog) 可行性报告

> 日期: 2026-06-16  
> 目标: 评估基于 `py-tree-sitter` 实现 SystemVerilog-only 的 Python 版 CodeGraph 的可行性  

---

## 1. 动机

当前 CodeGraph 基于 Node.js/TypeScript 实现，使用 `web-tree-sitter` 加载 WASM grammar 文件。验证工程师的日常工作环境以 Python 为主（UVM 仿真、脚本自动化），一个 Python 版本的 SV 代码索引工具可以：

- 零语言切换开销：直接在 Python 验证脚本中调用
- 更简单的部署：`pip install` 替代 Node.js 工具链
- 更易集成到现有验证工具链中

---

## 2. 核心依赖可用性

### 2.1 py-tree-sitter

| 项目 | 详情 |
|---|---|
| PyPI 包名 | `tree-sitter` |
| 版本 | 0.25.2 |
| Python 要求 | `>=3.10` |
| 实现方式 | C 扩展（非 ctypes/WASM），将 tree-sitter C 库静态链接 |
| 预编译平台 | Linux (manylinux), macOS, Windows — 全平台 |

**已验证安装**: `pip install tree-sitter` 成功。

### 2.2 tree-sitter-systemverilog

| 项目 | 详情 |
|---|---|
| PyPI 包名 | `tree-sitter-systemverilog` |
| 版本 | 0.3.1 |
| 实现方式 | 基于 grammar.js 编译的 C 扩展，通过 PyCapsule 暴露 `language()` |

**已验证安装**: `pip install tree-sitter-systemverilog` 成功。完整 AST 解析链路已验证通过（`source_file → module_declaration → module_ansi_header → simple_identifier`）。

### 2.3 依赖小结

```
pip install tree-sitter tree-sitter-systemverilog
```

两个纯 Python wheel，无外部系统依赖。**关键约束**：py-tree-sitter 不支持 WASM 加载，每种语言必须是编译好的 C 扩展 wheel。这对 SystemVerilog 来说已满足。

---

## 3. API 对比：TypeScript (web-tree-sitter) vs Python (py-tree-sitter)

### 3.1 核心对标

| 功能 | TS (web-tree-sitter) | Python (py-tree-sitter) | 兼容性 |
|---|---|---|---|
| 创建 Parser | `new Parser()` | `Parser(lang)` | ✅ 构造函数略有差异 |
| 设置语言 | `parser.setLanguage(lang)` | `parser.language = lang` 或构造函数 | ✅ |
| 解析代码 | `parser.parse(source)` | `parser.parse(bytes)` | ✅ Python 需传 bytes |
| 获取根节点 | `tree.rootNode` | `tree.root_node` | ✅ 命名风格差异 |
| 节点类型 | `node.type` | `node.type` | ✅ 完全一致 |
| 子节点 | `node.namedChildren` | `node.named_children` | ✅ 完全一致 |
| 按字段取值 | `node.childForFieldName('x')` | `node.child_by_field_name('x')` | ✅ 完全一致 |
| 获取文本 | `node.text` (需 source 参数) | `node.text` (属性，无需参数) | ✅ **Python 更简单** |
| 节点位置 | `node.startPosition.row` | `node.start_point.row` | ✅ |
| 树游标 | `node.walk()` | `node.walk()` | ✅ 完全一致 |
| Query | `new Query(lang, src)` | `Query(lang, src)` | ✅ 完全一致 |
| S-表达式 | 无 (需手写) | `str(node)` | ✅ Python 内置 |

### 3.2 Python 的优势

1. **`node.text` 是属性**，不需要传递 source 参数 — 树自动持有源代码引用
2. **`str(node)` 输出 S-表达式** — 调试更方便
3. **Query 谓词内置于 C 层** — `#eq?`、`#match?`、`#any-of?` 等无需 Python 回调
4. **无内存泄漏** — C 扩展由 Python GC 管理，不像 WASM 存在线性内存泄漏风险

### 3.3 需要注意的差异

| 差异点 | 影响 | 对策 |
|---|---|---|
| Language 通过 PyCapsule 而非 WASM 加载 | 加载方式完全不同 | 直接用 `Language(tssv.language())`，更简单 |
| source 必须是 `bytes`（不是 `str`） | 调用方需 encode | `source.encode('utf-8')` |
| `startPoint` 返回 `Point(row, col)` 而非 `{row, column}` | 属性名不同 | 写一个适配层统一命名 |
| 节点相等性使用 `ts_node_eq`（比较树指针） | 跨树的节点比较行为不同 | 对我们无影响 — 所有节点来自同一棵树 |

---

## 4. 核心架构映射

### 4.1 从 TypeScript 到 Python 的直译映射

```
TS CodeGraph                            Python CodeGraph (SV-only)
────────────────────────────────────    ────────────────────────────────
ExtractionOrchestrator (1319 行)   →   SVEextractor.run() (~80 行)
TreeSitterExtractor (4800 行)      →   _TreeSitterCore (~200 行)
LanguageExtractor 接口              →   SVEextractorVisitor 类 (~350 行)
systemverilog.ts (340 行)          →   同上，可直译
ExtractorContext                    →   ExtractionContext (~50 行)
tree-sitter-helpers.ts              →   _helpers.py (~80 行)
generateNodeId (SHA256)             →   hashlib.sha256 (5 行)
```

### 4.2 必需实现的最小接口

#### 数据模型 (dataclasses)

```python
@dataclass
class Node:
    id: str                    # "kind:sha256_32hex"
    kind: str                  # NodeKind 枚举值
    name: str
    qualified_name: str
    file_path: str
    language: str              # "systemverilog"
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    signature: str | None = None
    docstring: str | None = None
    # SV 使用不到的字段可省略: isAsync, isAbstract, decorators, typeParameters...

@dataclass
class Edge:
    source: str
    target: str
    kind: str                  # EdgeKind 枚举值
    line: int | None = None
    column: int | None = None
    provenance: str = 'tree-sitter'

@dataclass
class UnresolvedReference:
    from_node_id: str
    reference_name: str
    reference_kind: str
    line: int
    column: int
    file_path: str

@dataclass
class ExtractionResult:
    nodes: list[Node]
    edges: list[Edge]
    unresolved_references: list[UnresolvedReference]
    errors: list[str]
    duration_ms: float
```

#### ExtractionContext (与 TS 的 ExtractorContext 对应)

```python
class ExtractionContext:
    file_path: str
    source: bytes
    node_stack: list[str]          # 作用域栈
    nodes: list[Node]              # 已提取的节点
    edges: list[Edge]
    unresolved_refs: list[UnresolvedReference]

    def create_node(kind, name, ts_node, extra=None) -> Node | None: ...
    def add_unresolved_reference(ref: UnresolvedReference): ...
    def push_scope(node_id: str): ...
    def pop_scope(): ...
    def visit_node(ts_node): ...   # 递归调度
```

#### SVVisitor.visit_node (直译 systemverilog.ts)

直接迁移 290 行的 `visitNode` 函数，处理的 AST 节点类型完全一致：

| AST 节点类型 | 映射的 NodeKind | 备注 |
|---|---|---|
| `package_declaration` | `namespace` | 作用域节点 |
| `module_declaration`, `program_declaration` | `module` | 作用域节点 |
| `interface_declaration`, `interface_class_declaration` | `interface` | 作用域节点 |
| `checker_declaration` | `component` | 作用域节点 |
| `class_declaration` | `class` | + extends 引用 |
| `function_body_declaration` | `function` 或 `method` | 取决于作用域 |
| `task_body_declaration` | `function` 或 `method` | 取决于作用域 |
| `class_constructor_declaration` | `method` | name='new' |
| `package_import_declaration` | `import` + `imports` ref | |
| `parameter_declaration` | `parameter` | list_of_param_assignments |
| `local_parameter_declaration` | `parameter` | 同上 |
| `type_declaration` | `type_alias` | field: type_name |
| `enum_name_declaration` | `enum_member` | |
| `module_instantiation` 等 5 种 | `instantiates` ref | + visitChildren |
| `tf_call`, `method_call`, `system_tf_call` | `calls` ref | 过滤 `$` 系统调用 |

---

## 5. 估算：代码量与工作量

### 5.1 代码量估算（修订版）

> 范围扩大为全功能：提取 + 存储 + 引用解析 + FTS5 + FileWatcher + Filelist

| 模块 | 预估 Python 行数 | 复杂度 |
|---|---|---|
| 数据模型 (`models.py`) | ~60 | 低 — 纯 dataclass |
| 节点 ID 生成 (`helpers.py`) | ~80 | 低 — 字符串处理 + SHA256 |
| ExtractionContext | ~60 | 低 — 状态管理 |
| TreeSitterCore (extract pipeline) | ~200 | 中 — 解析 + 遍历调度 |
| SVVisitor (visit_node) | ~350 | 中 — 可直译 TS 代码 |
| Filelist 解析器 (`filelist.py`) | ~300 | 中 — 递归下降 + 条件编译栈 |
| SQLite 存储层 (`storage.py`) | ~250 | 中 — schema 对齐 CRUD |
| Reference Resolver (`resolver.py`) | ~300 | 中 — import/extends/instantiates |
| FTS5 搜索 (`search.py`) | ~150 | 低 — 主要为 SQL 查询封装 |
| FileWatcher (`watcher.py`) | ~100 | 低 — watchdog 库封装 |
| CLI/入口 (`cli.py`) | ~80 | 低 — argparse + 调度 |
| 测试 (`tests/`) | ~400 | 中 — pytest 参数化 |
| **合计** | **~2330** | |

参照：当前 TS 版 SV extractor 340 行，核心提取引擎 4800 行，但包含了 20+ 语言和大量通用逻辑。

### 5.2 开发工作量（修订版）

| 阶段 | 预估时间 | 交付物 |
|---|---|---|
| 1. 核心提取器 + Filelist | 4-5 天 | `extract_from_source()` + filelist 展开 |
| 2. SQLite 存储层 | 1-2 天 | 对标 schema.sql 的建表 + CRUD |
| 3. Reference Resolver | 2-3 天 | 跨文件 import/extends/instantiates 解析 |
| 4. FTS5 + FileWatcher | 1-2 天 | 全文搜索 + 自动增量索引 |
| 5. 测试 | 2-3 天 | pytest 覆盖提取/解析/filelist/FTS |
| 6. CLI + 文档 | 1 天 | 命令行入口 + 使用文档 |
| **合计** | **11-16 天** | 全功能版本 |

---

## 6. 风险与已知限制

### 6.1 低风险

| 项目 | 说明 |
|---|---|
| **py-tree-sitter API 差异** | 差异仅在于命名风格（snake_case vs camelCase），语义完全一致 |
| **SV grammar 版本** | `tree-sitter-systemverilog` PyPI 包 (v0.3.1) 与我们的 grammar.js 同源，AST 结构一致 |
| **node.text 行为** | Python 版更简单（属性，无需传参），无适配难度 |

### 6.2 中等风险

| 项目 | 说明 | 对策 |
|---|---|---|
| **node ID 生成兼容性** | 如果 Python 版生成的 ID 要与 JS 版互通，需严格遵循 `sha256(filePath:kind:name:line)` 格式 | 直接复制哈希方案，做兼容性测试 |
| **tree-sitter-systemverilog 更新** | PyPI 包不一定及时跟进 grammar.js 的更新 | 可用 `tree-sitter build --wasm` 生成的 binding 自行构建 wheel |

### 6.3 全功能清单（均为必需）

与初版评估不同，经过进一步分析，以下能力均需在 MVP 中实现，不可推迟：

| 能力 | 说明 | 与 JS 版对标 |
|---|---|---|
| Reference Resolver | 跨文件的 import/extends/instantiates 引用解析 | ✅ 对标 `src/resolution/` |
| FTS5 全文搜索 | SQLite FTS5 虚拟表，支撑 `search_nodes` | ✅ 对标 `nodes_fts` |
| 文件监听 (FileWatcher) | 文件变更自动重索引 | ✅ 对标 `src/sync/` |
| VCS-style filelist 支持 | 解析 `.f` 文件，展开 `-f`/`+incdir`/`+define`/`` `ifdef `` | ⭐ SV 特有需求 |
| Framework 提取器 | 路由、中间件等 | ❌ SV 不需要 |

---

## 7. VCS-style Filelist 支持可行性分析

### 7.1 需求背景

VCS 仿真流程中，源文件通过 **filelist**（通常 `.f` 后缀）组织，而非目录扫描。典型的 filelist 语法：

```tcl
# 注释行
+incdir+${PROJ_ROOT}/rtl/include
+incdir+/home/project/common
+define+SIMULATION
+define+FPGA_PROTO=1
+define+DATA_WIDTH=64

// 绝对路径
/home/project/rtl/top.sv

// 相对路径
../dut/uart_tx.sv

// 嵌套 filelist
-f ${PROJ_ROOT}/flist/sub_block.f
-f ./common_ip.f

// 条件编译
`ifdef FPGA_PROTO
-f fpga_lib.f
`else
-f asic_lib.f
`endif

// Verilog 宏定义
`define MAX_SIZE 256
```

### 7.2 需要的解析能力

| 功能 | 优先级 | 说明 |
|---|---|---|
| 注释过滤 | P0 | `#` 和 `//` 开头的行 |
| `-f <file>` 递归展开 | P0 | 嵌套 filelist，需循环引用检测 |
| `+incdir+<path>` | P0 | include 搜索路径 |
| `+define+<macro>=<value>` | P0 | 全局宏定义 |
| `` `ifdef `` / `` `ifndef `` / `` `else `` / `` `endif `` | P0 | 条件编译块 |
| `` `define `` | P1 | 文件级宏定义 |
| 环境变量展开 `${VAR}` | P1 | 如 `${PROJ_ROOT}` |
| `+define+<macro>` (无值) | P1 | 纯标志宏 |
| 通配符路径 `*.sv` | P2 | glob 展开 |
| `-v <lib_file>` | P2 | 库文件（Verilog 风格） |
| `-y <lib_dir>` | P2 | 库目录 |

### 7.3 现有 Python 生态

**没有现成的 VCS filelist 专用解析库。** 但存在相关工具链：

| 库/工具 | 类型 | 与 filelist 的关系 |
|---|---|---|
| **FuseSoC** (`fusesoc`) | HDL 包管理器 | 通过 `.core` YAML 描述文件组织源码，内部生成 filelist |
| **Edalize** (`edalize`) | EDA 工具抽象 | 消费 EDAM 数据结构，生成工具专用项目文件 |
| **pip-hdl** (`pip-hdl`) | pip 风格的 HDL 包管理 | 以 filelist 为核心编译单元，支持依赖解析 |
| **svinst** (`svinst`) | SV 模块/实例提取 | 接受 `defines` dict 和 `includes` list 参数 |
| **rtl-buddy** (`rtl-buddy`) | RTL 工作流自动化 | 从 YAML 模型生成 filelist |
| **VeribleVCSFilelist** ([GitHub](https://github.com/ColsonZhang/VeribleVCSFilelist)) | Filelist **生成器** + SV 依赖分析 | 扫描目录 → 解析 SV → DFS 依赖拓扑 → 生成 `.f` filelist |

#### VeribleVCSFilelist 深度分析 (⭐ 关键参考)

**仓库已 clone 并分析**。这是一个由上海科技大学 RICL 实验室开发的工具，用于自动生成 VCS filelist。

**核心架构**:

```
VeribleFilelist/
├── main.py          # CLI 入口 (argparse: -t topmodule, -s search-paths, -d defines)
├── preprocess.py    # ⭐ VerilogPreprocessor — 宏处理 + 条件编译栈
├── parse.py         # SV 结构提取 — module/interface/package/参数/端口/实例化
├── database.py      # 依赖图(DFS) + pickle 缓存 + 增量更新
└── verible_verilog_syntax.py  # 封装 Google Verible 外部解析器
```

**与我们需求的关系**:

| 模块 | 可借鉴程度 | 说明 |
|---|---|---|
| `preprocess.py` | ⭐⭐⭐ **可直接复用** | 宏定义提取 + 宏展开 + `` `ifdef ``/`` `ifndef ``/`` `else ``/`` `endif `` 条件编译栈，代码质量高，逻辑清晰 |
| `parse.py` | ⭐⭐ 架构参考 | 提取 module 名称/端口/参数/import/实例化 — 功能上等同于 CodeGraph 的 SV extractor，但基于 Verible 而非 tree-sitter |
| `database.py` | ⭐⭐ 模式参考 | DFS 依赖遍历 (`get_filelist_by_module`)、增量更新 (`sort_files_by_time`)、pickle 缓存机制 — 可参考但我们将用 SQLite 替代 |
| `main.py` | ⭐ 接口参考 | `+define+` 命令行解析、`-t` top module 指定 |

**关键技术细节**:

1. **VerilogPreprocessor 类** (`preprocess.py:13-152`):
   - `_extract_macros(text)` — 正则提取 `` `define NAME VALUE ``，跳过 `` `ifndef `` guard 块
   - `_expand_macros(text)` — 循环替换 `` `macro `` 引用直到不动点
   - `_process_conditionals(text)` — 条件栈 (`conditional_stack` + `skip_level`) 处理嵌套 `` `ifdef ``/`` `ifndef ``/`` `else ``/`` `endif ``
   - `_process_delay_expressions(text)` — 修复 `#delay;` → `#(delay);`
   - 两轮处理：先提取宏 → 展开 → 处理条件 → 再提取（条件块内可能有新宏定义）

2. **Database 类** (`database.py:354-410`):
   - 使用 DFS 从 top module 遍历依赖图 (`dict_module_references`)
   - `get_filelist_by_module()` — 递归收集所有需要的 `.sv/.v` 文件和 `+incdir+` 路径
   - 增量更新通过 `os.path.getmtime()` 比较文件修改时间
   - 缓存存储在 pickle 文件而非 SQLite

3. **与我们的差异**:
   - VeribleVCSFilelist 使用 **Verible** (Google 的 C++ SV 解析器)，我们使用 **tree-sitter**
   - 它是 filelist **生成器**（从目录树 + 依赖分析创建 `.f`），我们是 filelist **解析器**（从已有 `.f` 展开源文件列表）
   - 它做 SV 结构提取（类似 CodeGraph 的提取器），但不做跨项目索引/搜索

**可复用的代码**:
- `preprocess.py` 的 `VerilogPreprocessor` 类几乎可以直接搬到我们的 `FilelistParser` 中处理 `` `define `` 和 `` `ifdef `` 宏
- `database.py` 的 DFS 依赖遍历逻辑可参考用于实现 `ReferenceResolver`

**结论：需要自建 filelist 解析器。** 所有现有工具都是 filelist 的**生成器**而非**解析器**。但好消息是：

1. 语法简单：本质是行导向的标记解析
2. 有成熟的参考实现：CSDN 博客中的 Python filelist 解析器给出了核心算法
3. 可以复用 pip-hdl 和 FuseSoC 中对 `+incdir+`/`+define+` 的处理逻辑

### 7.4 实现方案

**自建 `SVEfilelistParser`**，核心架构：

```python
class FilelistParser:
    """解析 VCS-style .f filelist, 递归展开 -f, 处理条件编译"""
    
    def __init__(self, initial_defines: dict[str, str | None] = None):
        self.defines = dict(initial_defines or {})
        self.incdirs: list[str] = []
        self.visited: set[str] = set()  # 防循环引用
        
    def parse(self, filelist_path: str) -> list[str]:
        """返回展开后的源文件列表"""
        ...
    
    def _parse_file(self, path: str, defines_stack: list[dict]) -> list[str]:
        """递归解析单个 filelist"""
        ...
    
    def _expand_env(self, text: str) -> str:
        """展开 ${VAR} 和 $VAR 环境变量"""
        ...
    
    def _process_ifdef_block(self, lines, i, defines_stack):
        """处理 `ifdef/`else/`endif 条件块"""
        ...
```

**预估代码量**: ~250-300 行 Python

### 7.5 Filelist 解析的测试策略

由于 filelist 是**文件系统敏感**的格式（涉及路径解析和文件存在性检查），测试需要：

1. **参数化测试**：参照 CodeGraph `installer-targets.test.ts` 的模式，用 `pytest.mark.parametrize` 覆盖各种语法组合
2. **临时目录 + 真实文件**：通过 `tmp_path` fixture 创建真实的 `.f` 和 `.sv` 文件树
3. **条件编译矩阵**：`+define+` 的不同组合导致不同的展开结果
4. **循环引用检测**：创建 `a.f → b.f → a.f` 的循环引用，断言报错

### 7.6 与 CodeGraph 测试系统的对标

CodeGraph 使用 **Vitest** (Node.js 生态的 Vite 测试框架)。Python 版改用 **pytest**，后者在芯片验证领域广泛使用：

| CodeGraph (TS) | Python 版 (建议) | 对标程度 |
|---|---|---|
| Vitest (`it`, `describe`) | pytest (`test_*`, `class Test*`) | ✅ |
| `beforeAll` / `afterEach` | `setup_module` / `teardown_method` / `tmp_path` fixture | ✅ |
| `fs.mkdtempSync` | `tmp_path` (pytest 内置) | ✅ 更简洁 |
| 真实 SQLite (无 mock) | 真实 SQLite (通过 `sqlite3` 标准库) | ✅ |
| `extractFromSource(filePath, source)` | `extract_from_source(file_path, source)` | ✅ 完全对标 |
| 参数化 (`for target of ALL_TARGETS`) | `pytest.mark.parametrize` | ✅ |
| `expect(array).toContainEqual(obj)` | `assert obj in array` 或自定义 matcher | ✅ |
| Snapshot 测试 | 无 (CodeGraph 也没用) | ✅ |
| Evaluation runner (独立 `tsx` 脚本) | 独立 `python -m pytest --benchmark` | ✅ |

---

## 8. 修订后的路线图

> **重要变更**: Reference Resolver、FTS5、FileWatcher、Filelist 支持已从"未来可选"升级为**第一阶段必需**。

### 第一阶段：完整核心 (MVP)

```
pip install codegraph-sv
python -m codegraph_sv index <target> --output graph.db
```

交付物：
- **核心提取器**: 全部 15 种 SV 结构
- **Filelist 解析器**: 支持 `-f`/`+incdir+`/`+define+`/`` `ifdef `` 条件编译，递归展开，循环引用检测
- **SQLite 存储层**: 对标 JS 版 schema（nodes、edges、files、unresolved_refs、nodes_fts）
- **Reference Resolver**: import/extends/instantiates 跨文件引用解析
- **FTS5 全文搜索**: `search_nodes(name)` + `get_callers`/`get_callees`
- **FileWatcher**: 文件变更自动增量重索引（watchdog 库）
- **pytest 测试**: 涵盖提取 + 解析 + filelist + FTS 的完整测试

### 第二阶段：MCP Server

- 对标 JS 版的 MCP server 实现
- 让 Claude Code/Cursor 等 AI 工具能查询 Python 版索引

---

## 9. CodeGraph 测试系统分析与对标

CodeGraph (TS) 的测试体系成熟且结构化，以下分析为 Python 版测试体系设计提供参考。

### 9.1 测试基础设施概览

| 维度 | CodeGraph (TS) 现状 | Python 版建议 |
|---|---|---|
| 测试框架 | Vitest v2.1.9 (Vite 生态) | pytest |
| 总测试文件 | 74 个 `.test.ts` 文件 | — |
| 总测试用例 | ~1,348 个 `it()` 块 | — |
| 最大文件 | `extraction.test.ts` (253KB, 363 个测试) | — |
| 配置方式 | `vitest.config.ts` | `pyproject.toml [tool.pytest]` |
| 并行 | Vitest 默认 worker 并行 | `pytest -n auto` (pytest-xdist) |

### 9.2 核心测试模式

#### 模式 A: 提取测试

CodeGraph 的标准提取测试结构——每个语言一个 `describe` 块：

```typescript
describe('SystemVerilog Extraction', () => {
  beforeAll(async () => {
    await initGrammars();
    await loadGrammarsForLanguages(['systemverilog']);
  });

  const UARTISH_SV = `<inline test source>`;

  it('extracts package, class, interface, module...', () => {
    const result = extractFromSource('uart_top.sv', UARTISH_SV);
    expect(result.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: 'namespace', name: 'uart_pkg' }),
        expect.objectContaining({ kind: 'class',    name: 'uart_driver' }),
        // ...
      ])
    );
  });
});
```

**Python 版对标:**

```python
class TestSVEextraction:
    @pytest.fixture(autouse=True)
    def setup_grammar(self):
        from tree_sitter import Language, Parser
        import tree_sitter_systemverilog as tssv
        self.lang = Language(tssv.language())
        self.parser = Parser(self.lang)

    UARTISH_SV = """
    package uart_pkg;
        typedef enum { IDLE, RUN } state_e;
        ...
    endpackage
    """

    def test_extracts_all_node_kinds(self):
        result = extract_from_source('uart_top.sv', self.UARTISH_SV)
        nodes_by_kind = {(n.kind, n.name) for n in result.nodes}
        assert ('namespace', 'uart_pkg') in nodes_by_kind
        assert ('class', 'uart_driver') in nodes_by_kind
        assert ('parameter', 'WIDTH') in nodes_by_kind
```

#### 模式 B: 参数化测试（对标 installer-targets.test.ts）

CodeGraph 的 `installer-targets.test.ts` 使用嵌套 `for` 循环实现对 4 个 agent target × 2 种安装位置 × 7 个契约测试的参数化组合：

```typescript
for (const target of ALL_TARGETS) {
  describe(target.id, () => {
    for (const location of supportedLocations) {
      it('install writes files', () => { ... });
      it('re-running is idempotent', () => { ... });
      it('uninstall reverses install', () => { ... });
    }
  });
}
```

**Python 版应用于 filelist 测试:**

```python
FILECASES = [
    ("basic.sv", ["+incdir+/a"], ["top.sv"]),
    ("nested_f.f", ["-f sub.f"], ["a.sv", "b.sv"]),
    ("ifdef_true.f", ["+define+FPGA", "`ifdef FPGA", "fpga.sv", "`endif"], ["fpga.sv"]),
    ("ifdef_false.f", ["`ifdef ASIC", "asic.sv", "`endif"], []),
]

@pytest.mark.parametrize("name,content,expected_files", FILECASES)
def test_filelist_expand(self, tmp_path, name, content, expected_files):
    f = tmp_path / name
    f.write_text("\n".join(content))
    result = FilelistParser().parse(str(f))
    assert result == expected_files
```

#### 模式 C: 临时文件系统测试（对标 full-pipeline.test.ts）

CodeGraph 的集成测试创建含有 120 个模块的合成项目，运行完整的 `init → indexAll → resolveReferences → searchNodes → getCallers` 管道。

**Python 版对标**：利用 pytest 内置的 `tmp_path` fixture，无需手动 `mkdtempSync` + `afterEach` 清理：

```python
def test_end_to_end_index_and_search(self, tmp_path):
    """创建 3 个 SV 文件的微型项目，完整索引管道"""
    rtl = tmp_path / "rtl"
    rtl.mkdir()
    (rtl / "top.sv").write_text("""
    module top(input clk);
        sub u_sub(.clk(clk));
    endmodule
    """)
    (rtl / "sub.sv").write_text("""
    module sub(input clk);
    endmodule
    """)

    cg = CodeGraph.init(tmp_path)
    cg.index_all()
    results = cg.search_nodes("top")
    assert len(results) > 0
    assert results[0].name == "top"
```

#### 模式 D: 评估测试（对标 evaluation/runner.ts）

CodeGraph 使用独立脚本（`tsx runner.ts`，非 vitest）对预索引的 Elasticsearch 代码库运行 12 个查询，计算 recall 和 MRR。

**Python 版对标**：可以用 `pytest-benchmark` 或独立脚本：

```python
# tests/test_benchmark.py
def test_search_quality(benchmark, indexed_repo):
    """对预先索引的真实 SV 项目做质量评估"""
    cg = CodeGraph.open(indexed_repo)
    result = benchmark(cg.search_nodes, "axi_resp_e")
    assert any("axi_resp_e" in r.name for r in result)
```

### 9.3 测试辅助工具对比

| CodeGraph (TS) | Python 版 | 优劣 |
|---|---|---|
| `fs.mkdtempSync` (手动) | `tmp_path` fixture (pytest 内置) | ✅ Python 更简洁 |
| `process.env` 篡改 | `monkeypatch` fixture | ✅ |
| 无参数化内置支持 | `pytest.mark.parametrize` | ✅ Python 更强大 |
| 真实 SQLite (无 mock) | `sqlite3` 标准库 + `:memory:` DB | ✅ 对标 |
| `extractFromSource(file, src)` | `extract_from_source(file, src)` | ✅ 完全对标 |
| 无 snapshot 测试 | 无 (保持一致) | ✅ |
| 无共享 helper 文件 | `tests/conftest.py` 共享 fixtures | ✅ Python 更规范 |

### 9.4 Filelist 专用的测试设计

由于 filelist 是文件系统敏感的格式，需要专项测试策略：

```
tests/
├── conftest.py              # 共享 fixtures (Parser, Language)
├── test_extraction.py       # 15 种 SV AST 节点类型
├── test_resolution.py       # import/extends/instantiates 跨文件
├── test_filelist.py         # filelist 解析专项
│   ├── test_basic_paths     # 绝对/相对路径
│   ├── test_nested_f        # -f 递归展开
│   ├── test_incdir_define   # +incdir+/+define+
│   ├── test_ifdef_stack     # `ifdef/`else/`endif 条件栈
│   ├── test_env_expand      # ${PROJ_ROOT} 环境变量
│   ├── test_circular_ref    # 循环引用检测
│   └── test_glob            # *.sv 通配符 (可选)
├── test_fts.py              # FTS5 全文搜索
├── test_integration.py      # 端到端管道
└── test_benchmark.py        # 真实项目质量评估
```

---

## 10. 结论

**完全可行，且功能上已确认与 JS 版对标方案。**

### 可行性总结

| 维度 | 结论 |
|---|---|
| **核心依赖** | ✅ `pip install tree-sitter tree-sitter-systemverilog` 已验证 |
| **API 对标** | ✅ py-tree-sitter 的 Node/Tree/Parser/Query 与 web-tree-sitter 语义完全一致 |
| **SV extractor** | ✅ 340 行 TS 代码可逐行直译为 350 行 Python |
| **SQLite 存储** | ✅ `sqlite3` 标准库 + FTS5 扩展，对标 JS 版 schema |
| **Reference Resolver** | ✅ Python 版实现 import/extends/instantiates 跨文件解析 |
| **FTS5 全文搜索** | ✅ SQLite FTS5 虚拟表，对标 `nodes_fts` |
| **FileWatcher** | ✅ `watchdog` 库 (PyPI)，对标 `src/sync/` |
| **VCS Filelist** | ✅ 需自建解析器 (~300 行)，语法简单、有参考实现 |
| **测试** | ✅ pytest + parametrize + tmp_path，对标 Vitest 测试体系 |

### 关键风险

| 风险 | 等级 | 对策 |
|---|---|---|
| `tree-sitter-systemverilog` PyPI 包不跟进 grammar 更新 | 中 | 可自行从 grammar.js 构建 wheel |
| VCS filelist 无现成库 | 低 | 格式简单，自建 ~300 行即可 |
| Python 版 node ID 与 JS 版不兼容 | 低 | 严格遵循相同的 SHA256 哈希方案 |

### 预估投入

- **代码量**: ~2330 行 Python（含提取、存储、引用解析、FTS、FileWatcher、Filelist、测试）
- **开发周期**: 11-16 天（全功能 + 完整测试覆盖）
- **外部依赖**: `tree-sitter`, `tree-sitter-systemverilog`, `watchdog`（文件监听）
