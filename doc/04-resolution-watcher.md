# 阶段 4: 引用解析与文件监听

> 时间: 3-4 天 | 依赖: 阶段 1 (提取), 阶段 3 (存储) | 优先级: P0

## 目标

1. **Reference Resolver**: 跨文件解析 import/extends/instantiates 引用，将 UnresolvedReference 转换为 Edge
2. **FileWatcher**: 文件变更时自动增量重索引

## 交付物

### 4.1 Reference Resolver (`resolution/resolver.py`)

对标 JS 版 `src/resolution/`：

```python
class ReferenceResolver:
    """跨文件引用解析器"""

    def __init__(self, storage: Storage):
        self.storage = storage

    def resolve_all(self) -> ResolveResult:
        """解析所有未解析的引用"""
        unresolved = self.storage.get_all_unresolved_refs()
        resolved_count = 0
        for ref in unresolved:
            target = self._resolve(ref)
            if target:
                self._create_edge(ref, target)
                resolved_count += 1
        return ResolveResult(
            total=len(unresolved),
            resolved=resolved_count,
            edges_created=resolved_count,
        )

    def _resolve(self, ref: UnresolvedReference) -> Node | None:
        """多策略解析单个引用"""
        # 策略 1: 通过限定名精确匹配
        # 策略 2: 通过名称 + file_path 模糊匹配
        # 策略 3: 通过 import 路径推断
        ...
```

#### 解析策略

| 引用类型 | 解析方式 |
|---|---|
| `imports` | 搜索同名 package/namespace 节点 |
| `extends` | 搜索同名 class/interface 节点 |
| `instantiates` | 搜索同名 module/interface 节点 |
| `calls` | 搜索同名 function/task 节点 |

#### 生成的 Edge 类型映射

| 引用类型 | 目标节点类型 | 生成的 Edge |
|---|---|---|
| `imports` | `namespace` | `imports` |
| `extends` | `class` | `extends` |
| `extends` (目标为 interface) | `interface` | `implements` |
| `instantiates` | `module` / `interface` | `instantiates` |
| `calls` | `function` / `method` | `calls` |

### 4.2 FileWatcher (`watcher/watcher.py`)

基于 `watchdog` 库 (PyPI)：

```python
class FileWatcher:
    """文件系统变更监听器 — 对标 JS 版 src/sync/FileWatcher"""

    def __init__(self, codegraph: CodeGraph):
        self.cg = codegraph
        self.observer = Observer()

    def watch(self, paths: list[str]) -> None:
        """开始监听指定路径"""
        for path in paths:
            event_handler = SVFileEventHandler(self.cg)
            self.observer.schedule(event_handler, path, recursive=True)
        self.observer.start()

    def unwatch(self) -> None:
        self.observer.stop()
        self.observer.join()


class SVFileEventHandler(FileSystemEventHandler):
    """处理 .sv/.svh/.v/.vh/.sva/.f 文件的变更"""

    def on_modified(self, event):
        if self._is_sv_file(event.src_path):
            self.cg.reindex_file(event.src_path)

    def on_created(self, event):
        if self._is_sv_file(event.src_path):
            self.cg.index_files([event.src_path])

    def on_deleted(self, event):
        if self._is_sv_file(event.src_path):
            self.cg.remove_file(event.src_path)
```

#### 增量索引流程

```
文件变更事件
  → 判断文件类型 (.sv/.svh/.v/.vh/.sva/.f)
  → 重新提取该文件
  → 删除旧节点（级联删除 edges + refs）
  → 插入新节点
  → 更新 files 表 content_hash
  → 触发增量引用解析
```

## 验证标准

```bash
# 跨文件引用解析
pytest tests/test_resolution.py -v

# 文件监听 — 创建/修改/删除 → 自动重索引
pytest tests/test_watcher.py -v

# 集成: 多文件项目完整链路
pytest tests/test_integration.py -v
```
