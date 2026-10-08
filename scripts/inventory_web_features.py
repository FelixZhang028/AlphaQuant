"""Read Streamlit source with AST; never import pages or execute business actions."""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src/quant_platform/web"
OUTPUT = ROOT / "docs/migration/source-inventory.json"
INPUTS = {
    "text_input", "text_area", "number_input", "date_input", "time_input", "selectbox",
    "multiselect", "radio", "checkbox", "toggle", "slider", "select_slider", "pills",
    "segmented_control", "file_uploader", "data_editor", "color_picker", "chat_input",
}
ACTIONS = {"button", "form_submit_button", "download_button", "page_link", "link_button",
           "switch_page", "rerun", "stop", "login", "logout"}
OUTPUTS = {"dataframe", "table", "metric", "line_chart", "area_chart", "bar_chart",
           "scatter_chart", "altair_chart", "plotly_chart", "pyplot", "vega_lite_chart",
           "json", "code", "error", "warning", "success", "info", "progress", "status",
           "exception", "write_stream", "chat_message", "image", "audio", "video"}
STRUCTURE = {"title", "header", "subheader", "tabs", "expander", "form", "dialog",
             "Page", "navigation", "popover"}
METHODS = INPUTS | ACTIONS | OUTPUTS | STRUCTURE

def expression(node: ast.AST | None) -> str | None:
    return ast.unparse(node) if node is not None else None

class Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.context: list[str] = []
        self.ui: list[dict] = []
        self.state: set[str] = set()
        self.helper_calls: list[dict] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.context.append("function " + node.name)
        self.generic_visit(node)
        self.context.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        self.context.append("if " + ast.unparse(node.test))
        for child in node.body:
            self.visit(child)
        self.context.pop()
        if node.orelse:
            self.context.append("else of " + ast.unparse(node.test))
            for child in node.orelse:
                self.visit(child)
            self.context.pop()

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if ast.unparse(node.value) == "st.session_state":
            self.state.add(ast.unparse(node.slice))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        function = ast.unparse(node.func)
        method = function.rsplit(".", 1)[-1]
        if function.startswith("st.session_state.") and node.args:
            self.state.add(ast.unparse(node.args[0]))
        if method.startswith("render_") or method in {"tool_button", "open_tool", "open_result", "run_embedded", "javascript_html"}:
            self.helper_calls.append({"line": node.lineno, "function": function,
                                      "arguments": [ast.unparse(x) for x in node.args],
                                      "keywords": {k.arg or "**": ast.unparse(k.value) for k in node.keywords}})
        if method in METHODS and isinstance(node.func, ast.Attribute):
            base = ast.unparse(node.func.value)
            # Store non-st receivers too: Streamlit columns/containers expose these methods.
            category = ("input" if method in INPUTS else "action" if method in ACTIONS
                        else "output" if method in OUTPUTS else "structure")
            self.ui.append({
                "line": node.lineno, "method": function, "category": category,
                "label_or_first_argument": expression(node.args[0]) if node.args else None,
                "positional_arguments": [ast.unparse(x) for x in node.args],
                "keyword_arguments": {k.arg or "**": ast.unparse(k.value) for k in node.keywords},
                "conditions_and_function": list(self.context),
                "receiver_requires_review": base != "st" and not base.startswith("st."),
            })
        self.generic_visit(node)

def navigation(tree: ast.Module) -> dict:
    result: dict = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = ast.unparse(node.targets[0])
        if name not in {"WORKSPACES", "TOOLS", "EXTRA_ROUTES"}:
            continue
        if name == "EXTRA_ROUTES":
            result["legacy_routes"] = ast.literal_eval(node.value)
            continue
        rows = []
        assert isinstance(node.value, (ast.Tuple, ast.List))
        for call in node.value.elts:
            assert isinstance(call, ast.Call)
            args = [ast.literal_eval(x) for x in call.args]
            keys = ["title", "path", "icon"] if name == "WORKSPACES" else [
                "key", "title", "path", "workspace", "description", "initial_state"]
            rows.append(dict(zip(keys, args)))
        result["workspaces" if name == "WORKSPACES" else "tools"] = rows
    return result

files = []
for path in sorted(WEB.rglob("*.py")):
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    visitor = Visitor()
    visitor.visit(tree)
    imports = sorted({node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                      and node.module and node.module.startswith(("quant_platform", "trading_agents"))})
    links = sorted(set(re.findall(r'href=["\']([^"\']+)["\']', source)))
    files.append({"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "line_count": len(source.splitlines()), "ui_calls": visitor.ui,
                  "session_state_keys_or_expressions": sorted(visitor.state), "local_imports": imports,
                  "html_link_targets": links, "ui_helper_calls": visitor.helper_calls})

nav = navigation(ast.parse((WEB / "navigation.py").read_text(encoding="utf-8-sig")))
registered = {row["path"] for row in nav["workspaces"] + nav["tools"]} | set(nav["legacy_routes"])
pages = {p.relative_to(WEB).as_posix() for p in (WEB / "app_pages").glob("*.py")}
missing = sorted(p for p in registered if not (WEB / p).is_file())
assert not missing, missing
assert not pages - registered, "Unmapped page files: " + repr(pages - registered)
counts = Counter(call["category"] for item in files for call in item["ui_calls"])
catalog_path = WEB / "assets/xtick_apidoc.json"
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
dynamic_catalog = {"source": catalog_path.relative_to(ROOT).as_posix(),
                   "sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
                   "category_count": len(catalog),
                   "api_count": sum(len(c.get("docApis", [])) for c in catalog),
                   "categories": [{"id": c["id"], "name": c["name"],
                       "apis": [{"id": a.get("id"), "name": a.get("name"), "url": a.get("url"),
                                 "inputs": [p for p in a.get("inputParas", []) if p.get("name") != "token"],
                                 "outputs": a.get("outputParas", [])} for a in c.get("docApis", [])]}
                                  for c in catalog]}
metric_catalog = []
for node in ast.walk(ast.parse((WEB / "home.py").read_text(encoding="utf-8-sig"))):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_render_metric_grid":
        metric_catalog.append({"source": "src/quant_platform/web/home.py", "line": node.lineno,
                               "metrics": [{"label": label, "key": key, "format": fmt}
                                           for label, key, fmt in ast.literal_eval(node.args[1])]})
report = {"baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
          "scope": "Static source inventory; calls are source locations, not runtime-tested features. Non-st receivers require review.",
          "web_python_files": len(files), "page_files": len(pages), "registered_source_paths": sorted(registered),
          "ui_call_counts": dict(counts), **nav, "metric_catalog": metric_catalog,
          "xtick_catalog": dynamic_catalog, "files": files}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: report[k] for k in ["baseline_commit", "web_python_files", "page_files", "ui_call_counts"]}, ensure_ascii=False))
print("Wrote " + str(OUTPUT))
