"""Build the source-grounded migration register and its review documents."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/migration"
SCAN = json.loads((DIRECTORY / "source-inventory.json").read_text(encoding="utf-8"))
WEB = "src/quant_platform/web/"
GROUPS: list[dict] = []
FEATURES: list[dict] = []

def add(prefix, title, route, filename, tests, rows):
    group = {"prefix": prefix, "title": title, "route": route, "tests": tests}
    GROUPS.append(group)
    for number, row in enumerate(rows, 1):
        name, inputs, outputs, acceptance, marker, *status = row
        path = WEB + filename
        source = (ROOT / path).read_text(encoding="utf-8-sig")
        assert marker in source, (path, marker)
        line = source[:source.index(marker)].count("\n") + 1
        FEATURES.append({"id": f"{prefix}-{number:02d}", "group": title,
                         "name": name, "proposed_route": route,
                         "inputs_and_actions": inputs, "outputs_and_state": outputs,
                         "acceptance": acceptance, "source": {"path": path, "line": line},
                         "current_state": status[0] if status else "源码可达",
                         "migration_status": "待迁移", "acceptance_status": "待验收",
                         "existing_test_candidates": tests})

add("NAV", "全局导航与工作区", "/app/*", "navigation.py",
    ["test_workspace_navigation.py", "test_workspace_home.py"], [
    ("五个工作区", "首页、策略研究、我的研究、数据与运行、设置", "各入口可达；当前工作区明确", "逐一打开五区，子页可返回所属工作区", "WORKSPACES ="),
    ("全部工具与搜索", "按标题/描述搜索；从全部工具进入任一工具", "完整的23个工具及所属工作区", "23个工具逐项进入；查询无结果有提示", "def render_directory"),
    ("模式与上下文跳转", "同一页面按模式打开；从结果进入审计或验证", "携带运行ID、基准ID和模式；不串到其他运行", "分别打开不同结果验证上下文ID一致", "def open_result"),
    ("旧入口兼容", "7个旧源页面入口及已有书签", "映射到等价功能；旧模式仍可访问", "记录实际旧URL后逐个验证重定向和参数传递", "EXTRA_ROUTES ="),
])
add("APP", "应用外壳", "/app/*", "app.py", ["test_workspace_navigation.py", "test_user_center.py"], [
    ("工作台访问门槛", "未登录进入；已登录进入", "未登录仅使用指南；已登录显示工作区", "开发阶段可先做工作台，最终切换前恢复访问门槛", "if authenticated_user:"),
    ("品牌与支持入口", "Logo回首页、GitHub Issue、Star、打开个人中心", "正确目标；个人中心保留返回来源页", "点击Logo和支持链接，个人中心返回原页", "GITHUB_ISSUES_URL"),
])
add("HOME", "工作台首页", "/app", "app_pages/15_workspace_home.py", ["test_workspace_home.py"], [
    ("三类开始入口", "验证策略想法、检查外部策略、查看研究结果", "进入对应工作区或外部材料模式", "每个入口目标和审计模式正确", "验证策略想法"),
    ("最近研究与继续", "最近3条成功回测；继续上次研究；查看结果", "策略中文标签与正确运行报告", "成功记录排序一致；空记录/读取失败有提示", "最近研究"),
])
add("LAND", "公开欢迎页与使用指南", "/", "welcome.py", ["test_guide_steps.py", "test_user_center.py"], [
    ("欢迎展示与锚点", "启动屏向下浏览、品牌介绍、粒子背景", "欢迎页与内容锚点正常；视觉效果不遮挡操作", "桌面和窄屏均能进入正文及账号操作", "def _render_launch_splash"),
    ("中英文切换", "Language / 语言选择", "欢迎文案与账号相关文案切换；会话保留选择", "切换后欢迎页各区文案一致；不承诺全工作台翻译", "Language / 语言"),
    ("五类功能轮播", "数据、策略、回测、智能分析、优化的标签/轮播", "展示对应预览；预览是示意内容", "逐个标签可切换；不将示意收益当真实账户数据", "def _render_product_overview"),
    ("五步研究介绍", "研究流程卡片；读取就绪度、策略和回测存在状态", "当前版本展示说明卡片，不是五个可点击执行按钮", "保留内容和读取失败降级；避免制造已有按钮的错觉", "def _render_guide"),
    ("页尾账号入口", "登录、注册、已登录后进入工作台或退出", "HTML操作桥接到账号流程", "页头和页尾入口都能操作；不只保留原生隐藏按钮", "def _render_ending_page"),
    ("扩展欢迎区块", "模块直达、数据状态、最近记录、排障明细", "源码保留，但_LOAD_EXTENDED_WELCOME_SECTIONS=False", "标记休眠代码；若启用需另行验收，不冒充当前展示功能", "_LOAD_EXTENDED_WELCOME_SECTIONS = False", "休眠代码"),
])
add("HUB", "策略工作室总入口", "/app/strategies", "app_pages/0_strategy_hub.py", ["test_workspace_navigation.py"], [
    ("四种创建方式", "选股想法、策略搭建、自然语言、Python策略切换", "各嵌入工具及独立旧入口均可达；旧模式名映射", "四模式逐个打开；模板与积木旧模式映射到策略搭建", "MODES ="),
])
add("IDEA", "选股想法与运行前检查", "/app/strategies/ideas", "guided_research.py", ["test_guided_research.py"], [
    ("想法与研究范围", "想法、当前池选股、起止日期、持股数1～100、频率、资金", "推荐因子与实际执行规则、股票中文名", "同输入对应同策略；日期和空池校验；切页草稿可继续", "选股想法"),
    ("规则确认与风险约束", "人工确认规则；校验等权和风险限制兼容性", "不兼容警告；未确认/未通过检查不能运行", "未确认、持股过少或仓位限制不兼容时阻止运行", "我已确认以上规则符合我的想法"),
    ("数据检查与补齐", "检查数据；补齐所选股票和基准；自动复查", "检查表、缺口、更新失败原因；输入保留", "缺口阻止运行；补齐含回看期；失败后可重试", "检查本次研究数据"),
    ("确认运行与结果", "确认并运行；保存方案版本和运行关联；打开完整报告", "结果ID、执行版本、完成/失败说明", "运行前再次检查；改参数使旧检查/旧结果失效；结果ID对应本次", "确认并运行回测"),
    ("专业回测的待运行方案", "查看待运行参数、重新检查、补齐、运行已检查方案", "执行最后一次提交的参数，保存研究版本", "表单未再提交时不偷换执行参数；后端重查数据", "def render_pending_backtest"),
])
add("VIS", "模板与可视化策略", "/app/strategies/visual", "app_pages/7_strategy_studio.py", ["test_strategy_studio_ui.py", "test_strategy_studio_service.py", "test_rule_schema.py"], [
    ("回测范围", "起止日期、初始资金≥10000", "模板、自定义和已保存策略共用回测范围", "选择的区间和资金带入实际执行请求", "回测开始日期"),
    ("模板与风格", "模板、风格、持股数、频率、观察周期和条件值", "规则解释、参数默认值与高级设置", "逐模板按当前注册表验收；折叠高级设置不改值", "选择一种容易理解的策略"),
    ("模板运行和另存", "开始模板回测、另存为我的策略", "摘要、策略包、完整结果跳转", "另存可在我的策略找到；回测摘要对应同一运行", "开始模板回测"),
    ("自定义规则搭建", "名称、AND/OR、1～6条件、指标、周期、比较符/对象/值", "结构化策略定义、可读规则、校验结果", "每类指标和比较对象可组合；非法规则给出原因", "条件组合"),
    ("排序与策略生成", "排序指标/周期/方向、持股数、频率；生成并检查", "策略预览与合法策略包", "编辑后旧预览不能作为当前已验证定义运行", "生成并检查策略"),
    ("保存、版本与复制", "保存策略/新版本、选已有策略、载入积木编辑、复制为新策略", "版本或复制策略，不覆盖旧版本结果", "保存后可重载；修改版本与复制的ID语义正确", "载入积木编辑"),
    ("运行自定义或已保存策略", "使用该策略回测/回测已保存策略；打开完整结果", "当前定义签名对应的运行摘要和结果ID", "旧结果与当前编辑定义不一致时不误展示为本次结果", "回测已保存策略"),
])
add("NL", "自然语言创建策略", "/app/strategies/natural-language", "app_pages/10_nl_strategy.py", ["test_nl_builder.py", "test_strategy_studio_service.py"], [
    ("描述转规则", "描述、示例、持股数1～50、频率；默认AI模型", "结构化规则和中文解释；未配置模型指向设置", "模型失败和不支持规则清楚提示；不直接执行未经确认的规则", "生成策略规则"),
    ("人工确认与保存", "核对JSON及可读规则；确认并保存", "策略工作室可检索的策略包", "只有确认后保存；结构化规则校验与原实现一致", "确认并保存策略"),
    ("放弃与后续回测", "放弃重新描述；进入策略创作中心查看并回测", "清除生成结果或进入已保存策略流程", "放弃不注册；跳转后能选择刚保存的策略", "放弃，重新描述"),
])
add("PY", "Python自定义策略", "/app/strategies/python", "app_pages/8_custom_strategy.py", ["test_user_strategies.py", "test_strategy_safety.py"], [
    ("在线编写并注册", "Python代码、显示名、说明；BaseStrategy约定", "注册校验、安全检查与保存反馈", "阻断项不可绕过；警告需明确勾选；加载失败原因可见", "注册并保存"),
    ("上传.py文件", "上传.py、显示名、说明、风险确认", "与在线编写一致的注册和安全检查", "合法上传可保存；错误编码/代码/风险项不静默接收", "注册并保存该文件"),
    ("已保存策略及回测", "策略选择、源码、类型化参数、起止日、资金、持股数、频率", "运行摘要、完整回测结果跳转、已保存策略加载失败明细", "参数类型/边界/默认值一致；策略与运行结果ID匹配", "我的自定义策略"),
    ("删除自定义策略", "删除所选策略", "策略列表刷新；存储删除反馈", "仅处理选中策略；历史回测结果仍可读取", "删除该策略"),
])
add("BT", "单次回测与结果", "/app/backtests/new；/app/backtests/:runId", "home.py", ["test_backtest_service.py", "test_backtest_validity.py", "test_backtest_diagnosis.py", "test_workspace_navigation.py"], [
    ("四种研究阶段", "单次回测、参数优化与稳健性验证、风险规则、方案复用", "相应工具嵌入及独立入口可达", "切换阶段不把研究对象/当前运行误改成其他对象", "研究阶段"),
    ("策略与基础输入", "动态发现策略、起止日、初始资金≥1000", "策略中文说明和默认参数", "注册策略全部出现；同输入传给现有回测引擎", "selected_plugin = st.selectbox"),
    ("完整高级参数", "策略编号、各策略枚举/整数/浮点/布尔/文本参数、持股数、频率", "按策略元数据生成的控件/默认值/上下限", "动态字段不得按一个示例写死；高级区折叠不改默认值", "策略实例编号"),
    ("组合与股票池口径", "等权、波动倒数、风险平价、均值方差；固定/历史股票池", "参数进入请求并保留选择偏差和历史成分要求提示", "四种分配与两种股票池模式均可选择，缺数据不静默降级", "组合分配"),
    ("提交与检查", "检查数据并准备回测；待运行方案复查、补齐和确认运行", "已提交请求和检查表；与当前未提交表单区分", "沿用IDEA-05的二次检查；无数据不得生成成功结果", "检查数据并准备回测"),
    ("因子组合带入", "从因子组合页面带入验证过的权重/清洗规则", "factor_composite策略参数预填", "权重、方向、清洗和版本保持；不拿过期组合直接回测", "factor_composite_payload"),
    ("运行选择与通俗摘要", "选择成功回测；查看结论、收益、回撤、可信度", "有效/警告/无效及缺字段提示；审计评级和报告", "旧结果可读；无效指标不伪造；缺summary有提示", "def _render_result"),
    ("策略和基准曲线", "查看归一化净值、权益/回撤及月度收益", "各自在同一起始日归一；最大回撤起点/谷底/恢复日和持续时间；无基准时明确显示缺失", "图表底层数据逐日比对；不能用不同起点或补零基准；月度缺失显示缺失而非零收益", "策略与基准走势"),
    ("收益与风险指标", "展开专业区和收益风险标签", "全部指标键、单位和缺失值；详见指标附录", "与原summary逐字段比对；小数/百分比/年化口径一致", "def _render_return_metrics"),
    ("交易与成本明细", "展开订单、成交、完整FIFO交易及成本", "订单/成交尾200行；完整交易表；佣金税费滑点等指标", "拒单、参考价/成交价、费用、净毛盈亏和排序不丢", "def _render_trade_metrics"),
    ("持仓与诊断", "每日仓位、最新持仓、集中度；通俗诊断和完整有效性问题", "仓位图、持仓表、诊断段落、问题代码与级别；最大日历缺口、未知状态行/证券/订单数", "空仓/旧版无完整交易均有提示；数据和风险记录对应当前运行；有效性明细字段逐项比对", "def _render_position_metrics"),
    ("继续验证/审计/记录", "用本次结果创建验证实验、完整审计、样本外验证、记录库", "携带当前运行ID、基准ID及审计对象", "每个结果入口打开同一运行；不回到默认记录", "用本次结果创建验证实验"),
])
add("OPT", "参数优化与DSR", "/app/experiments/optimization", "app_pages/2_research.py", ["test_optimization_service.py", "test_multiple_testing.py", "test_selection_bias_ui.py"], [
    ("基准继承", "选择成功基准回测，读取保存配置与策略参数", "显示基准摘要；继承资金、持仓、频率等", "无基准/配置损坏/策略不可用阻止启动；不改用当前全局配置", "基准回测"),
    ("参数网格与约束", "各参数候选值、日期、目标指标、最大回撤、1/2/4进程", "最多100组合；类型化候选值及独立子运行", "超100组、非法值和日期被拒绝；组合总数与基准关联一致", "单次实验最多100组"),
    ("优化结果和下载", "排名表、成功组合详情、打开子回测、CSV下载", "原目标排名、约束状态、失败行和完整CSV", "未满足约束的有效试验仍入审计；子运行ID可追溯", "下载优化结果 CSV"),
    ("参数搜索偏差", "查看首行/选中组合DSR及独立试验、PSR、相关性等依据", "无法评估/不适用/警告状态，试验清单", "记录缺失清空旧概率；排序指标不偷偷替换成DSR", "参数搜索记录不完整"),
])
add("WF", "滚动样本外验证", "/app/experiments/walk-forward", "app_pages/2_research.py", ["test_walk_forward_service.py", "test_research_reliability.py"], [
    ("窗口与搜索配置", "基准、候选参数、总区间、训练月数≥3、测试/步长≥1、最多1～24窗、目标指标", "训练窗口与随后测试窗口构建及执行", "日期不合法/窗口不足有错误；选参只读训练数据", "滚动样本外验证"),
    ("样本外结果", "成功窗口、样本外收益、正收益比例、最差回撤、警告和窗口表", "全部窗口状态和测试运行ID", "测试结果与原服务一致；训练失败/空窗口不伪装成功", "样本外累计收益"),
    ("窗口详情与导出", "查看测试子回测、打开报告、CSV下载", "完整窗口结果与可追溯的测试运行", "对应测试ID正确；CSV包含全部结果而非仅预览", "下载滚动验证结果 CSV"),
])
add("FAC", "因子实验室", "/app/factors/*", "app_pages/9_factor_lab.py", ["test_factor_lab_ui.py", "test_factor_evaluation.py", "test_factor_research_service.py", "test_factor_combine.py"], [
    ("四个功能分区", "因子库、因子评估、因子组合、自定义因子", "内置/Alpha101/自定义注册项及无行情提示", "各分区可用；无数据可浏览，不误声称可评估", "因子库\", \"因子评估"),
    ("单因子输入", "因子、持有期1/5/10/20日、5/10组、起止日、中性化none/industry/size/both", "计算请求和历史暴露校验", "缺当时暴露数据明确报错；不静默跳过中性化", "暴露调整"),
    ("完整因子报告", "IC、Rank IC、IR、多空差、更替率、前后半段、显著性、年度、持有期衰减", "分组柱图、Rank IC图、年度/显著性/衰减表和备注", "t+1收盘及t+N+1收盘口径保留；覆盖率与样本不足提示一致", "def _render_report"),
    ("组合输入与清洗", "≥2因子；等权/手动/训练期IC权重；MAD、缺失处理；训练/测试日、持有期和分组", "归一化权重、方向和共同样本的验证请求", "训练/测试隔离；零权重和无效权重处理一致", "多因子合成"),
    ("组合结果和方案对比", "权重公式、训练相关性、组合/基准比较、方案详情", "相关≥0.7提示；配置指纹对应的有效报告", "改变任一配置/因子版本使旧验证失效，禁止旧组合带入回测", "设置已变化"),
    ("组合记录下载与回测", "下载factor_research.json；保存组合并去回测", "配置/因子/比较表/报告导出；已验证spec预填", "JSON可解析且内容完整；仅当前指纹有效结果可带入", "下载组合与验证记录"),
    ("新增自定义因子", "英文标识、字段、中文名、算子、N/N2、方向和说明", "窗口/命名/重复校验、写入注册库", "单窗和双窗规则完整；持久化后刷新可选", "添加因子"),
    ("删除自定义因子", "逐条删除自定义因子", "本地因子定义与注册库刷新", "仅删所选自定义项；关联组合重新验证", "del_custom_"),
])
add("LIB", "因子库浏览与跨区选择", "/app/factors/library", "factor_library.py", ["test_factor_lab_ui.py", "test_factor_taxonomy.py"], [
    ("筛选与检索", "研究意图多选、关键词、类别、来源；多意图OR，其余条件AND", "匹配列表、来源数量、空结果提示", "组合筛选语义和中文/编号检索一致", "我想研究"),
    ("行选择与详情", "单行选择、收起；公式、版本、窗口、字段说明、来源链接", "动态选择保持；筛选变化清理过期选中项", "选择正确因子；字段含义与来源可查；无数据仍能浏览", "selection_mode=\"single-row\""),
    ("带入评估或组合", "用于因子评估、加入因子组合", "对应控件预选；加入组合去重", "切换标签后因子正确；重复加入不产生重复项", "用于因子评估"),
])
add("KN", "先验知识库", "/app/knowledge", "app_pages/12_prior_knowledge.py", ["test_prior_knowledge.py"], [
    ("统计与筛选", "浏览知识、内容/来源搜索、来源过滤", "数量、来源数、最近更新与匹配条目", "筛选只影响显示，AI仍接收全部知识及来源", "搜索知识"),
    ("添加知识", "内容、来源；保存知识", "本地条目和统计更新，空内容错误提示", "刷新可读取；后续AI分析上下文包含新知识", "保存知识"),
    ("删除知识", "逐条删除", "条目移除、统计更新", "仅删除所选ID；后续AI上下文不再包含该条", "store.delete"),
])
add("AI", "AI研究员与对话", "/app/research/ai", "app_pages/8_agent_lab.py", ["test_agents_bridge.py", "test_agent_sources.py", "test_llm_settings.py"], [
    ("模型与研究对象", "股票代码/名称识别、默认模型和配置状态、设置及知识库跳转", "标准化代码；必要凭证/本地行情缺失提示", "非法/空代码及缺凭证不启动；可按原样处理非A股代码", "股票代码"),
    ("行情与新闻选择", "STOCK_SOURCES动态选项；新闻多选/全选；读取代理设置", "所选源进入AgentRunner；多源耗时说明", "新闻失败可降级；代理仅按当前配置作用于适用来源", "新闻来源（可多选）"),
    ("分析参数与缓存", "分析日、回看20～250日、辩论0～4轮、缓存、人为介入", "缓存最终决策或完整新分析；本地行情截至分析日", "缓存命中不编造中间报告；重新分析清空上一轮对话", "回看天数"),
    ("实时过程与回放", "不使用缓存时查看步骤、报告卡片、辩论、耗时及终态回放", "EventBus/LiveTrace过程与trace_log重绘", "切页/重绘不重复调用分析；过程与最终状态一致", "分析过程回放"),
    ("完整决策与证据", "经理审批/动作/仓位、拒绝和条件、理由链、分析报告、多空辩论、Trader、风控", "所有已有字段及非致命错误提示", "每个中间产物分区保留；缓存与完整模式的缺项语义正确", "组合经理决策"),
    ("模拟成交展示", "动作、数量、参考价/成交价、费用、交收日", "存在state.fill时显示；T+1核对说明", "字段与state.fill一致；止损/目标价仍只是研究参考", "模拟成交"),
    ("人为介入对话", "启用介入后聊天、质疑、历史消息", "带研究上下文的回答，失败降级和会话历史", "多轮顺序一致；消息只关联本次研究，错误不丢用户消息", "与 AI 对话交锋"),
])
add("REC", "研究记录与回测对比", "/app/research/records", "app_pages/6_run_library.py", ["test_run_store.py", "test_run_comparison.py", "test_run_labels.py"], [
    ("筛选与完整记录", "策略、运行类型、状态、名称/编号搜索", "成功/失败/无效/旧版标识及父实验/基准ID、错误原因", "默认成功状态；组合筛选与原记录一致；空结果有提示", "筛选记录"),
    ("记录CSV与报告", "下载回测记录；选择记录进入单次复盘", "完整筛选记录CSV及正确运行报告", "CSV不只含屏幕列；中文证券名和编码保留", "下载回测记录 CSV"),
    ("从结果保存方案", "输入新方案名，保存为新方案", "从历史执行快照保存并关联历史运行", "使用该结果配置而非全局当前配置；缺快照明确失败", "从此结果保存研究方案"),
    ("2～5次结果对比", "选择2～5条成功回测；指标、参数和归一净值；CSV", "策略/参数中文化，起点1的曲线和完整对比数据", "不足2条提示；最多5条；数据及文件对应所选ID", "选择2～5次回测"),
])
add("PLAN", "研究方案版本与复用", "/app/research/plans", "research_plans.py", ["test_guided_research.py"], [
    ("方案保存和自动关联", "名称、保存当前版本；运行时自动保存及关联结果", "股票池/规则/区间/费用/风控执行快照、版本号", "新增版本而非覆盖旧版；保存不复制行情数据", "def render_plan_save"),
    ("版本列表和恢复", "按账号列版本、恢复修改、打开关联报告", "引导式方案回想法页，专业方案回复用页", "同名按ID区分；账号方案隔离；运行记录仍为现有本地共享库", "def render_saved_plans"),
    ("2～4版本比较", "选版本比较配置差异和最近关联结果", "未运行/不可读提示；不同区间/费用等不可直接排名警告", "不为未运行版本填收益；可比性字段完整", "选择2～4个版本比较"),
    ("复用修改与重跑", "保存快照基础上改日期、资金、持仓、频率、策略参数JSON", "校验、运行前检查、保存版本和新单次回测", "JSON非法清除待运行请求；保留旧股票池/费用/风控而非换成全局配置", "def render_restored_plan"),
])
add("AUD", "可信度审计", "/app/audits/:runId", "app_pages/audit_report.py", ["test_audit_report_page.py", "test_credibility.py", "test_selection_bias_ui.py"], [
    ("对象与运行选择", "平台回测/外部材料切换，选择成功回测", "当前报告；空记录/读取失败提示", "结果页带入指定ID；切外部材料进入EXT流程", "审计对象"),
    ("评级与六维审计", "A/B/C/D、通过数、绩效可用性、观测数、成本比例；维度总览/明细", "数据、未来函数、样本偏差、成本、容量、参数搜索六维", "通过/警告/失败/无法评估/不适用语义和评级一致", "六维审计"),
    ("DSR依据和证据链", "参数搜索面板、原始问题代码/级别/说明", "当前记录的原始证据，不丢失无法评估原因", "与OPT-04同字段；不能用缺记录的旧概率代替", "证据链"),
    ("执行假设", "历史分期费率、参与率上限、滑点、未知状态处理", "取自执行快照，缺失标未记录", "不从当前配置推算历史假设；比例和单位一致", "审计假设"),
])
add("EXT", "外部成交材料核查", "/app/audits/external", "external_audit.py", ["test_forensics.py"], [
    ("导入和模板", "粘贴表格/上传CSV；下载模板", "前10条预览、总条数、5字段自动识别/人工映射", "日期/代码/方向/数量/价格均映射；净值截图报告暂不支持", "导入方式"),
    ("单位、价格与错误行", "股/手、未复权/复权或不确定；重复成交确认", "转换结果；错误行表；复权价证据不足", "不静默丢错行；未确认重复行不核查；映射变化使旧报告失效", "数量单位是什么"),
    ("核查与结论过滤", "核对上市、停牌、价格、成交占比；过滤结论", "各结论计数、证据覆盖率、行号和详细发现", "无本地证据标证据不足；行号含表头且对应原行", "证据齐备的成交记录"),
    ("Markdown报告下载", "下载检查报告", "外部成交检查.md，包含完整核查发现", "报告可读且反映全部发现，而不只筛选显示的结论", "下载检查报告"),
])
add("OPS", "数据与运行入口", "/app/operations", "app_pages/19_data_operations.py", ["test_workspace_navigation.py"], [
    ("工具入口和按需概览", "行情更新、股票池、任务记录、全部工具；展开概览", "配置股票数/历史充足数/知识条目数；失败降级", "概览按需读取，数据更新后可刷新，入口目标正确", "工作区概览"),
])
add("DATA", "日常行情与数据导出", "/app/data/update", "app_pages/1_data_management.py", ["test_data_center_service.py", "test_data_source_fallback.py", "test_web_exports.py", "test_safe_data_errors.py"], [
    ("配置与数据源状态", "就绪度、仓库摘要、来源和可用状态", "证券数、配置股票数、行情覆盖、记录数、未知状态行、最近成功来源；当前配置状态与实际更新成功来源区分", "六项概览逐项比对；未配置/读取失败提示；不以已配置声称下载成功", "行情数据源"),
    ("选择数据和来源更新", "日期；主表、股票日线、分红送配、多个基准；本次首选源和回退开关", "更新结果、成功/失败及实际来源版本", "至少一个数据集、合法日期；回填运行时禁日常更新；本次选源不改默认", "开始更新"),
    ("更新反馈与导出", "结果表、失败对象和脱敏原因；下载更新结果", "data_update_results.csv，成功与失败都可追溯", "部分失败仍保留成功项；原因不暴露凭证", "下载更新结果 CSV"),
    ("股票池覆盖率", "覆盖表、范围、缺失估算、重复数、覆盖率CSV", "configured_stock_coverage.csv", "覆盖率数值和股票范围与原计算一致；空数据有提示", "下载覆盖率 CSV"),
    ("股票行情筛选下载", "多股票与起止日期；预览最后500行；完整下载", "daily_bars_selected.csv按代码/日期排序", "下载包含全部筛选行，不能只下载500行；空筛选不给误导文件", "下载股票日线行情 CSV"),
    ("基准行情", "选择指数、收盘图、最后100行、全量CSV", "benchmark_代码.csv", "切换指数图/表/文件一致；下载不是100行预览", "下载完整基准行情 CSV"),
    ("证券主表", "前2000行预览、完整主表CSV", "security_master.csv", "完整主表不截断；中文证券名称和证券代码一致", "下载完整证券主表 CSV"),
    ("数据版本", "版本、数据集、实际/请求路由、回退、状态、时间、记录/证券数、区间、错误", "data_versions.csv和版本表", "源、回退路径与时间可追溯；错误脱敏；空版本有提示", "下载数据版本 CSV"),
])
add("JOB", "全市场回填与任务记录", "/app/data/backfill；/app/operations/jobs", "data_job_panel.py", ["test_data_jobs.py", "test_full_market_backfill.py"], [
    ("启动与互斥", "回填日期和bars/actions/derived；证券主表始终更新", "后台任务ID；同区间跳过已完成；改变区间重新抓取", "已有活动任务禁重复启动；日期/数据集校验一致", "启动回填"),
    ("进度与停止", "约5秒刷新阶段、完成/总数、失败、重试数；停止", "停止请求与安全结束状态；关闭页不影响后台执行", "重新打开能找回任务；不能把已请求停止当作立即完成", "停止任务"),
    ("历史与继续回填", "选择历史任务；失败/部分/停止/中断后继续", "沿原日期/数据集重启，最多自动重试20次", "全部8种状态正确；继续沿用原范围且不并行写同仓库", "继续回填"),
    ("日志查看", "最近最多32KB日志", "空日志/脱敏日志", "日志长度限制与脱敏有效；不把凭证写入页面", "最近日志"),
])
add("LOOP", "全市场数据闭环状态", "/app/data/backfill", "app_pages/1_data_management.py", ["test_full_market_backfill.py"], [
    ("闭环指标与检查点", "展开全市场数据闭环", "主表/退市/行情覆盖/成分/退市结算/公司行动，检查点表", "保留上市退市规则近似与推导值说明；数量取自仓库", "全市场数据闭环"),
])
add("UNI", "股票池维护", "/app/data/universe", "app_pages/5_universe_management.py", ["test_universe_service.py"], [
    ("批量代码与名称搜索添加", "多代码、证券名称/代码检索、多选添加", "规范化后的池、搜索结果与添加反馈", "市场后缀与重复处理一致；主表缺失提示先更新", "添加代码"),
    ("确认移除", "多选股票并明确确认移除", "股票池更新，保留本地历史行情", "不确认不得移除；只移除所选代码", "移除选中的股票"),
    ("过滤规则", "排ST/停牌、最少上市天数、最少历史天数、20日最低成交额", "持久化过滤配置；前往数据更新入口", "保存刷新仍一致；非法值提示；改池后补数据引导保留", "保存过滤设置"),
])
add("RISK", "风险规则与记录", "/app/risk", "app_pages/3_risk_management.py", ["test_daily_portfolio_risk.py", "test_risk_engine.py"], [
    ("仓位与风险参数", "启用、总仓位、单股权重、持股数、每日纠偏、现金、回撤、行业、单日亏损、调仓换手", "完整RiskLimits及保存校验", "所有字段/边界与YAML一致；新运行应用配置，旧结果保留原快照", "启用风控"),
    ("回撤处理方式", "停止新开仓/降低仓位/清仓；降仓目标仅reduce可编辑", "收盘检查、下一交易日开盘纠偏说明", "三种动作与依赖字段对应；不能改成当日成交", "达到回撤线后的处理"),
    ("最近风控记录", "最近10个成功运行的事件；次数/调整/拒绝指标", "合并排序后的前500条事件及运行ID", "计数基于完整合并事件，不只500条预览；旧版无事件有提示", "最近风控记录"),
])
add("ASSET", "数据资产与来源对比", "/app/data/sources", "app_pages/13_data_assets.py", ["test_data_credentials.py"], [
    ("来源对比和状态", "来源对比/XTick接口切换；XTick、BaoStock、AkShare、iFinD、Tushare说明", "凭证/安装状态、建议、专项接口入口", "来源列表状态读取一致；安装或凭证状态不冒充服务连通性", "来源对比"),
])
add("XT", "XTick动态接口", "/app/data/xtick", "app_pages/11_xtick_data.py", ["test_security_names.py", "test_web_exports.py"], [
    ("完整动态目录", "6分类85接口；本地apidoc优先，缺文件再拉目录；凭证设置跳转", "按docApis动态生成分类、接口说明和表单", "85个接口ID/URL均覆盖，不只迁移少数示例", "def _load_catalog"),
    ("参数类型与请求", "枚举、整数、小数、日期、文本、示例默认值和参数名修正", "日期格式化、枚举真实值；Token由服务端使用", "逐接口元数据一致；ZIP/JSON成功和错误均能处理；前端不收原始凭证", "def _render_field"),
    ("结果与下载", "表格/原始JSON、证券中文名、接口独立列名、CSV", "xtick_分类_接口.csv；非表格显示JSON；按接口保存结果", "同名字段在不同接口按各自outputParas解释；错误清空旧结果", "def _output_rename_map"),
])
add("SET", "模型、数据源与系统设置", "/app/settings", "app_pages/14_settings.py", ["test_llm_settings.py", "test_data_credentials.py"], [
    ("AI模型配置", "动态提供方、Base URL、Key、模型；仅保存/保存设默认", "各提供方配置、凭证状态与全局默认；空Key环境变量回退", "两保存动作区别保留；业务页读取同一默认模型；凭证由后端保存", "仅保存配置"),
    ("数据源凭证", "XTick Token/Base URL、iFinD账号密码、Tushare Token", "本地凭证及状态，BaoStock/AkShare无需凭证提示", "保存后相关服务读取；已有凭证延用，不传整个凭证文件到浏览器", "保存凭证"),
    ("系统与存储信息", "版本、Python、磁盘、系统、数据/运行/设置路径和代理是否设置", "只读诊断；Streamlit版本在新系统改为实际组件版本", "路径显示与后端实际一致；环境信息不包含密钥值", "系统运行信息"),
    ("个人中心和指南入口", "设置页跳个人中心或使用指南", "账号区/公开介绍页可达", "返回工作台时导航状态正确", "账号与使用指南"),
])
add("AUTH", "账号与登录（后期迁移）", "/login；/register；/app/account", "auth.py", ["test_user_center.py"], [
    ("注册校验", "用户名3～32位、邮箱、至少8位密码、确认密码", "重复账号/邮箱错误、注册成功；不自动宣称已登录", "旧校验和不区分大小写约束保持；测试在隔离数据库执行", "def register"),
    ("用户名或邮箱登录", "用户名/邮箱与密码；旧用户库自动兼容", "已登录身份；错误提示；保留原PBKDF2账号兼容", "备份账号可登录；旧库兼容；最终使用服务端会话而非前端布尔值", "def authenticate"),
    ("资料读取", "读取当前用户资料", "ID/用户名/邮箱/UTC注册时间，不暴露密码哈希", "保持账号字段和归属ID；非法访问有明确门槛", "def get_profile"),
])
add("ACC", "个人中心与占位功能", "/app/account", "app_pages/16_user_center.py", ["test_user_center.py"], [
    ("资料、返回来源页和设置跳转", "只读资料、个人中心分类、返回上一页、前往设置", "当前身份/账号资料及返回目标", "直接进入或来源页失效均有安全默认页；资料缺失有提示", "返回上一页"),
    ("退出登录", "账号安全中退出；页头/页尾退出入口", "身份与未保存会话输入清除；返回未登录入口", "新旧实现退出后均不能继续用旧会话访问工作台", "退出登录"),
    ("资料编辑、改密码、保存偏好", "当前禁用按钮及默认页/语言禁用选项", "即将开放提示，当前不产生持久化修改", "按占位项保留或另立新增需求；不伪称现成功能", "编辑资料 · 即将开放", "禁用占位"),
    ("个人策略/回测/收藏空间", "我的研究中的说明卡片", "即将开放；并非已实现的账号隔离成果库", "不得把共享回测库描述成已按账号隔离", "个人研究空间即将开放", "禁用占位"),
])

ROUTES = {
    "ai": "/app/research/ai", "ideas": "/app/strategies/ideas", "visual": "/app/strategies/visual",
    "natural": "/app/strategies/natural-language", "python": "/app/strategies/python",
    "backtest": "/app/backtests/new", "validation": "/app/experiments/optimization",
    "factor": "/app/factors/library", "knowledge": "/app/knowledge", "records": "/app/research/records",
    "audit": "/app/audits/:runId", "external": "/app/audits/external", "plans": "/app/research/plans",
    "data": "/app/data/update", "backfill": "/app/data/backfill", "jobs": "/app/operations/jobs",
    "assets": "/app/data/sources", "xtick": "/app/data/xtick", "universe": "/app/data/universe",
    "risk": "/app/risk", "settings": "/app/settings", "account": "/app/account", "welcome": "/",
}
LEGACY = {
    "app_pages/2_research.py": "/app/experiments/optimization（含walk-forward）",
    "app_pages/3_risk_management.py": "/app/risk",
    "app_pages/7_strategy_studio.py": "/app/strategies/visual",
    "app_pages/8_custom_strategy.py": "/app/strategies/python",
    "app_pages/10_nl_strategy.py": "/app/strategies/natural-language",
    "app_pages/11_xtick_data.py": "/app/data/xtick",
    "app_pages/strategy_forensics.py": "/app/audits/external",
}
assert set(ROUTES) == {t["key"] for t in SCAN["tools"]}
assert set(LEGACY) == set(SCAN["legacy_routes"])
assert len({f["id"] for f in FEATURES}) == len(FEATURES)
for feature in FEATURES:
    for test in feature["existing_test_candidates"]:
        assert list((ROOT / "tests").rglob(test)), test

register = {"baseline_commit": SCAN["baseline_commit"], "evidence": "源码核对；没有执行页面业务操作或迁移验收",
            "feature_count": len(FEATURES), "groups": GROUPS, "features": FEATURES,
            "tool_routes": ROUTES, "legacy_source_routes": LEGACY}
(DIRECTORY / "feature-register.json").write_text(json.dumps(register, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def cell(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")

lines = ["# React / FastAPI 迁移功能清单", "",
         "状态：第二步已完成源码盘点；全部功能仍待迁移、待验收。", "",
         f"基线：`zyf` · `{SCAN['baseline_commit']}` · 2026-10-07。", "",
         f"覆盖：5 个工作区、23 个工具入口、7 个旧源页面入口、22 个子页面文件、47 个网页 Python 模块；整理为 {len(FEATURES)} 项功能。", "",
         "本清单基于源代码和已有测试的静态核对，不表示旧网站或新网站已经逐项实测通过。源码中的休眠区块与禁用占位单列。", "",
         "建议的新路由是迁移草案；旧源文件路径不是浏览器URL，实施重定向前须记录实际旧URL。登录可以后做，但最终停用旧网站之前须完成可用账号功能。", "",
         "## 文档与验收方法", "",
         "- [逐项验收表](acceptance-checklist.md)：操作步骤、对照要求和未完成状态。",
         "- [功能登记数据](feature-register.json)：稳定编号、新路由、源码行号、已有测试候选。",
         "- [源码扫描结果](source-inventory.json)：输入、动作与核心输出的源码位置、参数表达式、条件、状态键、辅助渲染调用、动态接口和指标。扫描数量是静态调用候选数，不是功能数；非Streamlit接收者需人工复核，HTML交互另行梳理。",
         "- 重新生成：`python scripts/inventory_web_features.py`，然后 `python scripts/build_migration_inventory.py`。", "",
         "## 迁移时必须保留的行为", "",
         "1. 每项可用功能有对应新页面/API/验收记录；布局可调整，输入、计算口径、结果和异常语义必须对应。",
         "2. 后端校验仍是最终依据。研究确认、风险限制、数据检查、策略安全检查、样本外边界不得只留在按钮状态中。",
         "3. 每条历史运行按自己的执行快照读取；不能用现在的默认配置重新解释旧结果。",
         "4. 图表不仅看外观，还核对底层逐日数据、单位、排序、缺失值、基准起点和交易时间语义。",
         "5. 下载全量数据，不照搬页面预览的行数限制；中文CSV保留UTF-8 BOM、证券名称及原始字段。",
         "6. 临时会话草稿与磁盘持久化分开登记。新系统的刷新恢复/后台任务能力在后续步骤建设，不能当作旧系统已经全部具备。", "",
         "## 入口与新路由对照", "",
         "| 工具 | 当前源页面及模式 | 建议新位置 |", "| --- | --- | --- |"]
for tool in SCAN["tools"]:
    mode = "; ".join(f"{k}={v}" for k, v in tool.get("initial_state", [])) or "默认"
    lines.append(f"| {cell(tool['title'])} | `{tool['path']}`；{cell(mode)} | `{ROUTES[tool['key']]}` |")
lines += ["", "### 旧入口兼容", "", "| 当前旧源页面 | 对应新位置 |", "| --- | --- |"]
for source, route in LEGACY.items():
    lines.append(f"| `{source}` | `{route}` |")
lines += ["", "### 五个工作区", "", "| 工作区 | 现有源页面 | 建议新路由 |", "| --- | --- | --- |"]
for workspace, route in zip(SCAN["workspaces"], ["/app", "/app/strategies", "/app/research/records", "/app/operations", "/app/settings"]):
    lines.append(f"| {workspace['title']} | `{workspace['path']}` | `{route}` |")

for group in GROUPS:
    lines += ["", "## " + group["title"], "", "建议位置：`" + group["route"] + "`。", "",
              "| 编号 / 功能 | 输入与操作 | 结果与状态 | 验收要求 |", "| --- | --- | --- | --- |"]
    for feature in [f for f in FEATURES if f["group"] == group["title"]]:
        note = "" if feature["current_state"] == "源码可达" else "（" + feature["current_state"] + "）"
        source = feature["source"]
        link = f"[源码](../../{source['path']})（{source['line']}行）"
        lines.append("| " + " | ".join(cell(v) for v in [feature["id"] + " " + feature["name"] + note,
            feature["inputs_and_actions"], feature["outputs_and_state"], feature["acceptance"] + "；" + link]) + " |")

lines += ["", "## 数据、状态与归属保留表", "",
    "以下是代码默认位置；实际位置应以 configs/app.yaml 及历史快照为准。验收使用第一步备份的副本，写操作不对原始样本进行。", "",
    "| 数据/状态 | 当前载体 | 新系统要求 |", "| --- | --- | --- |",
    "| 行情、主表、公司行动、历史成分、退市结算、版本 | 配置中的data.repository，Parquet及版本记录；raw快照 | 延用数据含义与版本，接口分页不改底层原始数据 |",
    "| 历史回测与有效性证据 | runtime/runs（或配置运行目录）及每次配置快照 | 原运行ID、全部结果和父实验/基准关联可读 |",
    "| 参数优化与滚动验证 | runtime/optimizations、runtime/walk_forward（或配置运行目录） | 保留排名、试验清单、窗口、训练/测试子运行关联 |",
    "| 研究方案版本 | runtime/state/research_plans.sqlite3 | 沿用owner、plan_id、revision与关联运行；不是只迁移名称 |",
    "| Python策略与可视化策略包 | Python：runtime/user_strategies；可视化：runtime/strategy_definitions（由回测目录的父目录派生） | 保留源码、定义、版本、说明和安全检查语义 |",
    "| 自定义因子与先验知识 | runtime/custom_factors.json、runtime/prior_knowledge.json | 保留ID、版本、方向、字段和来源 |",
    "| 全市场任务与检查点 | runtime/data_jobs、runtime/full_market_backfill_state.json | 状态、日志、重试、进度、范围与停止/续跑关系可追溯 |",
    "| AI配置和数据源凭证 | runtime/llm_settings.json、runtime/data_source_settings.json、.env | 后端读取；前端仅获所需状态，不能发送整个原始凭证文件 |",
    "| 代理配置 | runtime/proxy_settings.json | 当前AI页读取，设置页无对应编辑控件；记录该差异 |",
    "| 账号 | data/fellowquant_auth.sqlite3及旧alphaquant_auth.sqlite3兼容 | 原账号、密码哈希和ID可用；最终采用服务端鉴权 |",
    "| 股票池与风险规则 | configs/universes、configs/risk.yaml及配置引用 | 保存与校验等价；只影响新运行，历史快照不被覆盖 |",
    "| 会话草稿/当前结果 | st.session_state中的guided_draft、pending_backtest_request、selected_run、agent_lab_run、battle_history、外部核查与组合指纹等 | 按source-inventory列出的键分配到前端草稿、后端任务或持久化结果；runner/服务对象不得JSON原样发送 |", "",
    "## 当前边界与需要单独记录的差异", "",
    "- 个人中心的资料编辑、修改密码、保存偏好、个人策略/回测/收藏空间是占位项，不能算已经可用。", 
    "- 仅研究方案已按账号隔离；当前本地回测记录、模型和数据源配置并非完整多租户隔离，迁移不应误称已经具备。",
    "- 外部核查只支持普通股票的成交明细粘贴/CSV；净值、截图、委托单及泛化报告导入未开放。",
    "- 欢迎页扩展模块由False开关关闭；首页轮播和部分指标是示意展示。",
    "- AI页有模拟成交展示；paper_service等后端模块不等于现有独立模拟账户网页入口，后端能力保留，新增界面另列需求。",
    "- AI页提示中的“设置→网络与存储”与当前设置分类不一致，现设置只有AI模型、数据源凭证、系统信息；登记为文案/入口差异，后续修正。",
    "- 旧Streamlit版本诊断显示改为新组件版本是框架信息替换；平台版本、Python、磁盘、目录等诊断能力仍要保留。", "",
    "## 结果指标附录", "",
    "从home.py的_render_metric_grid实参抽取；以下所有键及格式均须对照。其他独立metric和图表位置见source-inventory。", "",
    "| 源码行 | 显示名 | 原字段 | 格式 |", "| --- | --- | --- | --- |"]
for group in SCAN["metric_catalog"]:
    for metric in group["metrics"]:
        lines.append(f"| {group['line']} | {cell(metric['label'])} | `{metric['key']}` | `{metric['format']}` |")
lines += ["", "## XTick动态接口覆盖附录", "",
          f"本地目录SHA-256：`{SCAN['xtick_catalog']['sha256']}`。完整输入/输出定义见source-inventory.json的xtick_catalog，验收前对照目录版本。", "",
          "| 分类 | 接口ID | 接口名称 | 路径 |", "| --- | --- | --- | --- |"]
for category in SCAN["xtick_catalog"]["categories"]:
    for api in category["apis"]:
        lines.append(f"| {category['name']} | {api['id']} | {cell(api['name'])} | `{api['url']}` |")
lines += ["", "## 第二步完成条件", "",
          "- [x] 所有注册工具与旧入口有映射；全部子页面文件进入源码清单。",
          "- [x] 参数/动作/结果/导出/状态/异常及动态目录有来源。",
          "- [x] 可用项、禁用占位和休眠代码分开标明。",
          "- [x] 每项功能都有验收标准与迁移/验收状态。",
          "- [ ] 新系统逐项实现与实测：属于后续迁移和验收阶段。", ""]
(DIRECTORY / "feature-inventory.md").write_text("\n".join(lines), encoding="utf-8")

acceptance = ["# 迁移验收表", "", "基线与功能定义见[功能清单](feature-inventory.md)。当前所有项目均为待迁移、待验收。", "",
    "## 对照准备", "",
    "1. 复制第一步备份到隔离验收环境；添加/删除策略、股票、知识、保存配置和运行任务均用副本。",
    "2. 选取完整成功回测、失败/无效结果、旧版缺可选字段记录、优化实验和滚动验证记录作为固定样本。AI和外部服务使用固定响应样本，不因一次远程失败判定界面缺功能。",
    "3. 记录原系统实际URL、默认参数、输入、磁盘结果与截图。静态源码核对是本次证据；操作结果与截图要在后续阶段补充。",
    "4. 数值先按原始字段比对：代码/日期/ID/状态/计数精确一致；浮点容差按字段制定并记录，不能统一用较宽容差掩盖差异。随机/远程模型结果用同一响应验证呈现，不要求重新调用得到逐字相同内容。",
    "5. 每项完成后记录新路由、API、复现输入、结果或截图、测试记录和已知差异。只有前后输入、操作、输出、异常与数据保留都通过，才能标记通过。", "",
    "## 按功能逐项登记", "",
    "| 编号 | 功能 | 操作与核对标准 | 迁移 | 验收 | 新路由/API/证据 |", "| --- | --- | --- | --- | --- | --- |"]
for f in FEATURES:
    acceptance.append("| " + " | ".join(cell(v) for v in [f["id"], f["name"], f["acceptance"], "待迁移", "待验收", "待补充"]) + " |")
acceptance += ["", "## 必须贯通的流程", "",
    "| 流程 | 操作顺序 | 必须核对 | 状态 |", "| --- | --- | --- | --- |",
    "| E2E-01 初次研究 | 股票池→行情更新→选股想法→确认→检查/补齐→回测→完整结果→审计 | 参数、数据版本、方案revision、运行ID、评级一致 | 待验收 |",
    "| E2E-02 模板和规则 | 模板/积木→保存→版本/复制→重载→回测→历史记录 | 编辑签名与实际执行定义一致；旧版本保留 | 待验收 |",
    "| E2E-03 自然语言 | 模型设置→生成规则→核对→确认保存→工作室→回测 | 未确认不注册；不支持规则不伪造执行结果 | 待验收 |",
    "| E2E-04 Python | 编辑或上传→安全检查→确认警告→注册→参数回测→删除 | 阻断规则仍阻断；历史结果可读；错误行和加载失败可见 | 待验收 |",
    "| E2E-05 优化 | 成功基准→候选网格→优化→DSR→子回测→审计→下载 | 基准和所有试验关联；缺证据清空DSR | 待验收 |",
    "| E2E-06 样本外 | 基准→训练/测试窗口→选参→样本外结果→子报告→CSV | 严格先训练后测试；失败窗口和信任警告保留 | 待验收 |",
    "| E2E-07 因子 | 库筛选/行选择→评估→组合训练验证→下载→回测 | 完整报告、共同样本、已验证spec；修改配置失效 | 待验收 |",
    "| E2E-08 研究版本 | 保存→修改另存版本→2～4版比较→恢复→改JSON→检查→重跑 | 账号归属、revision、原费用风控、运行关联 | 待验收 |",
    "| E2E-09 外部材料 | 粘贴/CSV→映射→股手和价格确认→错误/重复检查→核查→筛选→报告 | 原行号、证据不足、完整发现导出；旧报告指纹失效 | 待验收 |",
    "| E2E-10 数据任务 | 启动回填→关页重开→进度→停止→续跑→版本/闭环 | 单活动任务、检查点、8种状态、脱敏日志 | 待验收 |",
    "| E2E-11 AI | 先验知识/模型→选行情/新闻→缓存或完整分析→证据→模拟成交→多轮对话 | 缓存不编造过程；过程/结果/聊天属于同次研究 | 待验收 |",
    "| E2E-12 账号 | 欢迎→注册→用户名/邮箱登录→工作台→个人中心→返回→退出 | 旧用户库兼容；方案归属；退出失效；占位仍明确 | 待验收（后期） |",
    "| E2E-13 下载 | 所有CSV/JSON/Markdown出口→本地解析 | 全量行数、原字段、中文编码/证券名、筛选范围与文件名 | 待验收 |",
    "| E2E-14 路由 | 5工作区、23工具、7旧入口、结果/审计/基准深链 | URL参数、返回来源页、刷新恢复及无效ID错误页 | 待验收 |", "",
    "## 现有测试索引", "",
    "仅列可复用候选测试，并未在本步骤运行或声称通过。旧界面源码断言需要为新实现调整，不能因旧测试文本匹配通过就视为新功能可用。", "",
    "| 功能组 | 候选测试文件（tests/unit或tests/integration） |", "| --- | --- |"]
for group in GROUPS:
    acceptance.append(f"| {group['title']} | {', '.join('`' + x + '`' for x in group['tests'])} |")
acceptance += ["", "## 最终切换门槛", "",
    "- 每个源码可达功能均有通过证据；登录可后迁移，但切换前不能漏掉。",
    "- 禁用占位/休眠项逐项记录处理方式；不能无声删除，也不计为已经完成的业务能力。",
    "- 旧行情、策略、账号、方案版本和研究结果在新系统可读取；核心计算及可信度语义完成对照。",
    "- 新后台任务的重复提交、刷新恢复、异常退出和重试有验证；这是新增架构的验收，不能仅照抄Streamlit会话表现。",
    "- 已登记的全部下载、动态接口元数据、深链接和关键错误状态通过。",
    "- 保留基线备份及回退方式；未完成项不以“布局简化”替代验收。", ""]
(DIRECTORY / "acceptance-checklist.md").write_text("\n".join(acceptance), encoding="utf-8")
print(json.dumps({"features": len(FEATURES), "groups": len(GROUPS), "states": dict(Counter(f['current_state'] for f in FEATURES)),
                  "tools": len(ROUTES), "legacy": len(LEGACY), "xtick_apis": SCAN['xtick_catalog']['api_count']}, ensure_ascii=False))
