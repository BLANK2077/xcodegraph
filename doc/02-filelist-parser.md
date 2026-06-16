# 阶段 2: Filelist 解析器

> 时间: 2-3 天 | 依赖: 无 (可与阶段 1 并行) | 优先级: P0

## 目标

实现 VCS-style `.f` filelist 的递归展开，支持 `-f`、`+incdir+`、`+define+`、`` `ifdef `` 条件编译。

## 背景

VCS 仿真工具链中，源文件不通过目录扫描，而是通过 filelist 组织。典型的 filelist：

```tcl
+incdir+${PROJ_ROOT}/rtl/include
+define+SIMULATION
+define+DATA_WIDTH=64

-f ./sub_block.f
-f ${PROJ_ROOT}/common/ip_lib.f

`ifdef FPGA_PROTO
-f fpga_lib.f
`else
../asic/asic_top.sv
`endif

/home/project/rtl/top.sv
../dut/uart_tx.sv
```

## 交付物

### 2.1 FilelistParser (`filelist/parser.py`)

```python
class FilelistParser:
    """VCS-style .f filelist 解析器"""

    def __init__(self, initial_defines: dict[str, str | None] = None):
        self.defines = dict(initial_defines or {})
        self.incdirs: list[str] = []
        self.visited: set[str] = set()  # 防 -f 循环引用

    def parse(self, filelist_path: str) -> FilelistResult:
        """递归展开 filelist，返回源文件列表 + incdir + defines"""
        ...

class FilelistResult:
    files: list[str]           # 展开后的绝对路径源文件列表
    incdirs: list[str]         # 所有 +incdir+ 路径
    defines: dict[str, str]    # 所有宏定义
    errors: list[str]          # 解析错误
```

### 2.2 解析能力矩阵

| 语法 | 优先级 | 实现方式 |
|---|---|---|
| `# ...` / `// ...` 注释行 | P0 | 行首正则匹配，跳过 |
| 空白行 | P0 | `line.strip() == ''` |
| `-f <path>` | P0 | 递归展开，`visited` set 防循环 |
| `+incdir+<path>` | P0 | 收集到 `incdirs` 列表 |
| `+define+<macro>=<value>` | P0 | 存 `defines[macro] = value` |
| `` `ifdef `` / `` `ifndef `` | P0 | 条件栈处理 |
| `` `else `` / `` `endif `` | P0 | 条件栈翻转/弹出 |
| `` `define `` | P1 | 两轮处理：先提取再展开 |
| `` `<macro>` `` 引用 | P1 | 在 filelist 路径中展开宏引用 |
| `${VAR}` 环境变量 | P1 | `os.path.expandvars()` |
| `+define+<macro>` (无值) | P1 | `defines[macro] = ''` |
| `*.sv` / `*.v` 通配符 | P2 | `glob.glob()` |

### 2.3 条件编译栈

借鉴 VeribleVCSFilelist `preprocess.py` 的实现：

```python
class Preprocessor:
    """处理 `define / `ifdef / `ifndef / `else / `endif"""

    def __init__(self, defines: dict[str, str]):
        self.defines = defines
        self.conditional_stack: list[tuple[str, str]] = []  # (type, macro)
        self.skip_level: int | None = None

    def process(self, lines: list[str]) -> list[str]:
        """两轮处理:
        1. 提取所有 `define 宏定义
        2. 展开 `macro 引用
        3. 处理条件编译指令
        4. 再次提取（条件块内可能有新宏定义）
        5. 再次展开
        """
        ...
```

### 2.4 循环引用检测

```python
def _parse_f_file(self, filelist_path: str) -> list[str]:
    abs_path = os.path.abspath(filelist_path)
    if abs_path in self.visited:
        raise FilelistCircularError(
            f"循环引用: {' -> '.join(self.visited)} -> {abs_path}"
        )
    self.visited.add(abs_path)
    ...
```

## 验证标准

```bash
# 参数化测试 — 覆盖所有语法组合
pytest tests/test_filelist.py -v

# 测试覆盖:
# - 基本路径（绝对/相对）
# - -f 嵌套展开
# - +incdir+ / +define+
# - `ifdef / `else / `endif 条件栈
# - 嵌套条件编译
# - ${VAR} 环境变量展开
# - 循环引用检测
# - 注释和空白行
```

## 参考实现

- `VeribleVCSFilelist/preprocess.py` — `VerilogPreprocessor` 类，宏处理和条件编译栈
- CSDN 博客 "一键解析IC设计中的复杂filelist条件编译" — 核心算法描述
