## 摘要

本次 PR 为平台新增「自定义策略（Python）」进阶方案，与已有的「零代码策略工作台」（新手模板）形成互补：

1. 提供 `BaseStrategy` 基类 + `register_strategy` 装饰器（OpenMMLab `register_module` 风格），进阶用户只需继承基类、重写 `generate_signals`；
2. 用 `__init__` 签名自省自动生成网页参数表单——策略参数个数、类型（int/float/bool/str）、默认值完全由用户决定，不再囿于固定参数；
3. 支持「网页内编写」与「上传 `.py` 文件」两种方式注册并保存策略；
4. 用户策略与内置策略统一进入 `StrategyCatalog`，可直接在既有「单次回测与复盘」「参数优化」等流程中使用；
5. 用户代码在受限命名空间（导入白名单）中执行，启动加载单条失败时降级容错，不影响其它页面。

## 改动详情

### 新增文件（8 个新文件，含 1 个新包目录）

| 文件 | 内容 |
|---|---|
| `src/quant_platform/user_strategies/__init__.py` | 公共 API 导出（`BaseStrategy` / `register_strategy` / `UserStrategyLoader` / `UserStrategyStore`） |
| `src/quant_platform/user_strategies/base.py` | `BaseStrategy` 基类（继承内置 `Strategy`）+ `register_strategy` 装饰器 + `__init__` 签名自省生成参数表单 |
| `src/quant_platform/user_strategies/loader.py` | `UserStrategyLoader`：受限命名空间执行用户源码 + 加载校验（重复注册/非法标识/缺默认值/抽象类） |
| `src/quant_platform/user_strategies/store.py` | `UserStrategyStore`：策略源码与元数据持久化到 `runtime/user_strategies/<标识>/` |
| `src/quant_platform/user_strategies/starter.py` | 网页代码编辑器起始模板 |
| `src/quant_platform/web/pages/8_custom_strategy.py` | 新网页页面：编写策略 / 上传文件 / 我的策略 三页签，含自动参数表单与回测 |
| `tests/unit/test_user_strategies.py` | 10 个单元测试（注册/自省/实例化/禁止导入/重复注册/缺默认值/非法标识/存储 CRUD/目录集成） |
| `docs/custom_strategy.md` | 完整使用文档 |

### 修改文件（6 个）

| 文件 | 改动 |
|---|---|
| `src/quant_platform/strategies/discovery.py` | 新增 `StrategyCatalog.register_classes()`：外部策略可注册进目录，与内置策略重名时报错拒绝 |
| `src/quant_platform/application/backtest_service.py` | 启动时自动加载已保存用户策略进目录；新增 `user_strategy_root` 属性与 `user_strategy_errors` 容错收集 |
| `src/quant_platform/web/app.py` | 新增「自定义策略（Python）」导航入口（🐍） |
| `README.md` | 更新特性清单、「当前策略与回测规则」与「新增自己的策略」章节 |
| `.gitignore` | 新增 `/runtime/user_strategies/`（用户策略属运行时数据，不提交） |
| `.tasks/current.md` | 任务记录 |

### 行为变化

- `BacktestService.available_strategies()` 返回值会包含已保存的用户策略，用户策略自动出现在「单次回测与复盘」「参数优化」等既有流程的策略下拉框中；
- 用户策略的 `strategy_plugin` / `strategy_id` / `strategy_parameters` 与内置策略一致，回测快照、结果复现流程无需改动；
- 用户策略加载失败（语法错误、校验不通过）只记录到 `user_strategy_errors`，不会中断平台启动或其它页面。

## 验证

- `python -m pytest -q`：`94 passed`（含新增 10 个，既有测试无回归）
- `python -m ruff check`（本次改动文件）：`All checks passed!`
- `python -m compileall -q src tests`：无语法错误
- 冒烟验证通过：注册 → 参数自省 → 实例化 → 禁止 `import os` → 存储往返 → 目录集成全链路

## 使用方式

用户在网页「自定义策略（Python）」中编写或上传如下形式的代码即可：

```python
@register_strategy("oversold_rebound", display_name="超跌反弹", description="按 RSI 超卖程度选股")
class OversoldReboundStrategy(BaseStrategy):
    def __init__(self, trend_ma: int = 60, rsi_window: int = 14, rsi_buy: float = 40.0, ...):
        self.trend_ma = trend_ma
        ...

    def generate_signals(self, context) -> list[Signal]:
        ...
        return signals   # score 越大越优先入选
```

