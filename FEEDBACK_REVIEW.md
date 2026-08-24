# 外部反馈评审与变更说明（AlphaQuant_v2）

本文档逐条回应外部对 AlphaQuant 提出的 15 条改进建议，说明哪些已实现、
如何实现的、哪些暂缓及理由。所有改动均在 `AlphaQuant_v2` 副本中完成，
原 `AlphaQuant` 目录未受影响。

## 总览

| # | 建议 | 状态 | 说明 |
|---|------|------|------|
| 1 | 首页增加新手引导 | ✅ 已实现 | 首页新增六步分步向导 |
| 2 | 整合策略创建入口 | ✅ 已实现 | 新增「策略创作中心」统一入口 |
| 3 | 自然语言创建策略 | ✅ 已实现 | 新增「自然语言建策略」页 + `nl_builder` 模块 |
| 4 | 自定义策略安全检查 | ✅ 已实现 | 注册前静态检查，阻断/警告两级 |
| 5 | 回测结果通俗诊断 | ✅ 已实现 | 回测页新增「通俗诊断」板块 |
| 6 | 强化回测可信度 | ✅ 部分实现/补强 | 训练/验证/样本外与滚动验证原本已有 |
| 7 | 模拟交易上线前检查 | ✅ 已实现 | 上线前检查清单，阻断项禁止运行 |
| 8 | 扩充研究数据 | ⏸️ 暂缓 | 需要长时间真实下载，见下文 |
| 9 | 因子基础系统 | ✅ 已实现 | `factors` 包：定义/上下文/注册表/存储约定 |
| 10 | 因子研究室 | ✅ 已实现 | 10 个内置因子 + IC/分层/换手/衰减评估页 |
| 11 | 因子清洗与组合 | ✅ 已实现 | 预处理 + 加权合成 + 一键转选股策略 |
| 12 | 接入 Qlib/LightGBM | ⏸️ 暂缓 | Windows 依赖重，见下文 |
| 13 | 模型实验室 | ⏸️ 暂缓 | 依赖第 8、12 条，统计前提不成立 |
| 14 | 深度学习模型 | ⏸️ 暂缓 | 同上，且反馈自身要求「LightGBM 稳定后再加」 |
| 15 | AI 策略创建智能体 | ✅ 核心已覆盖 | 由第 3 条覆盖核心闭环，见下文 |

## 已实现条目详述

### 1. 首页增加新手引导

- 新增 `src/quant_platform/web/guide.py`：`build_guide_steps()` 纯函数按
  「数据更新 → 股票池 → 创建策略 → 回测 → 查看结果 → 模拟交易」六步推导状态
  （已完成 ✅ / 建议下一步 👉 / 待办 ⬜）。
- `welcome.py` 首页 hero 下方渲染六步向导卡片，每步带直达按钮；
  状态由就绪度报告、策略包存储、回测记录、模拟账户本地推导，无网络访问。
- 高级参数仍折叠在各页面内部，普通用户默认只看到推荐配置。
- 测试：`tests/unit/test_guide_steps.py`。

### 2. 整合策略创建入口

- 新增 `src/quant_platform/web/pages/0_strategy_hub.py`「策略创作中心」，
  按三级组织：入门（模板）/ 普通（积木）/ 高级（Python），外加自然语言入口。
- 模板、积木、自然语言三种方式统一产出 `StrategyPackage`（JSON 策略包，
  `StrategyPackageStore`），共用同一套回测与版本管理流程；
  Python 自定义走 `user_strategies` 注册表（带第 4 条的安全检查）。
- 页面底部统一列出全部已保存策略包（含来源标签），可一键去回测。
- 导航（`web/app.py`）：「策略研究」分组以创作中心为首，新增自然语言建策略、
  因子研究室两个入口；首页模块卡片与启动器关键词同步更新。

### 3. 自然语言创建策略

- 新增 `src/quant_platform/strategies/nl_builder.py`：
  - `SYSTEM_PROMPT` 把白名单指标、比较符、协议字段完整告知模型；
  - `NLStrategyDraft`（Pydantic）初筛后再交 `RuleStrategyDefinition` 权威校验；
  - 校验失败时把错误回喂模型自动修复一次（`max_attempts=2`），仍失败则明确
    报错并引导改用模板/积木；
  - `definition_explanation()` 生成中文解释供用户确认后才保存。
