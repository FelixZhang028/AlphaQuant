# 智投引擎 · 品牌首页（Landing）

「智投引擎」量化交易平台的品牌官网首页 + 登录/功能台（聚合了 FellowQuant 工作台的全部功能模块）。深色奢华风格，Vue 3 + Vite + Tailwind CSS v3。

## 技术栈

- Vue 3（SFC，`<script setup>`）
- Vite 5
- Tailwind CSS v3 + PostCSS + Autoprefixer
- Inter 字体（Google Fonts，失败时回退系统字体栈）
- 无外部图片资源：产品卡头图均为纯 CSS 渐变占位，噪点为内联 SVG

## 页面入口

- `index.html` → 官网首页（`src/main.js` → `App.vue`）
- `auth.html` → 登录/注册（`src/auth.js` → `AuthPage.vue`）
- `app.html` → 功能台（`src/workspace.js` → `WorkspacePage.vue`）

## 功能台（AlphaQuant 导航与 v4 业务模块）

侧栏沿用 AlphaQuant 的分组和底部布局，并保留 v4 的全部业务入口：

- **首页**：欢迎、指标、快速回测、我的策略。
- **AI 智能投研**：AI研究员、先验知识库、WeKnora 知识库问答、Jev 决策中心。
- **策略研究**（4 个入口）：策略工作室、因子实验室、回测与验证、研究记录。策略工作室内含策略管理、模板与积木、自然语言、Python 策略；回测与验证内含单次回测、参数优化（含样本外验证）、可信度审计、成交核查。
- **数据管理**：数据资产、数据更新、XTick、风险管理、股票池。
- **系统**：个人中心、设置。

侧栏独立滚动，支持卡片和账户入口固定在底部；移动端选中模块后关闭菜单。
支持卡片沿用 AlphaQuant 的 GitHub Issue/Star 链接。页内功能导航保留原有 URL key，打开旧链接时仍高亮所属主入口。导航支持 `?view=knowledge-base`、`?view=decision-center` 等直达及浏览器前进/后退。

实现要点：
- `src/api.js` 封装全部后端 REST 接口（FastAPI，默认 `http://127.0.0.1:8000`，可用 `VITE_API_BASE` 覆盖）。
- `src/workspace/modules.js` 为导航分组与视图注册表（懒加载视图组件）。
- `src/workspace/ui/` 提供共享玻璃 UI 组件：`MetricCard / SectionCard / DataTable / LineChart / StatusPill / EmptyState / FormField`。
- `src/workspace/views/` 为各功能视图，均遵循 `src/workspace/VIEW_SPEC.md` 的设计规范。
- 后端扩展见 `../dashboard/backend/app/routes/workspace.py` 与 `database.py`（策略包/自定义因子/风控/股票池/模拟账户等 SQLite 表，业务数据为可复现的模拟数据，接口形状与 v3 对齐）。

## 目录结构

```
landing/
├── index.html / auth.html / app.html     # 三个页面入口
├── package.json
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── src/
│   ├── main.js / auth.js / workspace.js   # 各入口脚本
│   ├── App.vue                            # 官网页面装配
│   ├── api.js                             # 后端 API 封装
│   ├── style.css                          # Tailwind 层 + 玻璃/网格/动画
│   ├── composables/useReveal.js           # IntersectionObserver 滚动渐显
│   ├── components/                        # 官网区块 + AuthPage + WorkspacePage(功能台外壳)
│   └── workspace/
│       ├── modules.js                     # 导航分组 + 视图注册
│       ├── VIEW_SPEC.md                   # 视图开发规范
│       ├── ui/                            # 共享玻璃 UI 组件
│       └── views/                         # 功能台各模块视图
```

## 运行

```bash
cd landing
npm install
npm run dev      # 开发预览 http://localhost:5173（登录后进入 app.html 功能台）
npm run build    # 生产构建，输出 dist/
npm run preview  # 预览构建产物
```

后端（功能台接口）位于 `../dashboard/backend`：

```bash
cd ../dashboard/backend
pip install -r requirements.txt
uvicorn app.main:app --reload     # http://localhost:8000
```

## 交互说明

- 所有官网区块通过 `v-reveal`（IntersectionObserver）实现进入视口渐显，支持 `v-reveal="{ delay: 150 }"` 错峰延迟
- Hero 背景光晕随滚动视差下移（rAF 节流）
- 卡片 hover 上浮 + 边框/阴影变化
- 导航栏滚动超过 24px 后更不透明并加深阴影
- 锚点平滑滚动（`scroll-behavior: smooth`）
- 响应式：移动端折叠菜单
- 尊重 `prefers-reduced-motion`

## WeKnora 与 Jev

登录后打开左侧「系统 → 设置」，或在各集成页面点击「配置」。

- WeKnora：填写服务根地址（如 `http://127.0.0.1:8080`，也支持带 `/api/v1`）和空间 API Key。支持知识库列表、文档检索、流式问答聚合及引用。服务需已部署并建好知识库；Key 需具有相应知识库读取、检索和聊天权限。
- Jev：填写 OpenRouter API Key，默认模型 `typesafe/jev-1.13`，默认决策地址 `https://openrouter.ai/api/alpha/decisions`。Choice、Noul、Score 使用命名 questions 和 criteria；页面支持文本/JSON 上下文。
- 未配置时显示演示结果；已配置后的调用失败显示错误，不以演示数据冒充真实结果。
- 配置写入后端 `data/runtime/agent_lab/user_{id}/`；API 不回显密钥，留空保留原 Key。环境变量 `WEKNORA_BASE_URL`、`WEKNORA_API_KEY`、`OPENROUTER_API_KEY` 可作为部署默认值。
- 旧的全局 `data/runtime/data_source_settings.json` 内 WeKnora 配置保留在原文件；请在当前账户重新保存，以启用账户隔离。
- 先验知识库复用 AI研究员的账户知识存储；WeKnora 检索内容不会自动写成已验证的投资事实。

API 依据：[WeKnora 官方文档](https://github.com/Tencent/WeKnora/tree/main/website-docs/04-api)、[OpenRouter OpenAPI](https://openrouter.ai/openapi.json)。

验证命令：

```bash
# landing/
npm run build
# dashboard/backend/（测试环境需安装 pytest 和 httpx）
python -m pytest tests/unit/test_workspace_integrations.py tests/unit/test_forensics.py -q
```

真实外部服务需要有效配置；回归测试使用官方格式的模拟响应，不调用付费模型。
