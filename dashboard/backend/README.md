# 智投引擎 · 实时监控后端（FastAPI）

为前端实时监控大屏提供数据的 FastAPI 服务，当前使用内置模拟器生成拟真数据，
可平滑替换为真实数据源（见 `app/models.py` 与 `app/simulator.py` 中的注释）。

## 运行

```bash
cd backend
python -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# Linux/macOS:        source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- REST 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/
- WebSocket：`ws://localhost:8000/ws/dashboard`（每 1s 推送一次完整快照）

## 接口一览（均在 `/api/v1/stats` 前缀下）

| 路径 | 含义 |
| --- | --- |
| `/snapshot` | 完整仪表盘快照（推荐，前端轮询模式使用） |
| `/active_strategies` | 当前活跃策略总数 |
| `/running_instances` | 正在执行的策略实例数 |
| `/data_links` | 当前数据源连接数 |
| `/pending_orders` | 消息队列中待处理指令数 |
| `/today_trades` | 今日累计成交订单数 |
| `/process_rate` | 系统处理速率（笔/秒） |
| `/throughput` | 当前吞吐量（笔/秒） |
| `/avg_latency` | 订单平均处理延迟（ms） |
| `/pending_orders_count` | 当前挂起订单数 |
| `/module_load` | 六个模块的负载百分比 |

## 目录结构

```
app/
├── main.py          # FastAPI 入口，注册 CORS 与路由
├── models.py        # Pydantic 模型（含字段中文注释与真实数据源替换说明）
├── simulator.py     # 随机游走数据模拟器（替换真实数据只改这里）
├── routes/stats.py  # REST 端点
└── ws.py            # WebSocket /ws/dashboard
```

## 替换为真实数据

只需修改 `app/simulator.py` 的 `DataSimulator.tick()`：从数据库 / Redis /
消息队列 / Prometheus 等读取真实指标并填充 `DashboardSnapshot` 即可，
模型与接口层无需任何改动。
