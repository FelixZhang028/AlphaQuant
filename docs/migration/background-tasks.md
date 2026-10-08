# 第四步：持久化后台任务

日期：2026-10-07。沿用[第三步的启动方式](api-backend.md#启动)，API 版本为 `0.2.0`。

已为回测、参数优化、滚动验证、因子评价、日常数据更新和单股 AI 分析接入后台任务。新增 **8 个 HTTP 操作**，累计 **57 个**。任务在独立 Python 进程中执行；浏览器关闭或 API 服务重启不会停止已启动的任务。原同步接口继续兼容，后续 React 的耗时操作使用任务接口。

本阶段完成的是后端任务能力。旧 Streamlit 页面仍可使用，125 项页面功能尚未逐项迁移验收。

## 接口

以下路径均以 `/api/v1` 开头，完整类型见 [OpenAPI](api-openapi.json)。

| 方法与路径 | 用途 |
| --- | --- |
| `POST /tasks` | 提交 `{kind,input}`，返回 HTTP 202、任务 ID 和 `Location` |
| `GET /tasks` | 按状态和类型筛选，分页查询任务历史 |
| `GET /tasks/{id}` | 状态、时间、阶段进度、脱敏错误、结果是否可用 |
| `GET /tasks/{id}/events?after=0&limit=200` | 持久事件日志，使用 `next_after` 增量读取 |
| `GET /tasks/{id}/result` | 完整结果；尚无结果时返回 409 |
| `GET /tasks/{id}/input` | 查看提交参数，不返回内部配置或模型凭证 |
| `POST /tasks/{id}/cancel` | 取消排队任务，或向运行任务请求安全停止 |
| `POST /tasks/{id}/retry` | 对失败、部分完成、取消或中断任务手动重试，创建新 ID |

提交和重试均可携带 `Idempotency-Key` 请求头（1～128 位英文字母、数字、下划线或连字符）。相同键与相同请求返回同一个任务；相同键用于不同参数或不同重试来源返回 409。前端发生请求超时后应沿用该键重新查询/提交，避免重复计算。

### 任务类型

| `kind` | `input` | 结果与进度 |
| --- | --- | --- |
| `backtest` | 原 `POST /backtests/run` 请求 | 返回运行 ID、指标、有效性；净值等完整明细仍从 `/runs/{run_id}` 系列读取；按交易日报进度 |
| `optimization` | 原 `POST /experiments/optimization/run` 请求 | 返回完整实验表和搜索偏差分析；按组合报进度，串行回测还报告交易日阶段 |
| `walk_forward` | 原 `POST /experiments/walk-forward/run` 请求 | 返回窗口表和汇总；按窗口、训练组合、回测阶段报进度 |
| `factor_evaluation` | 原 `POST /factors/evaluate` 请求 | 返回完整因子报告；当前只报告执行阶段，不提供虚构的计算百分比 |
| `data_update` | 原 `POST /data/update` 请求 | 保留各数据集成功/失败明细；当前只报告执行阶段；沿用数据更新锁和全市场回填冲突检查 |
| `ai_analysis` | 证券、日期、模型提供方、数据来源等，详见契约 | 完整执行返回决策和 PipelineState；启用缓存时返回决策，`state=null`，不伪造中间报告 |

AI 默认使用服务器已有模型设置；不接受前端提交 API Key。无缓存执行会保存分析节点事件。默认本地行情来源，缺少本地行情时明确失败；远程来源可由请求指定。原多轮对话、研究回放等页面能力仍待第五步适配。

### 回测示例

```powershell
$base = 'http://127.0.0.1:8000/api/v1'
$request = Invoke-RestMethod "$base/backtests/defaults"
$body = @{kind='backtest'; input=@{request=$request; confirmed=$true}} | ConvertTo-Json -Depth 20
$job = Invoke-RestMethod "$base/tasks" -Method Post -ContentType 'application/json' -Body $body -Headers @{'Idempotency-Key'='my-first-backtest'}
Invoke-RestMethod "$base/tasks/$($job.id)"
Invoke-RestMethod "$base/tasks/$($job.id)/events"
# 终态且 result_available=true 时读取；回测仍会重新检查数据条件。
Invoke-RestMethod "$base/tasks/$($job.id)/result"
```

React 应保存任务 ID，在页面恢复时重新查询任务及日志。建议每 1 秒轮询状态，进入终态后停止轮询；运行结果通过 ID 读取，不依赖组件内存中的临时对象。

## 状态与恢复

```text
QUEUED → RUNNING → SUCCESS / PARTIAL / FAILED
QUEUED → CANCELLED
RUNNING → CANCEL_REQUESTED → CANCELLED
RUNNING / CANCEL_REQUESTED → INTERRUPTED（工作进程中断）
```

- `PARTIAL`：优化、验证或数据更新的部分子操作失败，成功结果和错误明细保留。全部子操作失败为 `FAILED`，也可以读取失败明细。
- 默认先进先出，同一运行目录串行执行任务；优化任务内部仍可使用原有 1/2/4 进程。最多 20 个非终态任务，队列满时返回 409。
- API 写入和后台计算共享操作系统文件锁；读取任务和取消请求不等待计算结束。旧 Streamlit 的所有 JSON/YAML 写入尚未统一使用该锁，迁移期间不应同时从两个入口编辑同一配置。
- 排队任务在 API 启动、任务查询时检查并恢复启动。运行进程失去文件租约后标记 `INTERRUPTED`；已记录的未完成回测同步标记失败，结果目录保留。
- 中断任务不会自动重跑。手动重试使用原参数与配置快照，新任务记录 `retry_of`，原记录保留。

## 取消边界

取消采用协作方式，等待当前操作到达安全边界：

- 单次回测在下一个交易日边界停止；串行优化和滚动验证也会检查组合/窗口边界。
- 并行优化需要等待已经提交的子进程结束；当前实现不强杀计算进程。
- 因子评价、数据更新和 AI 的当前计算/网络请求不能立即中断，完成当前操作后处理取消。已写入的数据和已完成回测不会撤销；如已有完整返回值，会保留供查询。
- 计算已经成功结束后的取消请求不会更改成功状态。取消和成功提交同时发生时，以持久化状态为准。

## 保存位置和快照

在应用配置的 `runtime_dir` 下保存：

```text
tasks/tasks.sqlite3         # 任务元数据、输入、服务端快照、事件
tasks/<id>/app.yaml         # 本次独立工作进程的配置入口
tasks/<id>/*.yaml           # 本次策略、执行、风险、股票池及数据源配置
tasks/<id>/result.json      # 脱敏后的返回结果
```

提交时冻结完整请求和有效配置；相对目录转换为绝对目录。内部配置可能含模型凭证，只在本机服务端保存，不通过任务查询暴露；公开错误、结果和事件使用已有脱敏函数。原回测与实验目录结构不变。

快照不复制行情仓库、Python 策略源码或自定义因子文件；排队期间若在旧界面或磁盘修改这些内容，执行可能读取新内容。后续页面验收仍需固定行情与代码版本，不能仅凭任务配置快照宣称完全可复现。

## 验证记录

- 后台任务集成测试：**14 项通过**，包含真实独立进程的回测、优化、验证、因子评价和离线 AI；日常更新使用固定响应验证部分失败，不下载行情。
- 真实 Uvicorn 子进程测试：任务排队后关闭 API，工作进程独立完成，再启动 API 读取成功结果。
- 回测完整净值逐行对照原服务，收益和 Sharpe 一致；执行配置在排队后被修改，工作进程仍使用提交时快照。
- 覆盖幂等提交、取消、重试、失败检查、中断修复、增量日志、启动失败脱敏和同任务重复启动保护。
- 后台任务、原 API、回测、数据中心、优化、验证、策略工作室、股票池、风险、有效性和研究可靠性回归测试合计 **75 项通过**；新代码 Ruff 检查通过。
- 已核对当前 OpenAPI 与保存契约完全一致，共 57 个操作；47 个旧网页 Python 文件的 SHA-256 与第二步清单一致；独立导入 API 未加载 `streamlit`。

所有写入测试均使用临时目录和样例数据，AI 使用 `mock` 提供方；没有对用户行情进行测试写入，也没有触发付费模型调用。

## 下一步

第五步搭建 React 页面并接入这些接口，按[功能清单](feature-inventory.md)补齐其余业务适配。第六步逐项验收，第七步切换入口；当前保留旧 Streamlit 网站。