平台自动生成 `trend_ma` / `rsi_window` / `rsi_buy` 等参数控件，无需任何 `StrategyParameter` 声明。完整说明见 `docs/custom_strategy.md`。

## 迁移说明

- 已保存的自定义策略存放于 `runtime/user_strategies/<标识>/`（`strategy.py` + `metadata.json`），平台启动时自动加载；加载失败只在页面顶部折叠展示，不中断其它页面；
- `/runtime/user_strategies/` 已加入 `.gitignore`，与 `runtime/runs/` 等运行时数据一致，不会被提交；
- 无磁盘格式迁移，现有内置策略、零代码策略与历史回测均不受影响。

## 已知未包含（不在本次范围）

- **进程级强隔离**：当前加载器是「防误操作」的软沙箱（导入白名单），并非安全边界；如需硬隔离需将策略执行迁移到独立子进程 + IPC，建议另立 PR；
- 工作区中与本次 PR 无关的其他未提交改动（LLM 多智能体、智能体分析台、pytdx 数据源等）不包含在本 PR，请按下方注意事项选择性暂存。

## 需要重点 review 的地方

- `base.py`：`__init__` 签名自省与 `param_specs` 覆盖的优先级、`strategy_id` 注入逻辑；
- `loader.py`：受限命名空间构造与导入白名单边界（`os`/`sys`/`importlib` 等已拦截）；
- `backtest_service.py`：启动加载用户策略的容错路径（单条失败不中断）；
- `discovery.py`：`register_classes` 与内置策略重名时的报错行为。

---

## 提交前注意事项（重要）

当前工作区除本 PR 内容外，还包含**其他未提交改动**，请勿直接 `git add -A`：

- **本 PR 相关（新增）**：`src/quant_platform/user_strategies/`、`src/quant_platform/web/pages/8_custom_strategy.py`、`tests/unit/test_user_strategies.py`、`docs/custom_strategy.md`
- **本 PR 相关（修改，可整体暂存）**：`src/quant_platform/application/backtest_service.py`、`.gitignore`、`.tasks/current.md`
- **本 PR 相关（修改，但混有他人改动，建议 `git add -p` 只选本 PR 的 hunk）**：`src/quant_platform/strategies/discovery.py`（他人的日志容错改动）、`src/quant_platform/web/app.py`（他人的「智能体分析台」入口）、`README.md`（他人的 LLM 多智能体说明与引号格式调整）
- **非本 PR（建议另开分支/PR）**：`pyproject.toml`、`src/quant_platform/web/pages/1_data_management.py`、`2_research.py`、`4_paper_trading.py`、`welcome.py`、`src/quant_platform/agents_bridge/`、`src/trading_agents/`、`src/quant_platform/strategies/llm_multi_agent.py`、`src/quant_platform/web/pages/8_agent_lab.py`、`src/quant_platform/data/pytdx_*.py`、`src/quant_platform/data/providers/pytdx_provider.py` 及对应测试/文档
- **运行时数据（已加入 `.gitignore`，无需处理）**：`runtime/user_strategies/`（其中 `oversold_rebound` 是你通过网页保存的策略）、`runtime/agent_cache/`、`runtime/agent_runs/`

建议暂存命令（PowerShell，项目根目录）：

```powershell
git add src/quant_platform/user_strategies src/quant_platform/web/pages/8_custom_strategy.py tests/unit/test_user_strategies.py docs/custom_strategy.md src/quant_platform/application/backtest_service.py .gitignore .tasks/current.md
git add -p src/quant_platform/strategies/discovery.py src/quant_platform/web/app.py README.md
git commit -m "feat: 新增自定义策略（Python）进阶模式，支持网页编写/上传策略并自动生成参数表单"
```

建议 PR 标题：

```text
feat: 新增「自定义策略（Python）」进阶模式，支持网页编写/上传策略并自动生成参数表单
```


当前分支为 `alpha/sch`，提交前请确认 PR 目标分支（`main` 或团队约定分支）。

---

## 追加记录（2026-08-21）

### 主题一：融合 EasyQuant 多智能体决策框架

