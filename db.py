"""
数据库抽象层：统一 SQLite / PostgreSQL / MySQL 接口。

通过 MCMONITOR_DB_URL 环境变量切换：
- 不设置或 sqlite:///...  → SQLite
- postgresql://user:pass@host/db → PostgreSQL
- mysql://user:pass@host/db → MySQL

用法：
    from db import get_db, close_db, init_db, row_get

    db = get_db()
    rows = db.execute_fetch("SELECT * FROM users WHERE id = ?", (1,))
    db.execute("INSERT INTO ...", (...))
    db.commit()
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 类型检测
# ---------------------------------------------------------------------------


def _parse_db_url(url=None):
    url = url or os.environ.get("MCMONITOR_DB_URL", "")
    if not url:
        return "sqlite", os.environ.get("MCMONITOR_DATABASE", "")
    if url.startswith("sqlite:///"):
        return "sqlite", url[len("sqlite:///"):]
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgresql", url
    if url.startswith("mysql://"):
        return "mysql", url
    return "sqlite", url


_backend, _dsn = _parse_db_url()

_first_run_admin_info = None


def get_first_run_admin_info():
    """获取首次启动创建的 admin 账号信息，返回 None 表示不是首次启动"""
    if _first_run_admin_info:
        return _first_run_admin_info
    env_val = os.environ.get("_MCMONITOR_FIRST_RUN_ADMIN", "")
    if env_val:
        try:
            import json
            return json.loads(env_val)
        except Exception:
            pass
    return None


def _save_first_run_to_env(info):
    """将首次启动信息保存到环境变量，方便子进程读取"""
    try:
        import json
        os.environ["_MCMONITOR_FIRST_RUN_ADMIN"] = json.dumps(info)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 连接管理
# ---------------------------------------------------------------------------

_connections = threading.local()


def _create_connection():
    if _backend == "sqlite":
        path = _dsn
        if not path:
            try:
                import app as _app
                path = _app.app.config.get("DATABASE") or _app.DB_PATH
            except Exception:
                path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcmonitor.db")
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA wal_autocheckpoint = 1000")
        return conn

    if _backend == "postgresql":
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_dsn)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn

    if _backend == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=os.environ.get("MYSQL_HOST", "localhost"),
            port=int(os.environ.get("MYSQL_PORT", "3306")),
            user=os.environ.get("MYSQL_USER", "root"),
            password=os.environ.get("MYSQL_PASSWORD", ""),
            database=os.environ.get("MYSQL_DATABASE", "mcmonitor"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        return conn

    raise RuntimeError(f"Unsupported backend: {_backend}")


def get_db():
    conn = getattr(_connections, "conn", None)
    if conn is None:
        conn = _create_connection()
        _connections.conn = conn
    return DBWrapper(conn, _backend)


def close_db():
    conn = getattr(_connections, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _connections.conn = None


def row_get(row, key, default=None):
    if row is None:
        return default
    try:
        val = row[key]
        return val if val is not None else default
    except (KeyError, IndexError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 统一包装器
# ---------------------------------------------------------------------------

class _CursorWrapper:
    """包装 cursor，使 execute() 返回自身后可以链式调用 fetchone/fetchall"""
    def __init__(self, cursor):
        self._cursor = cursor
        self._closed = False

    def fetchone(self):
        if self._closed:
            return None
        row = self._cursor.fetchone()
        self._cursor.close()
        self._closed = True
        return row

    def fetchall(self):
        if self._closed:
            return []
        rows = self._cursor.fetchall()
        self._cursor.close()
        self._closed = True
        return rows


class DBWrapper:
    def __init__(self, conn, backend):
        self._conn = conn
        self._backend = backend

    def _convert_sql(self, sql):
        if self._backend == "sqlite":
            return sql
        if self._backend == "postgresql":
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            sql = sql.replace("?", "%s")
            sql = sql.replace("datetime('now')", "NOW()")
            sql = sql.replace("ON CONFLICT(key) DO UPDATE SET",
                              "ON CONFLICT(key) DO UPDATE SET")
            return sql
        if self._backend == "mysql":
            sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INT AUTO_INCREMENT PRIMARY KEY")
            sql = sql.replace("?", "%s")
            sql = sql.replace("datetime('now')", "NOW()")
            return sql
        return sql

    def execute(self, sql, params=None):
        sql = self._convert_sql(sql)
        cur = self._conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return _CursorWrapper(cur)

    def executescript(self, sql):
        if self._backend == "sqlite":
            self._conn.executescript(sql)
        else:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    self.execute(stmt)
        return self

    def fetchone(self, sql, params=None):
        sql = self._convert_sql(sql)
        cur = self._conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        row = cur.fetchone()
        cur.close()
        return row

    def fetchall(self, sql, params=None):
        sql = self._convert_sql(sql)
        cur = self._conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        rows = cur.fetchall()
        cur.close()
        return rows

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    @property
    def raw(self):
        return self._conn


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

def init_db(db_path=None):
    if _backend != "sqlite":
        return

    import app as _app
    path = db_path or _app.app.config.get("DATABASE") or _app.DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA wal_autocheckpoint = 1000")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_admin INTEGER NOT NULL DEFAULT 0,
        minekuai_api_key TEXT,
        email TEXT,
        email_alert_enabled INTEGER NOT NULL DEFAULT 0,
        email_cooldown INTEGER NOT NULL DEFAULT 30,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS servers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        group_id INTEGER,
        name TEXT NOT NULL,
        host TEXT NOT NULL,
        port INTEGER NOT NULL DEFAULT 25565,
        protocol TEXT NOT NULL DEFAULT 'java',
        is_public INTEGER NOT NULL DEFAULT 0,
        show_players INTEGER NOT NULL DEFAULT 1,
        minekuai_instance_id TEXT,
        refresh_interval INTEGER NOT NULL DEFAULT 60,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(group_id) REFERENCES server_groups(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS server_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_servers_group ON servers(user_id, group_id);
    CREATE TABLE IF NOT EXISTS status_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER NOT NULL,
        online INTEGER NOT NULL,
        players_online INTEGER,
        players_max INTEGER,
        version TEXT,
        motd TEXT,
        latency_ms INTEGER,
        error_msg TEXT,
        checked_at TEXT NOT NULL,
        FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_logs_server_time ON status_logs(server_id, checked_at DESC);
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        server_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        acknowledged INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_alerts_user_ack ON alerts(user_id, acknowledged, created_at DESC);
    """)

    now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    for col_sql in (
        "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'",
        "ALTER TABLE servers ADD COLUMN refresh_interval INTEGER NOT NULL DEFAULT 60",
        "ALTER TABLE status_logs ADD COLUMN error_msg TEXT",
    ):
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    default_settings = [
        ("registration_enabled", "1"),
        ("maintenance_enabled", "0"),
        ("cleanup_logs_days", "30"),
        ("cleanup_alerts_days", "7"),
        ("default_refresh_interval", "60"),
    ]
    for key, val in default_settings:
        existing = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, val, now),
            )

    global _first_run_admin_info

    _bs_pass = os.environ.get("MCMONITOR_BOOTSTRAP_PASSWORD", "").strip()

    # 检查是否已有超级管理员
    has_super_admin = False
    try:
        existing_sa = conn.execute("SELECT id FROM users WHERE role = 'super_admin'").fetchone()
        has_super_admin = existing_sa is not None
    except Exception:
        has_super_admin = False

    if not has_super_admin:
        # 没有超级管理员，必须创建一个
        import hashlib
        import secrets
        if _bs_pass and len(_bs_pass) >= 8:
            username = "admin"
            password = _bs_pass
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
            pw_hash = f"pbkdf2:sha256:200000${salt}${digest}"
            try:
                conn.execute(
                    "INSERT INTO users "
                    "(username, password_hash, role, is_admin, created_at) "
                    "VALUES (?, ?, 'super_admin', 1, ?)",
                    (username, pw_hash, now),
                )
                _first_run_admin_info = {
                    "username": username,
                    "password": password,
                    "type": "bootstrap",
                }
                _save_first_run_to_env(_first_run_admin_info)
                print(f"[MC-Monitor] 首次启动：已创建超级管理员用户名: {username}")
            except Exception as e:
                print(f"[MC-Monitor] 创建超级管理员失败: {e}")
        else:
            username = "admin"
            password = secrets.token_urlsafe(16)
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200000).hex()
            pw_hash = f"pbkdf2:sha256:200000${salt}${digest}"
            try:
                conn.execute(
                    "INSERT INTO users "
                    "(username, password_hash, role, is_admin, created_at) "
                    "VALUES (?, ?, 'super_admin', 1, ?)",
                    (username, pw_hash, now),
                )
                _first_run_admin_info = {
                    "username": username,
                    "password": password,
                    "type": "temporary",
                }
                _save_first_run_to_env(_first_run_admin_info)
                print("[MC-Monitor] 首次启动：已创建随机密码超级管理员")
                print(f"[MC-Monitor] 用户名: {username} 密码: {password} — 请登录后立即修改")
            except Exception as e:
                print(f"[MC-Monitor] 创建超级管理员失败: {e}")

    # 将旧 is_admin=1 的用户升级为 admin 角色
    try:
        conn.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1 AND role = 'user'")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# RBAC 角色定义
