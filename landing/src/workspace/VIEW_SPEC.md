# 功能台视图开发规范（给子代理）

你要实现 `D:\code\github_proj\FellowQuant_v4\landing\src\workspace\views\` 下的一个 Vue 视图组件。
项目是 Vue 3 + Vite + Tailwind CSS v3，深色奢华毛玻璃 UI。请严格遵循本规范与既定设计语言，不要引入新依赖（禁止 ECharts/图表库，用已提供的 LineChart）。

## 一、通用约定

每个视图文件结构：

```vue
<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiFunc1, apiFunc2 } from '../../api.js'
import MetricCard from '../ui/MetricCard.vue'
import SectionCard from '../ui/SectionCard.vue'
// 按需引入其它 ui 组件

const props = defineProps({
  user: { type: Object, default: null },
  notify: { type: Function, default: () => {} },
})

// ... 状态与逻辑 ...
</script>

<template>
  <div class="space-y-6">
    <!-- 内容 -->
  </div>
</template>
```

规则：
- 根元素固定 `<div class="space-y-6">`。
- 必须声明 `props`（user / notify）。用 `props.notify(msg)` 弹提示（如「已保存」「已删除」「操作失败」）。
- 所有 API 调用包在 try/catch，失败用 `props.notify(e.message || '加载失败')`，可同时用局部 ref 存错误文本展示。
- 页面无需鉴权重定向（外壳已处理）。不要 import vue-router。
- 官网登录入口根据当前浏览器会话切换，登录页通过 `restoreSession` 验证已有会话后自动进入工作台；工作台仅在明确 401 时清除会话，网络或服务错误保留会话并展示重试，不能将任意请求失败视为退出登录。
- 设置页（`views/SettingsView.vue`）：外观（主题跟随系统 / 浅色 / 深色，重新打开新手引导）；研究默认值（回测初始资金、最多持仓、调仓频率、最近几年的区间，AI 研究员是否默认参考研究经验，`getPreferences/savePreferences`，保存在账户里；回测页第一次打开时填入，所选策略自带持仓和调仓时以策略为准）；今天各类 AI 的剩余次数（`todayUsage`）；我的数据（股票池和风控摘要、导出我的数据 `exportMyData`，一个 JSON 文件，不含密码）；账户（去个人中心）；关于（版本、法律页面、联系邮箱、问题反馈）。管理员另外看到管理后台入口和知识库配置。
- 个人中心：修改密码（`changePassword`，要原密码，改完其他设备的登录失效，这台设备拿到新令牌）、退出登录（`logout` 通知后端，所有设备的登录都失效）、注销账户（`deleteAccount`，输入密码确认，删除账户和全部研究数据；管理员不显示）。注册页按 `registrationMode()` 显示邀请码输入框或“暂时不开放注册”。
- 中文文案。无外部图片/字体。
- 加载状态可用 `ref(false)` 控制，展示「加载中…」或按钮 disabled。

## 二、设计语言（必须一致）

- 工作台外壳铺满窗口；内容在侧栏右侧居中，并保留现有内边距。普通页最大 1280px，复杂研究页 1440px，账户/设置页 960px，由 `modules.js` 的 `contentLayout` 和 `workspace.css` 统一管理。小屏自动缩至可用宽度。
- 侧栏的「数据」分组：所有人看到数据说明（`views/DataGuideView.vue`、`dataGuide.js`：有哪些数据、从哪里来、多久更新、回测怎么用、有什么局限，只读）、股票查询（`views/MarketLookupView.vue`，即行情查询）和股票池管理；数据运维（原数据更新页）只有管理员看得到，数据检查（原数据概览）和 XTick 从数据运维进入（`modules.js` 的 `admin: true`、`adminViews`、`viewFor`、`visibleGroups`）。普通用户打开旧链接（`data-update`、`data-management`、`xtick-data`）时落到数据说明，地址栏一起改。数据都由平台统一更新：给普通用户的提示一律写“平台还没有这类数据，管理员更新后就能用”，按钮去数据说明，不叫用户自己下载。
- 管理员的数据页：XTick 从数据检查的「数据源与高级工具」进入，保留原直达链接；风险管理属于回测与验证。概览标题及三个玻璃按钮置顶，其下「数据详情与版本说明」常驻展开，再展示股票池状态摘要。本地行情查询默认展示全部已下载股票，支持名称/代码搜索、当前股票池范围、后端分页与单股详情/更新/加入股票池；不能把历史覆盖率当作最新行情状态。日常更新参数直接展示，仅高级更新折叠；股票池高级筛选紧随名称搜索，删除操作位于每行末尾。
- 字号由 `../workspace.css` 限定在 `.workspace-shell` 内：正文/表格 15px，导航/输入 16px，标签/说明 14px，小注释至少 13px，区块标题 18px。下面的 `text-sm` / `text-xs` 工具类在工作台内遵循此映射，不影响官网。
- 卡片：`glass rounded-2xl p-5`（悬浮高光可加 `glass-sheen`）。
- 区块标题：`<h2 class="text-sm font-semibold text-white">标题</h2>`；副说明 `text-xs text-slate-500`。
- 表单标签：`text-xs text-slate-400`；正文 `text-slate-300`；弱化 `text-slate-500`。
- 主按钮：`class="rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/40 transition hover:-translate-y-0.5 disabled:opacity-70"`。
- 次按钮：`class="rounded-full border border-white/10 px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5"`。
- 输入框/下拉：`w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-400/40`。
- 正数 `text-emerald-300`，负数 `text-rose-300`。
- 指标行用 `grid gap-5 sm:grid-cols-2 xl:grid-cols-4`。
- Tab 用分段按钮：容器 `flex rounded-full border border-white/10 bg-white/5 p-0.5 text-xs`，每个 tab 按钮 `rounded-full px-3 py-1 transition`，激活态 `bg-gradient-to-r from-indigo-500 to-violet-500 text-white`，未激活 `text-slate-400 hover:text-slate-200`。

## 三、共享 UI 组件（`../ui/`）

- `MetricCard.vue`：props `label, value, sub, up(boolean|null), tone(css类)`
  `<MetricCard label="累计收益" value="12.3%" up tone="text-emerald-300" />`
- `SectionCard.vue`：props `title, hint`；插槽 `default`（内容）、`#actions`（右上角按钮组）
  `<SectionCard title="因子评估" hint="说明"><p>内容</p></SectionCard>`
