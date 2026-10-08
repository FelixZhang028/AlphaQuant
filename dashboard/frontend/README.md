# 智投引擎 · 实时监控前端（Vue 3 + Vite + Pinia + ECharts）

深色科技风的量化交易系统实时监控大屏，数据来自配套的 FastAPI 后端
（`../backend`，WebSocket 实时推送，断线自动降级为 HTTP 轮询）。

## 运行

先启动后端（默认 http://localhost:8000，见 `../backend/README.md`），然后：

```bash
cd frontend
npm install
npm run dev        # 开发服务器 http://localhost:5173（已配置 /api、/ws 代理到 8000）
```

生产构建：

```bash
npm run build      # 输出到 dist/
npm run preview    # 本地预览构建产物
```

> 部署到生产时，请让 Web 服务器把 `/api` 与 `/ws` 反代到后端服务，
> 或修改 `src/services/dashboardService.js` 顶部的 `WS_URL` / `SNAPSHOT_URL`。

## 功能

- 顶部 5 个统计数字（变化时 count-up 动画）：活跃策略 / 执行中 / 数据链路 / 待处理指令 / 今日成交
- 中央 Mesh 网络图（ECharts graph + lines 流动粒子）：
  策略引擎 / 数据服务 / 执行模块 / 风控模块 / 行情网关 / 订单管理六个发光节点，
  连线粒子流速跟随实时吞吐，节点呼吸脉冲、大小随负载变化
- 实时性能面板：处理速率 / 吞吐量 / 平均延迟 / 挂起订单数 + 六模块负载条 + 动态瓶颈分析文案
- 吞吐/延迟历史折线图（近 1 分钟）
- 连接状态指示：实时（WebSocket）/ 轮询（HTTP 2.5s）/ 断开，自动重连

## 交互

- 光标悬停节点：显示模块详情 tooltip
- 单击节点：打开右侧详情面板
- 长按节点（≥600ms）：打断当前任务并由指令环重派（顶部提示）
- 空格键：暂停 / 恢复实时更新

## 目录结构

```
src/
├── main.js
├── App.vue                      # 整体布局 + 键盘事件
├── style.css                    # 深色科技风全局样式
├── stores/dashboard.js          # Pinia：全部仪表盘状态
├── services/dashboardService.js # WebSocket 接入 + 轮询降级 + 自动重连
└── components/
    ├── StatCard.vue             # 统计数字卡（count-up 动画）
    ├── ConnectionBadge.vue      # 连接状态徽标
    ├── MeshGraph.vue            # 核心 Mesh 网络图
    ├── NodeDetail.vue           # 节点详情侧滑面板
    ├── MetricsPanel.vue         # 性能指标 + 负载条 + 分析文案
    ├── TrendChart.vue           # 吞吐/延迟历史折线图
    └── HintBar.vue              # 底部操作提示栏
```
