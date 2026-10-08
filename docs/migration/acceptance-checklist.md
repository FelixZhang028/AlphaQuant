# 迁移验收表

基线与功能定义见[功能清单](feature-inventory.md)。第六步最新状态见[逐项验收记录](step6-feature-results.md)；保留部分通过、延后及原版占位，不声明125项全通过。

## 对照准备

1. 复制第一步备份到隔离验收环境；添加/删除策略、股票、知识、保存配置和运行任务均用副本。
2. 选取完整成功回测、失败/无效结果、旧版缺可选字段记录、优化实验和滚动验证记录作为固定样本。AI和外部服务使用固定响应样本，不因一次远程失败判定界面缺功能。
3. 记录原系统实际URL、默认参数、输入、磁盘结果与截图。静态源码核对是本次证据；操作结果与截图要在后续阶段补充。
4. 数值先按原始字段比对：代码/日期/ID/状态/计数精确一致；浮点容差按字段制定并记录，不能统一用较宽容差掩盖差异。随机/远程模型结果用同一响应验证呈现，不要求重新调用得到逐字相同内容。
5. 每项完成后记录新路由、API、复现输入、结果或截图、测试记录和已知差异。只有前后输入、操作、输出、异常与数据保留都通过，才能标记通过。

## 按功能逐项登记

