# XCodeGraph Filelist 兼容性

## 支持的 VCS 选项

| 选项 | 说明 | 状态 |
|---|---|---|
| `-f <file>` / `-F <file>` | 嵌套 filelist，递归展开 | ✅ |
| `+incdir+<path>[+<path>...]` | Include 搜索路径，支持 VCS 多路径格式 | ✅ |
| `+define+<macro>[=<val>][+<macro>[=<val>]...]` | 宏定义，bare name 默认 "1" | ✅ |
| `-y <lib_dir>` | 库目录 | ✅ |
| `-v <lib_file>` | 库文件 | ✅ |
| `// comment` / `# comment` | 注释行 | ✅ |
| `\` (反斜杠续行) | 行拼接 | ✅ |
| `"路径引号"` | 路径中的空格/特殊字符 | ✅ |
| `${VAR}` / `$VAR` | 环境变量展开 | ✅ |
| 相对路径 | 相对 filelist 所在目录解析 | ✅ |

## 忽略的 VCS Option（warning 记录，不当作源文件）

| 选项 | 说明 |
|---|---|
| `-sverilog` / `-sv` / `-v2k` / `+v2k` | SV/Verilog 标准版本 |
| `-timescale=<val>` / `-override_timescale` | 时间精度 |
| `-full64` / `-cpp` / `-cc` | 编译器选项 |
| `-lca` / `-kdb` / `-debug_access[+all]` | 调试/许可 |
| `-debug_region` / `-debug` / `-vcs` | 调试选项 |
| `-cm` / `-cov` / `-cm_dir` / `-cm_name` | 覆盖率选项 |
| `-assert` | 断言控制 |
| `-P <pli>` / `-Mdir` / `-Mlib` | PLI/编译目录 |
| `-l <log>` / `-R` / `-u` | 运行时选项 |
| `-o <output>` | 输出重定向 |
| `-f` / `-F` / `-file` (后跟文件名) | 已作为命令处理 |
| `-vera` | Vera 兼容 |
| `-hera` / `-hera_cm` | Hera 工具 |
| `-fsdb` / `-vpd` / `-vpdtoggle` | 波形输出 |
| `-sdf` / `-sdfmin` / `-sdftyp` / `-sdfmax` | SDF 反标 |
| `+plusarg_save` / `+vcs` | 旧式 plusarg |
| `-notice` / `-nbaopt` | 其他编译选项 |

## 不支持

| 选项 | 说明 | 建议 |
|---|---|---|
| `+libext+<ext>` | 库文件扩展名 | P2 计划 |
| `` `define `` inside filelist | 文件内宏定义 | 使用 `+define+` 替代 |
| 带参数宏展开 | `uvm_component_utils(my_driver)` | 不在 P0 范围 |
| FuseSoC `.core` 文件 | 需 FuseSoC 转换 | `fusesoc run --setup` 后提取 |

## 与 VCS 的差异

1. **`+incdir+` 不作为 source list**: XCodeGraph 不会扫描 incdir 目录下的所有文件，只索引 filelist 显式列出的文件和通过 `` `include `` 实际引用的文件。

2. **`.svh` 不独立 parse**: 在 expand-includes 模式下，`.svh` 被展开到 compilation unit 内，不产生独立的顶层节点。

3. **`` `ifdef `` 只选 active branch**: 按 filelist `+define+` 配置选择 active branch，inactive 分支进入 conditionals 表而不进入主语义图。

4. **不展开 `` `define `` 宏**: 不做宏文本替换（token paste/stringify），但正确处理 `` `ifdef ``/`` `ifndef `` 条件编译。
