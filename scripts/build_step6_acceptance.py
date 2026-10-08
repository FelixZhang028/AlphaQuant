"""Build a conservative feature evidence register from actual JUnit results.

Test association records evidence, never implies that every acceptance clause
was exercised. Full sign-off is deliberately separate from a green test suite.
"""

import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/migration"
OUTPUT = ROOT / "outputs/migration"

API_PATTERNS = {
    "NAV": ["history_and_snapshot", "analytics", "plan_restores"],
    "APP": ["local_origin"],
    "HOME": ["health_openapi", "history_and_snapshot"],
    "LAND": ["health_openapi"],
    "HUB": ["health_openapi", "visual_templates"],
    "IDEA": ["preflight", "patch_request", "submission_returns", "plan_restores"],
    "VIS": ["visual_templates"],
    "NL": ["nl_adapter"],
    "PY": ["python_safety"],
    "BT": ["backtest_matches", "all_metrics", "analytics", "chart_contract", "snapshot", "preflight", "submission_returns"],
    "OPT": ["optimization", "history_and_snapshot", "real_detached_research"],
    "WF": ["walk_forward", "real_detached_research"],
    "FAC": ["factor_report", "custom_factor", "factor_combination", "real_detached_research"],
    "LIB": ["factor_report", "custom_factor"],
    "KN": ["knowledge", "ai_chat", "ai_analysis_freezes"],
    "AI": ["ai_chat", "real_detached_research", "ai_analysis_freezes", "ai_invalid", "ai_missing_model"],
    "REC": ["history_and_snapshot", "filters_pagination", "analytics"],
    "PLAN": ["plan_", "legacy_plan", "patch_request"],
    "AUD": ["backtest_matches", "optimization", "audit_preserves"],
    "EXT": ["external_evidence"],
    "OPS": ["health_openapi", "backfill_adapters"],
    "DATA": ["filters_pagination", "data_update", "health_openapi", "data_overview", "data_tables_full", "update_flags"],
    "JOB": ["cancel", "retry", "worker_crash", "concurrent", "backfill_adapters", "survives_real_api"],
    "LOOP": ["backfill_adapters"],
    "UNI": ["knowledge_write_lock"],
    "RISK": ["risk_", "all_metrics"],
    "ASSET": ["health_openapi", "settings_never"],
    "XT": ["xtick_"],
    "SET": ["settings_never", "risk_validation"],
    "AUTH": [],
    "ACC": [],
}
BROWSER_PATTERNS = {
    "NAV": ["tool search", "search empty", "four research", "backtest checks", "links children"],
    "APP": ["tool search", "search empty"],
    "HOME": ["desktop and phone"],
    "LAND": ["welcome language"],
    "HUB": ["all workspace routes"],
    "IDEA": ["backtest checks", "guided research", "invalid plan"],
    "VIS": ["visual rule", "every visual template"],
    "NL": ["natural language"],
    "PY": ["Python editor", "Python upload", "every strategy"],
    "BT": ["backtest checks", "every strategy", "four research", "invalid plan", "factor combination"],
    "OPT": ["optimization and", "optimization runs"],
    "WF": ["optimization and", "walk-forward runs"],
    "FAC": ["factor catalog", "custom factors", "factor combination"],
    "LIB": ["factor catalog"],
    "KN": ["knowledge saves", "AI full", "knowledge filtering"],
    "AI": ["AI full", "AI conversation", "AI cache", "AI input"],
    "REC": ["backtest checks", "record comparison", "four research"],
    "PLAN": ["backtest checks", "plan versions", "invalid plan"],
    "AUD": ["backtest checks", "audit opens", "audit grades"],
    "EXT": ["external material", "external duplicate", "external delayed", "external row"],
    "OPS": ["all workspace routes"],
    "DATA": ["filtered data CSV", "daily updates", "benchmark selection", "data overview", "data security_master", "data data_manifests"],
    "JOB": ["backtest checks", "backfill selection"],
    "LOOP": ["all workspace routes"],
    "UNI": ["universe additions"],
    "RISK": ["all risk actions"],
    "ASSET": ["all workspace routes"],
    "XT": ["XTick catalog", "failed XTick"],
    "SET": ["model keys"],
    "AUTH": [],
    "ACC": ["all workspace routes", "search empty"],
}
# These IDs have particularly direct evidence. Other IDs retain partial status;
# group-related tests alone cannot certify all of their exceptional UI states.
PASSED = {
    "LAND-03", "IDEA-05", "BT-08", "BT-09", "BT-10", "OPT-03", "WF-02", "WF-03",
    "FAC-07", "FAC-08", "KN-02", "KN-03", "DATA-05", "UNI-01", "UNI-02", "UNI-03",
    "RISK-01", "RISK-02", "RISK-03", "XT-03", "SET-01",
    "NAV-02", "LAND-02", "IDEA-01", "BT-01", "BT-02", "BT-03", "BT-05",
    "VIS-02", "VIS-05", "VIS-06", "NL-01", "NL-02", "NL-03", "PY-02",
    "FAC-05", "FAC-06", "OPT-04", "REC-04", "PLAN-01", "PLAN-03", "PLAN-04", "AUD-03",
    "EXT-02", "EXT-03", "EXT-04", "JOB-02",
    "DATA-01", "DATA-02", "DATA-03", "DATA-04", "DATA-06", "DATA-07", "DATA-08",
    "KN-01", "AI-01", "AI-03", "AI-04", "AI-07", "AUD-01", "AUD-02", "AUD-04",
}
DEFERRED = {"APP-01", "LAND-05", "AUTH-01", "AUTH-02", "AUTH-03", "ACC-02", "NAV-04"}
ORIGINAL = {"LAND-06", "ACC-03", "ACC-04"}


