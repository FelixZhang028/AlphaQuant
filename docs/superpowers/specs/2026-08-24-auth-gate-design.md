---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 58c6d64000c7fec1ca1a98ed34dbe688_f8c6f0ec9fbf11f1a413525400287e28
    ReservedCode1: iespsdl8QapgH2g6OyKt3pPpEnUHJgNpfJm5TzJC+3b0SetYeR97XC9oZg/SwXsXXnK7vaQZqjElmQlKCc+5ch4UDUb0x8dJSh4f0+PRP8s+kFHIxdI5qFfiAnHFs1sSymWTRTF+g2MnOt63klkWd2v6V1tgM25UpHJhFIcvyMc8nGrwxzGoR4YISjA=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 58c6d64000c7fec1ca1a98ed34dbe688_f8c6f0ec9fbf11f1a413525400287e28
    ReservedCode2: iespsdl8QapgH2g6OyKt3pPpEnUHJgNpfJm5TzJC+3b0SetYeR97XC9oZg/SwXsXXnK7vaQZqjElmQlKCc+5ch4UDUb0x8dJSh4f0+PRP8s+kFHIxdI5qFfiAnHFs1sSymWTRTF+g2MnOt63klkWd2v6V1tgM25UpHJhFIcvyMc8nGrwxzGoR4YISjA=
---

# FellowQuant 登录守卫设计文档

- 日期：2026-08-24
- 项目：FellowQuant_v2（quant-platform）
- 状态：已批准，进入实现

## 1. 目标

为 Streamlit 量化工作台增加前置登录守卫：未登录时只显示登录/注册/忘记密码页，登录成功后进入现有工作台。**登录功能必须可插拔**——通过配置一键开关，关闭后完全绕过登录、保持现有工作台行为不变。

## 2. 总体架构

登录页为**独立页面文件**（`auth_app.py`），由 `app.py` 的 `st.navigation` 注册为**默认入口**；登录成功后通过 `st.switch_page("welcome.py")` 跳转到工作台首页。`app.py` 本体不内嵌任何守卫逻辑。

```
app.py（入口：st.navigation 注册页面）
  ├─ "登录"  分组: auth_app.py（default=True）  ← 启动默认进入
  │     ├─ enabled=false → st.switch_page("welcome.py") 直接进入工作台
  │     └─ enabled=true  → 渲染 login.py（登录/注册/忘记密码）
  │            └─ 登录/注册成功 → st.switch_page("welcome.py") 进入工作台
  └─ 其余分组: welcome.py / home.py / pages/*（原工作台，零侵入）
```

> 说明：Streamlit 1.62 的 `st.switch_page` 仅支持跳转到主脚本或 `st.navigation` 注册的页面，因此登录页必须注册进导航而非作为独立 `streamlit run` 入口。

新增模块（`src/quant_platform/web/` 下）：

| 文件 | 职责 |
|---|---|
| `auth.py` | 配置读取、密码哈希（pbkdf2+盐）、SQLite 读写、会话校验 |
| `captcha.py` | Pillow 生成图片验证码（干扰线+噪点+字符，Base64 内嵌） |
| `login.py` | 登录/注册/忘记密码三合一扁平化页面 |
| `auth_app.py` | 独立登录页入口（st.navigation 注册的页面） |

## 3. 可插拔机制

优先级：环境变量 > `configs/app.yaml` > 默认值。

```yaml
# configs/app.yaml 新增段
auth:
  enabled: true          # false 时完全禁用登录，恢复原工作台
  db: runtime/auth.db    # SQLite 路径（相对项目根）
  captcha_length: 4      # 验证码位数
```

- `AUTH_ENABLED=0` 环境变量可临时强制关闭（部署时灵活切换）。
- 关闭时 `auth.py` 的守卫函数直接返回"已通过"，`app.py` 不做任何登录渲染。
- 登录相关模块仅在 `enabled=true` 时被 import/调用，不影响原有启动路径。

## 4. 数据模型（SQLite: `runtime/auth.db`）

```sql
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE,   -- 手机号或 email
    password_hash TEXT NOT NULL,         -- pbkdf2_hmac(sha256, 200k 迭代)
    salt         TEXT NOT NULL,          -- 16 字节随机盐（hex）
    created_at   TEXT NOT NULL,
    last_login_at TEXT
);
```

- username 格式：手机号（`1[3-9]\d{9}`）或 email（正则校验）。
- 密码 ≥ 8 位；只存哈希+盐，不存明文。

## 5. 页面与流程（login.py，扁平化风格）

沿用现有深色主题 tokens（背景 `#151517`、主色 `#5686fe`、文字 `#cfd3d6`），纯扁平化：无阴影渐变、无拟物，卡片+细边框+高对比按钮。

### 5.1 登录页
- 用户名输入框：placeholder「手机号 / Email」
- 密码输入框（type=password）
- 验证码行：图片 + 输入框 + 「换一张」按钮（点击刷新）
- 登录按钮；下方「注册账号」「忘记密码」文字链接
- 错误提示：统一「用户名或密码错误」（不暴露账号是否存在，防枚举）

### 5.2 注册页
- 用户名（格式校验：手机号/email）、密码（≥8 位）、确认密码、验证码
- 注册成功自动写库并建立登录态，直接进入工作台

### 5.3 忘记密码
- 本地单机无短信/邮件通道，流程：注册账号 + 验证码 + 新密码 + 确认新密码
- 校验账号存在后重置密码

### 5.4 验证码（captcha.py）
- 4 位随机字符（去 0O/1l 易混淆字符），Pillow 绘制：随机字体大小/旋转、干扰线、噪点、背景渐变
- Base64 内嵌 `<img>`，无临时文件
- 验证码存 `session_state`，大小写不敏感比对，登录/注册/重置失败或点击「换一张」即刷新

## 6. 会话

- 登录态：`session_state["auth_user"] = username`；附加 `auth_ts` 时间戳（会话内有效，重启即失效）
- `logout` 清空 `auth_user` 后 `st.rerun()`，回到登录页

## 7. 错误处理

| 场景 | 处理 |
|---|---|
| 账号不存在 / 密码错误 | 统一提示「用户名或密码错误」 |
| 验证码错误 | 「验证码不正确」+ 自动刷新验证码 |
| 用户名格式非法 | 注册时即时提示格式要求 |
| 注册账号已存在 | 提示「该账号已注册」 |
| SQLite 不可写 / 损坏 | 捕获异常，页面提示，不崩溃 |

## 8. 测试（tests/test_auth.py）

- 注册 → 登录成功
- 错误密码 → 拒绝
- 重复注册 → 拒绝
- 验证码比对：大小写不敏感、错误拒绝
- 密码哈希：非明文存储、同密码两次注册盐不同
- `AUTH_ENABLED=0` 时守卫直接放行

## 9. 依赖变更

- `pyproject.toml` 主依赖新增 `pillow`
*（内容由AI生成，仅供参考）*
