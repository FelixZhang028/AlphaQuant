# FellowQuant 品牌图标设计

## 🏷️ 品牌名称分析

**FellowQuant** — 已是非常出色的命名，建议保留：

| 创始人 | 贡献字母 | 含义 |
|--------|----------|------|
| **F**elix | F‑e‑l | 首字母 + 元音 |
| W**ell**ord | e‑l‑l‑o | 核音融合 |
| **Fellow** | | 伙伴、同仁 — 量化是团队游戏 |
| **Quant** | | 量化交易 — 行业锚点 |

> 备选名（仅供参考）：`Felwell Capital`、`FW Quant`、`QuantFellows`

---

## 🎨 设计语言

参考 **DeepSeek** 图标风格：扁平极简、蓝色系、生物意象、圆润友好。

### 色板

| 用途 | 色值 | 说明 |
|------|------|------|
| 主蓝 | `#4D6BFE` | DeepSeek 蓝 |
| 浅蓝 | `#5B7BFF` | 渐变亮端 |
| 深蓝 | `#2743C9` | 渐变暗端 |
| 品蓝 | `#16235A` | 文字色 |
| 趋势青 | `#9FE0FF` | 趋势线 & 高亮 |
| 白渐变 | `#FFFFFF → #D9E6FF` | 鲸尾填充 |

---

## 🐋 三款概念

### Concept A — 鲸尾·趋势线 ⭐ 推荐

**文件：** `fellowquant-concept-a-whale-trend.svg`

设计：一只鲸尾从上涨趋势线中跃出，象征量化信号从数据浪潮中捕捉机会。

- 鲸尾（双鳍）= 两位创始人 Felix & Wellord 并肩
- 趋势线 + 数据点 = 量化策略的信号捕捉
- 跃出姿态 = 突破、Alpha

### Concept B — 双鲸·伙伴

**文件：** `fellowquant-concept-b-fellow-tails.svg`

设计：两条鲸尾重叠（一青一白），呼应 "Fellow" = 伙伴。

- 白色主尾 = 主力策略
- 青色辅尾 = 伙伴策略 / 创始人协作
- 共享基线 = 统一风控

### Concept C — K线阶梯

**文件：** `fellowquant-concept-c-candle-stairs.svg`

设计：四根递增K线烛台，最右一根以青色高亮 + 信号点。

- 阶梯上升 = 持续 Alpha
- K线烛台 = 量化最直觉的符号
- 信号点 = 入场信号

---

## 📐 横排 Logo (Lockup)

**文件：** `fellowquant-lockup-a.svg`

鲸尾标记 + "FellowQuant" 文字 + "SYSTEMATIC QUANTITATIVE TRADING" 标语。

- "Fellow" 品蓝 / "Quant" 主蓝 — 视觉节奏
- 适用于：官网页眉、PPT 封面、名片

---

## 📁 文件清单

```
design/logo/
├── fellowquant-concept-a-whale-trend.svg    # ⭐ 主推图标
├── fellowquant-concept-b-fellow-tails.svg   # 双鲸伙伴
├── fellowquant-concept-c-candle-stairs.svg  # K线阶梯
├── fellowquant-lockup-a.svg                 # 横排 Logo
└── png/
    ├── fellowquant-concept-a-whale-trend.png    # 1024×1024
    ├── fellowquant-concept-b-fellow-tails.png
    ├── fellowquant-concept-c-candle-stairs.png
    ├── fellowquant-lockup-a.png                  # 2600×700
    ├── fellowquant-icon-32x32.png                # favicon
    ├── fellowquant-icon-64x64.png
    ├── fellowquant-icon-128x128.png
    ├── fellowquant-icon-256x256.png
    ├── fellowquant-icon-512x512.png              # App 图标
    ├── favicon-32.png                            # favicon
    └── apple-touch-icon-180.png                  # iOS 触摸图标
```

---

## 🔧 使用建议

1. **Favicon**：`favicon-32.png` 放入网站根目录，HTML `<link rel="icon" href="favicon-32.png">`
2. **iOS**：`apple-touch-icon-180.png` → `<link rel="apple-touch-icon" href="apple-touch-icon-180.png">`
3. **PWA manifest**：使用 512×512 和 192×192（可用 sharp 从 1024 缩放）
4. **深色模式**：SVG 可直接修改渐变色反转；或另存 `*-dark.svg`（白底→深底，蓝→青）
5. **正式 Wordmark**：当前横排版使用系统字体（Segoe UI）；正式发布建议使用 Inter / SF Pro Display 等专业无衬线体，并将文字转为路径

---

*Generated for FellowQuant · Felix & Wellord · 2025*
