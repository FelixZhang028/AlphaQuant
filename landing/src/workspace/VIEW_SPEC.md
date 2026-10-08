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
- 中文文案。无外部图片/字体。
- 加载状态可用 `ref(false)` 控制，展示「加载中…」或按钮 disabled。

## 二、设计语言（必须一致）

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
- `createPackage({definition:{name,description,entry_logic,entry_rules:[{left:{name,window},operator,value|right}],ranking:{indicator:{name,window},direction}},top_n,rebalance,source})` → 返回单个 package 对象
- `deletePackage(id)`、`copyPackage(id, name?)` → package 对象、`getPackage(id)`
- `preflightPackage(payload)` → `{ warnings:[], minimum_history_days }`
- `backtestPackage(id, payload?)` → `{ id, run_id, status, summary:{equity:[],total_return,max_drawdown,sharpe,win_rate,final_equity,...} }`
- `studioOptions()` → `{ templates:[{template_id,name,summary,suitable_market,main_risk,top_n,rebalance}], indicators:{name:中文}, operators:{key:中文}, frequencies:['daily','weekly','monthly'], directions:['descending','ascending'], styles:['conservative','balanced','aggressive'] }`

### 自然语言
- `nlProviders()` → `{ providers:[{key,display_name,default_base_url,requires_key,models:[],default_model}] }`
- `nlGenerate({description,provider,top_n,rebalance})` → `{ definition, explanation, minimum_history_days }`

### 自定义策略（Python）
- `previewUserStrategy({code,display_name,description,source,risk_acknowledged})` → `{ plugin_name,display_name,description,parameters:[],safety_report:{blocked,blockers:[],warnings:[]},errors:[] }`
- `saveUserStrategy({code,display_name,description,source,risk_acknowledged})` → `{ plugin_name,display_name,description,source,parameters:[] }`
- `listUserStrategies()` → `{ strategies:[{plugin_name,display_name,description,source,parameters,created_at,updated_at}] }`
- `deleteUserStrategy(name)`

### 因子研究室
- `listFactors()` → `{ factors:[{name,display_name,category,description,formula,required_fields:[],min_history,direction,version}] }`
- `evaluateFactor({factor_name,start_date,end_date,horizon,n_groups})` → `{ factor_name,horizon,n_groups,ic_mean,ic_ir,rank_ic_mean,rank_ic_ir,long_short_mean,first_half_ic,second_half_ic,turnover_mean,daily_ic:[{date,ic,rank_ic}],group_mean_returns:{G1:..,G2:..},notes }`
- `compositeFactors({factor_names:[],weight_mode:'equal'|'ic'|'custom',weights?,winsorize,zscore,fill_method,corr_threshold,start_date,end_date,horizon,n_groups})` → `{ correlation_matrix:{},dropped_factors:[],weights:{},composite_spec:[{name,weight}],report:{同 evaluateFactor 的 report 字段} }`
- `createCustomFactor({name,display_name,description,field,operator,window,window2,direction})` → `{ created:{...} }`
- `deleteCustomFactor(name)`

### 智能体分析台
- `agentConfig()` → `{ providers:[],stock_sources:[],news_sources:[],proxy_settings:{enabled,address},prior_knowledge:[] }`
- `runAgent({symbol,trade_date,lookback_days,debate_rounds,provider})` → `{ run_id,symbol,name,decision:{status,final_action,final_position_pct,confidence,rejection_reason,conditions:[],rationale_chain:[]},state:{analysts:[{dimension,score,confidence,summary,key_findings:[],risks:[]}],debate:[{round,bull,bear,bull_reply,bull_summary,bear_summary}],proposal:{action,position_pct,confidence,stop_loss,target_price,holding_period,reason},risk:{vetoed,volatility,est_max_drawdown,veto_reason,conditions,comment},fill:{action,quantity,price,benchmark_price,fee,settle}},trace_log:[] }`
- `battleAgent({message})` → `{ reply }`

### 单次回测与复盘
- `listBacktests()` → `[ {id,strategy,market,from_date,to_date,status,result,created_at} ]`
- `getBacktest(id)` → `{ id,strategy,market,from_date,to_date,status,created_at,result:{equity,total_return,max_drawdown,sharpe,win_rate,...},trades:[],positions:[] }`
- `submitBacktest({strategy,market,from_date,to_date})` → `{ id,status,result,created_at }`

### 参数优化与稳健性验证
- `researchBaselines()` → `{ items:[{run_id,strategy,market,from_date,to_date,created_at,display_label}] }`
- `runOptimization({baseline_run_id,parameter_grid:{参数名:[候选值]},objective,max_drawdown_limit,start_date,end_date})` → `{ optimization_id,objective,combination_count,results:[{rank,eligible,objective_value,parameters,max_drawdown,status,run_id}] }`
- `runWalkForward({baseline_run_id,parameter_grid,objective,training_months,test_months,step_months,max_windows,start_date,end_date})` → `{ validation_id,window_count,summary:{successful_windows,out_of_sample_cumulative_return,positive_window_ratio,worst_window_drawdown,trust_warning},windows:[{window,train_start,train_end,test_start,test_end,train_run_id,test_run_id,selected_parameters,train_objective_value,test_cumulative_return,test_max_drawdown,test_sharpe,status}] }`

### 回测记录库
- `listRuns({strategy?,run_kind?,status?,keyword?})` → `{ items:[{run_id,run_label,run_kind,status,validity_status,metrics_reliable,legacy_unverified,strategy,start_date,end_date,updated_at,cumulative_return,max_drawdown,sharpe,sortino,calmar}],total,stats:{all,success,failed,legacy_unverified,experiment} }`
- `compareRuns(runIds)` → `{ comparison:[{run_id,strategy,cumulative_return,max_drawdown,sharpe,sortino,calmar,metrics_reliable}], normalized_nav:[{trade_date, <runId>:number}] }`

### 数据管理
- `dataOverview()` → `{ security_count,configured_symbol_count,coverage_ratio,market_rows,unknown_status_rows,last_market_source,benchmark_symbol,per_symbol:[{symbol,coverage,start_date,end_date,rows}] }`
- `dataUpdate({start_date,end_date,include_security_master,include_market,include_benchmark,source_choice,allow_fallback})` → `{ results:[{dataset,version_id,status,rows,message,error}] }`

### XTick 数据服务
- `xtickCatalog()` → `{ catalog:[{id,name,apis:[{id,name,url,description,inputs:[{name,label,type,default,range}]}]}] }`（type 为 'String'|'date'|'range'，range 形如 `"1-沪深京A股，2-沪深指数"`）
- `xtickRequest({...请求参数})` → `{ rows:[对象数组], count }`

### 风险管理
- `getRisk()` → `{ enabled,max_total_weight,max_single_weight,max_positions,minimum_cash_ratio,max_drawdown,daily_position_limits,drawdown_action,drawdown_target_weight }`
- `saveRisk(payload)` → `{ saved:true }`
- `riskEvents()` → `{ events:[{run_id,trade_date,symbol,decision,reason}],checks,adjustments,rejections }`

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

## 五、交互细节
- 数字百分比用 `%` 后缀；比率保留 2 位小数。
- 表格列用 `columns` 数组声明，表头中文。
- 空列表用 EmptyState 或 DataTable 的 empty。
- 删除操作前用 `confirm()` 确认。
- 回测/评估等异步操作用 loading ref 控制按钮文案（「…中」）与 disabled。