# ---------------------------------------------------------------------------

ROLES = {
    "super_admin": {
        "label": "超级管理员",
        "permissions": ["*"],
    },
    "admin": {
        "label": "管理员",
        "permissions": [
            "users.list", "users.create", "users.edit", "users.delete",
            "servers.list_all", "servers.edit_all", "servers.delete_all",
            "settings.read", "settings.write",
            "alerts.read", "alerts.ack",
        ],
    },
    "moderator": {
        "label": "协管员",
        "permissions": [
            "servers.list_all", "servers.edit_all",
            "alerts.read", "alerts.ack",
        ],
    },
    "user": {
        "label": "普通用户",
        "permissions": [
            "servers.own", "servers.own_create", "servers.own_edit", "servers.own_delete",
            "groups.own", "groups.own_create", "groups.own_edit", "groups.own_delete",
            "alerts.own_read", "alerts.own_ack",
        ],
    },
}

ROLE_HIERARCHY = ["super_admin", "admin", "moderator", "user"]


def has_permission(role, permission):
    if role == "super_admin":
        return True
    perms = ROLES.get(role, {}).get("permissions", [])
    if "*" in perms:
        return True
    return permission in perms


def check_permission(role, permission):
    if not has_permission(role, permission):
        from flask import abort
        abort(403)


def get_role_label(role):
    return ROLES.get(role, {}).get("label", role)


def get_role_level(role):
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return len(ROLE_HIERARCHY)


def can_manage_role(actor_role, target_role):
    return get_role_level(actor_role) < get_role_level(target_role)
