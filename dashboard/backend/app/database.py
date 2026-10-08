"""
数据库初始化与连接（SQLite）。

表：
- users          官网注册用户（含 is_admin 标记）
- strategies     每个用户的策略
- backtests      每个用户的回测任务与结果

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
            CREATE TABLE IF NOT EXISTS strategies (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                name       TEXT    NOT NULL,
                type       TEXT    NOT NULL,
                market     TEXT    NOT NULL,
                status     TEXT    NOT NULL DEFAULT '已暂停',
                pnl        REAL    NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
            CREATE TABLE IF NOT EXISTS user_strategies (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                plugin_name  TEXT    NOT NULL,
                display_name TEXT    NOT NULL,
                description  TEXT    NOT NULL DEFAULT '',
                source       TEXT    NOT NULL DEFAULT 'editor',
                code         TEXT    NOT NULL,
                parameters   TEXT    NOT NULL DEFAULT '[]',   -- JSON 参数 schema
                created_at   TEXT    NOT NULL,
                updated_at   TEXT    NOT NULL,
                UNIQUE(user_id, plugin_name),
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
