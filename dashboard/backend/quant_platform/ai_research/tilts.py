"""The three ways a stock's data can lean, worded as a description of the data, not a forecast.

The judgement only says whether the favourable or the risk factors in today's data are more;
it never says where the price will go. Records saved before carry 偏多 / 中性 / 偏空, which
:func:`normalize` turns into the current words.
"""

from __future__ import annotations

from typing import Any

TILTS = ("利好较多", "大致相当", "风险较多")
OLD_TILTS = {"偏多": "利好较多", "中性": "大致相当", "偏空": "风险较多"}
# 说方向、像在预测涨跌的词：AI 写的要点和总结里出现就去掉。
DIRECTION_WORDS = ("偏多", "偏空", "看多", "看空", "看涨", "看跌", "做多", "做空")


def normalize(value: Any) -> Any:
    return OLD_TILTS.get(value, value)


def normalize_odds(odds: dict[str, Any] | None) -> dict[str, Any] | None:
    """A saved decision-model answer with the current words for its choice and probabilities."""

    if not isinstance(odds, dict):
        return odds
    fixed = dict(odds)
    if "choice" in fixed:
        fixed["choice"] = normalize(fixed["choice"])
    if isinstance(fixed.get("probabilities"), dict):
        fixed["probabilities"] = {normalize(key): value for key, value in fixed["probabilities"].items()}
    return fixed
