# XCodeGraph 开发计划修正

## 背景

基于 `review06161436.md` 的评审意见，对现有 6 阶段开发计划进行修正。

**评审核心观点**:

1. **删除 watchdog** — IC 服务器 NFS/shared workspace 场景下文件事件不可靠，改为 Git HEAD + AI 显式 reindex
2. **MCP 保留为 P0** — 但只做 thin adapter，core 逻辑与 MCP 完全解耦
3. **不做完整 CodeGraph 克隆** — 定位为"面向芯片验证 Agent 的离线 SV 结构索引器"
4. **Filelist-first** — 主入口是 filelist，目录扫描仅为补充
5. **只使用 tree-sitter backend** — 已验证 py-tree-sitter 在目标环境可用，不引入 regex fallback 增加维护负担
6. **增加 common block summary hook** — 防止 AI 盲目深入公共 IP 内部

**用户指示**: 忽略确认环境/测试环境相关内容；去除 regex fallback；保持 xcodegraph 独立仓库形态。

## 修正对比

| 维度 | 旧计划 | 新计划 |
|---|---|---|
| 文件监听 | watchdog 自动增量 | Git HEAD stale + AI 显式 reindex + file hash |
| MCP 定位 | 阶段 5 (P1) | P0，thin adapter 模式 |
| Parser | 仅 tree-sitter | tree-sitter (唯一 backend) |
| 入口 | 目录 + filelist | filelist-first |
| caller/callee/explore | P0 | 保留 CALLS edge (class/function/task 间)，但暂缓 explore/signal_flow |
| common block | 无 | P1 新增 |
| 验证语义 | 无 — 仅 RTL 视角 | P0 验证感知的 node/edge 设计 |

## 验证侧语义设计

RTL 和验证代码的关系模型有本质不同。需要为 class/package/interface/module/function/task 构建验证感知的语义关系。

### 两种语境下的同一 node kind 含义

```
                     RTL 语境                    验证语境
module          →   硬件模块                      testbench wrapper
interface       →   信号 bundle                  同 (硬件 interface)
package         →   函数/类型命名空间             共享类型/UVC 组件/SVA
class           →   很少出现 (仅 SV 2012+)       ⭐ 核心 OOP 载体
function        →   组合逻辑函数                 类方法、配置函数
task            →   很少 (仅 testbench)           ⭐ 时序逻辑、phase、sequence body
```

### 验证代码中的关键语义关系

以下以 UVM testbench 为例：

```
验证项目结构:
  tb_top.sv (module)                       ← 顶层 wrapper
  env_pkg.sv (package)                     ← UVC 环境包
    class my_env extends uvm_env            ← 环境组件
      my_agent u_agent;                    ← 子组件引用 (HAS_A)
    class my_agent extends uvm_agent
      my_driver u_drv;                     ← driver 引用
      my_monitor u_mon;                    ← monitor 引用
      uvm_sequencer #(item) u_sqr;         ← sequencer 引用
    class my_driver extends uvm_driver
      virtual my_if vif;                   ← virtual interface 引用
      task run_phase(uvm_phase phase);
        seq_item_port.get_next_item(req);  ← TLM 方法调用
      endtask
    class my_monitor extends uvm_monitor
      uvm_analysis_port #(item) ap;        ← TLM port 声明
  seq_lib_pkg.sv (package)
    class my_seq extends uvm_sequence
      task body();
        `uvm_do(req)                       ← 宏 → start_item/finish_item
      endtask
  test_pkg.sv (package)
    class my_test extends uvm_test
      my_env env;                          ← 环境引用
      function void build_phase(...);
        env = my_env::type_id::create(...); ← factory 创建
      endfunction
```

### 从 AST 可提取的验证语义 (P0)

| 语义关系 | AST 节点来源 | Edge Kind | 示例 |
|---|---|---|---|
| class 继承 | `class_declaration` → `class_type` 子节点 | **EXTENDS** | `my_driver extends uvm_driver` |
| class 组合 (HAS_A) | `class_declaration` 内的变量声明 — 类型是 class | **REFERENCES** (类型引用) | `my_agent u_agent` → 引用 `my_agent` 类 |
| factory 创建 | `tf_call` / `method_call` — `type_id::create("name", ...)` | **INSTANTIATES** (类→类) | `my_env::type_id::create(...)` → 实例化 `my_env` |
| virtual interface 绑定 | `class_declaration` 内 `virtual <if_name>` | **REFERENCES** (类→interface) | `virtual my_if vif` → 引用 `my_if` interface |
| function/task 调用 | `tf_call` / `method_call` | **CALLS** | `seq_item_port.get_next_item(req)` |
| TLM port 声明 | 类成员变量类型 (analysis_port 等) | **REFERENCES** (类→port 类型) | `uvm_analysis_port#(item) ap` |
| package import | `package_import_declaration` | **IMPORTS** | `import uvm_pkg::*` |
| class 包含 method | `function_body_declaration` / `task_body_declaration` | **CONTAINS** | `run_phase` 属于 `my_driver` |
| module 实例化 interface | `module_instantiation` / `interface_instantiation` | **INSTANTIATES** | `my_if u_if(.clk(clk))` |
| phase 方法覆写 | 子类中的 `build_phase / connect_phase / run_phase` 等 | **OVERRIDES** (AST: 子类→父类同名方法) | `my_driver::build_phase` overrides `uvm_driver::build_phase` |

