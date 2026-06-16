---
name: xcodegraph-sv
description: 当 AI 需要查询 SystemVerilog 代码结构、模块层次、UVM 组件继承、SVA 断言、覆盖率组、参数/typedef 定义时使用。适用于 RTL 和验证代码的符号搜索、实例化追踪、层次展开。
metadata:
  type: reference
---

# XCodeGraph Skill — SystemVerilog 代码智能查询

## 概述

XCodeGraph 是一个 SystemVerilog 代码结构索引器。它预先解析了项目中的 `.sv` / `.svh` / `.v` / `.vh` 文件，提取了模块、类、接口、参数、typedef、SVA、覆盖率等结构，存储在 SQLite 数据库中。AI Agent 可以通过 MCP 工具直接查询这些结构事实。

**核心价值**: 在进入波形和 RTL 细节之前，先用 XCodeGraph 获取可靠的代码结构事实。

## 何时使用

| 场景 | 使用的工具 |
|------|-----------|
| 查找某个模块/类/参数的定义位置 | `xcodegraph_search` → `xcodegraph_definition` |
| 了解模块内部结构（参数、子模块、import） | `xcodegraph_node` |
| 理解模块例化层次（top→子模块→更深） | `xcodegraph_hierarchy` |
| 追踪某个模块被谁例化 | `xcodegraph_instantiated_by` |
| 查看一个文件中的所有代码符号 | `xcodegraph_file_symbols` |
| 查询 UVM 类继承关系 | `xcodegraph_extends` |
| 查找 package 依赖 | `xcodegraph_imports` |
| 追踪 `` `include `` 依赖链 | `xcodegraph_includes` |
| 确认索引是否过期 | `xcodegraph_status` |
| 修改文件后刷新索引 | `xcodegraph_reindex_file` |

## 工具参考

### `xcodegraph_search`

**用途**: 按名称搜索代码符号。这是**最先使用的入口工具**。

**参数**:
- `query` (必填): 搜索关键词，支持部分名称匹配
- `kind` (可选): 过滤节点类型。可选值: `module`, `interface`, `package`, `class`, `function`, `task`, `parameter`, `typedef`, `property`, `sequence`, `assert`, `covergroup`, `coverpoint`, `cross`, `constraint`, `rand_field`, `tlminitf`, `checker`

**示例**:
```
xcodegraph_search("aes")                    → 搜索所有包含 "aes" 的符号
xcodegraph_search("driver", kind="class")   → 只搜索 driver 类
xcodegraph_search("ADDR_WIDTH", kind="parameter") → 搜索特定参数
xcodegraph_search("covergroup", kind="covergroup") → 搜索覆盖率组
```

**返回**: Markdown 表格，包含 kind、name、file、line。

### `xcodegraph_node`

**用途**: 查看某个代码符号的详细信息，包括它包含的子元素、引用的外部符号。

**参数**:
- `name` (必填): 符号名称
- `kind` (可选): 节点类型，用于消歧
- `source` (可选): 设为 `true` 可获取完整源代码

**示例**:
```
xcodegraph_node("aes")             → aes 模块的完整信息
xcodegraph_node("aes", source=true) → 含源代码
xcodegraph_node("uart_driver", kind="class") → UVM driver 类详情
```

**返回**:
- 位置 (文件 + 行号)
- 签名
- CONTAINS: 包含的参数、子模块、方法
- INSTANTIATES: 例化了哪些模块
- IMPORTS: 导入了哪些 package
- EXTENDS: 继承自哪个基类
- CALLS: 调用了哪些函数/任务

### `xcodegraph_hierarchy`

**用途**: 从顶模块向下展开例化树。用于理解芯片物理层次。

**参数**:
- `name` (必填): 顶模块名称
- `depth` (可选, 默认 10): 展开深度

**示例**:
```
xcodegraph_hierarchy("chip_earlgrey_asic")    → 完整芯片层次
xcodegraph_hierarchy("top_tb", depth=3)       → 限制深度 3 层
```

**返回**: 树形结构的模块列表，每层缩进显示。包含文件和行号。

**注意**: 这是模块硬件例化层次，不是 UVM 环境层次。

### `xcodegraph_instantiated_by`

**用途**: 反向查询——某个模块或接口被哪些模块例化。

**示例**:
```
xcodegraph_instantiated_by("tlul_socket_1n")  → 19 个模块例化了这个 socket
xcodegraph_instantiated_by("prim_clock_mux2")  → 时钟 mux 的所有使用点
```

### `xcodegraph_definition`

**用途**: 快速跳转到符号的定义位置。只返回文件路径和行号。

**示例**:
```
xcodegraph_definition("uart_tx")
xcodegraph_definition("axi_transfer", kind="class")
```

### `xcodegraph_file_symbols`

**用途**: 列出单个源文件中提取到的所有代码符号。

**示例**:
```
xcodegraph_file_symbols("hw/ip/uart/rtl/uart.sv")
```

### `xcodegraph_extends`

**用途**: 列出某个类的所有直接父类。

**示例**:
```
xcodegraph_extends("uart_driver")    → extends uvm_driver #(uart_transfer)
xcodegraph_extends("uart_monitor")   → extends uvm_monitor
```

### `xcodegraph_imports`

**用途**: 列出某个模块导入了哪些 package。

**示例**:
```
xcodegraph_imports("aes")    → aes_pkg, aes_reg_pkg
```

### `xcodegraph_includes`

**用途**: 列出文件中的 `` `include `` 引用。

