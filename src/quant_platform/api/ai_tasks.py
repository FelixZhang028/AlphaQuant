"""Serializable AI research adapter with model settings kept on the server."""

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.agents_bridge.proxy_settings import ProxySettingsStore
from quant_platform.api.common import ApiError, safe_wire
from quant_platform.application.universe_service import normalize_a_share_symbol
from quant_platform.core.exceptions import ConfigurationError


def freeze_ai(body, ctx):
    from quant_platform.api.workspace import model_snapshot

    model = model_snapshot(ctx, body.provider)
    try:
        symbol = normalize_a_share_symbol(body.symbol)
    except ConfigurationError:
        symbol = body.symbol.upper()
    proxy = ProxySettingsStore(ctx.runtime_root / "proxy_settings.json").load()
    return {
        **model,
        "symbol": symbol,
        "prior_knowledge": PriorKnowledgeStore(ctx.prior_path).render(),
        "proxy": proxy,
    }


def execute_ai(body, ctx, frozen, store, identifier):
    from quant_platform.agents_bridge import AgentRunner
    from trading_agents.orchestrator.events import EventBus

    ctx.progress("ai_history", 0, 1)
    history = ctx.data().repository.get_daily_bars(
        symbols=[frozen["symbol"]], end_date=body.trade_date
    )
    if "trade_date" in history:
        history = history.sort_values("trade_date")
    history = history.tail(body.lookback_days).reset_index(drop=True)
    if body.stock_source == "local" and history.empty:
        raise ApiError(409, "data_not_ready", "分析日期及之前没有该证券的本地行情")
    runner = AgentRunner(
        llm_provider=frozen["provider"],
        debate_rounds=body.debate_rounds,
        use_cache=body.use_cache,
        base_dir=ctx.runtime_root / "agent_runs",
        cache_dir=ctx.runtime_root / "agent_cache",
        prior_knowledge=frozen["prior_knowledge"],
        base_url=frozen["resolved"]["base_url"] or None,
        model=frozen["resolved"]["model"] or None,
        api_key=frozen["resolved"]["api_key"] or None,
        stock_source=body.stock_source,
        news_sources=tuple(body.news_sources),
        proxy_enabled=bool(frozen["proxy"]["enabled"]),
        proxy_address=str(frozen["proxy"]["address"]),
    )
    ctx.progress("ai_pipeline", 0, 1)
    if body.use_cache:
        decision = runner.decide(frozen["symbol"], body.trade_date, history)
        state = None
    else:
        bus = EventBus()

        def node(event, state):
            # EventBus swallows listener exceptions. Log nodes without claiming that
            # cancellation can abort a running model/network request.
            value = event.model_dump(mode="json", exclude={"artifacts"})
            store.event(identifier, {"stage": "ai_node", **safe_wire(value)})
            store.progress(identifier, "ai:" + event.node, int(event.kind == "finished"), 1)

        bus.subscribe(node)
        state = runner.decide_full(frozen["symbol"], body.trade_date, history, event_bus=bus)
        decision = state.decision
    ctx.progress("ai_pipeline", 1, 1)
    return safe_wire(
        {
            "decision": decision,
            "state": state,
            "mode": "cache_enabled" if body.use_cache else "full_pipeline",
        }
    )
