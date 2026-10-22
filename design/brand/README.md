# 镜思 Prismind 的图标

| 文件 | 用途 |
|---|---|
| `prismind-icon.svg` | 完整版图标（512×512 矢量图），64 像素以上用它 |
| `prismind-icon-small.svg` | 简化版图标，48 像素以下用它（浏览器标签页、页面角落的小 logo） |
| `prismind_icon.py` | 生成完整版图标的脚本：棱镜的形状、光路（按折射定律算）、背景都在这里改，运行 `python prismind_icon.py` 重新生成 `prismind-icon.svg` |
| `render_icons.py` | 把两个 SVG 导出成网站要用的 PNG（用本机的 Edge 渲染），运行 `python render_icons.py` |
| `legacy/fellowquant-logo.png` | 旧的 FellowQuant 图标备份（网站目录里的 `landing/public/fellowquant-logo.png` 也保留着） |

## 导出到哪里

`render_icons.py` 会写到：

- `landing/public/brand/`：`prismind-icon.svg`、`prismind-icon-small.svg`、`prismind-icon-512.png`、`prismind-icon-192.png`、`apple-touch-icon.png`（180，方形，iOS 自己会加圆角）、`prismind-mark-64.png`、`favicon-32.png`、`favicon-16.png`
- `admin/public/brand/`：`prismind-icon-small.svg`、`favicon-32.png`、`favicon-16.png`

## 设计说明

- 一个 60° 的玻璃三棱镜，三个角是平滑的圆角，站在光滑的地面上，位于画面正中。
- 左边的光源射出一束白光；光路按折射定律对 40 种波长分别计算：紫光偏折最多、红光最少，颜色重叠的地方是白色（玻璃里和刚出来时），越远越分开成连续的光谱。色散比真实的大，这样在图标尺寸下看得出来。
- 背景：极光光晕、带坐标轴和热力图格子的墙面、白光后面一条有涨有跌但整体平的走势线（不暗示上涨）。
- 改名和图标的讨论记录：英文名 Prismind（Prism + mind），中文名镜思（读音同“静思”，冷静地看数据）。
