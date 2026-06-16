# 阶段 1: 核心提取器

> 时间: 4-5 天 | 依赖: 无 | 优先级: P0

## 目标

实现从 SystemVerilog 源代码字符串中提取所有 15 种代码结构的核心管道。

## 交付物

### 1.1 数据模型 (`models.py`)

```python
@dataclass
class Node:
    id: str                    # "kind:sha256_32hex" 对标 JS 版
    kind: str                  # NodeKind 枚举值
    name: str
    qualified_name: str
    file_path: str
    language: str              # 固定 "systemverilog"
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    signature: str | None = None
    docstring: str | None = None

@dataclass
class Edge:
    source: str                # 源节点 ID
    target: str                # 目标节点 ID
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

### 1.2 工具函数 (`helpers.py`)

| 函数 | 说明 |
|---|---|
| `generate_node_id(file_path, kind, name, line) -> str` | `sha256(f"{path}:{kind}:{name}:{line}")[:32]` |
| `get_node_text(node, source) -> str` | 从 source bytes 中切片文本 |
| `get_child_by_field(node, field_name) -> Node \| None` | 封装 `node.child_by_field_name()` |
| `clean_identifier(text) -> str` | 去空白，折叠内部空格 |

### 1.3 ExtractionContext (`extraction/context.py`)

```python
class ExtractionContext:
    file_path: str
    source: bytes
    node_stack: list[str]          # 作用域栈 — 用于构建 qualifiedName
    nodes: list[Node]
    edges: list[Edge]
    unresolved_refs: list[UnresolvedReference]

    def create_node(self, kind, name, ts_node, extra=None) -> Node | None: ...
    def add_unresolved_reference(self, ref: UnresolvedReference): ...
    def push_scope(self, node_id: str): ...
    def pop_scope(self): ...
    def visit_node(self, ts_node): ...  # 递归调度
```

### 1.4 TreeSitterCore (`extraction/core.py`)

核心提取管道，对标 JS 版 `TreeSitterExtractor.extract()`：

```python
class TreeSitterCore:
    def __init__(self, visitor: SVVisitor):
        self.visitor = visitor

    def extract(self, file_path: str, source: str) -> ExtractionResult:
        # 1. 创建 Parser + Language
        # 2. parser.parse(source.encode('utf-8'))
        # 3. 创建文件节点 (kind='file')
        # 4. push_scope(文件节点)
        # 5. ctx.visit_node(root_node)  → 触发 SVVisitor
        # 6. 返回 ExtractionResult
```

### 1.5 SVVisitor (`extraction/visitor.py`)

**直译 JS 版 `systemverilog.ts` (340 行)**。处理的 AST 节点类型：

| AST 节点 | NodeKind | 备注 |
|---|---|---|
| `package_declaration` | `namespace` | 作用域节点 |
| `module_declaration`, `program_declaration` | `module` | 作用域 + 限定名构建 |
| `interface_declaration`, `interface_class_declaration` | `interface` | 作用域节点 |
| `checker_declaration` | `component` | 作用域节点 |
| `class_declaration` | `class` | + `extends` 引用 |
| `function_body_declaration` | `function` 或 `method` | 依赖 `currentScopeKind()` |
| `task_body_declaration` | `function` 或 `method` | 同上 |
| `class_constructor_declaration` | `method` | name='new' |
| `package_import_declaration` | `import` + `imports` ref | |
| `parameter_declaration`, `local_parameter_declaration` | `parameter` | list_of_param_assignments |
| `type_declaration` | `type_alias` | field: type_name |
| `enum_name_declaration` | `enum_member` | 第一个 named_child |
| `module_instantiation` 等 5 种 | `instantiates` ref | + visitChildren |
| `tf_call`, `method_call`, `system_tf_call` | `calls` ref | 过滤 `$` 前缀 |

### 关键辅助函数

从 JS 版直译:
- `declaration_name(node, source)` — 从 `module_ansi_header` 等头节点提取名称
- `current_scope_kind(ctx)` — 查询 node_stack 栈顶的节点类型
- `class_scope_name(node, source)` — 解析 `ClassName::method` 前缀
- `visit_children(node, ctx)` — 递归遍历 named_children
- `create_scoped_node(kind, node, ctx)` — 创建 + push→visit→pop
- `emit_reference(ctx, node, ref_name, ref_kind)` — 添加未解析引用
- `create_subroutine(node, ctx, is_task)` — 处理 function/task 声明

## 验证标准

```bash
# 单元测试 — 每种 AST 节点类型至少一个测试
pytest tests/test_extraction.py -v

# 对标 JS 版 syestemverilog-extraction.test.ts
# 所有 15 种 AST 节点的 Node 和 Reference 均被正确提取
```

## 与 JS 版的对标关系

| JS 版文件 | Python 版文件 |
|---|---|
| `src/types.ts` (Node/Edge 定义) | `models.py` |
| `src/extraction/tree-sitter-helpers.ts` | `helpers.py` |
| `src/extraction/tree-sitter.ts` (TreeSitterExtractor) | `extraction/core.py` |
| `src/extraction/tree-sitter-types.ts` (ExtractorContext) | `extraction/context.py` |
| `src/extraction/languages/systemverilog.ts` | `extraction/visitor.py` |