- `DataTable.vue`：props `columns`(数组 `{key,label,align?}`，align 可 `'right'`)、`rows`(对象数组)、`empty`
  `<DataTable :columns="cols" :rows="rows" empty="暂无数据" />`
- `LineChart.vue`：props `series`(数组 `{label,color,points:[数字]}`)、`height`(默认160)、`fill`
  `<LineChart :series="[{label:'净值',color:'#818cf8',points:[1.0,1.02,...]}]" :height="180" />`
- `StatusPill.vue`：props `value`（自动配色：运行中/完成/成功/批准→绿，警告/暂停→黄，失败/拒绝/停止→红）
- `EmptyState.vue`：props `text`
- `FormField.vue`：props `label, type('text'|'number'|'date'|'select'|'textarea'|'checkbox'), modelValue(v-model), options([{value,label}]), placeholder, min, max, step, disabled, hint, rows`
  `<FormField label="名称" v-model="name" />`
  `<FormField label="类型" type="select" v-model="t" :options="[{value:'a',label:'A'}]" />`
  `<FormField label="描述" type="textarea" v-model="desc" :rows="4" />`
  `<FormField label="启用" type="checkbox" v-model="enabled" />`

## 四、API 函数与返回结构（`../../api.js`）

所有函数已封装好。以下列出与本视图相关的签名与关键返回结构。数字均来自后端模拟，直接展示即可。

### 策略包（策略创作中心 / 自然语言 / 零代码工作台）
- `listPackages()` → `{ items:[{package_id,name,definition,top_n,rebalance,source,created_at,describe_text}], total }`
- `createPackage({definition:{name,description,entry_logic,entry_rules:[{left:{name,window},operator,value|right}],ranking:{indicator:{name,window},direction}},top_n,rebalance,source,style})` → 返回单个 package 对象。保存的是提交的规则；`source` 为 `template:<id>` 时后端与该风格的模板原文比较，记为 `template:<id>:<style>`（一致）或 `template_modified:<id>:<style>`（改过）。没有提交规则的旧客户端按模板原文保存。
- `deletePackage(id)`、`copyPackage(id, name?)` → package 对象、`getPackage(id)`
- `preflightPackage(payload)` → `{ warnings:[], minimum_history_days, description }`；`description` 是按将要执行的规则读出的一句中文说明，规则无效时返回 422 和原因。
- `backtestPackage(id, payload?)` → `{ id, run_id, status, summary:{equity:[],total_return,max_drawdown,sharpe,win_rate,final_equity,...} }`
- `studioOptions()` → `{ templates:[{template_id,name,summary,suitable_market,main_risk,top_n,rebalance,presets:{风格:{definition,top_n,rebalance}}}], indicators:{name:中文}, indicator_windows:{name:{default,minimum,maximum}|null}, operators:{key:中文}, frequencies:['daily','weekly','monthly'], directions:['descending','ascending'], styles:['conservative','balanced','aggressive'] }`