- 新增页面 `pages/10_nl_strategy.py`：支持 DeepSeek / Kimi / OpenAI / 通义 /
  GLM / Ollama 本地 / 自定义 OpenAI 兼容端点（复用 `agents_bridge.llm_settings`
  的本地配置存储，API Key 只落本地 `runtime/llm_settings.json`）；
  未配置模型时明确提示改用模板或积木编辑器，不会静默失败。
- 确认保存后写入策略包（`source="nl_builder"`），与模板/积木同一流程。
- 测试：`tests/unit/test_nl_builder.py`（假 LLM 客户端，不访问网络）。

### 4. 自定义策略安全检查（前次会话完成，本次验证）

- `src/quant_platform/user_strategies/safety.py`：未来函数、参数关系、数据字段、
  禁止模块等静态检查，输出阻断/警告两级报告。
- 已接入 `pages/8_custom_strategy.py`：阻断项直接阻止保存，警告需勾选
  「我已了解上述风险」后才能继续。
- 测试：`tests/unit/test_strategy_safety.py`。

### 5. 回测结果通俗诊断（前次会话完成，本次验证）

- `src/quant_platform/backtest/diagnosis.py`：在收益率、回撤、夏普之外生成
  通俗解读（盈亏来源、影响最大的股票/时期、胜率高但亏损的原因、交易成本、
  基准对比等）。
- 已接入 `home.py` 回测复盘页的「通俗诊断」折叠板块。
- 测试：`tests/unit/test_backtest_diagnosis.py`。

### 6. 强化回测可信度

- 平台原本已有 `backtest/validity.py`（可信度审计）、
  `application/walk_forward_service.py`（滚动样本外验证）、
  `application/optimization_service.py`（参数搜索，含调参记录），
  本次未重复建设；第 7 条的上线检查会强制引用样本外验证结论。
- 参数敏感性分析可由「参数优化与稳健性验证」页的网格/随机搜索覆盖。

### 7. 模拟交易上线前检查（前次会话完成，本次验证）

- `src/quant_platform/application/paper_checklist.py`：检查数据是否最新、
  策略是否通过样本外验证、参数与代码版本是否锁定、仓位/回撤/风险限制
  是否配置、运行版本与回测版本是否一致。
- 已接入 `pages/4_paper_trading.py`：阻断项存在时「运行模拟交易」按钮禁用。
- 测试：`tests/unit/test_paper_checklist.py`。

### 9 / 10 / 11. 因子系统、因子研究室、因子清洗与组合

- `src/quant_platform/factors/`（本次补齐 `__init__.py`、修正预处理实现）：
  - `base.py`：`FactorDefinition`（名称、中文说明、公式、所需字段、最小历史
    长度、方向、版本）+ `FactorContext`（`as_of` 截断的防未来数据锚点）；
  - `builtins.py`：10 个内置量价因子（动量、反转、波动率、成交额变化、RSI、
    新高距离、量比、量价相关性、乖离率、振幅），全部为因果算子；
  - `evaluation.py`：覆盖率、IC / Rank IC / IR、五分位收益、多空收益、
    换手率、前后半段 Rank IC 对比（样本外稳定性/衰减提示）；
  - `preprocess.py`：MAD/分位去极值、z-score 标准化、中位数/剔除缺失、
    行业中性化（security_master 无行业字段，需显式提供映射，否则明确跳过）。
    本次将 groupby.apply 实现重写为 transform 实现，修复了 `date` 列丢失的
    bug；
  - `combine.py`：多因子等权/IC 加权/自定义权重合成（合成前按日截面标准化、
    自动归一），因子相关性矩阵（按日 Spearman 均值）与贪心高相关剔除，
    `CompositeFactor` 可直接交给评估器。
- 新增页面 `pages/9_factor_lab.py`「因子研究室」：因子库浏览 / 单因子评估
  （指标卡 + 分组收益柱状图 + Rank IC 走势 + 衰减警告）/ 因子组合
  （清洗选项、三种权重、相关性矩阵、高相关剔除、合成评估）。