将 `D:\code\vibecoding\trading_quant` 项目的多智能体能力融合到当前 AlphaQuant 工作目录：

| 新增文件 | 说明 |
|---|---|
| `src/trading_agents/` | 完整多智能体决策框架（agents / orchestrator / llm / memory / prompts / schemas / utils） |
| `src/quant_platform/agents_bridge/` | 桥接层：将 AlphaQuant DataFrame 适配为 trading_agents 数据协议，决策映射为 Signal |
| `src/quant_platform/strategies/llm_multi_agent.py` | 回测策略插件：每个调仓日对候选标的调用 LLM 流水线生成信号 |
| `src/quant_platform/web/pages/8_agent_lab.py` | 智能体分析台：单票 LLM 多智能体研究并展示全部中间产物 |
| `src/quant_platform/data/pytdx_backfill.py` | PyTDX 数据回填适配器 |
| `src/quant_platform/data/providers/pytdx_provider.py` | PyTDX 数据提供者 |
| `tests/unit/test_agents_bridge.py` | 桥接层单元测试 |
| `tests/unit/test_llm_multi_agent_strategy.py` | 多智能体策略测试 |
| `tests/unit/test_dataframe_provider.py` | DataFrame Provider 测试 |
| `tests/unit/test_pytdx_provider.py` | PyTDX Provider 测试 |
| `docs/llm_agent_strategy.md` | LLM 多智能体策略与智能体分析台使用文档 |

| 修改文件 | 改动 |
|---|---|
| `pyproject.toml` | 新增 `pydantic>=2.5`、`requests>=2.31`、`rich>=13.0` 依赖；新增 `tdx` optional；新增 mypy overrides |
| `README.md` | 合并 LLM 多智能体功能说明、项目结构（agents_bridge / trading_agents）、依赖提示 |
| `src/quant_platform/web/app.py` | 导航新增「智能体分析台」入口 |

### 主题二：前端界面优化

| 文件 | 改动 |
|---|---|
| `.streamlit/config.toml`（新增） | 深色金融主题配置：主色调金色 `#e8b923`、深色背景 `#0e1117` |
| `src/quant_platform/web/welcome.py` | 「三步开始」升级为卡片式布局（`st.container(border=True)`），按钮全宽 |
| `src/quant_platform/web/pages/1_data_management.py` | 顶部 6 个核心指标包裹进带标题的边框容器，信息层级更清晰 |
| `src/quant_platform/web/pages/2_research.py` | **Bug 修复**：基准回测 `selectbox` 同时用 `index` 强控和手动写 `session_state` 导致需选两次才能切换；改为 `key="research_baseline_run_id"` 让 Streamlit 自管理状态 |
| `src/quant_platform/web/pages/4_paper_trading.py` | **Bug 修复**：同上，模拟账户 `selectbox` 同样修复 |

### 主题三：LLM Provider 图标与自定义模型

| 文件 | 改动 |
|---|---|
| `src/quant_platform/web/pages/8_agent_lab.py` | Provider 下拉框加 emoji 图标（🧪 mock / 🌙 kimi / 🅾️ openai / 🔮 deepseek / 🌀 qwen / 📐 glm / 🖥️ ollama / ⚙️ custom）；选择 custom 时展开 Base URL + 模型名输入 |
| `src/quant_platform/strategies/llm_multi_agent.py` | 策略参数：llm_provider 增加 choices（含 custom），新增 `custom_base_url` 和 `custom_model` 参数；`from_parameters` 与 `__init__` 透传自定义配置 |
| `src/trading_agents/llm/base.py` | 注册 `CustomClient`（`OpenAICompatClient` 子类，`default_base_url=""`） |
| `src/quant_platform/agents_bridge/runner.py` | `AgentRunner.__init__` 新增 `base_url` 和 `model` 参数，自定义时覆盖 `TradingConfig.llm` 配置 |

### 主题四：策略发现健壮性

| 文件 | 改动 |
|---|---|
| `src/quant_platform/strategies/discovery.py` | 单个策略模块导入失败（如缺少 `pydantic`）时记录警告并跳过，不再导致整个策略发现崩溃；其他策略仍可正常使用 |

### 验证

- `python -m compileall -q src tests`：全部通过
- `python -m py_compile` 逐个检查新增/修改文件：无语法错误

