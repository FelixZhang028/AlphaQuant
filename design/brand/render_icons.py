"""Render the Prismind icons into the PNG sizes the sites need (run: python render_icons.py).

Uses the local Microsoft Edge (or Chrome) in headless mode with a transparent background, so the
rounded corners stay transparent. The apple-touch icon is square without rounded corners, because
iOS rounds it itself.

Writes to landing/public/brand/ and admin/public/brand/; the old fellowquant-logo.png is kept.
"""
import pathlib
import shutil
import subprocess
import tempfile

here = pathlib.Path(__file__).parent
root = here.parent.parent
landing = root / "landing" / "public" / "brand"
admin = root / "admin" / "public" / "brand"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
browser = next((b for b in BROWSERS if pathlib.Path(b).exists()), None)
if browser is None:
    raise SystemExit("没有找到 Edge 或 Chrome")

full = (here / "prismind-icon.svg").read_text(encoding="utf-8")
small = (here / "prismind-icon-small.svg").read_text(encoding="utf-8")
square = full.replace('rx="116"', 'rx="0"').replace('rx="114.5"', 'rx="0"')    # 给 iOS 用的方形版本


def render(svg: str, size: int, out: pathlib.Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "icon.svg").write_text(svg, encoding="utf-8")
        page = tmp / "page.html"
        page.write_text(f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:transparent;overflow:hidden}}'
                        f'img{{display:block}}</style></head><body><img src="icon.svg" width="{size}" height="{size}"></body></html>',
                        encoding="utf-8")
        shot = tmp / "shot.png"
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--default-background-color=00000000", f"--window-size={size},{size}", f"--screenshot={shot}",
                        page.as_uri()], check=True, capture_output=True, timeout=120)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shot, out)
    print(f"{out.relative_to(root)}  {size}x{size}")


for folder in (landing, admin):
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(here / "prismind-icon-small.svg", folder / "prismind-icon-small.svg")
    render(small, 32, folder / "favicon-32.png")
    render(small, 16, folder / "favicon-16.png")
shutil.copyfile(here / "prismind-icon.svg", landing / "prismind-icon.svg")
render(full, 512, landing / "prismind-icon-512.png")
render(full, 192, landing / "prismind-icon-192.png")
render(square, 180, landing / "apple-touch-icon.png")
render(small, 64, landing / "prismind-mark-64.png")
