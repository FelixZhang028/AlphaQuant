"""Map the immutable feature baseline to React files, without claiming acceptance."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/migration"
PAGES = "frontend/src/pages/"
FILES = {
    "NAV": ["frontend/src/main.tsx", "frontend/src/navigation.ts"],
    "APP": ["frontend/src/main.tsx"],
    "HOME": [PAGES + "Home.tsx"],
    "LAND": [PAGES + "Home.tsx"],
    "HUB": [PAGES + "Home.tsx"],
    "IDEA": [PAGES + "Strategies.tsx", PAGES + "Backtests.tsx"],
    "VIS": [PAGES + "Strategies.tsx"],
    "NL": [PAGES + "Strategies.tsx"],
    "PY": [PAGES + "Strategies.tsx"],
    "BT": [PAGES + "Backtests.tsx"],
    "OPT": [PAGES + "Research.tsx"],
    "WF": [PAGES + "Research.tsx"],
    "FAC": [PAGES + "Factors.tsx"],
    "LIB": [PAGES + "Factors.tsx"],
    "KN": [PAGES + "AI.tsx"],
    "AI": [PAGES + "AI.tsx"],
    "REC": [PAGES + "Research.tsx"],
    "PLAN": [PAGES + "Research.tsx", PAGES + "Backtests.tsx", PAGES + "Strategies.tsx"],
    "AUD": [PAGES + "Research.tsx"],
    "EXT": [PAGES + "Research.tsx"],
    "OPS": [PAGES + "Home.tsx"],
    "DATA": [PAGES + "Data.tsx"],
    "JOB": [PAGES + "Data.tsx"],
    "LOOP": [PAGES + "Data.tsx"],
    "UNI": [PAGES + "Data.tsx"],
    "RISK": [PAGES + "Settings.tsx"],
    "ASSET": [PAGES + "Data.tsx"],
    "XT": [PAGES + "Data.tsx"],
    "SET": [PAGES + "Settings.tsx"],
    "AUTH": [PAGES + "Home.tsx"],
    "ACC": [PAGES + "Home.tsx"],
}


def main():
    baseline = json.loads((DOCS / "feature-register.json").read_text(encoding="utf-8"))
    rows = []
    for feature in baseline["features"]:
        identifier = feature["id"]
        files = FILES[identifier.split("-")[0]]
        assert all((ROOT / path).is_file() for path in files)
        status, note = "已接入，待逐项验收", "功能对照与边界测试属于第六步"
        if identifier in {"APP-01", "LAND-05", "AUTH-01", "AUTH-02", "AUTH-03", "ACC-02"}:
            status, note = "随登录后接入", "用户已明确暂不考虑登录；旧账号库保持原归属"
        elif identifier == "NAV-04":
            status, note = "正式切换时处理", "新旧入口并存；旧 URL 跳转兼容留到第七步"
        elif identifier == "LAND-06":
            status, note = "原休眠代码保留", "不将旧版休眠内容声称为已开放功能"
        elif identifier in {"ACC-03", "ACC-04"}:
            status, note = "保留未开放说明", "原版禁用占位，没有新增持久化账号功能"
        elif identifier in {"ACC-01", "PLAN-02"}:
            status, note = "本机模式已接入", "导航与本机方案可用；账号资料和私有方案列表随登录接入"
        rows.append(
            {
                "id": identifier,
                "name": feature["name"],
                "route": feature["proposed_route"],
                "implementation_files": files,
                "implementation_status": status,
                "acceptance_status": "待第六步验收",
                "note": note,
            }
        )
    assert len(rows) == 125 and len({row["id"] for row in rows}) == 125
    result = {
        "baseline_commit": baseline["baseline_commit"],
        "step": 5,
        "feature_count": len(rows),
        "scope": "实现索引；不等同于完整功能验收",
        "features": rows,
    }
    (DOCS / "react-coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Mapped {len(rows)} baseline feature IDs")


if __name__ == "__main__":
    main()