def read_results(filename):
    path = OUTPUT / filename
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failures = [case.attrib["name"] for case in cases if case.find("failure") is not None or case.find("error") is not None]
    skipped = [case.attrib["name"] for case in cases if case.find("skipped") is not None]
    if failures or skipped:
        raise RuntimeError(f"{filename}: failures={failures}, skipped={skipped}")
    return cases


def main():
    results = {name: read_results(f"step6-{name}.xml") for name in ("legacy", "api", "browser")}
    baseline = json.loads((DOCS / "feature-register.json").read_text(encoding="utf-8"))
    coverage = json.loads((DOCS / "react-coverage.json").read_text(encoding="utf-8"))
    implementation = {item["id"]: item for item in coverage["features"]}
    groups = {item["prefix"]: item for item in baseline["groups"]}
    features = []
    for feature in baseline["features"]:
        identifier = feature["id"]
        prefix = identifier.split("-")[0]
        legacy_modules = {Path(name).stem for name in groups[prefix]["tests"]}
        evidence = {
            "legacy": [case.attrib["classname"] + "::" + case.attrib["name"] for case in results["legacy"] if case.attrib.get("classname", "").split(".")[-1] in legacy_modules],
            "api": [case.attrib["classname"] + "::" + case.attrib["name"] for case in results["api"] if any(pattern in case.attrib["name"] for pattern in API_PATTERNS[prefix])],
            "browser": [case.attrib["name"] for case in results["browser"] if any(pattern in case.attrib["name"] for pattern in BROWSER_PATTERNS[prefix])],
        }
        status = "通过" if identifier in PASSED else "部分通过"
        remaining = "仍需覆盖本项标准中全部 React 操作与异常分支；关联分组测试不等于整项通过。"
        if identifier in PASSED:
            remaining = "通过范围为隔离样例与固定响应；不承诺所有行情、浏览器或外部服务状态。"
        if identifier in DEFERRED:
            status = "延后"
            remaining = "旧 URL 兼容随第七步处理。" if identifier == "NAV-04" else "用户约定暂不考虑登录，本机入口可使用。"
        elif identifier in ORIGINAL:
            status = "保留原状态"
            remaining = "原版休眠或禁用占位，无现成功能可作迁移验收。"
        elif identifier in {"ACC-01", "PLAN-02"}:
            remaining = "本机资料/方案流程已接入；账号归属隔离和真实资料读取随登录验收。"
        if prefix in {"AI", "NL", "XT", "DATA", "JOB", "ASSET"}:
            remaining += " 真实外部网络、付费模型、实际行情下载未自动执行。"
        features.append({
            "id": identifier, "name": feature["name"], "status": status,
            "route": feature["proposed_route"], "acceptance": feature["acceptance"],
            "implementation_files": implementation[identifier]["implementation_files"],
            "evidence": evidence, "remaining": remaining,
        })
    assert len(features) == 125 and len({item["id"] for item in features}) == 125
    counts = dict(Counter(item["status"] for item in features))
    result = {
        "step": 6, "baseline_commit": baseline["baseline_commit"], "feature_count": 125,
        "scope": "本机自动化回归及逐项证据登记；不等于125项全部签收",
        "test_counts": {name: len(cases) for name, cases in results.items()},
        "status_counts": counts, "features": features,
    }
    (DOCS / "step6-evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 第六步逐项验收记录", "", "基线125项，原定义不变。下表严格保留部分通过及延后项，不将绿色测试套件视为全量签收。", "", "状态统计：" + "；".join(f"{key} {value}" for key, value in counts.items()) + "。", "", "测试函数与实现路径见 [结构化证据](step6-evidence.json)。原版单元测试只证明原业务回归，不单独证明 React 交互。", "", "| 编号 | 功能 | 状态 | 关联证据数（原版/API/浏览器） | 未验边界 |", "| --- | --- | --- | --- | --- |"]
    for item in features:
        evidence_counts = "/".join(str(len(item["evidence"][name])) for name in results)
        lines.append(f"| {item['id']} | {item['name']} | {item['status']} | {evidence_counts} | {item['remaining']} |")
    (DOCS / "step6-feature-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Keep the original acceptance clauses intact, refresh only migration status.
    checklist = DOCS / "acceptance-checklist.md"
    text = checklist.read_text(encoding="utf-8")
    text = text.replace("当前所有项目均为待迁移、待验收。", "第六步最新状态见[逐项验收记录](step6-feature-results.md)；保留部分通过、延后及原版占位，不声明125项全通过。")
    for item in features:
        marker = f"| {item['id']} |"
        for line in text.splitlines():
            if line.startswith(marker):
                cells = line.split("|")
                cells[4] = " 已接入 " if item["status"] not in {"延后", "保留原状态"} else f" {item['status']} "
                cells[5] = f" {item['status']} "
                cells[6] = " [第六步证据](step6-feature-results.md) "
                text = text.replace(line, "|".join(cells))
                break
    checklist.write_text(text, encoding="utf-8")
    print(json.dumps({"test_counts": result["test_counts"], "status_counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