### 自然语言
- `nlProviders()` → `{ providers:[{key,display_name,default_base_url,requires_key,models:[],default_model}] }`
- `nlGenerate({description,provider,top_n,rebalance})` → `{ definition, explanation, minimum_history_days }`

### 因子研究室
- `listFactors()` → `{ factors:[{name,display_name,category,description,formula,required_fields:[],min_history,direction,version}] }`
- `evaluateFactor({factor_name,start_date,end_date,horizon,n_groups})` → `{ factor_name,horizon,n_groups,ic_mean,ic_ir,rank_ic_mean,rank_ic_ir,long_short_mean,first_half_ic,second_half_ic,turnover_mean,daily_ic:[{date,ic,rank_ic}],group_mean_returns:{G1:..,G2:..},notes }`
- `compositeFactors({factor_names:[],weight_mode:'equal'|'ic'|'custom',weights?,winsorize,zscore,fill_method,corr_threshold,start_date,end_date,horizon,n_groups})` → `{ correlation_matrix:{},dropped_factors:[],weights:{},composite_spec:[{name,weight}],report:{同 evaluateFactor 的 report 字段} }`
- `createCustomFactor({name,display_name,description,field,operator,window,window2,direction})` → `{ created:{...} }`
- `deleteCustomFactor(name)`

### AI 研究员
- `aiStatus()` → `{ ai:{available,model},decision:{available,model},usage:{brief:{limit,used,remaining},question:{...},review:{...}},experience_count,latest_date }`；管理员的 `limit`、`remaining` 为 null（不限次数）
- `decideBrief(id)` → 根据已经保存的数据调用 Jev；分析记录增加 `odds:{choice,probabilities,confidence,model}|null`。不依赖文本模型，成功计入评估额度，失败退还额度；已有结果直接返回。文字解读继续保存于 `brief`。
- 新报告 `odds.report_version=2`，增加 `summary,as_of,dimensions:[{key,title,status,assessment,confidence,probabilities,interpretation,evidence}],supports,concerns,coverage,followups,risk`。五个维度按实际数据可用性提问，缺项单独显示，不与中性混淆。`decideBrief(id,{upgrade:true})` 主动补全旧记录；补全失败保留原报告，已经是新版时不重复计费。页面使用 `JevStockReport.vue`，旧版保留概率图和升级入口。
- `createBrief({symbol,trade_date,use_experience})` → 第一步，只整理本地数据（`brief` 为 null）；`readBrief(id)` → 第二步，AI 根据保存的数据写解读（已解读过的直接返回，不再计数）。两者都返回一次分析：`{ id,symbol,name,trade_date,created_at,model,facts:{symbol,name,trade_date,facts:[{key,group,label,text,value,as_of}],missing:[{group,reason}],notes:[]},brief:{tilt,confidence,summary,bull_points:[{text,evidence:[fact]}],risk_points,watch_points,removed}|null,ai_note,use_experience,questions:[{question,answer,at}],later:{end_date,days,change,benchmark,benchmark_change}|null }`
- `getBrief(id)` / `listBriefs()` / `deleteBrief(id)` → 同上 / `{ items:[{id,symbol,name,trade_date,created_at,tilt,later}] }` / 无内容
- `askBrief(id, message)` → `{ questions:[...],usage }`
- `listPriorKnowledge()` → `{ entries:[{id,content,source}] }`

### 策略研究导航与统一回测流程（2026-10-10）

