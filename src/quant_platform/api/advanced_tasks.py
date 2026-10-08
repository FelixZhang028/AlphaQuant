"""Adapters for factor combinations, language rules, AI chat and dynamic XTick."""

import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import pandas as pd
import requests
from fastapi import APIRouter

from quant_platform.api.backtests import Context, request_payload
from quant_platform.api.common import ApiError, safe_wire
from quant_platform.api.workspace import (
    credential_store,
    factor_metadata,
    factor_registry,
    model_snapshot,
)
from quant_platform.api.workspace_schemas import (
    ChatInput,
    CombinationInput,
    CombinationPrepareInput,
    NLInput,
    XTickInput,
)
from quant_platform.application.factor_research_service import research_combination
from quant_platform.strategies.nl_builder import NLStrategyBuilder
from trading_agents.llm.base import create_llm_client

router = APIRouter(tags=["advanced research"])
CATALOG_FILE = Path(__file__).resolve().parents[1] / "web/assets/xtick_apidoc.json"


def xtick_catalog():
    return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))


def factor_fingerprint(ctx, names):
    registry = factor_registry(ctx)
    try:
        values = [factor_metadata(registry.get(name)) for name in names]
    except KeyError as exc:
        raise ApiError(409, "factor_changed", "组合中的因子不存在，请重新选择和验证") from exc
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def xtick_definition(category_id, api_id):
    for category in xtick_catalog():
        if category["id"] == category_id:
            for api in category.get("docApis", []):
                if api["id"] == api_id:
                    return api
    raise ApiError(404, "xtick_api_missing", "目录中不存在此接口")


def checked_xtick(body):
    api = xtick_definition(body.category_id, body.api_id)
    params = {
        p.get("name") or "seq": p for p in api.get("inputParas", []) if p.get("name") != "token"
    }
    if set(body.parameters) - set(params):
        raise ApiError(422, "xtick_parameters", "存在未声明参数；Token 仅从服务端读取")
    result = {}
    for key, value in body.parameters.items():
        param = params[key]
        value = str(value)
        options = [
            x.strip().partition("-")[0]
            for x in re.split("[，,]", param.get("range") or "")
            if x.strip()
        ]
        if options and value not in options:
            raise ApiError(422, "xtick_enum", f"{key} 枚举值无效")
        kind = str(param.get("type", "")).lower()
        if "int" in kind and value:
            value = str(int(value))
        elif kind in {"float", "double", "decimal"} and value:
            if not math.isfinite(float(value)):
                raise ApiError(422, "xtick_number", "数值必须有限")
        if key.lower() in {"startdate", "enddate", "tradedate"}:
            value = value.replace("-", "")
        result[key] = value
    return api, result


def freeze_advanced(kind, body, ctx):
    if kind == "nl_strategy":
        return model_snapshot(ctx, body.provider)
    if kind == "factor_combination":
        return {"factor_fingerprint": factor_fingerprint(ctx, body.factor_names)}
    if kind == "xtick_query":
        checked_xtick(body)
        store = credential_store(ctx)
        token = store.resolve("xtick", "token", "XTICK_TOKEN")
        if not token:
            raise ApiError(409, "xtick_not_ready", "请先在设置中配置 XTick Token")
        return {
            "token": token,
            "base_url": store.get("xtick").get("base_url") or "http://api.xtick.top",
        }
    if kind == "ai_chat":
        analysis = ctx.tasks.store.get(body.analysis_task_id, private=True)
        if analysis["kind"] != "ai_analysis" or analysis["status"] != "SUCCESS":
            raise ApiError(409, "analysis_required", "请先完成本次 AI 分析")
        result = ctx.tasks.store.result(body.analysis_task_id)
        context = json.dumps(result, ensure_ascii=False)
        if body.previous_task_id:
            previous = ctx.tasks.store.get(body.previous_task_id, private=True)
            if (
                previous["kind"] != "ai_chat"
                or previous["status"] != "SUCCESS"
                or previous["input"]["analysis_task_id"] != body.analysis_task_id
            ):
                raise ApiError(409, "chat_context", "对话历史不属于本次研究或尚未完成")
            history = ctx.tasks.store.result(body.previous_task_id)["messages"]
        else:
            history = []
        return {
            "model": {k: analysis["private"]["ai"][k] for k in ("provider", "resolved")},
            "context": context,
            "messages": history,
        }
    return {}


def llm(frozen):
    return create_llm_client(
        frozen["provider"], **{k: v or None for k, v in frozen["resolved"].items()}
    )


