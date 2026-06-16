# 阶段 3: 存储与搜索

> 时间: 2-3 天 | 依赖: 阶段 1 | 优先级: P0

## 目标

实现 SQLite 持久化存储层和 FTS5 全文搜索，对标 JS 版 `schema.sql`。

## 交付物

### 3.1 SQLite Schema (`storage/schema.py`)

对标 JS 版 `src/db/schema.sql`:

```sql
-- 节点表
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    start_column INTEGER NOT NULL,
    end_column INTEGER NOT NULL,
    docstring TEXT,
    signature TEXT,
    visibility TEXT,
    is_exported INTEGER DEFAULT 0,
    is_async INTEGER DEFAULT 0,
    is_static INTEGER DEFAULT 0,
    is_abstract INTEGER DEFAULT 0,
    decorators TEXT,           -- JSON 数组
    type_parameters TEXT,      -- JSON 数组
    return_type TEXT,
    updated_at INTEGER NOT NULL
);

-- 边表
CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    metadata TEXT,             -- JSON 对象
    line INTEGER,
    col INTEGER,
    provenance TEXT DEFAULT 'tree-sitter'
);

-- 文件表
CREATE TABLE files (
    path TEXT PRIMARY KEY,
    content_hash TEXT,
    language TEXT,
    size INTEGER,
    indexed_at INTEGER,
    node_count INTEGER DEFAULT 0
);

-- 未解析引用表
CREATE TABLE unresolved_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id TEXT REFERENCES nodes(id) ON DELETE CASCADE,
    reference_name TEXT NOT NULL,
    reference_kind TEXT NOT NULL,
    line INTEGER,
    col INTEGER,
    candidates TEXT,           -- JSON 数组
    file_path TEXT,
    language TEXT
);

-- FTS5 全文搜索
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    id UNINDEXED,
    name,
    qualified_name,
    docstring,
    signature,
    content='nodes',
    content_rowid='rowid'
);

-- 触发器: 自动同步 FTS
CREATE TRIGGER nodes_ai AFTER INSERT ON nodes BEGIN
    INSERT INTO nodes_fts(rowid, id, name, qualified_name, docstring, signature)
    VALUES (new.rowid, new.id, new.name, new.qualified_name, new.docstring, new.signature);
END;
-- (类似的 update/delete 触发器)
```

### 3.2 存储 API (`storage/queries.py`)

```python
class Storage:
    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")

    # 文件操作
    def upsert_file(self, path: str, content_hash: str, language: str, size: int) -> None: ...
    def get_file(self, path: str) -> FileRecord | None: ...
    def delete_file(self, path: str) -> None: ...

    # 批量写入（提取结果）
    def store_extraction(self, file_path: str, result: ExtractionResult) -> int:
        """批量插入 nodes + edges + unresolved_refs; 更新 files 表"""
        ...

    # 节点查询
    def get_nodes_by_kind(self, kind: str) -> list[Node]: ...
    def get_node_by_id(self, node_id: str) -> Node | None: ...
    def get_node_by_qualified_name(self, qname: str) -> Node | None: ...

    # 边查询
    def get_edges_by_source(self, node_id: str) -> list[Edge]: ...
    def get_edges_by_target(self, node_id: str) -> list[Edge]: ...
```

### 3.3 FTS5 搜索 (`storage/fts.py`)

```python
class SearchEngine:
    def __init__(self, storage: Storage):
        self.storage = storage

    def search_nodes(self, query: str, kind: str | None = None) -> list[Node]:
        """FTS5 全文搜索节点名称和限定名"""
        ...

    def get_callers(self, node_id: str) -> list[Node]:
        """查找所有调用目标节点的调用者"""
        # SELECT source FROM edges WHERE target = ? AND kind = 'calls'
        ...

    def get_callees(self, node_id: str) -> list[Node]:
        """查找目标节点调用的所有节点"""
        # SELECT target FROM edges WHERE source = ? AND kind = 'calls'
        ...

    def get_impact_radius(self, node_id: str, max_depth: int = 3) -> list[Node]:
        """BFS 影响范围分析"""
        ...

    def get_instantiations(self, node_id: str) -> list[Node]:
        """查找模块/接口的所有实例化"""
        ...
```

### 3.4 CodeGraph 主类 (`xcodegraph.py`)

```python
class CodeGraph:
    """顶层 API — 对标 JS 版 src/index.ts CodeGraph 类"""

    @classmethod
    def init(cls, project_path: str) -> 'CodeGraph':
        """初始化项目: 创建 .xcodegraph/ 目录和 SQLite DB"""
        ...

    @classmethod
    def open(cls, project_path: str) -> 'CodeGraph':
        """打开已有项目"""
        ...

    def index_files(self, file_paths: list[str]) -> None:
        """索引一批文件: 提取 → 存储 → 返回"""
        ...

    def index_filelist(self, filelist_path: str) -> None:
        """解析 filelist + 索引所有源文件"""
        ...

    def resolve_references(self) -> None:
        """运行 Reference Resolver (阶段 4)"""
        ...

    def search_nodes(self, query: str, kind: str | None = None) -> list[Node]:
        """FTS5 搜索"""
        ...

    def close(self) -> None:
        """关闭数据库连接"""
        ...
```

## 验证标准

```bash
# 端到端测试: init → index → search
pytest tests/test_integration.py -v
pytest tests/test_fts.py -v
pytest tests/test_storage.py -v
```