- 一键转换成选股策略：新增策略插件 `strategies/factor_composite.py`
  （`plugin_name="factor_composite"`，被 `StrategyCatalog` 自动发现），
  因子研究室可一键携带参数跳转回测页直接运行，复用现有回测、风控与
  模拟交易全链路。
- 测试：`tests/unit/test_factor_combine.py`、
  `tests/unit/test_factor_composite_strategy.py`。

### 15. AI 策略创建智能体（核心已由第 3 条覆盖）

反馈要求该智能体：理解策略描述 → 发现歧义 → 生成规则 → 调用检查器 →
自动修复 → 用户确认后注册。第 3 条的 `NLStrategyBuilder` 已实现
「生成 → 强校验 → 错误回喂自动修复 → 中文解释 → 用户确认 → 注册」的完整闭环，
区别仅在于「发现歧义主动提问」目前由用户重新描述完成，而非多轮对话。
完整的多轮对话式智能体可作为后续增强，与现有「智能体分析台」
（负责股票研究和观点分析）保持明确分工。

## 暂缓条目及理由

### 8. 扩充研究数据（全 A 股多年历史等）

数据下载管道（akshare/baostock/ifind/pytdx 多源回退、增量回补）已经存在，
但「全 A 股多年历史 + 财报 + 资金流」是一次长时间的网络下载运维动作，
不适合在代码评审任务里顺带执行；且 security_master 目前无行业字段，
行业中性化等依赖第 8 条补数据后才完整。建议作为独立运维任务执行。

### 12. 接入 Qlib 和机器学习

Qlib 在 Windows 上依赖较重（Cython 编译、特定 numpy 版本），贸然引入会
破坏当前「纯 pip 可装」的部署体验。因子系统（第 9-11 条）已按
Qlib 式长表约定设计，未来接入时只需补一个数据导出适配层。

### 13 / 14. 模型实验室与深度学习

反馈自身要求「在 LightGBM 流程稳定、数据量足够以后，再加入深度学习」。
当前本地只有约 8 只股票的行情，横截面统计上不成立；待第 8 条数据扩充
与第 12 条 LightGBM 流程落地后再做，避免提前交付一个无法验证的功能。

## 验证结果

- 单元 + 集成测试：**202 passed**（新增 21 个：factor_combine 7、
  factor_composite_strategy 3、nl_builder 6、guide_steps 4，另修复
  preprocess 后原有用例全部保持通过）。
- `ruff check src tests`：**All checks passed**（修复了前次会话遗留的
  evaluation.py B007/B905 与 test_agent_sources.py E501）。
- `mypy`（strict）：本次新增模块（factors、nl_builder、factor_composite、
  guide）零错误；存量 `trading_agents/llm` 有 7 个既有类型标注问题
  （非本次引入，未改动）。
- 页面文件均通过 `py_compile`；`factor_composite` 插件经 `StrategyCatalog`
  自动发现验证。

## 变更文件清单

新增：

- `src/quant_platform/factors/__init__.py`、`factors/combine.py`
- `src/quant_platform/strategies/factor_composite.py`、`strategies/nl_builder.py`
- `src/quant_platform/web/guide.py`
- `src/quant_platform/web/pages/0_strategy_hub.py`（策略创作中心）
- `src/quant_platform/web/pages/9_factor_lab.py`（因子研究室）
- `src/quant_platform/web/pages/10_nl_strategy.py`（自然语言建策略）
- `tests/unit/test_factor_combine.py`、`test_factor_composite_strategy.py`、
  `test_nl_builder.py`、`test_guide_steps.py`

修改：

- `src/quant_platform/factors/preprocess.py`（transform 重写，修 date 列丢失 bug）
- `src/quant_platform/factors/evaluation.py`（ruff B007/B905）
- `src/quant_platform/web/app.py`（导航注册新页面）
- `src/quant_platform/web/welcome.py`（新手引导向导 + 新模块卡片 + 启动器关键词）
- `src/quant_platform/web/home.py`（接收因子研究室的合成参数跳转）
- `tests/unit/test_agent_sources.py`（E501 超长行）

（第 4、5、7 条对应文件由前次会话新增：`user_strategies/safety.py`、
`backtest/diagnosis.py`、`application/paper_checklist.py` 及其接线改动，
本次仅做验证与缺陷修复。）