### 验证侧 node kind 扩展

在 RTL 已有 node kind 基础上，P0 增加:

| Node Kind | AST 来源 | 说明 |
|---|---|---|
| `tlminitf` | class 内 `uvm_*_port #(...)` 声明变量 | TLM 端口 (analysis_port, blocking_put_port 等) |
| `tlminitf` | class 内 `uvm_*_imp #(...)` / `uvm_*_export #(...)` 声明 | TLM 接口/export |
| `config_db_call` | `uvm_config_db#(...)::set/get` 调用点 | 配置数据库访问点 (存为 node 方便搜索) |

P1 增加:
| Node Kind | 说明 |
|---|---|
| `sequence` | extends uvm_sequence 的类 (特殊 class subtype) |
| `test` | extends uvm_test 的类 |
| `uvm_component` | extends uvm_component 的通用分类 (driver/monitor/env/agent/scoreboard) |

### 验证侧 edge kind 扩展

| Edge Kind | 方向 | 说明 |
|---|---|---|
| **EXTENDS** | class→class | 继承链 (已有) |
| **INSTANTIATES** | class→class / module→module | factory 创建 或 硬件实例化 |
| **REFERENCES** | node→node | 类型引用 (变量声明、virtual interface、TLM port) |
| **CALLS** | function/task→function/task | 方法调用 (保留，但不叫 explore/flow) |
| **OVERRIDES** | method→method | 子类覆写父类 phase 方法 |
| **IMPORTS** | file/package→package | import 关系 (已有) |
| **CONTAINS** | 父→子 | 层级包含 (已有) |

### SVA、约束、覆盖率的 AST 语义 (P0)

这三者在验证代码中与 class 同等重要，且均可从 AST 提取。

#### SVA (SystemVerilog Assertions)

```systemverilog
module fifo(input logic clk, input logic push, input logic pop);
  // 命名 property + sequence
  property push_no_overflow;
    @(posedge clk) push |-> !overflow;
  endproperty

  sequence fifo_full_seq;
    cnt == DEPTH;
  endsequence

  // 断言实例化
  assert property (push_no_overflow) else $error("overflow");
  assume property (fifo_full_seq |=> pop);
  cover property (push ##1 pop);

  // immediate assert
  always_comb begin
    assert (cnt >= 0) else $fatal;
  end
endmodule

// bind 绑定
bind fifo fifo_checker u_checker();
```

| Node Kind | AST 来源 | 说明 |
|---|---|---|
| `property` | `property_declaration` → 可选 name | 命名 temporal property |
| `sequence` | `sequence_declaration` → 可选 name | 命名 temporal sequence |
| `assert` | `concurrent_assertion_item` / `immediate_assertion_statement` | `assert property(...)` 或 `assert(...)` |
| `assume` | `concurrent_assertion_item` / `immediate_assume_statement` | 形式验证假设 |
| `cover_property` | `concurrent_assertion_item` | 覆盖率 property |
| `checker` | `checker_declaration` | 绑定到模块的断言检查器 |

| Edge Kind | 方向 | 说明 |
|---|---|---|
| **DECLARES** | module/checker→property/sequence/assert | 模块包含断言 |
| **REFERENCES** | assert/cover→property/sequence | 断言引用 property |
| **REFERENCES** | bind→checker | bind 绑定检查器 |

#### 约束 (Constraints)

```systemverilog
class axi_transfer extends uvm_sequence_item;
  rand bit [7:0] addr;
  rand bit [31:0] data;
  rand bit is_write;

  constraint addr_align {
    addr[1:0] == 2'b00;
  }

  constraint write_data_valid {
    is_write -> data != 0;
  }

  constraint size_order {
    solve is_write before data;
  }
endclass
```

