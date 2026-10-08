"""
Pydantic 数据模型定义。

所有字段都带中文注释，说明字段含义以及【如何替换为真实数据源】。
真实接入时，只需把 simulator.py 中的模拟生成逻辑替换为从
数据库 / Redis / 消息队列 / 监控系统读取即可，模型结构保持不变。
"""
from typing import List

from pydantic import BaseModel, Field


class OverviewStats(BaseModel):
    """顶部五个统计数字。"""

    active_strategies: int = Field(
        description="当前活跃策略总数（在编策略）。真实数据源：策略元数据表中 status='active' 的记录数。"
    )
    running_instances: int = Field(
        description="正在执行的策略实例数（实际在干活的进程/容器）。真实数据源：调度器（如 K8s / Supervisor）中运行中的实例数。"
    )
    data_links: int = Field(
        description="当前数据源连接数（行情/财务/另类数据链路）。真实数据源：连接池或网关中活跃会话数。"
    )
    pending_orders: int = Field(
        description="消息队列中待处理指令数（消息在途）。真实数据源：Kafka / RabbitMQ 的 lag 或队列深度。"
    )
    today_trades: int = Field(
        description="今日累计成交订单数（已交付）。真实数据源：成交回报表按交易日 COUNT。"
    )


class PerformanceMetrics(BaseModel):
    """底部实时性能指标。"""

    process_rate: float = Field(
        description="系统处理速率（笔/秒）。真实数据源：近 N 秒订单处理计数 / N。"
    )
    throughput: float = Field(
        description="当前吞吐量（笔/秒，含行情与指令全链路）。真实数据源：链路入口计数器速率。"
    )
    avg_latency: float = Field(
        description="订单平均处理延迟（毫秒）。真实数据源：订单从接收到回报的时间差均值。"
    )
    pending_orders_count: int = Field(
        description="当前挂起订单数（已报未成的在途订单）。真实数据源：订单表中 status='pending' 的记录数。"
    )


class ModuleLoad(BaseModel):
    """单个模块的负载。"""

    name: str = Field(description="模块名称，如 策略引擎 / 数据服务 等")
    key: str = Field(description="模块英文 key，前端用于关联图节点")
    load: float = Field(description="负载百分比 0-100。真实数据源：进程 CPU 使用率或内部队列占用率。")
    color: str = Field(description="前端展示用主题色（十六进制）")


class HistoryPoint(BaseModel):
    """吞吐/延迟历史曲线的一个采样点。"""

    ts: int = Field(description="Unix 时间戳（秒）")
    throughput: float = Field(description="该时刻吞吐量（笔/秒）")
    latency: float = Field(description="该时刻平均延迟（毫秒）")


class DashboardSnapshot(BaseModel):
    """完整仪表盘快照：REST /snapshot 与 WebSocket 推送共用的结构。"""

    overview: OverviewStats = Field(description="顶部统计数字")
    performance: PerformanceMetrics = Field(description="实时性能指标")
    module_load: List[ModuleLoad] = Field(description="六个模块的负载列表")
    history: List[HistoryPoint] = Field(description="最近一段时间的吞吐/延迟历史（用于折线图）")