def execute_advanced(kind, inputs, ctx, private):
    frozen = private["advanced"]
    if kind == "nl_strategy":
        body = NLInput.model_validate(inputs)
        ctx.progress("understand_strategy", 0, 1)
        definition = NLStrategyBuilder(llm(frozen)).generate(body.description)
        ctx.progress("understand_strategy", 1, 1)
        return {
            "definition": definition.to_dict(),
            "explanation": definition.describe(top_n=5, rebalance="weekly"),
        }
    if kind == "factor_combination":
        body = CombinationInput.model_validate(inputs)
        if factor_fingerprint(ctx, body.factor_names) != frozen["factor_fingerprint"]:
            raise ApiError(409, "factor_changed", "排队期间因子定义已变，请重新提交")
        ctx.progress("factor_combination", 0, 1)
        result = research_combination(
            ctx.data().repository,
            tuple(factor_registry(ctx).get(name) for name in body.factor_names),
            **body.model_dump(exclude={"factor_names"}),
        )
        ctx.progress("factor_combination", 1, 1)
        return {
            **safe_wire(result),
            "factor_fingerprint": frozen["factor_fingerprint"],
            "input": body.model_dump(mode="json"),
        }
    if kind == "ai_chat":
        body = ChatInput.model_validate(inputs)
        messages = [*frozen["messages"], {"role": "user", "content": body.message}]
        ctx.progress("ai_chat", 0, 1)
        reply = (
            llm(frozen["model"])
            .chat(
                [
                    {
                        "role": "system",
                        "content": "你是严谨的量化分析师，基于研究上下文回应质疑。\n"
                        + frozen["context"],
                    },
                    *messages,
                ],
                temperature=0.4,
                max_tokens=1024,
            )
            .text
        )
        ctx.progress("ai_chat", 1, 1)
        return {"messages": [*messages, {"role": "assistant", "content": reply}], "reply": reply}
    body = XTickInput.model_validate(inputs)
    api, params = checked_xtick(body)
    # URL comes from the server's catalog, never a user supplied arbitrary path.
    endpoint = api["url"]
    if not endpoint.startswith("/doc/") or ".." in endpoint:
        raise ApiError(422, "xtick_path", "目录接口地址无效")
    ctx.progress("xtick_request", 0, 1)
    response = requests.get(
        f"{frozen['base_url'].rstrip('/')}{endpoint}",
        params={"token": frozen["token"], **params},
        timeout=30,
    )
    response.raise_for_status()
    if response.content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            info = archive.getinfo("data.json")
            if info.file_size > 100_000_000:
                raise ApiError(422, "xtick_size", "接口数据过大，请缩小查询范围")
            payload = json.loads(archive.read(info))
    else:
        payload = response.json()
    if isinstance(payload, dict) and "code" in payload:
        if payload["code"] not in (0, 200):
            raise ApiError(422, "xtick_remote", "XTick 返回失败，请检查参数和服务权限")
        payload = payload.get("data", payload)
    frame = (
        pd.DataFrame(payload)
        if isinstance(payload, list) and all(isinstance(x, dict) for x in payload)
        else None
    )
    if frame is not None:
        master = ctx.data().repository.read_table("security_master")
        if not master.empty and {"symbol", "name"} <= set(master):
            names = dict(zip(master.symbol.str.split(".").str[0], master["name"], strict=False))
            code_key = next((c for c in ("code", "stockCode", "symbol") if c in frame), None)
            if code_key:
                frame["证券名称"] = frame[code_key].astype(str).str.split(".").str[0].map(names)
    ctx.progress("xtick_request", 1, 1)
    return {
        "raw": safe_wire(payload),
        "table": safe_wire(frame) if frame is not None else None,
        "output_labels": {
            p["name"]: str(p.get("description", "")).splitlines()[0]
            for p in api.get("outputParas", [])
            if p.get("name")
        },
    }


@router.get("/data/xtick/catalog")
def get_xtick_catalog():
    categories = xtick_catalog()
    for category in categories:
        for api in category.get("docApis", []):
            api["defaults"] = {
                k or "seq": v
                for k, v in parse_qsl(
                    urlparse(api.get("demoUrl") or api.get("demo") or "").query,
                    keep_blank_values=True,
                )
                if k != "token"
            }
            api["inputParas"] = [
                {**p, "name": p.get("name") or "seq"}
                for p in api.get("inputParas", [])
                if p.get("name") != "token"
            ]
    return {"items": categories}


@router.post("/factors/combinations/prepare")
def prepare_combination(body: CombinationPrepareInput, ctx: Context):
    job = ctx.tasks.store.get(body.task_id)
    if job["kind"] != "factor_combination" or job["status"] != "SUCCESS":
        raise ApiError(409, "combination_required", "请先完成当前组合的训练和测试验证")
    result = ctx.tasks.store.result(body.task_id)
    if factor_fingerprint(ctx, result["input"]["factor_names"]) != result["factor_fingerprint"]:
        raise ApiError(409, "factor_changed", "因子版本已变化，请重新验证组合")
    service = ctx.backtests()
    request = (
        body.base_request.model_dump(mode="json")
        if body.base_request
        else request_payload(service.default_request())
    )
    request.update(
        strategy_plugin="factor_composite",
        strategy_id="factor_research",
        strategy_parameters={"factors_json": json.dumps(result["spec"], ensure_ascii=False)},
        snapshot_run_id=None,
        plan_id=None,
        plan_revision=None,
    )
    return {"request": request}
