"""
数据模拟器：生成平滑、有边界约束的拟真波动数据。

实现方式：随机游走（random walk）+ 上下界钳制 + 均值回归，
使曲线连续且不会发散，看起来接近真实监控数据。

【替换为真实数据】
把 DataSimulator 各 _walk 字段的更新逻辑，替换为从真实数据源读取：
- 策略/实例数：查询策略管理服务或调度系统 API
- 链路数：读取行情网关连接注册表
- 待处理指令：读取消息队列（Kafka lag / Redis 队列长度）
- 成交数：查询数据库成交表
- 处理速率/吞吐/延迟：对接 Prometheus / 自研 metrics 采集
- 模块负载：读取各服务 /metrics 端点的 CPU 与队列占用率
模型（models.py）与接口层（routes/ws.py）无需改动。
"""
import random
import time
from typing import List

from .models import (
    DashboardSnapshot,
    HistoryPoint,
    ModuleLoad,
    OverviewStats,
    PerformanceMetrics,
)


def _walk(value: float, step: float, low: float, high: float, mean: float, pull: float = 0.05) -> float:
    """带均值回归的随机游走。

    :param value: 当前值
    :param step: 每步最大随机振幅
    :param low: 下界
    :param high: 上界
    :param mean: 回归目标值（长期均值）
    :param pull: 回归力度（0~1，越大回归越快）
    """
    # 随机扰动
    value += random.uniform(-step, step)
    # 均值回归，防止长期漂移
    value += (mean - value) * pull
    # 边界钳制
    return max(low, min(high, value))


class DataSimulator:
    """仪表盘全量数据模拟器（单例）。"""

    # 六个核心模块：名称、key、主题色（与前端 Mesh 图节点一致）
    MODULES = [
        ("策略引擎", "strategy", "#3b82f6"),
        ("数据服务", "data", "#22c55e"),
        ("执行模块", "execution", "#f97316"),
        ("风控模块", "risk", "#ef4444"),
        ("行情网关", "market", "#a855f7"),
        ("订单管理", "order", "#06b6d4"),
    ]

    HISTORY_LEN = 60  # 历史曲线保留的采样点数（约 1 分钟，1s 一个点）

    def __init__(self) -> None:
        # ---- 顶部统计数字的初始值与波动区间 ----
        self._active_strategies = 36.0    # 活跃策略：慢变量
        self._running_instances = 24.0    # 执行中实例
        self._data_links = 12.0           # 数据链路：比较稳定
        self._pending_orders = 48.0       # 待处理指令：波动较大
        self._today_trades = 15230.0      # 今日成交：单调递增为主

        # ---- 性能指标初始值 ----
        self._process_rate = 320.0        # 处理速率 笔/秒
        self._throughput = 460.0          # 吞吐量 笔/秒
        self._avg_latency = 8.5           # 平均延迟 ms
        self._pending_count = 17.0        # 挂起订单数

        # ---- 各模块负载（0~100%）----
        self._module_loads = {key: random.uniform(25, 65) for _, key, _ in self.MODULES}

        # ---- 历史曲线，预热一段数据让前端首次渲染就有内容 ----
        now = int(time.time())
        self._history: List[HistoryPoint] = []
        for i in range(self.HISTORY_LEN):
            ts = now - (self.HISTORY_LEN - i)
            self._history.append(
                HistoryPoint(
                    ts=ts,
                    throughput=round(random.uniform(380, 540), 1),
                    latency=round(random.uniform(6.0, 12.0), 2),
                )
            )

    def tick(self) -> DashboardSnapshot:
        """推进一拍并返回最新快照。REST 与 WebSocket 都调用它。"""
        # ---- 统计数字：整数型慢变量 ----
        self._active_strategies = _walk(self._active_strategies, 0.4, 20, 60, 36)
        self._running_instances = _walk(self._running_instances, 0.5, 10, 48, 24)
        self._data_links = _walk(self._data_links, 0.2, 8, 16, 12)
        self._pending_orders = _walk(self._pending_orders, 3.0, 0, 200, 48, pull=0.08)
        # 成交数大体单调递增，偶尔 +1~8 笔
        self._today_trades += random.randint(0, 8)

        # ---- 性能指标 ----
        self._process_rate = _walk(self._process_rate, 12.0, 120, 600, 320)
        self._throughput = _walk(self._throughput, 15.0, 200, 900, 460)
        # 延迟与吞吐正相关：吞吐越高延迟越高，再叠加噪声
        latency_bias = (self._throughput - 460) / 900 * 6
        self._avg_latency = _walk(self._avg_latency, 0.8, 2.0, 40.0, 8.5 + latency_bias, pull=0.15)
        self._pending_count = _walk(self._pending_count, 1.5, 0, 80, 17)

        # ---- 模块负载：各模块独立游走，风控略偏高 ----
        for name, key, _ in self.MODULES:
            mean = 55 if key == "risk" else 40
            self._module_loads[key] = _walk(self._module_loads[key], 3.5, 5, 97, mean, pull=0.06)

        # ---- 追加历史点并裁剪 ----
        self._history.append(
            HistoryPoint(
                ts=int(time.time()),
                throughput=round(self._throughput, 1),
                latency=round(self._avg_latency, 2),
            )
        )
        if len(self._history) > self.HISTORY_LEN:
            self._history = self._history[-self.HISTORY_LEN:]

        return DashboardSnapshot(
            overview=OverviewStats(
                active_strategies=int(self._active_strategies),
                running_instances=int(self._running_instances),
                data_links=int(self._data_links),
                pending_orders=int(self._pending_orders),
                today_trades=int(self._today_trades),
            ),
            performance=PerformanceMetrics(
                process_rate=round(self._process_rate, 1),
                throughput=round(self._throughput, 1),
                avg_latency=round(self._avg_latency, 2),
                pending_orders_count=int(self._pending_count),
            ),
            module_load=[
                ModuleLoad(name=name, key=key, load=round(self._module_loads[key], 1), color=color)
                for name, key, color in self.MODULES
            ],
            history=list(self._history),
        )


# 全局单例：REST 路由与 WebSocket 共享同一份状态，保证两处数据一致
simulator = DataSimulator()
