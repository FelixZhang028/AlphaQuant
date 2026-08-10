# 数据中心第一版

数据中心使用 iFinD、AkShare 和本地 Parquet。股票池日线优先从 iFinD 获取，
iFinD 不可用时自动回退 AkShare；证券主表与基准指数仍使用 AkShare。数据中心提供三个独立数据集：

- `security_master`：当前沪深京A股证券列表；
- `daily_bars`：配置股票池的未复权及前复权日线；
- `benchmark_bars`：应用配置中的基准指数日线。

每次更新都会在 `data_manifests` 中记录版本号、数据源、参数、日期范围、
行数、证券数量、质量摘要和异常信息。版本中的 `source` 是实际成功来源，
`provider_attempts` 记录自动回退过程。当前无法确认的历史 ST、停牌、
涨跌停状态继续标记为 `UNKNOWN_STATUS`，不能视为正常交易状态。

## 查看状态

```powershell
python -m quant_platform.data_cli --config configs/app.yaml status
```

## 更新数据

```powershell
python -m quant_platform.data_cli --config configs/app.yaml update `
  --start-date 20230101 --end-date 20241231
```

可以通过以下参数跳过某一类数据：

```text
--skip-security-master
--skip-market
--skip-benchmark
```

启动原有Streamlit应用后，侧边栏会自动出现数据管理页面：

```powershell
streamlit run src/quant_platform/web/app.py
```

默认行情更新只处理 `configs/universes/a_share_demo.yaml` 中的配置股票，
不会自动下载全市场数千只股票的全部历史行情。

数据管理页面允许为每次股票日线更新选择首选来源，并决定失败时是否自动回退。
用户选择、实际成功来源和调用路径都会写入数据版本记录；证券主表与基准指数目前仍使用
AkShare。

iFinD 的安装、账号环境变量和复权口径见 `docs/ifind_data_source.md`。
