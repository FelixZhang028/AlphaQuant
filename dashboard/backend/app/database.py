"""
数据库初始化与连接（SQLite）。

表：
- users          官网注册用户（含 is_admin 标记、最后访问时间）
- backtests      每个用户的回测任务与结果
- chart_drawings 每个用户在每只股票 K 线上画的线
- ai_usage       每个用户每天调用平台 AI 的次数
- stock_briefs   AI 研究员的每次分析（当时的数据、AI 解读、追问）
- ai_reviews     每次回测的 AI 评估（风险等级、过度拟合的可能）
- ai_chats       AI 问答的对话（每一轮的问题、回答和用到的数据）
- admin_audit    管理员做过的操作（改设置、停用用户、启动数据任务……；不记录密钥本身）
- ai_tokens      每天调用文本模型用掉的 token（服务商返回了用量时）
- point_lots / point_ledger  积分：每一批（有效期）和每一次增加、扣除
- redeem_codes / redeem_uses 兑换码和谁用过

使用 Python 标准库 sqlite3，无需额外依赖。
数据库文件：backend/data/app.db
"""
import os
import sqlite3
from datetime import datetime, timezone

from .security import gen_salt, hash_password

_DB_DIR = os.path.abspath(os.getenv("FELLOWQUANT_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
os.makedirs(_DB_DIR, exist_ok=True)
DB_PATH = os.path.join(_DB_DIR, "app.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """建表与轻量迁移。可重复调用。"""
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT    NOT NULL,
                email         TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                salt          TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 1,
                is_admin      INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS backtests (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                strategy   TEXT    NOT NULL,
                market     TEXT    NOT NULL,
                from_date  TEXT    NOT NULL,
                to_date    TEXT    NOT NULL,
                status     TEXT    NOT NULL DEFAULT '完成',
                result     TEXT,           -- JSON 文本：资金曲线与指标
                created_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS strategy_packages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                package_id  TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                definition  TEXT    NOT NULL,          -- JSON：RuleStrategyDefinition
                top_n       INTEGER NOT NULL,
                rebalance   TEXT    NOT NULL,
                source      TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                UNIQUE(user_id, package_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS custom_factors (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                name         TEXT    NOT NULL,
                display_name TEXT    NOT NULL DEFAULT '',
                description  TEXT    NOT NULL DEFAULT '',
                field        TEXT    NOT NULL,
                operator     TEXT    NOT NULL,
                window       INTEGER NOT NULL,
                window2      INTEGER,
                direction    INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    NOT NULL,
                UNIQUE(user_id, name),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS risk_limits (
                user_id                  INTEGER PRIMARY KEY,
                enabled                  INTEGER NOT NULL DEFAULT 1,
                max_total_weight         REAL    NOT NULL DEFAULT 0.95,
                max_single_weight        REAL    NOT NULL DEFAULT 0.20,
                max_positions            INTEGER NOT NULL DEFAULT 20,
                minimum_cash_ratio       REAL    NOT NULL DEFAULT 0.05,
                max_drawdown             REAL    NOT NULL DEFAULT 0.25,
                daily_position_limits    INTEGER NOT NULL DEFAULT 1,
                drawdown_action          TEXT    NOT NULL DEFAULT 'reduce',
                drawdown_target_weight   REAL    NOT NULL DEFAULT 0.50,
                updated_at               TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS universe (
                user_id                 INTEGER PRIMARY KEY,
                symbols                 TEXT    NOT NULL DEFAULT '[]',   -- JSON 数组
                exclude_st              INTEGER NOT NULL DEFAULT 1,
                exclude_suspended       INTEGER NOT NULL DEFAULT 1,
                minimum_listing_days    INTEGER NOT NULL DEFAULT 60,
                minimum_history_days    INTEGER NOT NULL DEFAULT 120,
                minimum_average_amount  REAL    NOT NULL DEFAULT 0,
                updated_at              TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS paper_accounts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                account_id   TEXT    NOT NULL,
                display_name TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT '已创建',
                strategy     TEXT    NOT NULL,
                start_date   TEXT    NOT NULL,
                initial_cash REAL    NOT NULL,
                top_n        INTEGER NOT NULL,
                last_date    TEXT,
                created_at   TEXT    NOT NULL,
                UNIQUE(user_id, account_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS data_manifests (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                dataset      TEXT    NOT NULL,
                source       TEXT    NOT NULL,
                status       TEXT    NOT NULL,
                rows         INTEGER NOT NULL DEFAULT 0,
                message      TEXT    NOT NULL DEFAULT '',
                completed_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chart_drawings (
                user_id    INTEGER NOT NULL,
                symbol     TEXT    NOT NULL,                -- 6 位裸码
                drawings   TEXT    NOT NULL DEFAULT '[]',   -- JSON 数组
                updated_at TEXT    NOT NULL,
                PRIMARY KEY (user_id, symbol),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS ai_usage (
                user_id INTEGER NOT NULL,
                day     TEXT    NOT NULL,                -- 北京时间日期
                kind    TEXT    NOT NULL,                -- brief / question / strategy
                count   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day, kind),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS stock_briefs (
                id         TEXT    PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                symbol     TEXT    NOT NULL,
                name       TEXT    NOT NULL,
                trade_date TEXT    NOT NULL,
                model      TEXT    NOT NULL DEFAULT '',     -- 空表示没有 AI 解读，只有数据
                facts      TEXT    NOT NULL,                -- JSON：当时的数据
                brief      TEXT,                            -- JSON：AI 解读
                questions  TEXT    NOT NULL DEFAULT '[]',   -- JSON：追问与回答
                created_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_stock_briefs_user ON stock_briefs(user_id, created_at);
            CREATE TABLE IF NOT EXISTS ai_chats (
                id         TEXT    PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                title      TEXT    NOT NULL,                -- 第一个问题的开头
                turns      TEXT    NOT NULL DEFAULT '[]',   -- JSON：每一轮的问题、回答、用到的数据
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ai_chats_user ON ai_chats(user_id, updated_at);
            CREATE TABLE IF NOT EXISTS admin_audit (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id    INTEGER,
                admin_email TEXT    NOT NULL DEFAULT '',
                action      TEXT    NOT NULL,                -- settings.update / user.disable / data.start ...
                summary     TEXT    NOT NULL,                -- 给人看的一句话
                detail      TEXT    NOT NULL DEFAULT '{}',   -- JSON：改了哪些项、哪个用户……
                created_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_admin_audit_time ON admin_audit(created_at);
            CREATE TABLE IF NOT EXISTS ai_tokens (
                day        TEXT    PRIMARY KEY,               -- 北京时间日期
                calls      INTEGER NOT NULL DEFAULT 0,
                prompt     INTEGER NOT NULL DEFAULT 0,
                completion INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ai_reviews (
                user_id     INTEGER NOT NULL,
                backtest_id INTEGER NOT NULL,
                review      TEXT    NOT NULL,                -- JSON：用到的数据和 AI 的估计
                created_at  TEXT    NOT NULL,
                PRIMARY KEY (user_id, backtest_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            -- 邀请码用过几次（.env 里的和管理后台生成的都记在这里）
            CREATE TABLE IF NOT EXISTS invite_uses (
                code TEXT PRIMARY KEY,
                used INTEGER NOT NULL DEFAULT 0
            );
            -- 管理员在管理后台生成的邀请码；停用以后不能再注册，用过的次数保留
            CREATE TABLE IF NOT EXISTS invite_codes (
                code       TEXT    PRIMARY KEY,
                max_uses   INTEGER,                         -- 空表示不限次数
                active     INTEGER NOT NULL DEFAULT 1,
                note       TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL
            );
            -- 每个用户的研究默认值（回测初始资金、持仓、调仓、区间，AI 研究员是否参考研究经验），JSON
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id    INTEGER PRIMARY KEY,
                data       TEXT    NOT NULL,
                updated_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            -- 管理员在页面上改的平台设置，例如注册方式（registration = open / invite / closed）
            CREATE TABLE IF NOT EXISTS site_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            -- 全站每天用掉的 AI 次数（FELLOWQUANT_AI_DAILY_TOTAL）；不跟着用户删除，注销重注册不能重置
            CREATE TABLE IF NOT EXISTS ai_usage_total (
                day   TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0
            );
            -- 积分：每一笔进账是一批（注册赠送、管理员发放、兑换码……），各有有效期；用的时候先用快过期的
            CREATE TABLE IF NOT EXISTS point_lots (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                source     TEXT    NOT NULL,                -- signup / admin / redeem / purchase
                amount     INTEGER NOT NULL,
                remaining  INTEGER NOT NULL,
                expires_at TEXT    NOT NULL,                -- UTC
                created_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_point_lots_user ON point_lots(user_id, expires_at);
            -- 积分明细：每一次增加（正数）和扣除（负数）；调用失败退回时这一笔会删掉
            CREATE TABLE IF NOT EXISTS point_ledger (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                delta      INTEGER NOT NULL,
                kind       TEXT    NOT NULL,                -- signup / admin / redeem / purchase / spend
                feature    TEXT    NOT NULL DEFAULT '',     -- 用在哪个功能（brief / chat ……）
                note       TEXT    NOT NULL DEFAULT '',
                detail     TEXT    NOT NULL DEFAULT '{}',   -- JSON：扣的时候从哪几批里扣了多少
                created_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_point_ledger_user ON point_ledger(user_id, id);
            -- 兑换码：每个码多少积分、兑换后多少天有效、能给几个账户用、多久以内能兑换
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code       TEXT    PRIMARY KEY,
                points     INTEGER NOT NULL,
                valid_days INTEGER NOT NULL,
                max_uses   INTEGER,                         -- 空表示不限
                used       INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT,                            -- 空表示一直能兑换
                active     INTEGER NOT NULL DEFAULT 1,
                note       TEXT    NOT NULL DEFAULT '',
                created_at TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS redeem_uses (
                code    TEXT    NOT NULL,
                user_id INTEGER NOT NULL,
                used_at TEXT    NOT NULL,
                PRIMARY KEY (code, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        # 旧库迁移：补 is_admin 列（已存在则忽略）
        try:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "token_version" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")
        if "last_seen_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")

    # No public default credentials. Bootstrap only when explicitly configured.
    email = os.getenv("FELLOWQUANT_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("FELLOWQUANT_ADMIN_PASSWORD", "")
    if email and password:
        if len(password) < 12:
            raise ValueError("管理员初始密码至少需要 12 位")
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if not row:
                salt = gen_salt()
                conn.execute(
                    "INSERT INTO users (name, email, password_hash, salt, created_at, is_admin) VALUES (?,?,?,?,?,?)",
                    ("管理员", email, hash_password(password, salt), salt, _now(), 1),
                )


# 应用启动时确保表与种子存在
init_db()
