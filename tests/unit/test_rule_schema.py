from __future__ import annotations

import json

import pytest

from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.rule_schema import RuleStrategyDefinition
from quant_platform.strategies.templates import beginner_templates


def test_all_beginner_templates_have_three_valid_presets() -> None:
    templates = beginner_templates()

    assert len(templates) == 6
    assert len({template.template_id for template in templates}) == 6
    for template in templates:
        assert set(template.presets) == {"conservative", "balanced", "aggressive"}
        for preset in template.presets.values():
            preset.definition.validate()
            restored = RuleStrategyDefinition.from_json(preset.definition.to_json())
            assert restored == preset.definition
            assert restored.minimum_history_days >= 2
            assert preset.top_n > 0
            assert preset.rebalance in {"weekly", "monthly"}


def test_rule_schema_rejects_unknown_indicator_and_ambiguous_right_side() -> None:
    definition = beginner_templates()[0].presets["balanced"].definition.to_dict()
    definition["entry_rules"][0]["left"]["name"] = "future_return"

    with pytest.raises(ConfigurationError, match="不支持的指标"):
        RuleStrategyDefinition.from_mapping(definition)

    definition = beginner_templates()[0].presets["balanced"].definition.to_dict()
    definition["entry_rules"][0]["right"] = {"name": "close"}
    with pytest.raises(ConfigurationError, match="必须且只能"):
        RuleStrategyDefinition.from_json(json.dumps(definition))


def test_strategy_description_is_plain_chinese() -> None:
    preset = beginner_templates()[0].presets["balanced"]

    description = preset.definition.describe(top_n=preset.top_n, rebalance=preset.rebalance)

    assert "每周调仓" in description
    assert "等权持有前5只" in description
    assert "条件失效" in description