- 主栏目为「行情图表」「我的策略」「因子研究」「回测与验证」「研究记录」。创建入口只有「新建规则策略」一个；旧直达链接继续有效，`nl-strategy` 落到新建规则策略页。Python 策略已停用（服务器不运行用户写的代码），旧链接 `custom-strategy` 落到我的策略，研究记录里旧的 `user:` 引用回测时提示已停用。
- 新建规则策略是一页一张表单：从模板开始、用一句话描述、自己填，三种方式都把规则填进同一张可编辑的表单（每个条件可选周期，可与数值或另一个指标比较，最多 10 条）。页面实时显示后端读出的“这个策略的意思”，保存的就是表单里的规则。`mode=template|describe|blank` 选择开始方式，旧的 `mode=builder` 等同 `blank`。
- 我的策略列出规则策略，支持名称搜索、规则策略复制、行内确认删除。创建页只负责保存，保存后「去回测」进入统一配置页，不自动执行。
- 回测与验证分为策略回测、参数验证两页；参数验证在同一页先做参数优化、再做样本外验证，共用基准回测与候选参数。风控设置只在回测表单里折叠出现这一处（独立的风险管理页已删除），未保存修改会阻止运行。回测结果的概览包含全部收益与风险指标。完整审计附于结果，外部成交核查位于高级工具。旧链接 `walk-forward`、`risk-management` 分别落到参数验证页和策略回测页。
- 模板的规则在表单里可见、可改，副本保持规则一致。统一回测记录保存策略引用与实际执行配置。
- 因子研究默认三个栏目：因子库、单因子评估、组合研究。组合页完成选因子、权重/区间配置和评估；原合成评估作为高级方式保留。
- 因子库表格（`ui/FactorLibraryTable.vue`、`factorPresentation.js`）一行一个因子，只有 6 列：因子（中文名，下面一行小字是代码，非内置的带来源标签）、类型、说明、方向（正向绿色 / 反向红色；正向表示因子值越大越好，反向表示越小越好）、最小历史（“25 天”）、详情。说明只显示一行，太长的截断，鼠标停留看全文；Alpha101 的说明和名字一样，这一列改为显示一行公式，统一的提示（按原公式计算、A 股有效性需要自己评估）只在表格上方写一次。完整公式在详情侧栏里，自动换行，可以复制。每页 20 个；手机上改成卡片。
- 因子库可以搜索中文名或代码（几个词用空格分开，都要出现），也可以筛选（`ui/FactorFilter.vue`、`factorFilters.js`）：按来源（内置、Alpha101、自定义……）和类型（动量与趋势、反转与价格位置、波动与风险、成交与流动性、K线与量价关系……）两排，每一项后面是点下去以后的因子数。筛选项来自因子自己的 `source` 和 `logical_category` 字段，以后增加新的来源或类型时会自动出现。组合研究里选因子的列表共用同一个筛选条件，已经选中的因子即使不符合条件也留在列表里；单因子评估的下拉框按来源分组。目前有 23 个内置因子和 100 个 Alpha101 因子（101 个里只差需要市值的 #56）；其中 18 个要和同行业比较，需要先下载行业分类，没有下载时评估会提示去下载。内置因子里，价值与估值 4 个、换手类 2 个、净资产收益率（TTM）和净利率（TTM）需要先下载估值与换手率；毛利率、资产负债率、两个同比增长因子和总市值需要先下载财务数据。
- 历史回测只在研究记录里列出。策略回测页的结果区只显示一次回测：刚运行的，或从研究记录打开的（链接里的 `run`）；没有 `run` 时显示一句说明。运行完成后把 `run` 写进链接，刷新和后退可恢复；在「策略回测」与「参数验证」两个标签之间切换时带着这次回测。
- 研究记录是一张表：搜索、勾选 2~5 次做对比、查看结果、带入历史配置继续研究、回到原策略都在表里；默认显示关键指标，可开启详细字段。日期、资金、持仓与策略参数可以复用，股票池与风险使用当前设置。运行时间按本地时间显示到分钟。
- 策略、记录、基准与股票代码通过白名单 URL 参数传递，支持刷新/后退；常规导航清除旧上下文。参数优化与滚动验证运行真实回测：同步执行，上限 24 种组合、100 次回测。

### 单次回测与复盘
- `getBacktest(id)` → `{ id,strategy,market,from_date,to_date,status,created_at,result:{equity,total_return,max_drawdown,sharpe,win_rate,...},trades:[],positions:[],benchmark }`
- `benchmark`（和基准的对比，默认沪深 300）：`{ symbol,name,comparable:true,strategy_curve:[],benchmark_curve:[],benchmark_return,excess_return,benchmark_max_drawdown,beta,alpha,information_ratio,tracking_error }`；百分比字段已乘 100，两条曲线是从同一天 0% 出发的累计收益。查看时从运行目录读出，所以以前的回测也有。基准行情晚于回测开始日时为 `{ symbol,name,comparable:false,benchmark_start }`，页面只说明原因、不做比较；回测没有记录基准时为 `null`，页面显示资金曲线。
- `benchmark_options`：`[{symbol,name,start_date,end_date}]`，本地有行情的常用指数。`getBacktestBenchmark(id,symbol)` 返回和这个指数的对比（形状同 `benchmark`），按引擎同样的方法用本地指数行情重算；指数行情比回测早结束超过 5 个交易日时为 `{comparable:false,benchmark_end}`。页面在标题里提供下拉框，选择记在浏览器里（`fq-benchmark`），下次查看回测时沿用。
- `submitBacktest({strategy,market,from_date,to_date})` → `{ id,status,result,created_at }`；`market` 是 `当前股票池` 或指数代码（见数据管理的「回测的股票范围」）

