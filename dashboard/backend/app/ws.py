"""
WebSocket 接口：/ws/dashboard

连接建立后每 1 秒推送一次完整仪表盘快照（JSON）。
前端断线后会自动重连或降级为 HTTP 轮询，本端无需特殊处理。
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .simulator import simulator

logger = logging.getLogger(__name__)

router = APIRouter()

PUSH_INTERVAL = 1.0  # 推送间隔（秒）


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await websocket.accept()
    client = websocket.client
    logger.info("dashboard ws client connected: %s", client)
    try:
        while True:
            snapshot = simulator.tick()
            # model_dump_json 直接序列化为 JSON 字符串，减少一次拷贝
            await websocket.send_text(snapshot.model_dump_json())
            await asyncio.sleep(PUSH_INTERVAL)
    except WebSocketDisconnect:
        logger.info("dashboard ws client disconnected: %s", client)
    except Exception as exc:  # 网络中断等异常，记录后结束协程
        logger.warning("dashboard ws error: %s", exc)
