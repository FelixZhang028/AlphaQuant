# BaoStock 数据源

平台默认把 BaoStock 作为股票日线的首选免费数据源，iFinD 和 AkShare 依次作为回退来源。所需客户端版本为 `baostock>=0.9.3`。

## 已接入字段

BaoStock 原始日线使用不复权口径（`adjustflag=3`），同时获取前复权日线（`adjustflag=2`）。标准表保留：

- `pre_close`：原始前收盘价；
- `is_suspended`：由 `tradestatus` 严格映射；
- `is_st`：由历史日频 `isST` 严格映射；
- `adjusted_close` 和 `adj_factor`：由前复权与原始收盘价计算；
- `status_source`、`adjustment_source`、`price_limit_source`：字段级来源；
- `limit_rule_id`：涨跌停规则版本和分支。

`tradestatus` 或 `isST` 出现未定义值时不会默认成正常交易，而是写入 `UNKNOWN_STATUS`。

## 涨跌停价格

BaoStock 不直接提供标准化的每日涨跌停价。平台使用版本化规则 `cn_daily_limit_v1`，根据前收盘价、证券板块、交易日期和 ST 状态推导，并采用分为最小报价单位的四舍五入。

以下情况不会猜测涨跌停价：

- 缺少上市日期、前收盘价或 ST 状态；
- 上市后的特殊交易窗口；
- 日期或证券状态无法验证。

这些记录保持 `UNKNOWN_STATUS`，默认执行模型会拒绝订单。后续可使用 Tushare `stk_limit` 对规则结果做抽样或全量核验。

## 更新命令

```powershell
python scripts/backfill_data.py --start-date 20230103 --end-date 20241231
```

更新顺序由 `configs/data_sources.yaml` 控制。每次成功来源、失败尝试、参数和质量统计都会写入数据版本记录；BaoStock 原始响应会写入 `runtime/raw/baostock`，不会覆盖旧快照。