**示例**:
```
xcodegraph_includes("uart_tx")
```

### `xcodegraph_status`

**用途**: 查看索引状态——文件数、节点数、边数、是否有未解析引用、索引时间。

**示例**:
```
xcodegraph_status()
```

### `xcodegraph_reindex_file`

**用途**: 修改某个源文件后，重新索引该文件。

**示例**:
```
xcodegraph_reindex_file("hw/ip/uart/rtl/uart.sv")
```

## 常见查询模式

### 模式 1: 理解一个模块

```
1. xcodegraph_search("模块名")         → 确认模块存在
2. xcodegraph_node("模块名")           → 查看参数、例化、import
3. xcodegraph_hierarchy("模块名")       → 如果需要层次上下文
```

### 模式 2: 追踪信号或总线

```
1. xcodegraph_search("总线名", kind="interface")   → 找到接口定义
2. xcodegraph_instantiated_by("接口名")             → 谁使用了它
3. xcodegraph_node("使用者模块")                    → 查看具体连接
```

### 模式 3: 理解 UVM 验证环境

```
1. xcodegraph_search("env", kind="class")      → 找到 env 类
2. xcodegraph_node("env_name")                  → 查看包含的 agent
3. xcodegraph_extends("agent_name")             → 查看继承链
4. xcodegraph_search("sequence", kind="class")  → 找到测试序列
5. xcodegraph_search("covergroup", kind="covergroup") → 查看覆盖率组
```

### 模式 4: 修改前影响分析

```
1. xcodegraph_search("模块名")                   → 找到模块
2. xcodegraph_instantiated_by("模块名")           → 谁例化了它
3. xcodegraph_node("每个例化者")                   → 理解使用上下文
```

### 模式 5: 理解 SVA 断言覆盖

```
1. xcodegraph_search("", kind="assert")       → 列出所有断言
2. xcodegraph_search("", kind="property")     → 列出命名 property
3. xcodegraph_search("", kind="sequence")     → 列出命名 sequence
4. xcodegraph_node("断言名")                    → 查看具体断言
```

## 重要注意事项

1. **先 search 再 node**: 先用 `xcodegraph_search` 找到符号的确切名称，再用 `xcodegraph_node` 获取详情。直接调用 `xcodegraph_node` 可能因名称不精确而找不到。

2. **kind 过滤消歧**: 一个名称可能对应多种类型（如 `uart` 既是 module 名也出现在 parameter 名中），用 `kind` 参数精确过滤。

3. **区分 RTL 层次和 UVM 层次**: `xcodegraph_hierarchy` 展示的是模块例化层次（RTL），不是 UVM class 继承层次。UVM 继承用 `xcodegraph_extends`。

4. **索引可能不完整**: 如果 `xcodegraph_status` 显示大量 unresolved refs，说明 filelist 可能缺少某些源文件（如 UVM base class library）。

5. **重新索引**: 修改代码后，AI 应主动调用 `xcodegraph_reindex_file` 刷新对应文件的索引，而不是盲目使用过时结果。

6. **不要做 RTL signal trace**: XCodeGraph 不做信号级数据流分析——那是 xdebug 的职责。XCodeGraph 只提供模块级结构事实。

7. **Common block 意识**: 某些公共 IP（FIFO、arbiter、clock mux）是基础设施，不需要深入内部实现。XCodeGraph 的 AI summary 会标记这些 common block。
