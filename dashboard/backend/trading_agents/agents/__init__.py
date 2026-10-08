"""Agent 层：每个角色一个独立模块与独立 prompt，输入输出均为 schemas 契约。"""

from trading_agents.agents.analysts import (
    FundamentalAnalyst,
    NewsAnalyst,
    SentimentAnalyst,
    TechnicalAnalyst,
    run_analyst_team,
)
from trading_agents.agents.pm import PortfolioManager
from trading_agents.agents.researchers import DebaterOutput, run_debate
from trading_agents.agents.risk import RiskTeam
from trading_agents.agents.trader import Trader

__all__ = [
    "DebaterOutput",
    "FundamentalAnalyst",
    "NewsAnalyst",
    "PortfolioManager",
    "RiskTeam",
    "SentimentAnalyst",
    "TechnicalAnalyst",
    "Trader",
    "run_analyst_team",
    "run_debate",
]