| Node Kind | AST 来源 | 说明 |
|---|---|---|
| `constraint` | `constraint_declaration` — `constraint_block` | 命名约束块 |
| `rand_field` | 类型声明中带 `rand`/`randc` 的变量 | 随机化字段 |

| Edge Kind | 方向 | 说明 |
|---|---|---|
| **CONTAINS** | class→constraint | 类包含约束 |
| **REFERENCES** | constraint→rand_field | 约束引用随机字段 |
| **SOLVES_BEFORE** | constraint→field→field | solve...before 顺序 |

#### 覆盖率 (Coverage)

```systemverilog
class my_agent extends uvm_agent;
  covergroup cg_transfer @(posedge clk);
    option.per_instance = 1;

    addr_cp: coverpoint vif.mon_cb.addr {
      bins low = {[0:63]};
      bins mid = {[64:191]};
      bins high = {[192:255]};
      illegal_bins reserved = {[8:15]};
    }

    data_cp: coverpoint vif.mon_cb.data;

    addr_x_data: cross addr_cp, data_cp {
      ignore_bins ignored = binsof(addr_cp) intersect {0};
    }
  endgroup

  function void sample_cg();
    cg_transfer.sample();
  endfunction
endclass
```

| Node Kind | AST 来源 | 说明 |
|---|---|---|
| `covergroup` | `covergroup_declaration` | 覆盖率组 |
| `coverpoint` | `coverpoint` — covergroup 子节点 | 覆盖率采样点 |
| `cross` | `cross` — covergroup 子节点 | coverpoint 交叉 |
| `coverage_option` | covergroup 内的 `option.xxx = yyy` | 覆盖率选项 |

| Edge Kind | 方向 | 说明 |
|---|---|---|
| **CONTAINS** | class/module→covergroup | 包含覆盖率组 |
| **CONTAINS** | covergroup→coverpoint/cross | 包含采样点 |
| **REFERENCES** | coverpoint→signal/field | 采样点引用信号 |
| **CROSSES** | cross→coverpoint | 交叉覆盖关系 |

### P0 不做（需运行时/仿真信息）

```
TLM connection      — port.connect(imp) 需仿真运行时
factory override    — set_type_override_by_type 在 build_phase 中动态执行
config chain        — uvm_config_db::set→get 的匹配需要运行时路径+类型
sequence→sequencer  — uvm_do / start() 的绑定是动态的
RTL signal trace    — 交给 xdebug
```

### 为什么要区分 RTL 和验证语义

对 AI Agent 而言，"`my_driver extends uvm_driver`"和"`axi_fifo u_fifo()`"都是结构事实，但 AI 的后续行为完全不同:

- 看到 `module A instantiates module B` → AI 应该展开 B 的内部结构
- 看到 `env.agent.driver` 的引用链 → AI 应该理解 UVM 分层架构，不需要展开每个 component 的内部
- 看到 `extends uvm_driver` → AI 应该知道这个类是 driver，行为模式是 "get item → drive → item_done"
- 看到 `common_fifo` 的实例化 → AI 应该读 common block summary 而非深入 FIFO 内部

这就是 common block summary hook 和验证语义分类的协同价值。

## 修正后的阶段计划

### Phase 1: 核心索引 (P0) — 4-5 天

**目标**: 基本的 SV 结构索引能力。

```
xcodegraph index --filelist filelist.f --db .xcodegraph/index.sqlite
```

交付物:
- **filelist parser** — `-f` 递归展开, `+incdir+`, `+define+`, `-y`/`-v`, 注释/空白处理, `${VAR}` 展开
- **SQLite schema** — files/nodes/edges/unresolved_refs/meta 五表
- **tree-sitter backend** — 唯一 parser，复刻 JS 版 SV extractor 的 visitNode 逻辑
- **indexer** — 批量索引管道，单文件 parse 失败不中断整体
- **CLI**: `index`, `status`, `search`, `node`, `definition`, `file-symbols`, `clean`
- **所有 CLI 支持 `--json` 输出**

P0 node kind:
```
module, interface, package, class, function, task,
instance, import, parameter, typedef, tlminitf,
config_db_call,
// SVA
property, sequence, assert, assume, cover_property, checker,
// 约束
constraint, rand_field,
// 覆盖率
covergroup, coverpoint, cross, coverage_option
```

P0 edge kind:
```
CONTAINS, INSTANTIATES, EXTENDS, IMPORTS, REFERENCES,
CALLS, OVERRIDES, DECLARES, CROSSES, SOLVES_BEFORE
```