| 编号 | 功能 | 操作与核对标准 | 迁移 | 验收 | 新路由/API/证据 |
| --- | --- | --- | --- | --- | --- |
| NAV-01 | 五个工作区 | 逐一打开五区，子页可返回所属工作区 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| NAV-02 | 全部工具与搜索 | 23个工具逐项进入；查询无结果有提示 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| NAV-03 | 模式与上下文跳转 | 分别打开不同结果验证上下文ID一致 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| NAV-04 | 旧入口兼容 | 记录实际旧URL后逐个验证重定向和参数传递 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| APP-01 | 工作台访问门槛 | 开发阶段可先做工作台，最终切换前恢复访问门槛 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| APP-02 | 品牌与支持入口 | 点击Logo和支持链接，个人中心返回原页 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| HOME-01 | 三类开始入口 | 每个入口目标和审计模式正确 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| HOME-02 | 最近研究与继续 | 成功记录排序一致；空记录/读取失败有提示 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| LAND-01 | 欢迎展示与锚点 | 桌面和窄屏均能进入正文及账号操作 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| LAND-02 | 中英文切换 | 切换后欢迎页各区文案一致；不承诺全工作台翻译 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| LAND-03 | 五类功能轮播 | 逐个标签可切换；不将示意收益当真实账户数据 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| LAND-04 | 五步研究介绍 | 保留内容和读取失败降级；避免制造已有按钮的错觉 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| LAND-05 | 页尾账号入口 | 页头和页尾入口都能操作；不只保留原生隐藏按钮 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| LAND-06 | 扩展欢迎区块 | 标记休眠代码；若启用需另行验收，不冒充当前展示功能 | 保留原状态 | 保留原状态 | [第六步证据](step6-feature-results.md) |
| HUB-01 | 四种创建方式 | 四模式逐个打开；模板与积木旧模式映射到策略搭建 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| IDEA-01 | 想法与研究范围 | 同输入对应同策略；日期和空池校验；切页草稿可继续 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| IDEA-02 | 规则确认与风险约束 | 未确认、持股过少或仓位限制不兼容时阻止运行 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| IDEA-03 | 数据检查与补齐 | 缺口阻止运行；补齐含回看期；失败后可重试 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| IDEA-04 | 确认运行与结果 | 运行前再次检查；改参数使旧检查/旧结果失效；结果ID对应本次 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| IDEA-05 | 专业回测的待运行方案 | 表单未再提交时不偷换执行参数；后端重查数据 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| VIS-01 | 回测范围 | 选择的区间和资金带入实际执行请求 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| VIS-02 | 模板与风格 | 逐模板按当前注册表验收；折叠高级设置不改值 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| VIS-03 | 模板运行和另存 | 另存可在我的策略找到；回测摘要对应同一运行 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| VIS-04 | 自定义规则搭建 | 每类指标和比较对象可组合；非法规则给出原因 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| VIS-05 | 排序与策略生成 | 编辑后旧预览不能作为当前已验证定义运行 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| VIS-06 | 保存、版本与复制 | 保存后可重载；修改版本与复制的ID语义正确 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| VIS-07 | 运行自定义或已保存策略 | 旧结果与当前编辑定义不一致时不误展示为本次结果 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| NL-01 | 描述转规则 | 模型失败和不支持规则清楚提示；不直接执行未经确认的规则 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| NL-02 | 人工确认与保存 | 只有确认后保存；结构化规则校验与原实现一致 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| NL-03 | 放弃与后续回测 | 放弃不注册；跳转后能选择刚保存的策略 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| PY-01 | 在线编写并注册 | 阻断项不可绕过；警告需明确勾选；加载失败原因可见 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| PY-02 | 上传.py文件 | 合法上传可保存；错误编码/代码/风险项不静默接收 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| PY-03 | 已保存策略及回测 | 参数类型/边界/默认值一致；策略与运行结果ID匹配 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| PY-04 | 删除自定义策略 | 仅处理选中策略；历史回测结果仍可读取 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| BT-01 | 四种研究阶段 | 切换阶段不把研究对象/当前运行误改成其他对象 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-02 | 策略与基础输入 | 注册策略全部出现；同输入传给现有回测引擎 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-03 | 完整高级参数 | 动态字段不得按一个示例写死；高级区折叠不改默认值 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-04 | 组合与股票池口径 | 四种分配与两种股票池模式均可选择，缺数据不静默降级 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| BT-05 | 提交与检查 | 沿用IDEA-05的二次检查；无数据不得生成成功结果 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-06 | 因子组合带入 | 权重、方向、清洗和版本保持；不拿过期组合直接回测 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| BT-07 | 运行选择与通俗摘要 | 旧结果可读；无效指标不伪造；缺summary有提示 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| BT-08 | 策略和基准曲线 | 图表底层数据逐日比对；不能用不同起点或补零基准；月度缺失显示缺失而非零收益 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-09 | 收益与风险指标 | 与原summary逐字段比对；小数/百分比/年化口径一致 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-10 | 交易与成本明细 | 拒单、参考价/成交价、费用、净毛盈亏和排序不丢 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| BT-11 | 持仓与诊断 | 空仓/旧版无完整交易均有提示；数据和风险记录对应当前运行；有效性明细字段逐项比对 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| BT-12 | 继续验证/审计/记录 | 每个结果入口打开同一运行；不回到默认记录 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| OPT-01 | 基准继承 | 无基准/配置损坏/策略不可用阻止启动；不改用当前全局配置 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| OPT-02 | 参数网格与约束 | 超100组、非法值和日期被拒绝；组合总数与基准关联一致 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| OPT-03 | 优化结果和下载 | 未满足约束的有效试验仍入审计；子运行ID可追溯 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| OPT-04 | 参数搜索偏差 | 记录缺失清空旧概率；排序指标不偷偷替换成DSR | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| WF-01 | 窗口与搜索配置 | 日期不合法/窗口不足有错误；选参只读训练数据 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| WF-02 | 样本外结果 | 测试结果与原服务一致；训练失败/空窗口不伪装成功 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| WF-03 | 窗口详情与导出 | 对应测试ID正确；CSV包含全部结果而非仅预览 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| FAC-01 | 四个功能分区 | 各分区可用；无数据可浏览，不误声称可评估 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| FAC-02 | 单因子输入 | 缺当时暴露数据明确报错；不静默跳过中性化 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| FAC-03 | 完整因子报告 | t+1收盘及t+N+1收盘口径保留；覆盖率与样本不足提示一致 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| FAC-04 | 组合输入与清洗 | 训练/测试隔离；零权重和无效权重处理一致 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| FAC-05 | 组合结果和方案对比 | 改变任一配置/因子版本使旧验证失效，禁止旧组合带入回测 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| FAC-06 | 组合记录下载与回测 | JSON可解析且内容完整；仅当前指纹有效结果可带入 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| FAC-07 | 新增自定义因子 | 单窗和双窗规则完整；持久化后刷新可选 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| FAC-08 | 删除自定义因子 | 仅删所选自定义项；关联组合重新验证 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| LIB-01 | 筛选与检索 | 组合筛选语义和中文/编号检索一致 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| LIB-02 | 行选择与详情 | 选择正确因子；字段含义与来源可查；无数据仍能浏览 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| LIB-03 | 带入评估或组合 | 切换标签后因子正确；重复加入不产生重复项 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| KN-01 | 统计与筛选 | 筛选只影响显示，AI仍接收全部知识及来源 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| KN-02 | 添加知识 | 刷新可读取；后续AI分析上下文包含新知识 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| KN-03 | 删除知识 | 仅删除所选ID；后续AI上下文不再包含该条 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AI-01 | 模型与研究对象 | 非法/空代码及缺凭证不启动；可按原样处理非A股代码 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AI-02 | 行情与新闻选择 | 新闻失败可降级；代理仅按当前配置作用于适用来源 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| AI-03 | 分析参数与缓存 | 缓存命中不编造中间报告；重新分析清空上一轮对话 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AI-04 | 实时过程与回放 | 切页/重绘不重复调用分析；过程与最终状态一致 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AI-05 | 完整决策与证据 | 每个中间产物分区保留；缓存与完整模式的缺项语义正确 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| AI-06 | 模拟成交展示 | 字段与state.fill一致；止损/目标价仍只是研究参考 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| AI-07 | 人为介入对话 | 多轮顺序一致；消息只关联本次研究，错误不丢用户消息 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| REC-01 | 筛选与完整记录 | 默认成功状态；组合筛选与原记录一致；空结果有提示 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| REC-02 | 记录CSV与报告 | CSV不只含屏幕列；中文证券名和编码保留 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| REC-03 | 从结果保存方案 | 使用该结果配置而非全局当前配置；缺快照明确失败 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| REC-04 | 2～5次结果对比 | 不足2条提示；最多5条；数据及文件对应所选ID | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| PLAN-01 | 方案保存和自动关联 | 新增版本而非覆盖旧版；保存不复制行情数据 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| PLAN-02 | 版本列表和恢复 | 同名按ID区分；账号方案隔离；运行记录仍为现有本地共享库 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| PLAN-03 | 2～4版本比较 | 不为未运行版本填收益；可比性字段完整 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| PLAN-04 | 复用修改与重跑 | JSON非法清除待运行请求；保留旧股票池/费用/风控而非换成全局配置 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AUD-01 | 对象与运行选择 | 结果页带入指定ID；切外部材料进入EXT流程 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AUD-02 | 评级与六维审计 | 通过/警告/失败/无法评估/不适用语义和评级一致 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AUD-03 | DSR依据和证据链 | 与OPT-04同字段；不能用缺记录的旧概率代替 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| AUD-04 | 执行假设 | 不从当前配置推算历史假设；比例和单位一致 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| EXT-01 | 导入和模板 | 日期/代码/方向/数量/价格均映射；净值截图报告暂不支持 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| EXT-02 | 单位、价格与错误行 | 不静默丢错行；未确认重复行不核查；映射变化使旧报告失效 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| EXT-03 | 核查与结论过滤 | 无本地证据标证据不足；行号含表头且对应原行 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| EXT-04 | Markdown报告下载 | 报告可读且反映全部发现，而不只筛选显示的结论 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| OPS-01 | 工具入口和按需概览 | 概览按需读取，数据更新后可刷新，入口目标正确 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| DATA-01 | 配置与数据源状态 | 六项概览逐项比对；未配置/读取失败提示；不以已配置声称下载成功 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-02 | 选择数据和来源更新 | 至少一个数据集、合法日期；回填运行时禁日常更新；本次选源不改默认 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-03 | 更新反馈与导出 | 部分失败仍保留成功项；原因不暴露凭证 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-04 | 股票池覆盖率 | 覆盖率数值和股票范围与原计算一致；空数据有提示 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-05 | 股票行情筛选下载 | 下载包含全部筛选行，不能只下载500行；空筛选不给误导文件 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-06 | 基准行情 | 切换指数图/表/文件一致；下载不是100行预览 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-07 | 证券主表 | 完整主表不截断；中文证券名称和证券代码一致 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| DATA-08 | 数据版本 | 源、回退路径与时间可追溯；错误脱敏；空版本有提示 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| JOB-01 | 启动与互斥 | 已有活动任务禁重复启动；日期/数据集校验一致 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| JOB-02 | 进度与停止 | 重新打开能找回任务；不能把已请求停止当作立即完成 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| JOB-03 | 历史与继续回填 | 全部8种状态正确；继续沿用原范围且不并行写同仓库 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| JOB-04 | 日志查看 | 日志长度限制与脱敏有效；不把凭证写入页面 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| LOOP-01 | 闭环指标与检查点 | 保留上市退市规则近似与推导值说明；数量取自仓库 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| UNI-01 | 批量代码与名称搜索添加 | 市场后缀与重复处理一致；主表缺失提示先更新 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| UNI-02 | 确认移除 | 不确认不得移除；只移除所选代码 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| UNI-03 | 过滤规则 | 保存刷新仍一致；非法值提示；改池后补数据引导保留 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| RISK-01 | 仓位与风险参数 | 所有字段/边界与YAML一致；新运行应用配置，旧结果保留原快照 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| RISK-02 | 回撤处理方式 | 三种动作与依赖字段对应；不能改成当日成交 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| RISK-03 | 最近风控记录 | 计数基于完整合并事件，不只500条预览；旧版无事件有提示 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| ASSET-01 | 来源对比和状态 | 来源列表状态读取一致；安装或凭证状态不冒充服务连通性 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| XT-01 | 完整动态目录 | 85个接口ID/URL均覆盖，不只迁移少数示例 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| XT-02 | 参数类型与请求 | 逐接口元数据一致；ZIP/JSON成功和错误均能处理；前端不收原始凭证 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| XT-03 | 结果与下载 | 同名字段在不同接口按各自outputParas解释；错误清空旧结果 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| SET-01 | AI模型配置 | 两保存动作区别保留；业务页读取同一默认模型；凭证由后端保存 | 已接入 | 通过 | [第六步证据](step6-feature-results.md) |
| SET-02 | 数据源凭证 | 保存后相关服务读取；已有凭证延用，不传整个凭证文件到浏览器 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| SET-03 | 系统与存储信息 | 路径显示与后端实际一致；环境信息不包含密钥值 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| SET-04 | 个人中心和指南入口 | 返回工作台时导航状态正确 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| AUTH-01 | 注册校验 | 旧校验和不区分大小写约束保持；测试在隔离数据库执行 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| AUTH-02 | 用户名或邮箱登录 | 备份账号可登录；旧库兼容；最终使用服务端会话而非前端布尔值 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| AUTH-03 | 资料读取 | 保持账号字段和归属ID；非法访问有明确门槛 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| ACC-01 | 资料、返回来源页和设置跳转 | 直接进入或来源页失效均有安全默认页；资料缺失有提示 | 已接入 | 部分通过 | [第六步证据](step6-feature-results.md) |
| ACC-02 | 退出登录 | 新旧实现退出后均不能继续用旧会话访问工作台 | 延后 | 延后 | [第六步证据](step6-feature-results.md) |
| ACC-03 | 资料编辑、改密码、保存偏好 | 按占位项保留或另立新增需求；不伪称现成功能 | 保留原状态 | 保留原状态 | [第六步证据](step6-feature-results.md) |
| ACC-04 | 个人策略/回测/收藏空间 | 不得把共享回测库描述成已按账号隔离 | 保留原状态 | 保留原状态 | [第六步证据](step6-feature-results.md) |

