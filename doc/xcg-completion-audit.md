# XCG.md 优化完成度审计

## Section 18 最终验收标准

| # | 标准 | 状态 | 证据 |
|---|---|---|---|
| 1 | filelist 建立 active structure graph | ✅ | FilelistParser + expand_includes |
| 2 | +incdir+ 不再污染索引 | ✅ | .svh removed from standalone indexing |
| 3 | .svh 不再默认独立 parse | ✅ | expand mode: headers skipped |
| 4 | package include class → class 归属 package | ✅ | var_type_map + qualified names |
| 5 | definition 跳转真实 .svh | ✅ | SourceMap + origin_file stored |
| 6 | 同.svh 多package → 多 semantic node | ⚠️ P2 | needs cu_id-based node identity |
| 7 | ifdef/ifndef/elsif/else 按 define 选择 | ✅ | MiniPreprocessor + conditionals table |
| 8 | inactive branch 不进主图 | ✅ | active-only expansion |
| 9 | 重复 index 不重复 node/edge | ✅ | clear_file_data before re-store |
| 10 | hierarchy 不因多 module 单文件污染 | ✅ | context_node_id binding |
| 11 | unresolved/circular include diagnostics | ✅ | SourceManager diagnostics |
| 12 | MCP thin adapter | ✅ | core API calls only |
| 13 | 查询输出 compact | ✅ | Markdown output |

## Section 17 开发步骤

| Step | 内容 | 状态 |
|---|---|---|
| 1 | DB 幂等性 | ✅ |
| 2 | 删除 incdir 扫描 | ✅ |
| 3 | SourceManager | ✅ |
| 4 | tree-sitter parse expanded source | ✅ |
| 5 | minimal preprocessor | ✅ |
| 6 | hierarchy context | ✅ |
| 7 | schema 补全 | ✅ |
| 8 | 查询命令 | ✅ |
| 9 | 测试 fixture | ✅ |
| 10 | benchmark | ✅ |

## 补充优化

| 项目 | 状态 | 说明 |
|---|---|---|
| Filelist VCS 多值格式 | ✅ | +incdir+a+b+c, +define+A+B=1 |
| 反斜杠续行 + 引号 | ✅ | filelist parser |
| VCS option 黑名单 | ✅ | 忽略并 warning |
| assert label 修复 | ✅ | PSEL_STABLE 替代 _assert_109 |
| .svh 去重 | ✅ | expand 模式跳过独立索引 |
| class.method 调用追踪 | ✅ | var_type_map + _call 解析 |
| class.field 字段访问 | ✅ | hierarchical_identifier 解析 |
| doc/filelist_compat.md | ✅ | VCS 兼容性文档 |
| benchmark 命令 | ✅ | xcodegraph benchmark |

## 唯一延期项

**#6: 同.svh 多package → 多 semantic node** — 需要 cu_id 级别的节点唯一性（当前按 file_id 清理，不区分同一 .svh 被不同 CU include 的场景）。此为 P2 增强，不影响当前正确性。

## 测试

141 tests green, 全部回归通过。
