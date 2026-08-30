## 摘要

本次 PR 为平台新增两大能力：

1. **自定义策略（Python）进阶方案**：进阶用户可直接在网页编写或上传 `.py` 策略，继承 `BaseStrategy` 并注册后回测，参数由 `__init__` 签名自动生成表单，不再囿于固定参数；
2. **LLM 多智能体分析与数据源增强**：集成多智能体决策框架（分析师团队、多空辩论、风控与组合经理审批）、智能体分析台页面，并新增 pytdx 行情数据源。

## 改动详情

### 1. 自定义策略（Python）

- `src/quant_platform/user_strategies/`：`BaseStrategy` 基类 + `register_strategy` 装饰器（OpenMMLab `register_module` 风格）+ `__init__` 签名自省生成参数表单；`UserStrategyLoader`（受限命名空间 + 导入白名单）与 `UserStrategyStore`（持久化到 `runtime/user_strategies/`）；
- `src/quant_platform/web/pages/8_custom_strategy.py`：编写策略 / 上传文件 / 我的策略 三页签，含自动参数表单与回测；
- 集成：`StrategyCatalog.register_classes()` 支持外部策略注册；`BacktestService` 启动时自动加载已保存用户策略，单条失败不中断；
- 测试：`tests/unit/test_user_strategies.py`（10 个用例）；文档：`docs/custom_strategy.md`。

### 2. LLM 多智能体分析

- `src/trading_agents/`：多智能体决策框架（分析师、多空研究员、交易员、风控、组合经理、回测回放、记忆沉淀、LLM 抽象）；
- `src/quant_platform/agents_bridge/`：平台与决策流水线的桥接层；
- `src/quant_platform/strategies/llm_multi_agent.py`：LLM 多智能体策略插件；
- `src/quant_platform/web/pages/8_agent_lab.py`：智能体分析台页面（单只股票完整分析流程展示）；
- 文档：`docs/llm_agent_strategy.md`；测试：`test_agents_bridge.py`、`test_llm_multi_agent_strategy.py`。

### 3. 数据源与页面完善

- pytdx 数据源：`data/pytdx_backfill.py`、`data/providers/pytdx_provider.py` 及 dataframe provider 与对应测试；
- 页面完善：数据管理、参数研究、模拟交易、欢迎页；
- `StrategyCatalog` 增加策略模块导入失败的日志容错；
- 依赖：`pyproject.toml` 新增 `pydantic`、`requests`、`rich` 等；
- `.gitignore`：忽略 `runtime/user_strategies/`、`runtime/agent_cache/`、`runtime/agent_runs/` 等运行时数据。

## 验证

- `python -m pytest -q`：`94 passed`（含新增的自定义策略与多智能体测试，无回归）
- `python -m ruff check`（本次改动文件）：`All checks passed!`
- `python -m compileall -q src tests`：无语法错误

## 已知未包含（不在本次范围）

- 自定义策略的**进程级强隔离**：当前加载器是「防误操作」的软沙箱（导入白名单），并非安全边界；如需硬隔离需将策略执行迁移到独立子进程 + IPC，建议另立 PR；
- LLM 多智能体依赖外部大模型 API，需自行配置密钥；当前为研究/教学用途，不连接真实券商。

## 需要重点 review 的地方

- `user_strategies/base.py`：`__init__` 签名自省与 `param_specs` 覆盖优先级、`strategy_id` 注入；
- `user_strategies/loader.py`：受限命名空间与导入白名单边界；
- `agents_bridge/` 与 `trading_agents/`：平台与多智能体流水线的职责边界与状态传递；
- `backtest_service.py`：启动加载用户策略的容错路径。