## 必须贯通的流程

| 流程 | 操作顺序 | 必须核对 | 状态 |
| --- | --- | --- | --- |
| E2E-01 初次研究 | 股票池→行情更新→选股想法→确认→检查/补齐→回测→完整结果→审计 | 参数、数据版本、方案revision、运行ID、评级一致 | 待验收 |
| E2E-02 模板和规则 | 模板/积木→保存→版本/复制→重载→回测→历史记录 | 编辑签名与实际执行定义一致；旧版本保留 | 待验收 |
| E2E-03 自然语言 | 模型设置→生成规则→核对→确认保存→工作室→回测 | 未确认不注册；不支持规则不伪造执行结果 | 待验收 |
| E2E-04 Python | 编辑或上传→安全检查→确认警告→注册→参数回测→删除 | 阻断规则仍阻断；历史结果可读；错误行和加载失败可见 | 待验收 |
| E2E-05 优化 | 成功基准→候选网格→优化→DSR→子回测→审计→下载 | 基准和所有试验关联；缺证据清空DSR | 待验收 |
| E2E-06 样本外 | 基准→训练/测试窗口→选参→样本外结果→子报告→CSV | 严格先训练后测试；失败窗口和信任警告保留 | 待验收 |
| E2E-07 因子 | 库筛选/行选择→评估→组合训练验证→下载→回测 | 完整报告、共同样本、已验证spec；修改配置失效 | 待验收 |
| E2E-08 研究版本 | 保存→修改另存版本→2～4版比较→恢复→改JSON→检查→重跑 | 账号归属、revision、原费用风控、运行关联 | 待验收 |
| E2E-09 外部材料 | 粘贴/CSV→映射→股手和价格确认→错误/重复检查→核查→筛选→报告 | 原行号、证据不足、完整发现导出；旧报告指纹失效 | 待验收 |
| E2E-10 数据任务 | 启动回填→关页重开→进度→停止→续跑→版本/闭环 | 单活动任务、检查点、8种状态、脱敏日志 | 待验收 |
| E2E-11 AI | 先验知识/模型→选行情/新闻→缓存或完整分析→证据→模拟成交→多轮对话 | 缓存不编造过程；过程/结果/聊天属于同次研究 | 待验收 |
| E2E-12 账号 | 欢迎→注册→用户名/邮箱登录→工作台→个人中心→返回→退出 | 旧用户库兼容；方案归属；退出失效；占位仍明确 | 待验收（后期） |
| E2E-13 下载 | 所有CSV/JSON/Markdown出口→本地解析 | 全量行数、原字段、中文编码/证券名、筛选范围与文件名 | 待验收 |
| E2E-14 路由 | 5工作区、23工具、7旧入口、结果/审计/基准深链 | URL参数、返回来源页、刷新恢复及无效ID错误页 | 待验收 |

