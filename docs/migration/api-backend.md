# 第三步：独立 FastAPI 后端

日期：2026-10-07。代码基线：`49e3143d9955c37742221d47dac1c2a4d3c0d9a1`。

第三步交付独立的后端入口和核心业务接口，共 **49 个 HTTP 操作**。第四步已新增持久化后台任务，当前累计 **57 个操作**，耗时操作的调用方式见[后台任务说明](background-tasks.md)。第三步验证记录保留如下；125 项页面功能的迁移验收仍以[验收表](acceptance-checklist.md)为准。

## 启动

从项目根目录 `D:\zyf\quant` 启动，保持原有配置相对路径的解析语义。

```powershell
# 新环境安装接口依赖；本次使用机器上已有依赖，未重新安装。
python -m pip install -e ".[api]"

# 启动接口
python -m quant_platform.api.cli
```

也可以双击项目根目录的 `start_api.bat`。脚本优先使用 `.venv`，缺依赖时显示安装命令。

- 接口文档：启动后访问 [Swagger UI](http://127.0.0.1:8000/docs)。
- 健康状态：[health](http://127.0.0.1:8000/api/v1/health)。
- 支持 `--config <配置路径>` 和 `--port <端口>`。
- 本阶段仅监听 `127.0.0.1`，无登录；允许本机 Vite 的 `5173` 端口访问，其他网站来源及远程客户端被拒绝。启动器关闭代理头解析。
- 真实服务器只读检查结束后已停止测试进程，当前文档链接需要先启动服务。

导出供后续 React 接口类型使用的契约：

```powershell
python -m quant_platform.api.cli --export-openapi docs/migration/api-openapi.json
```

已保存一份 [OpenAPI 契约](api-openapi.json)。核心输入、分页表格、历史列表、回测结果等有显式类型；策略参数和研究报告中的动态指标保留原字段。

## 本次接口覆盖

所有路径以 `/api/v1` 开头。精确参数和方法见 OpenAPI；下表中的功能编号对应[功能登记](feature-register.json)，表示已有后端能力，不代表页面验收通过。

| 领域 | 主要接口 | 对应功能及边界 |
| --- | --- | --- |
| 状态 | `GET /health`、`GET /readiness` | 独立服务健康、原平台就绪度；没有引入 Streamlit 运行时 |
| 策略元数据 | `GET /strategies`、`GET /backtests/defaults` | BT-02～04、PY-03：动态策略、默认参数、类型、上下限、选项、加载错误 |
| 想法与检查 | `GET /research/ideas`、`POST /research/ideas/prepare`、`POST /backtests/inspect` | IDEA-01～03、BT-05：想法转规则、等权风险兼容性、区间/回看期/基准数据检查；自动补齐和方案保存尚待接入 |
| 单次回测 | `POST /backtests/run` | IDEA-04、BT-05～06：明确确认、实际提交参数、执行前重新检查、原引擎计算及持久化；同步执行 |
| 历史记录 | `GET /runs`、`GET /runs/export.csv`、`GET /runs/{run_id}` | REC-01～02、BT-07：按策略/状态/类型/名称或编号筛选，分页和全量导出，读取现有目录 |
| 历史复用 | `GET /runs/{run_id}/request` | 执行参数和快照引用；历史费用、股票池、风险口径可以在检查/重跑时复用 |
| 明细及导出 | `GET /runs/{run_id}/tables/{name}` 及 `/export.csv` | BT-08～11：净值、信号、目标仓位、订单、成交、完整交易、持仓、风险事件、公司行为；分页不截断下载 |
| 诊断与审计 | `GET /runs/{run_id}/diagnosis`、`GET /runs/{run_id}/audit` | BT-11、AUD-02～04：通俗诊断、六维审计、DSR、证据链；已有审计模块直接复用 |
| 回测对比 | `POST /runs/compare`、`POST /runs/compare/export.csv` | REC-04：2～5条不同结果、指标、归一净值及完整指标CSV |
| 参数优化 | `POST /experiments/optimization/run` | OPT-01～04：可信基准、最多100组合、目标/回撤约束、1/2/4进程、排名及搜索偏差结果；同步执行 |
| 滚动验证 | `POST /experiments/walk-forward/run` | WF-01～03：训练/测试/步长/窗口数、训练选参、后续样本外评价；同步执行 |
| 实验记录 | `GET /experiments/{kind}`、`GET /experiments/{kind}/{id}` 及 `/export.csv` | 读取优化/滚动验证请求、结果和汇总，完整CSV；`kind` 为 `optimization` 或 `walk-forward` |
| 可视化策略 | `/strategies/templates`、`/strategies/packages` 系列 | VIS、NL-02的保存能力：6模板/3风格、定义检查、保存、新版本、复制、载入及生成普通回测请求；自然语言生成本身尚待接入 |
| 因子 | `GET /factors`、`POST /factors/evaluate` | FAC-02～03、LIB部分：注册元数据、关键词/类别/来源筛选、单因子完整报告及中性化；组合、自定义编辑及研究意图筛选尚待接入 |
| 数据查询 | `/data/overview`、`/data/sources`、`/data/coverage`、`/data/closed-loop` | DATA-01、04、闭环状态；实际更新来源由完整版本记录查询 |
| 数据表与下载 | `/data/tables/{name}` 及 `/export.csv`、`/data/coverage/export.csv` | DATA-04～08：证券/日期过滤、分页、完整CSV、版本来源及脱敏错误 |
| 日常更新 | `POST /data/update` | DATA-02～03：所选数据集、多基准、本次选源、回退开关、成功/失败结果；沿用更新文件锁，检测现有回填任务 |
| 股票池 | `/universe`、`/universe/search`、`/universe/symbols`、`/universe/symbols/remove`、`/universe/filters` | 原有代码归一化、去重、名称检索、添加、移除、过滤配置；移除保留本地行情 |
| 先验知识 | `GET/POST /knowledge`、`DELETE /knowledge/{id}` | KN-01～03：查询、来源统计、添加、删除；默认沿用 `runtime/prior_knowledge.json` |

## 请求与结果约定

### 回测

`GET /backtests/defaults` 返回可直接提交检查的请求对象。修改后，先调用 `POST /backtests/inspect`；最终运行结构如下：

```json
{
  "request": {
    "snapshot_run_id": null,
    "strategy_plugin": "a_share_momentum",
    "strategy_id": "my_research",
    "strategy_parameters": {"short_window": 20, "long_window": 60},
    "start_date": "2023-01-03",
    "end_date": "2023-04-28",
    "initial_cash": 1000000,
    "top_n": 5,
    "rebalance": "weekly",
    "portfolio_method": "equal_weight",
    "universe_mode": "fixed",
    "risk_limits": null
  },
  "confirmed": true
}
```

示例不是当前配置的保证可运行区间；以本机检查结果为准。`risk_limits` 省略或为 null 时使用有效配置。策略参数的未知键、非法枚举、类型与边界错误会被拒绝。

执行请求自带完整参数，前端未提交的草稿不会参与运行。`confirmed` 必须为布尔值 true；运行时再次检查实际请求的数据，不能复用旧的“检查通过”状态。

`snapshot_run_id` 指定现有历史结果时，使用其执行/股票池等配置快照，同时把数据仓库和结果保存目录固定在当前 API 实例配置中。API不向客户端暴露整份内部配置文件。参数优化和滚动验证要求基准结果的 `metrics_reliable=true`，旧版未验证结果不能用作基准。

### 表格与下载

```json
{"columns": ["symbol", "trade_date"], "rows": [], "total": 0, "offset": 0, "limit": 500}
```

表格列名沿用引擎原始字段。日期为 ISO 字符串，缺失值和非有限数值为 null，保留真实的零值；Series另带 `index` 和 `values`，防止因子分组编号丢失。界面负责中文标签、显示格式和缺失标记。

下载接口接收相同筛选条件，不接收分页参数；CSV为 UTF-8 BOM，分块输出所有筛选行。可读取的市场表和运行明细均由枚举限定，不提供任意文件路径读取。

### 失败与冲突

业务失败返回 `{"error":{"code":"...","message":"...","details":...}}`。非法请求422、资源或旧版缺失明细404、未确认/数据未就绪/写入忙409。外部请求错误和数据版本凭证脱敏；校验失败不会回显整个提交内容。没有结果的运行不伪造成功指标。

第四步已将写入和计算互斥扩展为操作系统文件锁，覆盖 API 和独立任务进程；读取不被该锁阻止。数据更新同时沿用原项目的文件锁和回填任务检查。此锁不承诺 Streamlit 与 API 同时修改所有 JSON/YAML 文件时的跨进程事务一致性；正式写入切换随新页面上线进行。

## 验证记录

- `tests/integration/test_api.py`：**25项通过**。含真实HTTP应用调用、真实回测/优化/滚动验证/因子评价、原引擎结果对照、全量下载、历史结果、版本复制、知识和股票池编辑、执行前检查、回填冲突、来源限制和错误脱敏。
- 加原回测、数据中心、参数优化、滚动验证、策略工作室和股票池相关测试：**33项通过**。
- 新代码 Ruff 检查通过。
- 实际启动 Uvicorn 临时本机端口，用当前配置验证 health、OpenAPI、策略目录和历史列表均HTTP200；读取到7个策略、36条历史记录。只读检查后停止测试进程。
- 独立进程导入后端入口时，`streamlit` 不在 `sys.modules` 中。

回测和写入测试全部使用临时配置、样例行情和临时结果目录；未在用户真实行情或历史运行中创建测试回测。外部数据更新测试使用固定响应，没有实际下载行情或调用付费模型。未宣称125项页面操作已实测通过。

## 后续仍须接入

1. **第四步后台任务已完成**：见[后台任务说明](background-tasks.md)。同步接口保留兼容，新页面使用任务 ID、持久状态、进度、日志、取消和重试；原全市场回填实现保留。
2. **逐页适配**：AI分析/对话、自然语言生成、Python源码上传和安全确认、因子组合/自定义编辑、研究方案版本/运行关联、外部材料核查、XTick动态查询、模型/凭证/风控设置、账户与欢迎页交互。
3. **第五步React**：使用当前核心接口，按功能清单补齐以上适配器，保留高级参数、完整明细、跨页上下文、草稿失效和下载语义。
4. **第六步对照与第七步切换**：补实际URL、固定结果和截图，逐项验收后再停用旧入口。登录阶段完成后接入真实身份，研究方案不能由客户端指定任意账号。

第二步登记数据仍保持“待迁移/待验收”，避免把本次后端测试当作前后网站的完整验收。

## 实现依据

接口按领域拆成 `APIRouter` 并共享服务依赖，遵循 [FastAPI 多文件应用结构](https://fastapi.tiangolo.com/tutorial/bigger-applications/)。隔离集成测试使用 [FastAPI TestClient](https://fastapi.tiangolo.com/tutorial/testing/)。