### 参数优化与稳健性验证
- `researchBaselines()` → `{ items:[{run_id,strategy,market,from_date,to_date,created_at,display_label,parameters:[{name,label,kind,description,current,minimum,maximum,choices,choice_labels}]}],max_combinations,max_backtests }`；只列出保存了运行明细的记录。`parameters` 先列策略自己的可调参数，再列所有策略共用的 `top_n`（持股数量）和 `rebalance`（调仓频率），所以规则策略也能做参数验证；策略已删除或无法加载时为空。
- `runOptimization({baseline_run_id,parameter_grid:{参数名:[候选值]},objective,max_drawdown_limit})` → `{ optimization_id,objective,combination_count,start_date,end_date,results:[{rank,eligible,status,error,run_id,parameters,objective_value,cumulative_return,annual_return,max_drawdown,sharpe,dsr,selection_bias_status,selection_bias_reason}],selection_bias:{status,message,dsr} }`；百分比字段已乘 100，回撤为正数；`max_drawdown_limit` 为 0 表示不限制。
- `runWalkForward({baseline_run_id,parameter_grid,objective,training_months,test_months,step_months,max_windows})` → `{ validation_id,objective,window_count,backtest_count,start_date,end_date,summary:{successful_windows,failed_windows,out_of_sample_cumulative_return,average_window_return,positive_window_ratio,worst_window_drawdown,average_window_sharpe,trust_warning},windows:[{window,status,error,train_start,train_end,test_start,test_end,train_run_id,test_run_id,selected_parameters,train_objective_value,test_cumulative_return,test_max_drawdown,test_sharpe}] }`；使用本地最近一段能放下这些窗口的行情，不限于基准回测的区间。

### 回测记录库
- `listRuns({strategy?,run_kind?,status?,keyword?})` → `{ items:[{run_id,run_label,run_kind,status,validity_status,metrics_reliable,legacy_unverified,strategy,start_date,end_date,updated_at,cumulative_return,max_drawdown,sharpe,sortino,calmar}],total,stats:{all,success,failed,legacy_unverified,experiment} }`
- `compareRuns(runIds)` → `{ comparison:[{run_id,strategy,cumulative_return,max_drawdown,sharpe,sortino,calmar,metrics_reliable}], normalized_nav:[{trade_date, <runId>:number}] }`