## 现有测试索引

仅列可复用候选测试，并未在本步骤运行或声称通过。旧界面源码断言需要为新实现调整，不能因旧测试文本匹配通过就视为新功能可用。

| 功能组 | 候选测试文件（tests/unit或tests/integration） |
| --- | --- |
| 全局导航与工作区 | `test_workspace_navigation.py`, `test_workspace_home.py` |
| 应用外壳 | `test_workspace_navigation.py`, `test_user_center.py` |
| 工作台首页 | `test_workspace_home.py` |
| 公开欢迎页与使用指南 | `test_guide_steps.py`, `test_user_center.py` |
| 策略工作室总入口 | `test_workspace_navigation.py` |
| 选股想法与运行前检查 | `test_guided_research.py` |
| 模板与可视化策略 | `test_strategy_studio_ui.py`, `test_strategy_studio_service.py`, `test_rule_schema.py` |
| 自然语言创建策略 | `test_nl_builder.py`, `test_strategy_studio_service.py` |
| Python自定义策略 | `test_user_strategies.py`, `test_strategy_safety.py` |
| 单次回测与结果 | `test_backtest_service.py`, `test_backtest_validity.py`, `test_backtest_diagnosis.py`, `test_workspace_navigation.py` |
| 参数优化与DSR | `test_optimization_service.py`, `test_multiple_testing.py`, `test_selection_bias_ui.py` |
| 滚动样本外验证 | `test_walk_forward_service.py`, `test_research_reliability.py` |
| 因子实验室 | `test_factor_lab_ui.py`, `test_factor_evaluation.py`, `test_factor_research_service.py`, `test_factor_combine.py` |
| 因子库浏览与跨区选择 | `test_factor_lab_ui.py`, `test_factor_taxonomy.py` |
| 先验知识库 | `test_prior_knowledge.py` |
| AI研究员与对话 | `test_agents_bridge.py`, `test_agent_sources.py`, `test_llm_settings.py` |
| 研究记录与回测对比 | `test_run_store.py`, `test_run_comparison.py`, `test_run_labels.py` |
| 研究方案版本与复用 | `test_guided_research.py` |
| 可信度审计 | `test_audit_report_page.py`, `test_credibility.py`, `test_selection_bias_ui.py` |
| 外部成交材料核查 | `test_forensics.py` |
| 数据与运行入口 | `test_workspace_navigation.py` |
| 日常行情与数据导出 | `test_data_center_service.py`, `test_data_source_fallback.py`, `test_web_exports.py`, `test_safe_data_errors.py` |
| 全市场回填与任务记录 | `test_data_jobs.py`, `test_full_market_backfill.py` |
| 全市场数据闭环状态 | `test_full_market_backfill.py` |
| 股票池维护 | `test_universe_service.py` |
| 风险规则与记录 | `test_daily_portfolio_risk.py`, `test_risk_engine.py` |
| 数据资产与来源对比 | `test_data_credentials.py` |
| XTick动态接口 | `test_security_names.py`, `test_web_exports.py` |
| 模型、数据源与系统设置 | `test_llm_settings.py`, `test_data_credentials.py` |
| 账号与登录（后期迁移） | `test_user_center.py` |
| 个人中心与占位功能 | `test_user_center.py` |

## 最终切换门槛

- 每个源码可达功能均有通过证据；登录可后迁移，但切换前不能漏掉。
- 禁用占位/休眠项逐项记录处理方式；不能无声删除，也不计为已经完成的业务能力。
- 旧行情、策略、账号、方案版本和研究结果在新系统可读取；核心计算及可信度语义完成对照。
- 新后台任务的重复提交、刷新恢复、异常退出和重试有验证；这是新增架构的验收，不能仅照抄Streamlit会话表现。
- 已登记的全部下载、动态接口元数据、深链接和关键错误状态通过。
- 保留基线备份及回退方式；未完成项不以“布局简化”替代验收。
