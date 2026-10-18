"""
统计 REST 接口，统一挂载在 /api/v1/stats 下。

每个端点返回快照中的一个字段，方便前端轮询降级时按需获取；
/snapshot 一次返回全量数据，是轮询模式的主接口。
"""
from fastapi import APIRouter

from ..simulator import simulator

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("/snapshot", summary="完整仪表盘快照（推荐）")
def get_snapshot():
    return simulator.tick()


@router.get("/active_strategies", summary="当前活跃策略总数")
def get_active_strategies():
    return {"active_strategies": simulator.tick().overview.active_strategies}


@router.get("/running_instances", summary="正在执行的策略实例数")
def get_running_instances():
    return {"running_instances": simulator.tick().overview.running_instances}


@router.get("/data_links", summary="当前数据源连接数")
def get_data_links():
    return {"data_links": simulator.tick().overview.data_links}


@router.get("/pending_orders", summary="消息队列中待处理指令数")
def get_pending_orders():
    return {"pending_orders": simulator.tick().overview.pending_orders}


@router.get("/today_trades", summary="今日累计成交订单数")
def get_today_trades():
    return {"today_trades": simulator.tick().overview.today_trades}


@router.get("/process_rate", summary="系统处理速率（笔/秒）")
def get_process_rate():
    return {"process_rate": simulator.tick().performance.process_rate}


@router.get("/throughput", summary="当前吞吐量（笔/秒）")
def get_throughput():
    return {"throughput": simulator.tick().performance.throughput}


@router.get("/avg_latency", summary="订单平均处理延迟（ms）")
def get_avg_latency():
    return {"avg_latency": simulator.tick().performance.avg_latency}


@router.get("/pending_orders_count", summary="当前挂起订单数")
def get_pending_orders_count():
    return {"pending_orders_count": simulator.tick().performance.pending_orders_count}


@router.get("/module_load", summary="各模块负载百分比")
def get_module_load():
    return {"module_load": [m.model_dump() for m in simulator.tick().module_load]}