### 数据管理
- 每天自动更新（2026-10-16）：行情数据所有用户共用一份，由平台在每个交易日 18:30（`FELLOWQUANT_DAILY_UPDATE_TIME`）以后自动更新全市场（后台任务 `datasets:['daily']`，见 `quant_platform/application/daily_update.py`）：先确认当天是交易日、行情已发布，再更新股票列表、全部在市股票的日线（每批 200 只，走和手动更新相同的复权对齐；新上市股票下载全部历史）、分红送转缺口、指数行情、指数成分股、行业分类和历史股票池。一步失败不影响后面的步骤，同一天重新运行时跳过已经完成的步骤和批次；行情没发布或没完成时 30 分钟后再试，最多 4 次，23:30 以后不再启动。`dailyUpdateStatus()` → `{enabled,time,state,text,last:{trade_date,status,market,finished_at,summary,errors,trigger},progress,data:{latest_date,stocks_on_latest,listed}}`（`job_id` 只给管理员）；`runDailyUpdate()` 管理员现在运行。页面：数据更新页顶部「每天自动更新」卡片（`ui/DailyUpdateCard.vue`，文字在 `dailyUpdate.js`）。
- 只有管理员能下载数据和操作后台任务：`dataUpdate`、`updateLocalStock`、`dataJobs`、`startDataJob`、`stopDataJob`、`dataJobLog`、`runDailyUpdate`、XTick 凭证与查询，其他用户返回 403。普通用户的数据更新页只显示自动更新状态和各类数据的覆盖情况（不显示下载按钮、高级更新和任务记录），本地行情查询不显示「更新行情」，XTick 页只显示说明。
- 耗时计算的限制（2026-10-16，`app/quant/compute.py`）：回测、策略包回测、参数优化、滚动验证、因子评估、多因子合成、组合研究、成交核查、AI 研究员整理数据，每人同一时间一件，全站同时最多 `FELLOWQUANT_COMPUTE_SLOTS` 件，满了返回 429（“你有一个计算正在进行……”/“服务器正忙……”），页面照常显示这段提示；一件最多 `FELLOWQUANT_COMPUTE_TIMEOUT` 秒，回测每个交易日、因子评估每个因子之后检查时间，超时返回 422 并提示缩小范围（`quant_platform/core/deadline.py`）。因子评估、合成、组合研究的结果按 用户 + 请求 + 本地数据版本（行情文件的大小和修改时间）记住最近 64 份，命中时不占计算名额。
- 行情表写入是原子的（`write_parquet_atomic`：先写同目录下以 `.` 开头的临时文件再整份替换，Windows 上旧文件正被读取时稍等再换），进程在写入中途被结束不会损坏文件。后台数据任务用 `launch_detached` 启动，脱离启动脚本的 Windows 作业对象（作业设置了 BREAKAWAY_OK），关闭启动窗口后继续运行；不允许脱离时按原来的方式启动。
- 所有后台任务（日线以外的阶段）有卡住保护：15 分钟没有进展就结束进程，由守护进程从断点续传（以前只有全市场日线有）。
- `dataOverview()` → `{ security_count,configured_symbol_count,coverage_ratio,market_rows,unknown_status_rows,last_market_source,benchmark_symbol,per_symbol:[{symbol,coverage,start_date,end_date,rows}] }`
- `localMarketList({q,scope:'all'|'universe',page,page_size})` → `{items:[{symbol,name,start_date,end_date,status,status_label,in_universe}],total,page,pages,page_size,downloaded_count,universe_count,universe_downloaded_count}`；全部范围仅列已下载股票，股票池范围也列出未下载标的。按行情/名称/交易日历文件版本缓存摘要，翻页不重复读取行情价格。
- `localMarketDetail(symbol)` → `{symbol,name,rows,coverage,missing_rows,unknown_rows,duplicate_rows,unexpected_rows,missing_ranges:[{start_date,end_date,days}],missing_range_count,...}`；覆盖率只核对已保存区间，缺失段最多展示 20 段，本地日历不足时标记待核对。
- `localMarketBars(symbol,adjust:'forward'|'none')` → `{symbol,name,adjust,start_date,end_date,suspended_days,invalid_rows,bars:[{date,open,high,low,close,volume,factor}]}`；前复权以最新一根为基准，`factor` 是当天的复权比例，停牌日与价格不完整的记录只计数不返回。K 线只在「行情图表」页显示，详情面板提供跳转链接。
- `updateLocalStock(symbol,{start_date,end_date})` → `{status,message,rows,version_id,symbol}`；仅下载所选单股，不修改股票池。先展示日期表单，再明确执行。
- `dataUpdate({start_date,end_date,include_security_master,include_market,include_benchmark,source_choice,allow_fallback})` → `{ results:[{dataset,version_id,status,rows,message,error}] }`
- 估值与换手率（每日指标）：市盈率、市净率、市销率、市现率（TTM/最近一季）和换手率，单独存在 `daily_indicators` 表里，不改动行情表。用 BaoStock 更新行情时在同一次请求里取回并保存；以前下载的行情通过后台任务补全（`startDataJob({start_date,end_date,datasets:['indicators']})`，每只股票一次请求，只请求还没有的日期，可中断后继续）。`closedLoopStatus()` 的返回值增加 `indicators:{symbols,missing_symbols,rows,start_date,end_date}`；数据更新页据此显示覆盖情况和「补全历史数据」按钮。还没有下载时使用相关因子会提示去数据更新页补全。
- 财务数据（季度财报）：净资产收益率、净利率、毛利率、净利润、同比增长（净资产、总资产、净利润、每股收益）、流动比率、速动比率、权益乘数、总股本和流通股本，存在 `quarterly_fundamentals` 表里，每行是一只股票的一个报告期，带公告日。**每份财报从公告日起才会被使用**（同一天公告两期时用较新的一期；超过 370 天的财报不再使用）。BaoStock 一次只能取一只股票的一个季度，所以默认只下载股票池：`startDataJob({start_date,end_date,datasets:['fundamentals'],scope:'universe'})`；不带 `scope` 时是本地有行情的全部股票（约 20 多个小时，可续传）。`closedLoopStatus()` 的返回值增加 `fundamentals:{symbols,missing_symbols,reports,latest_stat_date,latest_pub_date}`；数据更新页据此显示覆盖情况和「下载股票池的财务数据」按钮。
- 行业分类：证监会行业分类（门类字母 + 两位大类，如 `J66货币金融服务`，共 84 个大类）。每个季度末取一张全市场快照，只把「第一次分类」和「发生变化」的记录存进 `security_exposures`，所以使用时是当时的行业。后台任务 `startDataJob({start_date,end_date,datasets:['industry']})`，第一次大约 1 小时（每个时点 1 到 2 分钟），以后只取新的时点。`closedLoopStatus()` 的返回值增加 `industry:{symbols,missing_symbols,snapshots,start_date,end_date}`。
- 行情不完整的股票：`closedLoopStatus()` 的返回值增加 `bar_gaps:{symbols,without_bars,examples:[{symbol,name,expected_start,first_bar}]}`，指行情开始得比上市日期（或本地数据的第一天）晚 10 天以上、或者完全没有行情的股票。`symbols` 大于 0 时数据更新页显示提示和「补全这些股票的行情」按钮，后台任务 `startDataJob({start_date,end_date,datasets:['bar_gaps']})` 把这些股票整只重新下载，然后重建历史股票池和退市结算。
- 分红送转记录：`closedLoopStatus()` 的返回值增加 `action_gaps:{changes,symbols,to_check}`，指复权因子变化了、却找不到分红送转记录的次数和股票数，以及还可以向 BaoStock 补查的股票数。后台任务 `startDataJob({start_date,end_date,datasets:['action_gaps']})` 只查有缺口的股票和年份，查过的往年记在 `corporate_action_checks` 不再重复查。回测持有的股票遇到仍然没有记录的变化（多半是配股）时，按复权因子推算成现金，结果的数据状态里有警告 `IMPLIED_CORPORATE_ACTIONS`；因子变小时仍然拒绝运行。
- 指数成分股：沪深300（`000300.SH`）、上证50（`000016.SH`）、中证500（`000905.SH`）在历史上每一天的成分股。数据源的名单每周一更新一次；下载时把区间切成半年一段，只在两头名单不同的段里折半查找发生变化的那一周，把第一天和每次变化后的完整名单存进 `index_constituents`，核对过的起止日期记在 `index_constituent_checks`。后台任务 `startDataJob({start_date,end_date,datasets:['index_constituents']})`，第一次约 10 分钟，以后只核对新的几周。`closedLoopStatus()` 的返回值增加 `index_constituents:[{symbol,name,start_date,end_date,changes,members}]`。
- 回测的股票范围：`getBacktestCatalog()` 的返回值增加 `markets:[{value,label,available,start_date,end_date}]`，第一项是 `当前股票池`，其余是指数。`submitBacktest({...,market})` 的 `market` 传 `当前股票池` 或指数代码；选指数时每个调仓日只在当时的成分股里选股，运行快照记下 `universe.mode='historical'` 和 `universe.index`，参数验证用同一个范围重跑。成分股历史没有覆盖回测区间（开始日期早于第一份名单，或核对日期落后结束日超过 31 天）时返回 422 并说明原因。
- 因子研究的股票范围：`factorUniverses()` → `{ items:[{value,label,available,start_date,end_date}] }`（与回测的股票范围相同）。`evaluateFactor`、`compositeFactors`、`researchFactors` 都接受 `universe`（`当前股票池` 或指数代码）。选指数时只读当过成分股的股票，每天只用当天的成分股做样本（结果的 `notes` 里写明平均每天多少只），Alpha101 的截面排名也只在当天的成分股之间进行。页面上三个功能共用一个选择，记在浏览器里；没有选过时有沪深300 就默认用沪深300。
- 因子评估的中性化：`evaluateFactor({...,neutralization:'none'|'industry'|'size'|'both'})`。行业用当时的分类，市值用当天收盘价乘以当时已公告的总股本。缺少行业或市值的样本不参与，并在返回的 `notes` 里说明数量（评估结果上方会显示）；股票太少（每天的股票数不比行业数多）时返回 422 并说明原因。

