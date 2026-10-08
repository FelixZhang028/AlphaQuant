# AlphaQuant React

生产预览：项目根目录双击 `start_react.bat`，或运行：

```powershell
python -m quant_platform.api.cli --web
```

访问 `http://127.0.0.1:8000/app`。前后端同源，由 FastAPI 提供构建后的文件。
首次设置可双击根目录的 `install_react.bat`；它安装 API 依赖、执行 `npm ci` 并构建网页。

开发：先在项目根目录启动 API，再在此目录启动 Vite：

```powershell
python -m quant_platform.api.cli
```

```powershell
npm ci
npm run dev
```

开发地址为 `http://127.0.0.1:5173/app`，`/api` 代理至 8000 端口。

```powershell
npm run build
npm test
```

`npm test` 使用 Microsoft Edge 无头浏览器，在 8001 端口启动独立临时数据服务。
构建后再测试；不写入真实行情、账号或模型配置，不调用付费模型或真实行情网络。
本机任务和表单草稿保存在浏览器本地存储；API Key 字段只保存在当前页面内存。

当前为本机共享工作区，登录、旧账号私有方案归属和正式替换旧入口尚未迁移。
详细覆盖与验证记录见 `docs/migration/react-frontend.md`。