目录结构:
```
xcodegraph/
  xcodegraph/
    cli.py
    core/
      filelist.py
      storage.py
      schema.sql
      parser.py              ← tree-sitter extractor
      visitor.py             ← visit_node 逻辑 (直译 JS 版)
      indexer.py
      query.py
      reindex.py
      status.py
      common_block.py
      models.py
```

### Phase 2: 实例化与层次 (P0) — 3-4 天

**目标**: 支持 module hierarchy 查询。

交付物:
- **instance extractor** — module/interface instantiation
- **INSTANTIATES edge** + **INSTANTIATED_BY 反向查询**
- **hierarchy** — 从 top module 展开 instance tree (支持 `--depth`)
- **unresolved instance type** — 记录到 unresolved_refs 表
- **CLI**: `hierarchy`, `instantiated-by`, `imports`, `includes`, `extends`

验证:
- `xcodegraph instantiated-by axi_fifo` 返回正确的实例化位置
- `xcodegraph hierarchy top_tb --depth 3` 返回正确的树结构
- 找不到的 module type 出现在 unresolved_refs 中

### Phase 3: MCP Server (P0) — 2-3 天

**目标**: AI Agent 可直接查询。

硬性约束:
- MCP handler 只做参数校验、调用 core API、格式化返回、错误包装
- 禁止在 MCP handler 中写解析逻辑、SQL 拼接、业务状态处理

MCP tools (P0):
```
xcodegraph_status        — 索引状态 + stale 检测
xcodegraph_reindex       — 全量/增量重建索引
xcodegraph_reindex_file  — 单文件重索引
xcodegraph_search        — 按名称/kind 搜索
xcodegraph_node          — 节点详情 + 关联 edges
xcodegraph_definition    — 跳转定义
xcodegraph_file_symbols  — 文件所有符号
xcodegraph_hierarchy     — 实例层次树
xcodegraph_instantiated_by
xcodegraph_imports / includes / extends
```

MCP 暂缓 (P2):
```
xcodegraph_callers / callees / explore / signal_flow
```

返回原则:
```
短 → 稳定 → 可引用 → 含文件行号 → 明确 stale → 明确 warning → 明确 unresolved
```

### Phase 4: Reindex 与 Stale 检测 (P0) — 2-3 天

**目标**: 替代 watchdog 的索引更新机制。

交付物:
- **Git HEAD stale check** — `status` 命令比较当前 HEAD vs 索引记录的 HEAD
- **file hash tracking** — `files` 表存储 sha256 + mtime
- **reindex --file** — 单文件增量重索引
- **reindex --changed** — 检测所有变更文件并重索引
- **reindex --full** — 全量重建
- **stale-policy**: `warn` (默认) / `auto-reindex` / `error`
- **MCP reindex tools** — AI 修改代码后主动调用

meta 表记录:
```
repo_root, git_head, git_branch, filelist_path, filelist_hash,
defines_hash, incdirs_hash, schema_version, parser_version,
backend, created_at, updated_at
```

索引更新触发矩阵:
```
Git HEAD 变化   → status stale → 用户/AI 决定 reindex
AI 修改文件     → AI 显式 xcodegraph_reindex_file
filelist/define → 强制 full reindex
schema/parser   → 强制 full reindex
```

### Phase 5: 验证增强 (P1) — 3-4 天

**目标**: 更适合验证 Agent 使用。