### XTick 数据服务
- `xtickCatalog()` → `{ catalog:[{id,name,apis:[{id,name,url,description,inputs:[{name,label,type,default,range}]}]}] }`（type 为 'String'|'date'|'range'，range 形如 `"1-沪深京A股，2-沪深指数"`）
- `xtickRequest({...请求参数})` → `{ rows:[对象数组], count }`

### 风控设置（回测表单内）
- `getRisk()` → `{ enabled,max_total_weight,max_single_weight,max_positions,minimum_cash_ratio,max_drawdown,daily_position_limits,drawdown_action,drawdown_target_weight }`
- `saveRisk(payload)` → `{ saved:true }`

### 行情图表
- 左侧股票列表、中间 K 线（日/周/月、MACD/KDJ/RSI、前复权/不复权）、右侧行情摘要；周线与月线由日线在前端合并。
- `listAuditRuns()` 提供可叠加的回测；`runTradedSymbols(runId)` → `{ run_id,run_label,start_date,end_date,symbols:[{symbol,name,buys,sells,rejected}] }`
- `runSymbolTrades(runId,symbol)` → `{ symbol,fills:[{date,side,quantity,price,reference_price,fees,slippage_cost}],rejected:[{date,side,quantity,reason,reason_label}],holdings:[{start_date,end_date}] }`；成交价为不复权价格，前端按当天 `factor` 换算后标在 K 线上。
- 画线：线段、射线、水平线、斐波那契四种。画完自动保存到账户，按股票分开；点一条线选中后可以拖动或删除（右键也可以删除），「清除全部」要点两次。每只股票最多 50 条。
- `chartDrawings(symbol)` / `saveChartDrawings(symbol,drawings)` → `{ symbol,drawings:[{name:'segment'|'rayLine'|'horizontalStraightLine'|'fibonacciLine',points:[{date,price}]}],max_drawings }`；保存是整体替换。`price` 是不复权价格，前端按当天 `factor` 换算，所以换周期、换复权方式、以后再有分红，线都落在同一根 K 线的同一个位置。

### 模拟交易
- `paperAccounts()` → `{ accounts:[{account_id,display_name,status,strategy,start_date,initial_cash,top_n,last_date}] }`
- `createPaperAccount({name,start_date,initial_cash,top_n})` → `{ account_id,display_name,status }`
- `advancePaperAccount(id,{target_date})` → `{ summary:{equity,total_return,max_drawdown,...},nav:[],target_date }`
- `paperChecklist(id)` → `{ blocked, items:[{title,detail,passed,severity}] }`

### 股票池管理
- `getUniverse()` → `{ symbols:[],filters:{exclude_st,exclude_suspended,minimum_listing_days,minimum_history_days,minimum_average_amount},description:[{symbol,name,local_rows,start_date,end_date}] }`
- `universeAdd(symbols)` / `universeRemove(symbols)` → `{ symbols,count }`
- `universeSearch(q)` → `{ results:[{symbol,name}] }`
- `universeSaveFilters(payload)` → `{ saved:true }`

### AI 智能投研导航与页面
- 侧栏只有 AI研究员。投研知识库（文档问答）和决策辅助暂不放进侧栏，旧链接仍能打开；研究经验在 AI研究员页面底部“我的研究经验”里管理，旧 `prior-knowledge` 链接进入 AI研究员。
- AI研究员只有股票（输入代码或名称，从下拉列表选，支持上下键和回车）、分析日期（留空为本地最近的交易日）和“参考我的研究经验”。分析分两步并显示进度：先整理本地数据（几秒，马上显示），再等 AI 解读。页面下方“以前的分析”列出每次分析的倾向和之后实际涨跌（到本地最新行情，和同期沪深300比较），可以打开或删除。模型由平台统一提供（服务器环境变量），页面不填密钥；每人每天有分析和追问次数，管理员不限。
- 每次分析先从本地数据整理出当天已知的数据（价格走势按复权价、成交、全市场与同行业比较、估值、财报、行业、指数、分红），不需要 AI、不限次数；当天只更新了一部分股票时不做全市场比较并说明原因；本地没有的数据列在“本地缺少的数据”。
- 有模型时显示 AI 解读：倾向（页面上写“利好多/中性/风险多”，保存的数据仍是偏多/中性/偏空；不用红绿色，旁边写“对当前数据的归纳，不是买卖建议”）、信心、一段话和三组要点（支持的因素、风险、接下来留意），每条要点下面列出它引用的本地数据。没有依据、数字和数据对不上、或给出买卖建议（买入、仓位、目标价等）的要点会被去掉并写明条数。不显示交易提案、目标价、止损和模拟成交。
- 分析编号写进链接（`brief=`），刷新或后退可以打开同一次分析；有 AI 解读时可以继续追问，追问只用这次的数据。
- 文档问答（WeKnora）是整个平台共用的服务，只有管理员能在设置页配置（`weknoraSettings()` 返回 `can_configure`）；普通用户看不到服务地址和配置面板。没有配置时说明“知识库服务还没有配置，暂时不能使用”，不显示问答和检索，也不再给演示回答。
- 决策辅助（不在侧栏）的三个标签为方案比较、条件判断、等级评分，使用平台的决策模型并计入每天的“AI 评估”次数；没有配置时说明“平台还没有配置决策模型”，不再给演示结果。设置页不再配置 Jev。
- AI研究员先整理数据，再独立调用 Jev 判断倾向，最后按文本模型是否可用生成文字解读。Jev 的概率单独显示在“Jev 数据判断”卡片；和文字解读的倾向不同时说明“两个模型看法不同”。没有文本模型时仍可显示 Jev 结果，并在历史分析中显示倾向。
- 回测结果页的“AI 评估”：点按钮后由决策模型根据这次回测自己的数字（区间、收益、回撤、交易、成本、和基准比较、有效性警告）估计风险等级（五级及各级概率）和在新数据上做不到的可能；“AI 看到的数据”列出发给模型的全部内容。每次回测只评估一次并保存，再打开不重复计数。
- `getBacktestReview(id)` / `runBacktestReview(id)` → `{ review:{risk:{level,score,probabilities,confidence},overfit:{probability},model,facts:[],created_at}|null,available,usage }`；`jevStatus()` → `{ available,model,usage }`

## 五、交互细节
- 数字百分比用 `%` 后缀；比率保留 2 位小数。
- 表格列用 `columns` 数组声明，表头中文。
- 空列表用 EmptyState 或 DataTable 的 empty。
- 删除操作前用 `confirm()` 确认。
- 回测/评估等异步操作用 loading ref 控制按钮文案（「…中」）与 disabled。