交付物:
- **UVM class kind inference** — component/sequence/monitor/scoreboard/driver/env/agent 粗分类
- **class extends chain** — 完整继承链查询
- **package/import relationship** — 跨文件包引用
- **include relationship** — `` `include `` 文件追踪 + 找不到时进入 unresolved
- **common block summary hook** — 配置文件驱动的公共 IP 摘要，指导 AI 不盲目深入内部

common block 配置示例:
```json
{
  "patterns": [
    {
      "name": "common_fifo",
      "path_regex": ".*/common/.*/fifo.*\\.sv",
      "kind": "fifo",
      "summary": "Common FIFO block. Treat as enqueue/dequeue storage first."
    }
  ]
}
```

### Phase 6: 高级查询 (P2) — 延后

可选增强，不进 P0:
```
task/function callers/callees   — 仅适用 function/task/method
assign/always block summary      — 粗粒度摘要
covergroup/property/sequence     — 提取但不做 SVA 语义
AI-oriented module summary        — 自然语言摘要
```

明确不做:
```
RTL signal flow / dataflow trace → 交给 xdebug
完整 macro elaboration            → 交给仿真器
generate elaboration              → 交给仿真器
IDE 级实时分析                   → 非目标场景
```

## 优先级总览

### P0 (必须立刻做)
```
Phase 1: 核心索引 (filelist + SQLite + tree-sitter)
Phase 2: 实例化与层次 (hierarchy + instantiated-by + 验证语义 edges)
Phase 3: MCP server (thin adapter)
Phase 4: reindex + stale 检测 (Git HEAD + file hash)
```

### P1 (第二优先级)
```
Phase 5: UVM component 分类 + common block summary + include/import/extends 完善
```

### P2 (延后)
```
Phase 6: covergroup + property/sequence + AI module summary
```

## P0 最小闭环

P0 完成时必须具备:
```
1.  filelist parser
2.  SQLite schema (files/nodes/edges/unresolved_refs/meta)
3.  tree-sitter backend
4.  CLI: index / status / search / node / definition / file-symbols / clean
5.  CLI: hierarchy / instantiated-by / imports / includes / extends
6.  CLI: --json 输出
7.  MCP server (thin adapter)
8.  MCP: status / reindex / reindex_file / search / node / definition / file_symbols / hierarchy / instantiated_by
9.  Git HEAD stale 检测
10. reindex --file / --changed / --full
11. 单文件 parse 失败不中断索引，记录 warning
12. node kind 覆盖: module/interface/package/class/function/task/instance/import/parameter/typedef/tlminitf
13. edge kind 覆盖: CONTAINS/INSTANTIATES/EXTENDS/IMPORTS/REFERENCES/CALLS/OVERRIDES
```

## 测试策略

最小测试集放在 `tests/data/simple/`:

RTL 用例:
```systemverilog
// module + instance
module fifo(input logic clk, input logic rst_n); endmodule
module top; fifo u_fifo(); endmodule

// package + import
package my_pkg; typedef enum { IDLE, BUSY } state_e; endpackage
module top; import my_pkg::*; endmodule

// include
`include "defs.svh"
```

验证用例:
```systemverilog
// class + extends (UVM component hierarchy)
class my_driver extends uvm_driver #(item);
  virtual my_if vif;
  task run_phase(uvm_phase phase);
    seq_item_port.get_next_item(req);
  endtask
endclass

// factory instantiation
class my_env extends uvm_env;
  my_agent m_agent;
  function void build_phase(uvm_phase phase);
    m_agent = my_agent::type_id::create("m_agent", this);
  endfunction
endclass

// TLM port
class my_monitor extends uvm_monitor;
  uvm_analysis_port #(item) ap;
endclass

// 约束
class axi_item extends uvm_sequence_item;
  rand bit [7:0] addr;
  rand bit [31:0] data;
  constraint addr_align { addr[1:0] == 2'b00; }
endclass

// SVA
property push_no_overflow;
  @(posedge clk) push |-> !overflow;
endproperty
assert property (push_no_overflow) else $error("overflow");

// 覆盖率
covergroup cg_xfer @(posedge clk);
  addr_cp: coverpoint vif.mon_cb.addr {
    bins low = {[0:63]};
  }
  addr_x_data: cross addr_cp, data_cp;
endgroup
```

验证项:
```
RTL:
  module/interface/package 识别      → nodes 表
  module→module INSTANTIATES        → edges 表
  package→IMPORTS edge              → edges 表
  filelist 展开                      → -f 嵌套 + 去重

验证语义:
  class EXTENDS chain               → 完整继承链
  class REFERENCES class (HAS_A)    → 类型引用
  factory create → INSTANTIATES     → type_id::create() 识别
  virtual interface → REFERENCES    → class→interface 绑定
  TLM method → CALLS                → 方法调用追踪
  phase 覆写 → OVERRIDES            → build_phase/run_phase 等

SVA:
  property/sequence 定义            → property/sequence node
  assert/assume/cover 位置           → assert/assume/cover_property node
  assert→property REFERENCES        → 断言引用 property
  checker + bind                     → checker node + bind 关系

约束:
  constraint 块识别                  → constraint node
  rand 字段识别                      → rand_field node
  class→constraint CONTAINS          → 包含关系
  constraint→rand_field REFERENCES   → 约束引用字段

覆盖率:
  covergroup 声明                    → covergroup node
  coverpoint 声明                    → coverpoint node
  cross 声明                         → cross node + CROSSES edge
  coverpoint→signal REFERENCES       → 采样点引用的信号
  class→covergroup CONTAINS          → 包含关系
```

## 验证

```bash
# CLI 端到端
xcodegraph index --filelist tests/data/simple/filelist.f
xcodegraph search fifo --json
xcodegraph hierarchy top --json
xcodegraph instantiated-by fifo --json

# MCP
xcodegraph serve --mcp
```
