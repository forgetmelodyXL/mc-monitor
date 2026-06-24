import os
import sys
import json
import socket
import struct
import sqlite3
import secrets
import hashlib
import time
import logging
import logging.handlers
import concurrent.futures
from datetime import datetime, timedelta
from functools import wraps

import db as db_module

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

_candidate_site_pkgs = []
try:
    import site as _site
    for _p in _site.getsitepackages():
        _candidate_site_pkgs.append(os.path.normpath(_p))
    try:
        for _p in _site.getusersitepackages():
            _candidate_site_pkgs.append(os.path.normpath(_p))
    except Exception:
        pass
except Exception:
    pass
_candidate_site_pkgs += [
    os.path.join(_this_dir, "runtime", "Lib", "site-packages"),
    os.path.join(_this_dir, "runtime", "site-packages"),
    os.path.join(_this_dir, "Lib", "site-packages"),
    os.path.join(_this_dir, "site-packages"),
]
for _p in _candidate_site_pkgs:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from flask import (
        Flask, render_template, request, redirect, url_for,
        session, flash, jsonify, g, abort, send_file
    )
except ImportError:
    print("=" * 60)
    print("  ERROR: Flask not found in this Python environment")
    print("  Python executable:", sys.executable)
    print("  Current dir     :", os.getcwd())
    print("  sys.path entries:")
    for _entry in sys.path:
        print("    -", _entry)
    print()
    print("  Fix: go to the project folder and double-click start.bat again.")
    print("  Or run:", sys.executable, "-m pip install flask")
    print("=" * 60)
    raise


def _get_resource_path():
    if getattr(sys, "frozen", False):
        return os.path.abspath(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return os.path.abspath(os.path.dirname(__file__))


def _get_data_dir():
    if getattr(sys, "frozen", False):
        return os.path.abspath(os.path.dirname(sys.executable))
    return os.path.abspath(os.path.dirname(__file__))


RESOURCE_DIR = _get_resource_path()
DATA_DIR = _get_data_dir()
DB_PATH = os.path.join(DATA_DIR, "mcmonitor.db")
TEMPLATE_DIR = os.path.join(RESOURCE_DIR, "templates")
STATIC_DIR = os.path.join(RESOURCE_DIR, "static")

# PyInstaller 打包检测：frozen 状态下强制生产环境，关闭 debug
if getattr(sys, "frozen", False):
    os.environ.setdefault("MCMONITOR_ENV", "production")
    os.environ["MCMONITOR_DEBUG"] = "0"

_ENV = os.environ.get("MCMONITOR_ENV", "development").lower()
IS_PRODUCTION = _ENV == "production"

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
)
_secret_key = os.environ.get("MCMONITOR_SECRET_KEY")
_secret_key = _secret_key or secrets.token_hex(32)

app.config["SECRET_KEY"] = _secret_key
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION
app.config["PREFERRED_URL_SCHEME"] = "https" if IS_PRODUCTION else "http"


def _setup_logging():
    log_level = os.environ.get("MCMONITOR_LOG_LEVEL", "INFO").upper()
    log_dir = os.environ.get("MCMONITOR_LOG_DIR", DATA_DIR)
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    access_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台（非生产环境）
    if not IS_PRODUCTION:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)

    # 应用日志（轮转，保留 10 个文件，每个 5MB）
    app_log = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "mcmonitor.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    app_log.setFormatter(fmt)
    root.addHandler(app_log)

    # 审计日志（独立文件，不轮转，由数据清理策略管理）
    audit_logger = logging.getLogger("audit")
    audit_logger.propagate = False
    audit_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "audit.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    audit_handler.setFormatter(access_fmt)
    audit_logger.addHandler(audit_handler)

    # 抑制 Flask/Werkzeug 的默认日志，避免重复
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers.clear()
    if IS_PRODUCTION:
        werkzeug_logger.setLevel(logging.WARNING)
    else:
        access_handler = logging.StreamHandler(sys.stdout)
        access_handler.setFormatter(access_fmt)
        werkzeug_logger.addHandler(access_handler)
        werkzeug_logger.setLevel(logging.INFO)

    logging.info("Logging initialized: env=%s level=%s", _ENV, log_level)


_setup_logging()


def _audit(action: str, detail: str = "", user_id=None, username=None):
    user_id = user_id or session.get("user_id")
    username = username or session.get("username", "anonymous")
    ip = _get_client_ip()
    logging.getLogger("audit").info(
        "user=%s(%s) ip=%s action=%s detail=%s",
        username, user_id or "-", ip, action, detail,
    )


# ============================================================
# 数据库（委托给 db 模块，支持 SQLite / PostgreSQL / MySQL）
# ============================================================
def get_db():
    return db_module.get_db()


@app.teardown_appcontext
def close_db(_exc):
    db_module.close_db()


def row_get(row, key, default=None):
    return db_module.row_get(row, key, default)


def _ensure_schema(db):
    """确保数据库包含所有新表和新列（用于兼容旧数据库）。

    在访问 server_groups/protocol/group_id/show_players/minekuai_* 等
    新 schema 前调用。所有 ALTER TABLE 都用 try/except 包裹，重复执行无害。
    """
    try:
        db.execute("SELECT 1 FROM server_groups LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS server_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        except Exception:
            pass
    for col_sql in (
        "ALTER TABLE servers ADD COLUMN group_id INTEGER",
        "ALTER TABLE servers ADD COLUMN protocol TEXT NOT NULL DEFAULT 'java'",
        "ALTER TABLE servers ADD COLUMN show_players INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE servers ADD COLUMN minekuai_instance_id TEXT",
        "ALTER TABLE servers ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN minekuai_api_key TEXT",
    ):
        try:
            db.execute(col_sql)
        except sqlite3.OperationalError:
            pass


# ============================================================
# 数据库迁移系统
# ============================================================
_SCHEMA_VERSION = 6  # 当前代码库对应的 schema 版本


def _get_schema_version(conn):
    """读取当前数据库的 schema 版本，不存在则返回 0"""
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'schema_version'").fetchone()
        return int(row["value"]) if row else 0
    except (sqlite3.OperationalError, ValueError, TypeError):
        return 0


def _set_schema_version(conn, version):
    """写入 schema 版本"""
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES ('schema_version', ?, ?)"
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(version), datetime.utcnow().isoformat(sep=" ", timespec="seconds")),
    )


def _run_migrations(conn):
    """
    按顺序执行未应用的数据库迁移，直到达到 _SCHEMA_VERSION。
    每个迁移是 (version, description, sql_statements_list) 格式。
    """
    current = _get_schema_version(conn)
    if current >= _SCHEMA_VERSION:
        return  # 已是最新的

    migrations = [
        # v1: 初始完整 schema（users, servers, status_logs, settings, alerts）
        (1, "init_schema", [
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                minekuai_api_key TEXT,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 25565,
                is_public INTEGER NOT NULL DEFAULT 0,
                show_players INTEGER NOT NULL DEFAULT 1,
                minekuai_instance_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS status_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                online INTEGER NOT NULL,
                players_online INTEGER,
                players_max INTEGER,
                version TEXT,
                motd TEXT,
                latency_ms INTEGER,
                checked_at TEXT NOT NULL,
                FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE
            )""",
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(server_id) REFERENCES servers(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
        ]),
        # v2: servers.is_public 列（历史遗留迁移）
        (2, "add_servers_is_public", [
            "ALTER TABLE servers ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0",
        ]),
        # v3: servers.show_players 列
        (3, "add_servers_show_players", [
            "ALTER TABLE servers ADD COLUMN show_players INTEGER NOT NULL DEFAULT 1",
        ]),
        # v4: users.is_admin, users.minekuai_api_key 列
        (4, "add_users_admin_and_minekuai", [
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN minekuai_api_key TEXT",
        ]),
        # v5: servers.group_id + server_groups 表 + servers.protocol
        (5, "add_server_groups_and_protocol", [
            """CREATE TABLE IF NOT EXISTS server_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_servers_group ON servers(user_id, group_id)",
            "ALTER TABLE servers ADD COLUMN group_id INTEGER",
            "ALTER TABLE servers ADD COLUMN protocol TEXT NOT NULL DEFAULT 'java'",
        ]),
        # v6: 邮件告警相关字段
        (6, "add_email_alerts", [
            "ALTER TABLE users ADD COLUMN email TEXT",
            "ALTER TABLE users ADD COLUMN email_alert_enabled INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN email_cooldown INTEGER NOT NULL DEFAULT 30",
        ]),
    ]

    for version, desc, statements in migrations:
        if version <= current:
            continue
        logging.info(f"[Migration] 应用 v{version}: {desc}")
        for stmt in statements:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                # 列/表已存在等错误不影响迁移继续
                logging.info(f"[Migration] v{version} SQL 跳过 (可能已存在): {e}")
        _set_schema_version(conn, version)
        conn.commit()
        logging.info(f"[Migration] v{version} 完成")


def init_db():
    """初始化数据库（委托给 db 模块）。"""
    path = None
    try:
        path = app.config.get("DATABASE") or DB_PATH
    except RuntimeError:
        path = DB_PATH
    db_module.init_db(path)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000
    ).hex()
    return f"pbkdf2:sha256:200000${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rest = stored.split("$", 1)
        salt, digest = rest.split("$", 1)
        iterations = int(algo.rsplit(":", 1)[1])
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations
        ).hex()
        return secrets.compare_digest(computed, digest)
    except Exception:
        return False


# ============================================================
# CSRF 保护
# ============================================================
CSRF_TOKEN_NAME = "_csrf_token"


def generate_csrf_token():
    """生成一个安全的 CSRF token 并存入 session"""
    token = secrets.token_hex(32)
    session[CSRF_TOKEN_NAME] = token
    return token


def validate_csrf_token():
    """验证请求中的 CSRF token，验证通过返回 True"""
    form_token = request.form.get(CSRF_TOKEN_NAME) or ""
    session_token = session.get(CSRF_TOKEN_NAME, "")
    header_token = request.headers.get("X-CSRF-Token", "")
    header_token = header_token or request.headers.get("X-CSRFToken", "")
    token = form_token if form_token else header_token
    if not token or not session_token:
        return False
    return secrets.compare_digest(token, session_token)


def csrf_protect(view):
    """装饰器：保护所有 POST/PUT/DELETE 请求免受 CSRF 攻击"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return view(*args, **kwargs)
        if not validate_csrf_token():
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# 预先为模板生成 token（登录页等无需登录的页面也可用）
@app.before_request
def ensure_csrf_token():
    # 为所有请求生成/更新 session 中的 CSRF token，供模板使用
    session.permanent = True
    if CSRF_TOKEN_NAME not in session:
        session[CSRF_TOKEN_NAME] = secrets.token_hex(32)

    # 非 GET 请求验证 CSRF
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not validate_csrf_token():
        abort(403)


# ============================================================
# 版本信息 & 模板上下文
# ============================================================
APP_VERSION = "1.3.0"


@app.context_processor
def inject_version():
    return {"app_version": APP_VERSION}


# ============================================================
# 错误页面 & Favicon
# ============================================================
@app.route("/favicon.ico")
def favicon():
    """返回站点 favicon（内联 SVG pickaxe 图标）"""
    import io
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#1a1d2e"/>'
        '<text x="32" y="46" font-size="36" text-anchor="middle" fill="#6c8dff">&#x26CF;</text>'
        '</svg>'
    ).encode("utf-8")
    return send_file(io.BytesIO(svg), mimetype="image/svg+xml")


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


@app.route("/health")
def health_check():
    """健康检查：返回 200 表示服务存活，返回 503 表示数据库不可用"""
    try:
        db = get_db()
        db.execute("SELECT 1")
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "db": str(e)}), 503


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def get_setting(key: str, default: str = "") -> str:
    """读取 settings 表中的开关值，不存在时返回默认值"""
    try:
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default
    except Exception:
        return default


def set_setting(key: str, value: str) -> None:
    """写入 settings 表中的开关值"""
    db = get_db()
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    db.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, now),
    )
    db.commit()


# ============================================================
# 邮件告警
# ============================================================

_EMAIL_COOLDOWN = {}


def send_email(to_email: str, subject: str, body: str) -> bool:
    """发送邮件，返回是否成功"""
    if get_setting("email_enabled", "0") != "1":
        return False

    smtp_host = get_setting("email_smtp_host", "")
    smtp_port = int(get_setting("email_smtp_port", "465"))
    smtp_ssl = get_setting("email_smtp_ssl", "1") == "1"
    smtp_user = get_setting("email_smtp_user", "")
    smtp_pass = get_setting("email_smtp_password", "")
    from_addr = get_setting("email_from", smtp_user)
    prefix = get_setting("email_subject_prefix", "[MC监控]")

    if not smtp_host or not smtp_user or not smtp_pass:
        return False

    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = Header(from_addr)
        msg["To"] = Header(to_email)
        msg["Subject"] = Header(f"{prefix} {subject}")

        if smtp_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()

        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        logging.info(f"[Email] 邮件发送成功: {to_email} - {subject}")
        return True
    except Exception as e:
        logging.warning(f"[Email] 发送失败 ({to_email}): {e}")
        return False


def _check_email_cooldown(user_id: int, server_id: int) -> bool:
    """检查是否在冷却期内，返回 True 表示在冷却中（不发送）"""
    key = (user_id, server_id)
    last = _EMAIL_COOLDOWN.get(key)
    if not last:
        return False
    db = get_db()
    user_row = db.execute(
        "SELECT email_cooldown FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    cooldown_min = int(row_get(user_row, "email_cooldown", 30))
    elapsed = (datetime.utcnow() - last).total_seconds() / 60
    return elapsed < cooldown_min


def _set_email_cooldown(user_id: int, server_id: int) -> None:
    """设置冷却时间"""
    _EMAIL_COOLDOWN[(user_id, server_id)] = datetime.utcnow()


def send_alert_email(user_id: int, server_id: int, server_name: str,
                    event_type: str, message: str) -> bool:
    """发送告警邮件（带冷却检查）"""
    db = get_db()
    user_row = db.execute(
        "SELECT email, email_alert_enabled FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    if not user_row:
        return False
    if row_get(user_row, "email_alert_enabled", 0) != 1:
        return False
    to_email = row_get(user_row, "email", "")
    if not to_email:
        return False
    if _check_email_cooldown(user_id, server_id):
        return False

    subject = "服务器掉线告警" if event_type == "offline" else "服务器恢复通知"
    body = (
        f"{message}\n"
        f"\n"
        f"服务器: {server_name}\n"
        f"时间: {datetime.utcnow().isoformat(sep=' ', timespec='seconds')} UTC\n"
        f"\n"
        f"-- MC 服务器监控\n"
    )
    ok = send_email(to_email, subject, body)
    if ok:
        _set_email_cooldown(user_id, server_id)
    return ok


def admin_required(view):
    """需要管理员及以上角色（admin / super_admin）"""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        role = session.get("role", "")
        if not db_module.has_permission(role, "settings.read"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def role_required(permission):
    """基于 RBAC 权限的装饰器"""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            role = session.get("role", "user")
            if not db_module.has_permission(role, permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/metrics")
@login_required
@admin_required
def metrics():
    """监控指标页：轮询成功率、延迟、失败统计"""
    db = get_db()
    total = db.fetchone("SELECT COUNT(*) as cnt FROM status_logs")
    total_checks = total["cnt"] if total else 0
    online = db.fetchone("SELECT COUNT(*) as cnt FROM status_logs WHERE online = 1")
    online_checks = online["cnt"] if online else 0
    success_rate = round(online_checks / total_checks * 100, 1) if total_checks > 0 else 0
    avg_lat = db.fetchone(
        "SELECT AVG(latency_ms) as avg_ms FROM status_logs WHERE online = 1 AND latency_ms IS NOT NULL"
    )
    avg_latency = round(avg_lat["avg_ms"], 1) if avg_lat and avg_lat["avg_ms"] else 0
    since = (datetime.utcnow() - timedelta(hours=24)).isoformat(sep=" ", timespec="seconds")
    fail_24h = db.fetchone(
        "SELECT COUNT(*) as cnt FROM status_logs WHERE online = 0 AND checked_at >= ?", (since,)
    )
    fail_count_24h = fail_24h["cnt"] if fail_24h else 0
    total_24h = db.fetchone(
        "SELECT COUNT(*) as cnt FROM status_logs WHERE checked_at >= ?", (since,)
    )
    check_count_24h = total_24h["cnt"] if total_24h else 0
    servers = db.fetchall(
        "SELECT s.id, s.name, s.host, s.port, s.protocol, s.user_id, u.username, "
        "(SELECT online FROM status_logs WHERE server_id = s.id ORDER BY checked_at DESC LIMIT 1) as online, "
        "(SELECT players_online FROM status_logs WHERE server_id = s.id ORDER BY checked_at DESC LIMIT 1) as players, "
        "(SELECT latency_ms FROM status_logs WHERE server_id = s.id ORDER BY checked_at DESC LIMIT 1) as latency, "
        "(SELECT checked_at FROM status_logs WHERE server_id = s.id ORDER BY checked_at DESC LIMIT 1) as last_check "
        "FROM servers s LEFT JOIN users u ON s.user_id = u.id ORDER BY s.name"
    )
    recent_fails = db.fetchall(
        "SELECT sl.server_id, s.name, sl.error_msg, sl.checked_at "
        "FROM status_logs sl JOIN servers s ON sl.server_id = s.id "
        "WHERE sl.online = 0 AND sl.error_msg IS NOT NULL "
        "ORDER BY sl.checked_at DESC LIMIT 20"
    )
    return render_template(
        "metrics.html",
        total_checks=total_checks, online_checks=online_checks,
        success_rate=success_rate, avg_latency=avg_latency,
        fail_count_24h=fail_count_24h, check_count_24h=check_count_24h,
        servers=servers, recent_fails=recent_fails, roles=db_module.ROLES,
        username=session.get("username", ""),
    )


# ============================================================
# Minecraft SLP (Server List Ping) 协议实现 - 纯 Python Socket
# 参考: https://wiki.vg/Server_List_Ping
# ============================================================
def _encode_varint(value: int) -> bytes:
    """Encode an integer as a Minecraft VarInt.

    Minecraft VarInts are at most 5 bytes (32 bits). Negative values must be
    masked to 32 bits (e.g. -1 => 0xFFFFFFFF) which yields exactly 5 bytes -
    this is the standard encoding used by the Minecraft protocol for
    signalling "any version" during server list ping.
    """
    data = bytearray()
    # Treat as unsigned 32-bit; values like -1 become 0xFFFFFFFF.
    unsigned = value & 0xFFFFFFFF
    written = 0
    while True:
        byte = unsigned & 0x7F
        unsigned >>= 7
        if unsigned:
            data.append(byte | 0x80)
        else:
            data.append(byte)
            break
        written += 1
        if written >= 5:  # MC spec: VarInt max 5 bytes
            data.append(byte & 0x7F)
            break
    return bytes(data)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from the socket, or raise."""
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError(
                f"Connection closed by remote (got {len(data)}/{n} bytes)"
            )
        data.extend(chunk)
    return bytes(data)


def _read_varint(sock: socket.socket, max_bytes: int = 5) -> int:
    result = 0
    shift = 0
    bytes_read = 0
    while bytes_read < max_bytes:
        byte = _recv_exact(sock, 1)
        b = byte[0]
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result
        shift += 7
        bytes_read += 1
    raise ValueError(f"VarInt too long (>{max_bytes} bytes) - invalid protocol data")


def _pack_packet(packet_id: int, payload: bytes) -> bytes:
    return _encode_varint(len(payload) + 1) + _encode_varint(packet_id) + payload


def _parse_description(desc) -> str:
    """Extract plain text from an MC description (str, dict with text/extra)."""
    if desc is None:
        return ""
    if isinstance(desc, str):
        return desc
    if isinstance(desc, dict):
        parts = []
        txt = desc.get("text")
        if txt:
            parts.append(str(txt))
        extra = desc.get("extra")
        if isinstance(extra, list):
            for seg in extra:
                if isinstance(seg, dict) and seg.get("text"):
                    parts.append(str(seg["text"]))
                elif isinstance(seg, str):
                    parts.append(seg)
        return "".join(parts)
    return str(desc)


def ping_mc_server(host: str, port: int, timeout: float = 5.0):
    """
    通过原生 TCP socket + Minecraft SLP 协议获取服务器状态，
    不调用任何第三方 API / Web 服务。每一步都有独立的超时保护。

    timeout: 连接 + 每次读取的单独超时（秒）。
    """
    host = host.strip()
    port = int(port)

    # ---- Phase 1: DNS + TCP connection (separate from protocol errors) ----
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except socket.gaierror as e:
        raise ConnectionError(f"DNS 解析失败: {e}") from e
    except socket.timeout as e:
        raise ConnectionError(
            f"连接 {host}:{port} 超时 ({timeout}s). 请检查 IP/端口是否正确。"
        ) from e
    except OSError as e:
        raise ConnectionError(
            f"无法连接到 {host}:{port} ({e}). 请确认 IP/端口正确，服务器在线，且网络可达。"
        ) from e

    try:
        sock.settimeout(timeout)

        # ---- Phase 2: Handshake (packet id = 0) ----
        # protocol_version = -1 表示 "任意版本"。
        # next_state = 1 表示状态查询。
        handshake = (
            _encode_varint(-1)
            + _encode_varint(len(host))
            + host.encode("utf-8")
            + struct.pack(">H", port)
            + _encode_varint(1)
        )
        sock.sendall(_pack_packet(0, handshake))
        sock.sendall(_pack_packet(0, b""))  # empty request packet

        # ---- Phase 3: Read response ----
        try:
            _length = _read_varint(sock)
            _packet_id = _read_varint(sock)
            json_length = _read_varint(sock)
        except socket.timeout as e:
            raise ConnectionError(
                "服务器接受了 TCP 连接但没有返回任何数据。它可能不是一个 Minecraft Java 版服务器，或被防火墙静默拦截。"
            ) from e
        except (ValueError, ConnectionError) as e:
            raise ConnectionError(
                f"协议解析失败 - 这可能不是一个标准的 Minecraft Java 服务器: {e}"
            ) from e

        if json_length <= 0:
            raise ConnectionError("服务器未返回有效 JSON 数据")
        if json_length > 2 * 1024 * 1024:  # 2 MB 上限，防御
            raise ConnectionError(f"响应过大 ({json_length} bytes), 拒绝解析")

        try:
            data = _recv_exact(sock, json_length)
        except socket.timeout as e:
            raise ConnectionError(
                f"读取 JSON 体超时 ({len(data) if 'data' in dir() else 0}/{json_length} bytes)"
            ) from e

        try:
            info = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ConnectionError(
                f"JSON 解析失败: {e}. 前 200 字节: {data[:200]!r}"
            ) from e

        # ---- Phase 4: Optional latency ping ----
        try:
            sock.sendall(_pack_packet(0, struct.pack(">Q", int(time.time() * 1000))))
            _len2 = _read_varint(sock)
            _pid2 = _read_varint(sock)
            _ = _recv_exact(sock, 8)
        except Exception:
            pass

        v = info.get("version") or {}
        version = v.get("name", "") if isinstance(v, dict) else str(v)

        p = info.get("players") or {}
        players_online = None
        players_max = None
        sample = None
        if isinstance(p, dict):
            players_online = p.get("online")
            players_max = p.get("max")
            sample = p.get("sample")

        motd = _parse_description(info.get("description"))

        # 安全转换
        try:
            players_online = int(players_online) if players_online is not None else 0
        except (ValueError, TypeError):
            players_online = 0
        try:
            players_max = int(players_max) if players_max is not None else 0
        except (ValueError, TypeError):
            players_max = 0

        return {
            "online": True,
            "version": str(version),
            "players_online": players_online,
            "players_max": players_max,
            "players_sample": sample,
            "motd": motd.strip(),
            "raw_json": info,
        }
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _ping_with_diagnostics(host: str, port: int, timeout_per_step: float = 5.0):
    """底层实现：带有分阶段诊断日志的 ping（不带总体超时，外层加）。"""
    diagnostics = []
    t0 = time.perf_counter()

    # Step 1: DNS
    try:
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout_per_step)
        try:
            addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            resolved_ip = addrs[0][4][0]
            diagnostics.append(f"[1] DNS 解析成功: {host} -> {resolved_ip}:{port}")
        finally:
            socket.setdefaulttimeout(old)
    except Exception as e:
        diagnostics.append(f"[1] DNS 解析失败: {e}")
        return {
            "online": False,
            "error": f"DNS 解析失败: {e}",
            "diagnostics": diagnostics,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }

    # Step 2: TCP connect
    try:
        sock = socket.create_connection((resolved_ip, port), timeout=timeout_per_step)
        diagnostics.append(f"[2] TCP 连接成功: {resolved_ip}:{port}")
    except socket.timeout as e:
        diagnostics.append(f"[2] TCP 连接超时 ({timeout_per_step}s): {e}")
        return {
            "online": False,
            "error": f"TCP 连接超时 ({timeout_per_step}s). 该端口可能被防火墙拦截，或服务器不在线。",
            "diagnostics": diagnostics,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }
    except Exception as e:
        diagnostics.append(f"[2] TCP 连接失败: {e}")
        return {
            "online": False,
            "error": f"TCP 连接失败: {e}",
            "diagnostics": diagnostics,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }

    try:
        sock.settimeout(timeout_per_step)

        # Step 3: handshake
        handshake = (
            _encode_varint(-1)
            + _encode_varint(len(host))
            + host.encode("utf-8")
            + struct.pack(">H", port)
            + _encode_varint(1)
        )
        sock.sendall(_pack_packet(0, handshake))
        sock.sendall(_pack_packet(0, b""))
        diagnostics.append("[3] 已发送 Handshake + Request 包")

        # Step 4: read response
        try:
            _length = _read_varint(sock)
            _packet_id = _read_varint(sock)
            json_length = _read_varint(sock)
            diagnostics.append(
                f"[4] 响应头: 总长度={_length}, packet_id={_packet_id}, JSON 长度={json_length}"
            )
        except socket.timeout as e:
            diagnostics.append(
                "[4] 读取响应超时: 服务器接受 TCP 连接但不返回 SLP 响应。"
                " 它可能不是 Minecraft Java 版服务器，也可能是 Bedrock 版。"
            )
            raise ConnectionError(
                "服务器接受了 TCP 连接但没有返回 SLP 响应。"
                " 它可能不是 Minecraft Java 版服务器（如是 Bedrock 版则需要不同协议）。"
            ) from e
        except (ValueError, ConnectionError) as e:
            diagnostics.append(f"[4] 协议解析失败: {e}")
            raise

        if json_length <= 0 or json_length > 2 * 1024 * 1024:
            raise ValueError(f"无效的 JSON 数据长度: {json_length}")

        try:
            raw_json_bytes = _recv_exact(sock, json_length)
            diagnostics.append(f"[5] 已读取 {len(raw_json_bytes)} 字节响应体")
        except socket.timeout as e:
            diagnostics.append(f"[5] 读取响应体超时: {e}")
            raise ConnectionError(f"读取响应体超时: {e}") from e

        try:
            info = json.loads(raw_json_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            diagnostics.append(f"[5] JSON 解码失败: {e}")
            raise ConnectionError(
                f"JSON 解码失败: {e}. 前 200 字节: {raw_json_bytes[:200]!r}"
            ) from e

        v = info.get("version") or {}
        version = v.get("name", "") if isinstance(v, dict) else str(v)
        p = info.get("players") or {}
        players_online = p.get("online") if isinstance(p, dict) else None
        players_max = p.get("max") if isinstance(p, dict) else None
        sample = p.get("sample") if isinstance(p, dict) else None
        motd = _parse_description(info.get("description"))

        diagnostics.append(f"[6] 解析成功: 版本={version}, 玩家={players_online}/{players_max}")

        return {
            "online": True,
            "version": version,
            "players_online": players_online,
            "players_max": players_max,
            "players_sample": sample,
            "motd": motd,
            "raw_json": info,
            "diagnostics": diagnostics,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }

    except Exception as e:
        return {
            "online": False,
            "error": str(e),
            "diagnostics": diagnostics + [f"[X] 最终错误: {type(e).__name__}: {e}"],
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }
    finally:
        try:
            sock.close()
        except Exception:
            pass


def ping_with_timeout(host: str, port: int, overall_timeout: float = 15.0, step_timeout: float = 5.0):
    """
    在独立线程中执行 ping，并设置硬性的全局超时（overall_timeout 秒）。
    即使 getaddrinfo / socket.recv 在某个环节完全卡死，也能保证返回。
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_ping_with_diagnostics, host, int(port), step_timeout)
        try:
            return future.result(timeout=overall_timeout)
        except concurrent.futures.TimeoutError:
            return {
                "online": False,
                "error": f"整体超时 ({overall_timeout}s). 服务器可能网络不通、响应极慢，或不接受来自本机的连接。",
                "diagnostics": [f"[超时] 等待 {overall_timeout} 秒仍未完成"],
                "elapsed_ms": int(overall_timeout * 1000),
            }
        except Exception as e:
            return {
                "online": False,
                "error": str(e),
                "diagnostics": [f"[内部错误] {type(e).__name__}: {e}"],
                "elapsed_ms": int(overall_timeout * 1000),
            }


def _ping_bedrock_with_diagnostics(host: str, port: int, timeout_per_step: float = 5.0):
    """底层 Bedrock ping，带诊断日志。"""
    diagnostics = []
    t0 = time.perf_counter()
    try:
        info = ping_bedrock_server(host, port, timeout=timeout_per_step)
        diagnostics.append(f"[Bedrock] 成功: 延迟={info.get('latency_ms')}ms")
        return {
            **info,
            "diagnostics": diagnostics,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }
    except Exception as e:
        return {
            "online": False,
            "error": str(e),
            "diagnostics": diagnostics + [f"[Bedrock] 错误: {type(e).__name__}: {e}"],
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        }


def ping_with_timeout_bedrock(host: str, port: int, overall_timeout: float = 15.0, step_timeout: float = 5.0):
    """Bedrock ping with overall timeout protection."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_ping_bedrock_with_diagnostics, host, int(port), step_timeout)
        try:
            return future.result(timeout=overall_timeout)
        except concurrent.futures.TimeoutError:
            return {
                "online": False,
                "error": f"整体超时 ({overall_timeout}s)",
                "diagnostics": [f"[超时] Bedrock ping 在 {overall_timeout}s 内未完成"],
                "elapsed_ms": int(overall_timeout * 1000),
            }
        except Exception as e:
            return {
                "online": False,
                "error": str(e),
                "diagnostics": [f"[内部错误] {type(e).__name__}: {e}"],
                "elapsed_ms": int(overall_timeout * 1000),
            }


def ping_with_latency(host: str, port: int, timeout: float = 5.0):
    """给 /api/status 用的简洁版（不带冗长诊断）。"""
    result = ping_with_timeout(host, port, overall_timeout=15.0, step_timeout=timeout)
    # 把字段映射到 api/status 需要的形式
    return {
        "online": result.get("online", False),
        "error": result.get("error") or ("" if result.get("online") else "未知错误"),
        "latency_ms": result.get("elapsed_ms", 0),
        "version": result.get("version") or "",
        "players_online": result.get("players_online"),
        "players_max": result.get("players_max"),
        "players_sample": result.get("players_sample"),
        "motd": result.get("motd") or "",
    }


def ping_server(host: str, port: int, protocol: str = "java", timeout: float = 5.0):
    """
    统一的服务器检测接口，根据 protocol 分派到对应协议检测函数。
    protocol: 'java' | 'bedrock' | 'http' | 'tcp'
    """
    if protocol == "bedrock":
        try:
            return ping_bedrock_server(host, port, timeout=timeout)
        except Exception as e:
            return {"online": False, "error": str(e), "latency_ms": 0,
                    "version": "", "players_online": None, "players_max": None,
                    "players_sample": None, "motd": "", "protocol": "bedrock"}
    elif protocol == "http":
        try:
            return ping_http_server(host, timeout=timeout)
        except Exception as e:
            return {"online": False, "error": str(e), "latency_ms": 0,
                    "version": "", "players_online": None, "players_max": None,
                    "players_sample": None, "motd": "", "protocol": "http"}
    elif protocol == "tcp":
        try:
            return ping_tcp_server(host, port, timeout=timeout)
        except Exception as e:
            return {"online": False, "error": str(e), "latency_ms": 0,
                    "version": "", "players_online": None, "players_max": None,
                    "players_sample": None, "motd": "", "protocol": "tcp"}
    else:
        # java (default)
        return ping_with_latency(host, port, timeout=timeout)


# ============================================================
# Bedrock (Minecraft PE / Nintendo Switch) 协议
# Raknet Ping 参考: https://wiki.vg/Raknet_Protocol
# ============================================================
def ping_bedrock_server(host: str, port: int, timeout: float = 5.0):
    """
    通过 Raknet 协议获取 Bedrock 服务器状态。
    timeout: 连接超时（秒）。
    """
    import struct

    host = host.strip()
    port = int(port)
    raknet_ping_id = b"\x01\x00"  # ID 0x01 = Unconnected Ping

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(raknet_ping_id + struct.pack(">Q", int(time.time() * 1000)), (host, port))
        sock.settimeout(timeout)
        data, _ = sock.recvfrom(65535)
        sock.close()
    except socket.timeout:
        raise ConnectionError(f"连接 {host}:{port} 超时 ({timeout}s)")
    except OSError as e:
        raise ConnectionError(f"无法连接到 {host}:{port}: {e}")

    if not data:
        raise ConnectionError("服务器未返回任何数据")

    # Raknet 响应格式：0x1c (Unconnected Pong) + 8字节 ping ID + 64字节 server ID + ...
    if data[0:1] != b"\x1c":
        raise ConnectionError(f"无效的 Raknet 响应 (首字节: {data[0]!r})")

    try:
        # 跳过 0x1c(1) + ping_id(8) + server_id(8) = 17 字节，之后是 motd 等
        # 安全读取
        body = data[17:]
        # 前 4 字节是大端序整数，表示字符串段数量
        if len(body) < 4:
            raise ConnectionError("Raknet 响应体太短")
        str_count = struct.unpack(">I", body[:4])[0]
        # 解析字符串列表: [edition, motd, protocol, version, online, max, nat?]
        offset = 4
        strings = []
        for _ in range(str_count):
            if offset + 2 > len(body):
                break
            str_len = struct.unpack(">H", body[offset:offset + 2])[0]
            offset += 2
            if offset + str_len > len(body):
                break
            s = body[offset:offset + str_len].decode("utf-8", errors="replace")
            strings.append(s)
            offset += str_len

        motd = strings[1] if len(strings) > 1 else ""
        protocol = strings[2] if len(strings) > 2 else ""
        version = strings[3] if len(strings) > 3 else ""
        players_online_str = strings[4] if len(strings) > 4 else "0"
        players_max_str = strings[5] if len(strings) > 5 else "0"

        try:
            players_online = int(players_online_str)
        except (ValueError, TypeError):
            players_online = 0
        try:
            players_max = int(players_max_str)
        except (ValueError, TypeError):
            players_max = 0

        return {
            "online": True,
            "version": f"Bedrock {version}",
            "players_online": players_online,
            "players_max": players_max,
            "players_sample": None,
            "motd": motd.strip(),
            "protocol": "bedrock",
        }
    except Exception as e:
        raise ConnectionError(f"Bedrock 数据解析失败: {e}")


# ============================================================
# HTTP(S) 健康检查
# ============================================================
def ping_http_server(url: str, timeout: float = 5.0):
    """
    对任意 URL 进行 HTTP HEAD/GET 健康检查。
    返回在线状态（2xx=在线）、响应时间。
    """
    _requests_mod = None
    try:
        import requests as _req
        _requests_mod = _req
    except ImportError:
        pass

    if not _requests_mod:
        raise ConnectionError("requests 模块未安装，无法进行 HTTP 健康检查")

    url = url.strip()
    if not url.startswith("http"):
        url = "http://" + url

    try:
        t0 = time.perf_counter()
        resp = _requests_mod.get(url, timeout=timeout, allow_redirects=True,
                                  headers={"User-Agent": "MC-Monitor/1.0"})
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        online = 200 <= resp.status_code < 400
        return {
            "online": online,
            "version": f"HTTP {resp.status_code}",
            "players_online": None,
            "players_max": None,
            "players_sample": None,
            "motd": f"{resp.status_code} {resp.reason}",
            "protocol": "http",
            "latency_ms": elapsed_ms,
        }
    except _requests_mod.Timeout:
        raise ConnectionError(f"HTTP 请求超时 ({timeout}s)")
    except Exception as e:
        raise ConnectionError(f"HTTP 检查失败: {e}")


# ============================================================
# 通用 TCP Ping（仅检测端口是否开放）
# ============================================================
def ping_tcp_server(host: str, port: int, timeout: float = 3.0):
    """
    通用 TCP 端口检测：仅检测端口是否开放，不解析任何协议。
    """
    host = host.strip()
    port = int(port)
    try:
        t0 = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "online": True,
            "version": f"TCP:{port}",
            "players_online": None,
            "players_max": None,
            "players_sample": None,
            "motd": f"端口 {port} 开放",
            "protocol": "tcp",
            "latency_ms": elapsed_ms,
        }
    except socket.timeout:
        raise ConnectionError(f"TCP 连接超时 ({timeout}s)")
    except OSError as e:
        raise ConnectionError(f"TCP 连接失败: {e}")


# ============================================================
# 视图
# ============================================================
@app.route("/")
def index():
    # 维护模式
    if get_setting("maintenance_enabled", "0") == "1":
        # 如果当前已登录管理员，允许访问主页；其他一律跳转到 /maintenance
        if not session.get("is_admin"):
            return redirect(url_for("maintenance"))
    db = get_db()
    servers = db.execute(
        "SELECT s.*, u.username AS owner_name "
        "FROM servers s JOIN users u ON s.user_id = u.id "
        "WHERE s.is_public = 1 ORDER BY s.id DESC"
    ).fetchall()
    return render_template("index.html", servers=servers,
                           logged_in=("user_id" in session),
                           current_username=session.get("username", ""))


@app.route("/register", methods=["GET", "POST"])
def register():
    # 维护模式：关闭注册
    if get_setting("maintenance_enabled", "0") == "1":
        return redirect(url_for("maintenance"))
    # 管理员关闭了注册
    if get_setting("registration_enabled", "1") != "1":
        if request.method == "GET":
            return render_template("register.html", registration_disabled=True)
        # POST: 直接返回提示
        return render_template("register.html", registration_disabled=True)

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        if len(username) < 3 or len(username) > 32:
            flash("用户名长度应在 3-32 个字符之间", "error")
        elif len(password) < 6:
            flash("密码至少需要 6 个字符", "error")
        elif password != confirm:
            flash("两次输入的密码不一致", "error")
        else:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing:
                flash("该用户名已被注册", "error")
            else:
                db.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, hash_password(password), datetime.utcnow().isoformat(sep=" ", timespec="seconds")),
                )
                db.commit()
                flash("注册成功，请登录", "success")
                _audit("register", f"new user: {username}", user_id=None, username=username)
                return redirect(url_for("login"))
    return render_template("register.html", registration_disabled=False)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # POST 请求应用登录速率限制
        allowed, remaining, retry = _check_rate_limit("login", _get_client_ip())
        if not allowed:
            flash(f"登录请求过于频繁，请 {retry} 秒后重试", "error")
            return render_template("login.html", username=(request.form.get("username") or ""))
    in_maintenance = get_setting("maintenance_enabled", "0") == "1"
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user and verify_password(password, user["password_hash"]):
            # 维护模式：仅允许管理员登录
            if in_maintenance and not (user["is_admin"] or 0):
                flash("系统维护中，仅管理员可登录", "error")
                return redirect(url_for("maintenance"))
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            session["role"] = row_get(user, "role", "admin" if user["is_admin"] else "user")
            session.permanent = True
            _audit("login", "success", user_id=user["id"], username=user["username"])
            next_url = request.args.get("next") or url_for("dashboard")
            try:
                from urllib.parse import urlparse
                parsed = urlparse(next_url)
                if parsed.scheme or parsed.netloc:
                    next_url = url_for("dashboard")
                elif not next_url.startswith("/"):
                    next_url = url_for("dashboard")
            except Exception:
                if not next_url.startswith("/"):
                    next_url = url_for("dashboard")
            return redirect(next_url)
        flash("用户名或密码错误", "error")
    return render_template("login.html", in_maintenance=in_maintenance)


@app.route("/maintenance")
def maintenance():
    return render_template("maintenance.html")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def user_profile():
    db = get_db()
    _ensure_schema(db)
    user = db.execute(
        "SELECT id, username, email, email_alert_enabled, email_cooldown, created_at FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    if not user:
        abort(404)
    error = None
    email_error = None
    username_error = None
    password_error = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "change_username":
            new_username = (request.form.get("new_username") or "").strip()
            if len(new_username) < 3 or len(new_username) > 32:
                username_error = "用户名长度必须在 3-32 个字符之间"
            else:
                existing = db.execute(
                    "SELECT id FROM users WHERE username = ? AND id != ?",
                    (new_username, session["user_id"]),
                ).fetchone()
                if existing:
                    username_error = "该用户名已被占用"
                else:
                    db.execute(
                        "UPDATE users SET username = ? WHERE id = ?",
                        (new_username, session["user_id"]),
                    )
                    db.commit()
                    session["username"] = new_username
                    flash("用户名已更新，请重新登录", "success")
                    _audit("profile_change_username", f"new_username={new_username}")
                    session.clear()
                    return redirect(url_for("login"))
        elif action == "change_password":
            current_password = request.form.get("current_password") or ""
            new_password = (request.form.get("new_password") or "").strip()
            confirm_password = request.form.get("confirm_password") or ""
            if len(new_password) < 8:
                password_error = "新密码长度至少 8 个字符"
            elif new_password != confirm_password:
                password_error = "两次输入的新密码不一致"
            else:
                user_full = db.execute(
                    "SELECT password_hash FROM users WHERE id = ?",
                    (session["user_id"],),
                ).fetchone()
                if not verify_password(current_password, user_full["password_hash"]):
                    password_error = "当前密码不正确"
                else:
                    db.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (hash_password(new_password), session["user_id"]),
                    )
                    db.commit()
                    flash("密码已更新，请重新登录", "success")
                    _audit("profile_change_password", "password changed")
                    session.clear()
                    return redirect(url_for("login"))
        elif action == "save_email":
            email = (request.form.get("email") or "").strip()
            email_enabled = 1 if request.form.get("email_alert_enabled") else 0
            try:
                cooldown = int(request.form.get("email_cooldown", "30"))
                cooldown = max(1, min(cooldown, 1440))
            except ValueError:
                cooldown = 30
            import re
            email_re = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
            if email and not re.match(email_re, email):
                email_error = "邮箱格式不正确"
            else:
                db.execute(
                    "UPDATE users SET email = ?, email_alert_enabled = ?, email_cooldown = ? WHERE id = ?",
                    (email or None, email_enabled, cooldown, session["user_id"]),
                )
                db.commit()
                _audit("profile_save_email", f"email={email}, enabled={email_enabled}")
                flash("邮件通知设置已保存", "success")
                return redirect(url_for("user_profile"))
    return render_template(
        "profile.html",
        user=user,
        error=error,
        email_error=email_error,
        username_error=username_error,
        password_error=password_error,
        username=session.get("username", ""),
    )


@app.route("/logout", methods=["GET", "POST"])
def logout():
    _audit("logout")
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# 管理后台
# ============================================================
@app.route("/admin")
@admin_required
def admin_panel():
    db = get_db()
    users_raw = db.execute(
        "SELECT id, username, is_admin, role, created_at, "
        "(SELECT COUNT(*) FROM servers s WHERE s.user_id = u.id) AS server_count "
        "FROM users u ORDER BY u.id ASC"
    ).fetchall()
    users = []
    for u in users_raw:
        user = dict(u)
        user["role_label"] = db_module.get_role_label(
            row_get(u, "role", "admin" if u["is_admin"] else "user")
        )
        users.append(user)
    server_rows = db.execute(
        "SELECT s.*, u.username AS owner_name "
        "FROM servers s JOIN users u ON s.user_id = u.id ORDER BY s.id DESC"
    ).fetchall()
    servers = [
        {
            "id": r["id"],
            "name": r["name"],
            "host": r["host"],
            "port": r["port"],
            "owner_name": r["owner_name"],
            "created_at": row_get(r, "created_at", ""),
            "is_public": bool(row_get(r, "is_public", 0)),
        }
        for r in server_rows
    ]
    total_users = len(users)
    total_servers = len(servers)
    total_public = sum(1 for s in servers if s["is_public"])
    # 当前开关状态
    reg_enabled = get_setting("registration_enabled", "1") == "1"
    maint_enabled = get_setting("maintenance_enabled", "0") == "1"
    cleanup_logs_days = get_setting("cleanup_logs_days", "30")
    cleanup_alerts_days = get_setting("cleanup_alerts_days", "7")
    # 统计当前数据量
    count_row = db.execute(
        """SELECT
           (SELECT COUNT(*) FROM status_logs) AS logs_count,
           (SELECT COUNT(*) FROM alerts) AS alerts_count
           """
    ).fetchone()
    status_logs_count = count_row["logs_count"] if count_row else 0
    alerts_count = count_row["alerts_count"] if count_row else 0
    # 邮件配置
    email_enabled = get_setting("email_enabled", "0") == "1"
    smtp_host = get_setting("email_smtp_host", "")
    smtp_port = get_setting("email_smtp_port", "465")
    smtp_ssl = get_setting("email_smtp_ssl", "1") == "1"
    smtp_user = get_setting("email_smtp_user", "")
    smtp_pass_set = bool(get_setting("email_smtp_password", ""))
    email_from = get_setting("email_from", "")
    subject_prefix = get_setting("email_subject_prefix", "[MC监控]")
    return render_template("admin.html",
                           users=users, servers=servers,
                           total_users=total_users,
                           total_servers=total_servers,
                           total_public=total_public,
                           registration_enabled=reg_enabled,
                           maintenance_enabled=maint_enabled,
                           cleanup_logs_days=cleanup_logs_days,
                           cleanup_alerts_days=cleanup_alerts_days,
                           status_logs_count=status_logs_count,
                           alerts_count=alerts_count,
                           email_enabled=email_enabled,
                           smtp_host=smtp_host,
                           smtp_port=smtp_port,
                           smtp_ssl=smtp_ssl,
                           smtp_user=smtp_user,
                           smtp_pass_set=smtp_pass_set,
                           email_from=email_from,
                           subject_prefix=subject_prefix,
                           current_username=session.get("username", ""))


@app.route("/admin/settings/register-toggle", methods=["POST"])
@admin_required
def admin_toggle_register():
    current = get_setting("registration_enabled", "1")
    new_val = "0" if current == "1" else "1"
    set_setting("registration_enabled", new_val)
    _audit("toggle_registration", f"set to {new_val}")
    flash("已%s注册功能" % ("开启" if new_val == "1" else "关闭"), "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings/maintenance-toggle", methods=["POST"])
@admin_required
def admin_toggle_maintenance():
    current = get_setting("maintenance_enabled", "0")
    new_val = "0" if current == "1" else "1"
    set_setting("maintenance_enabled", new_val)
    _audit("toggle_maintenance", f"set to {new_val}")
    flash("已%s维护模式" % ("开启" if new_val == "1" else "关闭"), "success")
    # 如果关闭维护模式，把普通用户踢出去
    if new_val == "0":
        # 只保留 admin 会话
        if session.get("is_admin"):
            pass  # 管理员不影响
    # 开启维护模式后，若当前会话不是管理员就自动踢出
    if new_val == "1" and not session.get("is_admin"):
        session.clear()
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings/cleanup-logs", methods=["POST"])
@admin_required
def admin_update_cleanup_logs():
    """更新状态历史保留天数"""
    days_str = (request.form.get("days") or "").strip()
    try:
        days = int(days_str)
        if days < 1 or days > 365:
            raise ValueError()
    except ValueError:
        flash("保留天数无效（请输入 1-365 之间的整数）", "error")
        return redirect(url_for("admin_panel"))
    set_setting("cleanup_logs_days", str(days))
    flash(f"状态历史保留天数已更新为 {days} 天", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings/cleanup-alerts", methods=["POST"])
@admin_required
def admin_update_cleanup_alerts():
    """更新告警历史保留天数"""
    days_str = (request.form.get("days") or "").strip()
    try:
        days = int(days_str)
        if days < 1 or days > 365:
            raise ValueError()
    except ValueError:
        flash("保留天数无效（请输入 1-365 之间的整数）", "error")
        return redirect(url_for("admin_panel"))
    set_setting("cleanup_alerts_days", str(days))
    flash(f"告警保留天数已更新为 {days} 天", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings/run-cleanup", methods=["POST"])
@admin_required
def admin_run_cleanup():
    """手动执行一次数据清理"""
    _cleanup_old_data()
    flash("已手动触发一次数据清理，详情请查看控制台日志", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings/email", methods=["GET", "POST"])
@admin_required
def admin_email_settings():
    """邮件告警配置页面"""
    db = get_db()

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "save":
            set_setting("email_enabled", "1" if request.form.get("email_enabled") else "0")
            set_setting("email_smtp_host", request.form.get("smtp_host", "").strip())
            set_setting("email_smtp_port", request.form.get("smtp_port", "465").strip() or "465")
            set_setting("email_smtp_ssl", "1" if request.form.get("smtp_ssl") else "0")
            set_setting("email_smtp_user", request.form.get("smtp_user", "").strip())
            new_pass = request.form.get("smtp_password", "").strip()
            if new_pass:
                set_setting("email_smtp_password", new_pass)
            set_setting("email_from", request.form.get("email_from", "").strip())
            set_setting("email_subject_prefix", request.form.get("subject_prefix", "[MC监控]").strip() or "[MC监控]")
            _audit("update_email_settings", "updated SMTP config")
            flash("邮件配置已保存", "success")
            return redirect(url_for("admin_email_settings"))

        elif action == "test":
            test_to = request.form.get("test_email", "").strip()
            if not test_to:
                flash("请输入测试收件邮箱", "error")
                return redirect(url_for("admin_email_settings"))
            ok = send_email(
                test_to,
                "测试邮件",
                "这是一封测试邮件，说明 SMTP 配置正确。\n\n-- MC 服务器监控"
            )
            if ok:
                flash("测试邮件发送成功，请查收", "success")
            else:
                flash("测试邮件发送失败，请检查配置和日志", "error")
            return redirect(url_for("admin_email_settings"))

    email_enabled = get_setting("email_enabled", "0") == "1"
    smtp_host = get_setting("email_smtp_host", "")
    smtp_port = get_setting("email_smtp_port", "465")
    smtp_ssl = get_setting("email_smtp_ssl", "1") == "1"
    smtp_user = get_setting("email_smtp_user", "")
    smtp_pass_set = bool(get_setting("email_smtp_password", ""))
    email_from = get_setting("email_from", "")
    subject_prefix = get_setting("email_subject_prefix", "[MC监控]")

    return render_template(
        "admin.html",
        email_settings=True,
        email_enabled=email_enabled,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_ssl=smtp_ssl,
        smtp_user=smtp_user,
        smtp_pass_set=smtp_pass_set,
        email_from=email_from,
        subject_prefix=subject_prefix,
        current_username=session.get("username", ""),
    )


@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(user_id):
    conn = get_db()
    user = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)

    admin_user_id = session["user_id"]
    if user_id == admin_user_id:
        flash("不能在管理后台重置自己的密码，请前往个人中心修改", "error")
        return redirect(url_for("admin_panel"))

    admin_user = db.execute("SELECT id, password_hash, role FROM users WHERE id = ?", (admin_user_id,)).fetchone()
    if not admin_user:
        abort(404)

    admin_current_password = request.form.get("admin_password", "").strip()
    if not admin_current_password:
        flash("请输入管理员当前密码", "error")
        return redirect(url_for("admin_panel"))

    if not verify_password(admin_current_password, admin_user["password_hash"]):
        flash("管理员密码错误", "error")
        return redirect(url_for("admin_panel"))

    actor_role = row_get(admin_user, "role", "user")
    target_role = row_get(user, "role", "user")
    if not db_module.can_manage_role(actor_role, target_role):
        flash("你不能重置级别不低于你的用户的密码", "error")
        return redirect(url_for("admin_panel"))

    if user["username"] == "admin" and not request.form.get("confirm_admin"):
        flash("请确认重置admin账号密码", "error")
        return redirect(url_for("admin_panel"))

    new_password = (request.form.get("new_password") or "").strip()
    if len(new_password) < 6:
        flash("新密码长度至少 6 个字符", "error")
        return redirect(url_for("admin_panel"))

    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (hash_password(new_password), user_id))
    db.commit()
    _audit("admin_reset_password", f"target user: {user['username']}")
    flash(f"已重置用户 {user['username']} 的密码", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def admin_toggle_admin(user_id):
    db = get_db()
    user = db.execute("SELECT id, username, is_admin, role FROM users WHERE id = ?",
                      (user_id,)).fetchone()
    if not user:
        abort(404)
    if user["username"] == "admin":
        flash("不能修改默认管理员 admin 的身份", "error")
        return redirect(url_for("admin_panel"))
    actor_role = session.get("role", "user")
    target_role = row_get(user, "role", "user")
    if not db_module.can_manage_role(actor_role, target_role):
        flash("你不能管理该用户的角色", "error")
        return redirect(url_for("admin_panel"))
    current_role = target_role
    new_role = "admin" if current_role not in ("admin", "super_admin") else "user"
    if new_role == "admin" and not db_module.can_manage_role(actor_role, new_role):
        flash("你不能将用户升级到超过你自身级别的角色", "error")
        return redirect(url_for("admin_panel"))
    new_is_admin = 1 if new_role in ("admin", "super_admin") else 0
    db.execute("UPDATE users SET is_admin = ?, role = ? WHERE id = ?", (new_is_admin, new_role, user_id))
    db.commit()
    _audit("admin_toggle_admin", f"target: {user['username']} -> {new_role}")
    flash(f"已将用户 {user['username']} 设为{db_module.get_role_label(new_role)}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/set-role", methods=["POST"])
@admin_required
def admin_set_role(user_id):
    """设置用户角色"""
    new_role = (request.form.get("role") or "").strip()
    if new_role not in db_module.ROLES:
        flash("无效的角色", "error")
        return redirect(url_for("admin_panel"))
    conn = get_db()
    user = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    if user["username"] == "admin" and new_role != "super_admin":
        flash("不能降级默认管理员 admin", "error")
        return redirect(url_for("admin_panel"))
    actor_role = session.get("role", "user")
    if new_role == "super_admin" and actor_role != "super_admin":
        flash("只有超级管理员才能设置超级管理员角色", "error")
        return redirect(url_for("admin_panel"))
    if not db_module.can_manage_role(actor_role, row_get(user, "role", "user")):
        flash("你不能管理该用户的角色", "error")
        return redirect(url_for("admin_panel"))
    is_admin = 1 if new_role in ("admin", "super_admin") else 0
    conn.execute("UPDATE users SET role = ?, is_admin = ? WHERE id = ?", (new_role, is_admin, user_id))
    conn.commit()
    _audit("admin_set_role", f"target: {user['username']} -> {new_role}")
    flash(f"已将用户 {user['username']} 设为{db_module.get_role_label(new_role)}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    user = db.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    if user["username"] == "admin":
        flash("不能删除默认管理员 admin", "error")
        return redirect(url_for("admin_panel"))
    if int(user_id) == int(session.get("user_id", 0)):
        flash("不能删除自己的账号", "error")
        return redirect(url_for("admin_panel"))
    actor_role = session.get("role", "user")
    target_role = row_get(user, "role", "user")
    if not db_module.can_manage_role(actor_role, target_role):
        flash("你不能删除级别不低于你的用户", "error")
        return redirect(url_for("admin_panel"))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    _audit("admin_delete_user", f"deleted user: {user['username']}")
    flash(f"已删除用户 {user['username']} 及其全部服务器", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/servers/<int:server_id>/toggle-public", methods=["POST"])
@admin_required
def admin_toggle_server_public(server_id):
    db = get_db()
    server = db.execute("SELECT id, name, is_public FROM servers WHERE id = ?",
                        (server_id,)).fetchone()
    if not server:
        abort(404)
    new_val = 0 if (server["is_public"] or 0) == 1 else 1
    db.execute("UPDATE servers SET is_public = ? WHERE id = ?", (new_val, server_id))
    db.commit()
    flash(f"服务器 {server['name']} 已设为{'公开' if new_val else '私有'}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/servers/<int:server_id>/delete", methods=["POST"])
@admin_required
def admin_delete_server(server_id):
    db = get_db()
    server = db.execute("SELECT id, name FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not server:
        abort(404)
    db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    db.commit()
    _audit("admin_delete_server", f"deleted server: {server['name']}")
    flash(f"已删除服务器 {server['name']}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/servers/<int:server_id>/edit", methods=["POST"])
@admin_required
def admin_edit_server(server_id):
    db = get_db()
    server = db.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not server:
        abort(404)
    name = (request.form.get("name") or "").strip()
    host = (request.form.get("host") or "").strip()
    port_str = (request.form.get("port") or "").strip()
    try:
        port = int(port_str)
        if port <= 0 or port > 65535:
            raise ValueError
    except ValueError:
        flash("端口必须是 1-65535 之间的整数", "error")
        return redirect(url_for("admin_panel"))
    if not name or not host:
        flash("名称和主机不能为空", "error")
        return redirect(url_for("admin_panel"))
    db.execute("UPDATE servers SET name = ?, host = ?, port = ? WHERE id = ?",
               (name[:64], host[:253], port, server_id))
    db.commit()
    _audit("admin_edit_server", f"edited server: {name}")
    flash(f"服务器 {name} 已更新", "success")
    return redirect(url_for("admin_panel"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    _ensure_schema(db)
    # 用 SELECT * 避免旧数据库缺列导致查询崩溃；ORDER BY 的新字段用 row_get 等效处
    server_rows = db.execute(
        "SELECT * FROM servers WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()

    # 统一转成 dict，对新字段（group_id/protocol/show_players/minekuai_instance_id/is_public）提供默认值
    def _server_dict(row):
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "name": row["name"],
            "host": row["host"],
            "port": row["port"],
            "group_id": row_get(row, "group_id"),
            "protocol": row_get(row, "protocol", "java"),
            "is_public": bool(row_get(row, "is_public", 0)),
            "show_players": bool(row_get(row, "show_players", 1)),
            "minekuai_instance_id": row_get(row, "minekuai_instance_id"),
            "sort_order": row_get(row, "sort_order", 0),
            "created_at": row_get(row, "created_at", ""),
        }

    # 按 group_id 和 sort_order 排序
    servers = sorted(
        (_server_dict(r) for r in server_rows),
        key=lambda s: (s["group_id"] is not None, s["group_id"] or 0, s["sort_order"] or 0, s["id"]),
    )

    # groups：旧数据库可能没有 server_groups 表，用 try/except 保护
    try:
        group_rows = db.execute(
            "SELECT * FROM server_groups WHERE user_id = ? ORDER BY sort_order ASC, id ASC",
            (session["user_id"],),
        ).fetchall()
        groups = [{"id": r["id"], "name": r["name"], "sort_order": r["sort_order"]} for r in group_rows]
    except sqlite3.OperationalError:
        groups = []
    return render_template("dashboard.html",
                           servers=servers,
                           groups=groups,
                           username=session.get("username", ""))


@app.route("/server/add", methods=["POST"])
@login_required
def server_add():
    # 速率限制（每个用户每分钟 5 次）
    if session.get("user_id"):
        allowed, remaining, retry = _check_rate_limit("server_add", f"u{session['user_id']}")
        if not allowed:
            flash(f"添加服务器过于频繁，请 {retry} 秒后重试", "error")
            return redirect(url_for("dashboard"))
    name = (request.form.get("name") or "").strip()
    host = (request.form.get("host") or "").strip()
    port_str = (request.form.get("port") or "").strip() or "25565"
    show_players = 1 if request.form.get("show_players") else 0
    group_id_str = (request.form.get("group_id") or "").strip()
    protocol = (request.form.get("protocol") or "java").strip().lower()
    if protocol not in ("java", "bedrock", "http", "tcp"):
        protocol = "java"
    try:
        port = int(port_str)
        if port < 1 or port > 65535:
            raise ValueError()
    except ValueError:
        flash("端口必须是 1-65535 的整数", "error")
        return redirect(url_for("dashboard"))

    if not name or not host:
        flash("请填写完整的服务器名称和地址", "error")
        return redirect(url_for("dashboard"))

    db = get_db()
    _ensure_schema(db)
    # 验证 group_id 归属当前用户
    group_id = None
    if group_id_str:
        try:
            gid = int(group_id_str)
            grp = db.execute(
                "SELECT id FROM server_groups WHERE id = ? AND user_id = ?",
                (gid, session["user_id"]),
            ).fetchone()
            if grp:
                group_id = gid
        except ValueError:
            pass

    try:
        db.execute(
            "INSERT INTO servers (user_id, group_id, name, host, port, protocol, is_public, show_players, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (
                session["user_id"],
                group_id,
                name[:64],
                host[:253],
                port,
                protocol,
                show_players,
                datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
            ),
        )
    except sqlite3.OperationalError:
        # 旧数据库无新字段时，降级为基础字段插入
        db.execute(
            "INSERT INTO servers (user_id, name, host, port, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                session["user_id"],
                name[:64],
                host[:253],
                port,
                datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
            ),
        )
    db.commit()
    _audit("server_add", f"added server: {name}")
    flash(f"已添加服务器：{name}", "success")
    return redirect(url_for("dashboard"))


@app.route("/server/<int:server_id>/delete", methods=["POST"])
@login_required
def server_delete(server_id):
    db = get_db()
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    db.commit()
    _audit("server_delete", f"deleted server: {server['name']}")
    flash("服务器已删除", "success")
    return redirect(url_for("dashboard"))


@app.route("/server/<int:server_id>/edit", methods=["POST"])
@login_required
def server_edit(server_id):
    db = get_db()
    _ensure_schema(db)
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    name = (request.form.get("name") or "").strip()
    host = (request.form.get("host") or "").strip()
    port_str = (request.form.get("port") or "").strip() or "25565"
    protocol = (request.form.get("protocol") or "java").strip().lower()
    if protocol not in ("java", "bedrock", "http", "tcp"):
        protocol = "java"
    try:
        port = int(port_str)
        if port < 1 or port > 65535:
            raise ValueError()
    except ValueError:
        flash("端口必须是 1-65535 的整数", "error")
        return redirect(url_for("dashboard"))
    if not name or not host:
        flash("请填写完整的服务器名称和地址", "error")
        return redirect(url_for("dashboard"))
    try:
        db.execute(
            "UPDATE servers SET name = ?, host = ?, port = ?, protocol = ? WHERE id = ?",
            (name[:64], host[:253], port, protocol, server_id),
        )
    except sqlite3.OperationalError:
        db.execute(
            "UPDATE servers SET name = ?, host = ?, port = ? WHERE id = ?",
            (name[:64], host[:253], port, server_id),
        )
    db.commit()
    _audit("server_edit", f"edited server: {server['name']} -> {name}")
    flash(f"服务器 {name} 已更新", "success")
    return redirect(url_for("dashboard"))


@app.route("/server/reorder", methods=["POST"])
@login_required
def server_reorder():
    """拖拽排序：接收 JSON {order: [id1, id2, ...]}"""
    db = get_db()
    _ensure_schema(db)
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "无效数据"}), 400
    order = data.get("order", [])
    if not isinstance(order, list):
        return jsonify({"error": "无效数据"}), 400
    for idx, sid in enumerate(order):
        row = db.execute(
            "SELECT id FROM servers WHERE id = ? AND user_id = ?",
            (sid, session["user_id"]),
        ).fetchone()
        if row:
            try:
                db.execute("UPDATE servers SET sort_order = ? WHERE id = ?", (idx, sid))
            except sqlite3.OperationalError:
                pass
    db.commit()
    return jsonify({"ok": True})


@app.route("/server/<int:server_id>/toggle-public", methods=["POST"])
@login_required
def server_toggle_public(server_id):
    db = get_db()
    _ensure_schema(db)
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    new_val = 0 if (row_get(server, "is_public") or 0) == 1 else 1
    try:
        db.execute(
            "UPDATE servers SET is_public = ? WHERE id = ?",
            (new_val, server_id),
        )
    except sqlite3.OperationalError:
        pass
    db.commit()
    label = "公开" if new_val == 1 else "私有"
    flash(f"服务器已设为{label}", "success")
    if request.is_json or (request.headers.get("Accept") or "").startswith("application/json"):
        return jsonify({"ok": True, "is_public": bool(new_val), "id": server_id})
    return redirect(url_for("dashboard"))


@app.route("/server/<int:server_id>/toggle-show-players", methods=["POST"])
@login_required
def server_toggle_show_players(server_id):
    db = get_db()
    _ensure_schema(db)
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    new_val = 0 if (row_get(server, "show_players", 1) or 0) == 1 else 1
    try:
        db.execute(
            "UPDATE servers SET show_players = ? WHERE id = ?",
            (new_val, server_id),
        )
    except sqlite3.OperationalError:
        pass
    db.commit()
    label = "显示玩家名" if new_val == 1 else "隐藏玩家名"
    flash(f"已{label}", "success")
    if request.is_json or (request.headers.get("Accept") or "").startswith("application/json"):
        return jsonify({"ok": True, "show_players": bool(new_val), "id": server_id})
    return redirect(url_for("dashboard"))


@app.route("/server/<int:server_id>/set-refresh-interval", methods=["POST"])
@login_required
def server_set_refresh_interval(server_id):
    """修改服务器刷新间隔（秒）"""
    interval_str = (request.form.get("refresh_interval") or "").strip()
    try:
        interval = int(interval_str)
    except ValueError:
        flash("刷新间隔无效", "error")
        return redirect(url_for("dashboard"))
    interval = max(10, min(3600, interval))
    db = get_db()
    _ensure_schema(db)
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    try:
        db.execute("UPDATE servers SET refresh_interval = ? WHERE id = ?", (interval, server_id))
    except sqlite3.OperationalError:
        pass
    db.commit()
    flash(f"刷新间隔已设为 {interval} 秒", "success")
    return redirect(url_for("dashboard"))


# ============================================================
# 服务器分组
# ============================================================
@app.route("/group/add", methods=["POST"])
@login_required
def group_add():
    """创建新分组"""
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("分组名称不能为空", "error")
        return redirect(url_for("dashboard"))
    if len(name) > 32:
        flash("分组名称不能超过 32 个字符", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    _ensure_schema(db)
    # 取最大 sort_order —— 如果旧数据库没有 server_groups 表，先创建
    max_order_row = db.execute(
        "SELECT MAX(sort_order) FROM server_groups WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()
    max_order = (max_order_row[0] if max_order_row and max_order_row[0] is not None else 0)
    db.execute(
        "INSERT INTO server_groups (user_id, name, sort_order, created_at) VALUES (?, ?, ?, ?)",
        (session["user_id"], name[:32], max_order + 1,
         datetime.utcnow().isoformat(sep=" ", timespec="seconds")),
    )
    db.commit()
    _audit("group_add", f"created group: {name}")
    flash(f"已创建分组：{name}", "success")
    return redirect(url_for("dashboard"))


@app.route("/group/<int:group_id>/rename", methods=["POST"])
@login_required
def group_rename(group_id):
    """重命名分组"""
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("分组名称不能为空", "error")
        return redirect(url_for("dashboard"))
    if len(name) > 32:
        flash("分组名称不能超过 32 个字符", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    _ensure_schema(db)
    grp = db.execute(
        "SELECT * FROM server_groups WHERE id = ? AND user_id = ?",
        (group_id, session["user_id"]),
    ).fetchone()
    if not grp:
        abort(404)
    db.execute(
        "UPDATE server_groups SET name = ? WHERE id = ?",
        (name[:32], group_id),
    )
    db.commit()
    _audit("group_rename", f"renamed group to: {name}")
    flash(f"分组已重命名为：{name}", "success")
    return redirect(url_for("dashboard"))


@app.route("/group/<int:group_id>/delete", methods=["POST"])
@login_required
def group_delete(group_id):
    """删除分组（组内服务器移至未分组）"""
    db = get_db()
    _ensure_schema(db)
    grp = db.execute(
        "SELECT * FROM server_groups WHERE id = ? AND user_id = ?",
        (group_id, session["user_id"]),
    ).fetchone()
    if not grp:
        abort(404)
    try:
        db.execute(
            "UPDATE servers SET group_id = NULL WHERE group_id = ?",
            (group_id,),
        )
    except sqlite3.OperationalError:
        pass
    db.execute("DELETE FROM server_groups WHERE id = ?", (group_id,))
    db.commit()
    _audit("group_delete", f"deleted group: {grp['name']}")
    flash(f"分组 {grp['name']} 已删除（服务器已移至未分组）", "success")
    return redirect(url_for("dashboard"))


@app.route("/group/<int:group_id>/set-order", methods=["POST"])
@login_required
def group_set_order(group_id):
    """更新分组顺序"""
    order_str = (request.form.get("sort_order") or "").strip()
    try:
        order = int(order_str)
    except ValueError:
        flash("顺序值无效", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    _ensure_schema(db)
    grp = db.execute(
        "SELECT * FROM server_groups WHERE id = ? AND user_id = ?",
        (group_id, session["user_id"]),
    ).fetchone()
    if not grp:
        abort(404)
    db.execute(
        "UPDATE server_groups SET sort_order = ? WHERE id = ?",
        (order, group_id),
    )
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/server/<int:server_id>/set-group", methods=["POST"])
@login_required
def server_set_group(server_id):
    """修改服务器所属分组"""
    group_id_str = (request.form.get("group_id") or "").strip()
    db = get_db()
    _ensure_schema(db)
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    group_id = None
    if group_id_str:
        try:
            gid = int(group_id_str)
            grp = db.execute(
                "SELECT id FROM server_groups WHERE id = ? AND user_id = ?",
                (gid, session["user_id"]),
            ).fetchone()
            if grp:
                group_id = gid
        except (ValueError, sqlite3.OperationalError):
            pass
    try:
        db.execute(
            "UPDATE servers SET group_id = ? WHERE id = ?",
            (group_id, server_id),
        )
    except sqlite3.OperationalError:
        pass
    db.commit()
    flash("服务器分组已更新", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/public_status")
def api_public_status():
    # 速率限制（每个 IP 每分钟 30 次）
    allowed, remaining, retry = _check_rate_limit("api_status")
    if not allowed:
        return jsonify({
            "error": "rate_limited",
            "message": f"请求过于频繁，请 {retry} 秒后重试"
        }), 429
    """只读公开接口：返回所有 is_public = 1 的服务器状态"""
    db = get_db()
    servers = db.execute(
        "SELECT s.*, u.username AS owner_name "
        "FROM servers s JOIN users u ON s.user_id = u.id "
        "WHERE s.is_public = 1 ORDER BY s.id DESC"
    ).fetchall()

    results = []
    total_players = 0
    total_online = 0
    for s in servers:
        protocol = row_get(s, "protocol", "java") or "java"
        info = ping_server(s["host"], s["port"], protocol=protocol, timeout=5.0)
        online = bool(info.get("online", False))
        show_players = bool(row_get(s, "show_players", 1))
        entry = {
            "id": s["id"],
            "name": s["name"],
            "host": s["host"],
            "port": s["port"],
            "online": online,
            "version": info.get("version") or "",
            "players_online": info.get("players_online"),
            "players_max": info.get("players_max"),
            "players_sample": (info.get("players_sample") if show_players else None),
            "show_players": show_players,
            "motd": info.get("motd") or "",
            "latency_ms": info.get("latency_ms"),
            "error": info.get("error") or "",
            "owner_name": row_get(s, "owner_name", "") or "",
            "checked_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }
        results.append(entry)
        if online:
            total_online += 1
            total_players += (entry["players_online"] or 0)
        try:
            db.execute(
                "INSERT INTO status_logs (server_id, online, players_online, players_max, version, motd, latency_ms, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    s["id"],
                    1 if online else 0,
                    entry["players_online"],
                    entry["players_max"],
                    entry["version"],
                    entry["motd"],
                    entry["latency_ms"],
                    entry["checked_at"],
                ),
            )
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        pass

    return jsonify({
        "servers": results,
        "total": len(results),
        "online": total_online,
        "offline": len(results) - total_online,
        "total_players": total_players,
        "updated_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
    })


@app.route("/api/status")
@login_required
def api_status():
    # 速率限制（每个用户每分钟 30 次）
    if session.get("user_id"):
        allowed, remaining, retry = _check_rate_limit("api_status", f"u{session['user_id']}")
        if not allowed:
            return jsonify({
                "error": "rate_limited",
                "message": f"请求过于频繁，请 {retry} 秒后重试"
            }), 429
    db = get_db()
    servers = db.execute(
        "SELECT s.*, g.name AS group_name "
        "FROM servers s "
        "LEFT JOIN server_groups g ON s.group_id = g.id "
        "WHERE s.user_id = ? ORDER BY s.id ASC",
        (session["user_id"],),
    ).fetchall()

    results = []
    for s in servers:
        protocol = row_get(s, "protocol", "java") or "java"
        info = ping_server(s["host"], s["port"], protocol=protocol, timeout=10.0)
        online = bool(info.get("online", False))
        show_players = bool(row_get(s, "show_players", 1))
        entry = {
            "id": s["id"],
            "name": s["name"],
            "host": s["host"],
            "port": s["port"],
            "protocol": protocol,
            "is_public": bool(row_get(s, "is_public", 0)),
            "show_players": show_players,
            "group_id": row_get(s, "group_id"),
            "group_name": row_get(s, "group_name"),
            "online": online,
            "version": info.get("version") or "",
            "players_online": info.get("players_online"),
            "players_max": info.get("players_max"),
            "players_sample": (info.get("players_sample") if show_players else None),
            "motd": info.get("motd") or "",
            "latency_ms": info.get("latency_ms"),
            "error": info.get("error") or "",
            "checked_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        }
        results.append(entry)
        try:
            db.execute(
                "INSERT INTO status_logs (server_id, online, players_online, players_max, version, motd, latency_ms, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    s["id"],
                    1 if online else 0,
                    entry["players_online"],
                    entry["players_max"],
                    entry["version"],
                    entry["motd"],
                    entry["latency_ms"],
                    entry["checked_at"],
                ),
            )
        except Exception:
            pass
    try:
        db.commit()
    except Exception:
        pass

    total_online = sum(1 for r in results if r["online"])
    total_players = sum(r["players_online"] or 0 for r in results)

    return jsonify({
        "servers": results,
        "total": len(results),
        "online": total_online,
        "offline": len(results) - total_online,
        "total_players": total_players,
    })


@app.route("/api/server/<int:server_id>/history")
@login_required
def api_history(server_id):
    db = get_db()
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    limit = min(int(request.args.get("limit", 30)), 200)
    rows = db.execute(
        "SELECT online, players_online, players_max, version, motd, latency_ms, checked_at "
        "FROM status_logs WHERE server_id = ? ORDER BY id DESC LIMIT ?",
        (server_id, limit),
    ).fetchall()
    return jsonify({
        "name": server["name"],
        "host": server["host"],
        "port": server["port"],
        "history": [dict(r) for r in rows],
    })


# ============================================================
# 麦块联机 (minekuai) API 接入
# 基础 URL: https://minekuai.com/api/client
# 每用户可绑定 API Key；每台服务器可绑定实例 ID
# ============================================================
MINEKUAI_BASE = "https://minekuai.com/api/client"

# 延迟加载 requests，避免强制依赖
_requests_module = None


def _get_requests():
    """返回 requests 模块；如未安装则返回 None 供调用方给出提示。"""
    global _requests_module
    if _requests_module is not None:
        return _requests_module
    try:
        import requests  # noqa: F401
        _requests_module = requests
        return _requests_module
    except ImportError:
        _requests_module = False
        return None


def _minekuai_headers(api_key: str) -> dict:
    return {
        "Authorization": "Bearer " + (api_key or "").strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _minekuai_proxy(method: str, path: str, api_key: str, json_body=None):
    """把请求代理到 minekuai，并返回 (status_code, body_or_error)。"""
    requests_mod = _get_requests()
    if not requests_mod:
        return 500, {
            "errors": [{
                "code": "MissingDependency",
                "status": "500",
                "detail": "服务器未安装 requests 模块，请先运行: pip install requests",
            }]
        }
    url = MINEKUAI_BASE + (path if path.startswith("/") else "/" + path)
    try:
        resp = requests_mod.request(
            method=method.upper(),
            url=url,
            headers=_minekuai_headers(api_key),
            json=json_body,
            timeout=15.0,
        )
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text}
        return resp.status_code, payload
    except Exception as e:
        return 502, {
            "errors": [{
                "code": "UpstreamError",
                "status": "502",
                "detail": "请求麦块联机 API 失败: " + str(e),
            }]
        }


def _require_api_key():
    """从当前会话用户的记录中读取 minekuai_api_key；如未绑定则返回 None 并附带错误信息。"""
    db = get_db()
    user = db.execute(
        "SELECT id, username, minekuai_api_key FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    if not user or not user["minekuai_api_key"]:
        return None, (400, {
            "errors": [{
                "code": "ApiKeyMissing",
                "status": "400",
                "detail": "您尚未绑定麦块联机的 API 密钥，请先在页面中绑定。",
            }]
        })
    return user["minekuai_api_key"], None


@app.route("/minekuai/bind-key", methods=["POST"])
@login_required
def minekuai_bind_key():
    """绑定/更新/清除当前用户的麦块联机 API Key。
    传空字符串或仅空白 = 清除绑定。
    """
    api_key = request.form.get("api_key") or (request.get_json() or {}).get("api_key") or ""
    api_key = (api_key or "").strip()
    db = get_db()
    # 归一化为：空则 NULL，否则保留
    db.execute(
        "UPDATE users SET minekuai_api_key = ? WHERE id = ?",
        (api_key or None, session["user_id"]),
    )
    db.commit()
    message = "已更新 API 密钥" if api_key else "已清除 API 密钥绑定"
    if request.is_json or (request.headers.get("Accept") or "").startswith("application/json"):
        return jsonify({"ok": True, "has_key": bool(api_key), "message": message})
    flash(message, "success")
    return redirect(url_for("dashboard"))


@app.route("/minekuai/me")
@login_required
def minekuai_me():
    """返回当前用户的 minekuai 绑定状态（不泄露 key，仅返回是否绑定）。"""
    db = get_db()
    user = db.execute(
        "SELECT id, username, minekuai_api_key FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    servers = db.execute(
        "SELECT * FROM servers WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    return jsonify({
        "user_id": user["id"],
        "username": user["username"],
        "has_minekuai_key": bool(row_get(user, "minekuai_api_key")),
        "servers": [
            {
                "id": s["id"],
                "name": s["name"],
                "host": s["host"],
                "port": s["port"],
                "minekuai_instance_id": row_get(s, "minekuai_instance_id"),
            }
            for s in servers
        ],
    })


@app.route("/server/<int:server_id>/bind-instance", methods=["POST"])
@login_required
def server_bind_minekuai_instance(server_id):
    """为某台服务器绑定/清除麦块实例 ID。"""
    db = get_db()
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    instance_id = request.form.get("instance_id") or (request.get_json() or {}).get("instance_id") or ""
    instance_id = (instance_id or "").strip()
    if instance_id and not _validate_instance_id(instance_id):
        error_msg = "无效的实例 ID，只允许字母、数字、下划线和连字符。"
        if request.is_json or (request.headers.get("Accept") or "").startswith("application/json"):
            return jsonify({"ok": False, "error": error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for("dashboard"))
    db.execute(
        "UPDATE servers SET minekuai_instance_id = ? WHERE id = ?",
        (instance_id or None, server_id),
    )
    db.commit()
    message = "已绑定实例 ID" if instance_id else "已解除实例 ID 绑定"
    if request.is_json or (request.headers.get("Accept") or "").startswith("application/json"):
        return jsonify({"ok": True, "minekuai_instance_id": instance_id or None, "message": message})
    flash(message, "success")
    return redirect(url_for("dashboard"))


@app.route("/api/minekuai/account")
@login_required
def api_minekuai_account():
    """获取当前用户在麦块的账户信息。"""
    api_key, err = _require_api_key()
    if err:
        status, body = err
        return jsonify(body), status
    status, body = _minekuai_proxy("GET", "/account", api_key)
    return jsonify(body), status


@app.route("/api/minekuai/servers")
@login_required
def api_minekuai_list_servers():
    """从麦块拉取当前用户的所有服务器实例列表。"""
    api_key, err = _require_api_key()
    if err:
        status, body = err
        return jsonify(body), status
    status, body = _minekuai_proxy("GET", "/", api_key)
    return jsonify(body), status


import re

_INSTANCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')

def _validate_instance_id(instance_id: str) -> bool:
    """校验 instance_id 是否合法，只允许字母、数字、下划线和连字符。"""
    if not isinstance(instance_id, str) or not instance_id:
        return False
    if '..' in instance_id or '../' in instance_id or '..\\' in instance_id:
        return False
    if '@' in instance_id or ':' in instance_id:
        return False
    return bool(_INSTANCE_ID_PATTERN.match(instance_id))


def _get_server_for_minekuai(server_id: int):
    """校验服务器归属，并返回 (server_row, api_key) 或报错返回 (None, (status, body))。"""
    db = get_db()
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        return None, (404, {
            "errors": [{"code": "NotFound", "status": "404", "detail": "未找到该服务器"}]
        })
    instance_id = row_get(server, "minekuai_instance_id", "")
    if not instance_id:
        return None, (400, {
            "errors": [{
                "code": "InstanceIdMissing",
                "status": "400",
                "detail": "该服务器尚未绑定麦块实例 ID，请先在页面中绑定。",
            }]
        })
    if not _validate_instance_id(instance_id):
        return None, (400, {
            "errors": [{
                "code": "InvalidInstanceId",
                "status": "400",
                "detail": "无效的实例 ID，只允许字母、数字、下划线和连字符。",
            }]
        })
    api_key, err = _require_api_key()
    if err:
        return None, err
    return server, api_key


@app.route("/api/minekuai/servers/<int:server_id>/power", methods=["POST"])
@login_required
def api_minekuai_server_power(server_id):
    """控制某台服务器的电源：signal in {start, stop, restart, kill}。"""
    server, api_key = (None, None)
    result = _get_server_for_minekuai(server_id)
    if result[0] is None:
        status, body = result[1]
        return jsonify(body), status
    server, api_key = result

    data = request.get_json(silent=True) or {}
    signal = (request.form.get("signal") or data.get("signal") or "").strip()
    if signal not in ("start", "stop", "restart", "kill"):
        return jsonify({
            "errors": [{
                "code": "InvalidSignal",
                "status": "400",
                "detail": "signal 必须为 start / stop / restart / kill 中的一个。",
            }]
        }), 400
    instance_id = row_get(server, "minekuai_instance_id", "")
    status, body = _minekuai_proxy(
        "POST", f"/servers/{instance_id}/power", api_key, json_body={"signal": signal}
    )
    return jsonify(body), status


@app.route("/api/minekuai/servers/<int:server_id>/command", methods=["POST"])
@login_required
def api_minekuai_server_command(server_id):
    """向某台服务器控制台发送命令。"""
    result = _get_server_for_minekuai(server_id)
    if result[0] is None:
        status, body = result[1]
        return jsonify(body), status
    server, api_key = result

    data = request.get_json(silent=True) or {}
    command = request.form.get("command") or data.get("command") or ""
    command = command.strip()
    if not command:
        return jsonify({
            "errors": [{
                "code": "EmptyCommand",
                "status": "400",
                "detail": "命令内容不能为空。",
            }]
        }), 400
    instance_id = row_get(server, "minekuai_instance_id", "")
    status, body = _minekuai_proxy(
        "POST", f"/servers/{instance_id}/command", api_key, json_body={"command": command}
    )
    return jsonify(body), status


@app.route("/api/minekuai/servers/<int:server_id>/resources")
@login_required
def api_minekuai_server_resources(server_id):
    """获取某台服务器的资源使用情况（CPU、内存、磁盘等）。"""
    result = _get_server_for_minekuai(server_id)
    if result[0] is None:
        status, body = result[1]
        return jsonify(body), status
    server, api_key = result

    instance_id = row_get(server, "minekuai_instance_id", "")
    status, body = _minekuai_proxy(
        "GET", f"/servers/{instance_id}/resources", api_key
    )
    return jsonify(body), status


@app.route("/api/minekuai/servers/<int:server_id>/details")
@login_required
def api_minekuai_server_details(server_id):
    """获取某台服务器的详细信息。"""
    result = _get_server_for_minekuai(server_id)
    if result[0] is None:
        status, body = result[1]
        return jsonify(body), status
    server, api_key = result

    instance_id = row_get(server, "minekuai_instance_id", "")
    status, body = _minekuai_proxy(
        "GET", f"/servers/{instance_id}", api_key
    )
    return jsonify(body), status


# ============================================================
# 后台定时采集任务
# ============================================================

# 全局字典：存储每个 server_id 最近一次在线状态
# {server_id: {"online": bool, "checked_at": str}}
_POLL_LAST_STATE = {}


# ============================================================
# 速率限制 (Rate Limiting)
# ============================================================
# 每个 (bucket_key, 类别) 存储一个简单的 token 桶
# {(key, bucket_name): {"tokens": int, "last_refill": float}}
_RATE_LIMIT_TOKENS = {}

# 配置：每个限制类别的速率（每分钟）
_RATE_LIMIT_CONFIG = {
    "login":         {"per_minute": 10, "max_burst": 10},   # 登录：每分钟 10 次
    "api_status":    {"per_minute": 30, "max_burst": 30},   # 状态查询：每分钟 30 次
    "api_alert":     {"per_minute": 60, "max_burst": 60},   # 告警 API：每分钟 60 次
    "server_add":    {"per_minute": 5,  "max_burst": 5},    # 添加服务器：每分钟 5 次
    "minekuai":      {"per_minute": 30, "max_burst": 30},   # 麦块联机 API：每分钟 30 次
}


def _get_client_ip():
    """获取客户端 IP，优先取 X-Forwarded-For 头"""
    try:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    except RuntimeError:
        pass
    try:
        return request.remote_addr or "unknown"
    except RuntimeError:
        return "unknown"


def _check_rate_limit(bucket_name, key=None):
    """
    检查当前请求是否超出速率限制
    返回: (is_allowed: bool, remaining_tokens: int, retry_after_seconds: int)
    """
    if key is None:
        key = _get_client_ip()

    full_key = (key, bucket_name)
    config = _RATE_LIMIT_CONFIG.get(bucket_name)
    if not config:
        return (True, -1, 0)

    now = time.time()
    tokens_per_sec = config["per_minute"] / 60.0

    entry = _RATE_LIMIT_TOKENS.get(full_key)
    if entry is None:
        # 新客户端：允许
        _RATE_LIMIT_TOKENS[full_key] = {
            "tokens": float(config["max_burst"]) - 1,
            "last_refill": now,
        }
        return (True, config["max_burst"] - 1, 0)

    # 计算自上次请求以来应该补充多少 token
    time_delta = now - entry["last_refill"]
    new_tokens = entry["tokens"] + time_delta * tokens_per_sec
    new_tokens = min(new_tokens, float(config["max_burst"]))

    if new_tokens >= 1.0:
        entry["tokens"] = new_tokens - 1.0
        entry["last_refill"] = now
        return (True, int(entry["tokens"]), 0)
    else:
        entry["tokens"] = new_tokens
        entry["last_refill"] = now
        # 需要多少秒后重试才能有 1 个 token
        retry_after = int((1.0 - new_tokens) / tokens_per_sec) + 1
        return (False, 0, retry_after)


def rate_limit(bucket_name, include_user=False):
    """装饰器：给路由加速率限制"""
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            key = _get_client_ip()
            if include_user and session.get("user_id"):
                key = f"{key}_u{session['user_id']}"
            allowed, remaining, retry = _check_rate_limit(bucket_name, key)
            if not allowed:
                response = {
                    "error": "rate_limited",
                    "message": f"请求过于频繁，请 {retry} 秒后重试",
                    "retry_after_seconds": retry,
                }
                return jsonify(response), 429
            return func(*args, **kwargs)
        return wrapped
    return decorator


def _check_apscheduler():
    """确保 APScheduler 已安装"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        return True
    except ImportError:
        print("⚠  缺少 APScheduler 模块，正在安装…")
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "APScheduler", "-q"])
        print("✅ APScheduler 安装完成。")
        return True


def _poll_all_servers():
    """
    后台任务：定期采集所有服务器的实时状态并写入 status_logs。
    每次采集会对所有服务器并发执行 ping，检测掉线/恢复时生成告警。
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return

    db = None
    try:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

        # 获取所有需要采集的服务器
        # 用 SELECT * 而非显式列，避免旧数据库缺列（protocol/group_id 等）导致查询崩溃
        servers = db.execute("SELECT * FROM servers").fetchall()

        if not servers:
            return

        def poll_one(server_row):
            """对单个服务器执行 ping，返回结果 dict（含 user_id/name 用于告警）"""
            try:
                protocol = row_get(server_row, "protocol", "java") or "java"
                info = ping_server(server_row["host"], server_row["port"], protocol=protocol, timeout=5.0)
                return {
                    "server_id": server_row["id"],
                    "user_id": server_row["user_id"],
                    "name": server_row["name"],
                    "online": 1 if info.get("online") else 0,
                    "players_online": info.get("players_online"),
                    "players_max": info.get("players_max"),
                    "version": info.get("version") or "",
                    "motd": info.get("motd") or "",
                    "latency_ms": info.get("latency_ms"),
                    "error": info.get("error") or "",
                    "protocol": protocol,
                }
            except Exception as e:
                return {
                    "server_id": server_row["id"],
                    "user_id": server_row["user_id"],
                    "name": server_row["name"],
                    "online": 0,
                    "players_online": None,
                    "players_max": None,
                    "version": "",
                    "motd": "",
                    "latency_ms": None,
                    "error": str(e),
                    "protocol": "java",
                }

        # 并发 ping 所有服务器
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(poll_one, s): s for s in servers}
            for future in concurrent.futures.as_completed(futures, timeout=15):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception:
                    pass

        # 批量写入数据库，同时检测状态变化生成告警
        now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        alerts_to_insert = []

        for r in results:
            db.execute(
                """INSERT INTO status_logs
                   (server_id, online, players_online, players_max, version, motd, latency_ms, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    r["server_id"],
                    r["online"],
                    r["players_online"],
                    r["players_max"],
                    r["version"],
                    r["motd"],
                    r["latency_ms"],
                    now,
                ),
            )

            # 检测状态变化：与上一次记录对比
            last = _POLL_LAST_STATE.get(r["server_id"])
            prev_online = last["online"] if last else None

            if prev_online is not None and prev_online != r["online"]:
                # 状态切换：离线->在线 或 在线->离线
                if r["online"]:
                    event_type = "online"
                    msg = f"✅ 服务器 \"{r['name']}\" 已恢复在线"
                else:
                    event_type = "offline"
                    msg = f"🚨 服务器 \"{r['name']}\" 已掉线"
                alerts_to_insert.append((
                    r["server_id"], r["user_id"], event_type, msg, now
                ))

            # 更新内存中的最近状态
            _POLL_LAST_STATE[r["server_id"]] = {
                "online": bool(r["online"]),
                "checked_at": now,
            }

        # 批量插入告警，同时触发邮件推送
        email_count = 0
        for alert in alerts_to_insert:
            server_id, user_id, event_type, msg, _ = alert
            db.execute(
                """INSERT INTO alerts (server_id, user_id, event_type, message, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                alert,
            )
            if send_alert_email(user_id, server_id,
                              next((r["name"] for r in results if r["server_id"] == server_id), ""),
                              event_type, msg):
                email_count += 1
        if alerts_to_insert:
            logging.info(f"[Scheduler] 生成 {len(alerts_to_insert)} 条告警，发送 {email_count} 封邮件")

        db.commit()
        logging.info(f"[Scheduler] 已采集 {len(results)} 台服务器状态")
    except Exception as e:
        logging.warning(f"[Scheduler] 采集失败: {e}")
    finally:
        if db:
            db.close()


def _cleanup_old_data():
    """
    定期清理过期数据：
    - status_logs: 超过 logs_retention_days 天的记录（默认 30 天）
    - alerts:     超过 alerts_retention_days 天的已读记录（默认 7 天），未读最多保留 30 天
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return

    db = None
    try:
        db = sqlite3.connect(DB_PATH)

        # 读取配置
        logs_days = 30
        alerts_days = 7
        try:
            row = db.execute(
                "SELECT key, value FROM settings WHERE key IN ('cleanup_logs_days', 'cleanup_alerts_days')"
            ).fetchall()
            for r in row:
                if r["key"] == "cleanup_logs_days":
                    try:
                        logs_days = max(1, int(r["value"]))
                    except (ValueError, TypeError):
                        logs_days = 30
                elif r["key"] == "cleanup_alerts_days":
                    try:
                        alerts_days = max(1, int(r["value"]))
                    except (ValueError, TypeError):
                        alerts_days = 7
        except Exception:
            pass

        # 由于 SQLite 日期格式不一致，先用简单方式：根据 ID 范围估算
        # 更精确的方式：用 checked_at/created_at 字段比较
        now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")

        logs_cutoff = (datetime.utcnow() - timedelta(days=logs_days)).isoformat(sep=" ", timespec="seconds")
        alerts_cutoff = (datetime.utcnow() - timedelta(days=alerts_days)).isoformat(sep=" ", timespec="seconds")
        # 未读告警最多 30 天
        unread_cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat(sep=" ", timespec="seconds")

        # 删除过期日志
        log_cursor = db.execute(
            "SELECT COUNT(*) AS cnt FROM status_logs WHERE checked_at < ?",
            (logs_cutoff,)
        ).fetchone()
        logs_deleted = log_cursor["cnt"] if log_cursor else 0
        if logs_deleted > 0:
            db.execute(
                "DELETE FROM status_logs WHERE checked_at < ?",
                (logs_cutoff,)
            )

        # 删除过期告警（已读超 alerts_days 天，或不管是否已读超 30 天）
        alert_cursor = db.execute(
            """SELECT COUNT(*) AS cnt FROM alerts
               WHERE (acknowledged = 1 AND created_at < ?)
                  OR (created_at < ?)""",
            (alerts_cutoff, unread_cutoff)
        ).fetchone()
        alerts_deleted = alert_cursor["cnt"] if alert_cursor else 0
        if alerts_deleted > 0:
            db.execute(
                """DELETE FROM alerts
                   WHERE (acknowledged = 1 AND created_at < ?)
                      OR (created_at < ?)""",
                (alerts_cutoff, unread_cutoff)
            )

        db.commit()
        if logs_deleted > 0 or alerts_deleted > 0:
            logging.info(
                f"[Cleanup] 已删除 {logs_deleted} 条状态历史 (>{logs_days}天), "
                f"{alerts_deleted} 条告警 (已读>{alerts_days}天/ 任意>30天)"
            )
    except Exception as e:
        logging.warning(f"[Cleanup] 清理失败: {e}")
    finally:
        if db:
            db.close()


# ============================================================
# 告警 API
# ============================================================
@app.route("/api/alerts")
@login_required
def api_alerts():
    """获取当前用户的未读告警列表（速率限制：每个用户每分钟 60 次）"""
    if session.get("user_id"):
        allowed, remaining, retry = _check_rate_limit("api_alert", f"u{session['user_id']}")
        if not allowed:
            return jsonify({
                "error": "rate_limited",
                "message": f"请求过于频繁，请 {retry} 秒后重试"
            }), 429
    db = get_db()
    alerts = db.execute(
        """SELECT a.*, s.name AS server_name, s.host, s.port
           FROM alerts a
           JOIN servers s ON a.server_id = s.id
           WHERE a.user_id = ? AND a.acknowledged = 0
           ORDER BY a.created_at DESC
           LIMIT 50""",
        (session["user_id"],)
    ).fetchall()
    return jsonify({"alerts": [dict(a) for a in alerts]})


@app.route("/api/alerts/acknowledge", methods=["POST"])
@login_required
def api_alerts_acknowledge():
    """确认（标记为已读）全部或指定告警"""
    if session.get("user_id"):
        allowed, remaining, retry = _check_rate_limit("api_alert", f"u{session['user_id']}")
        if not allowed:
            return jsonify({
                "error": "rate_limited",
                "message": f"请求过于频繁，请 {retry} 秒后重试"
            }), 429
    data = request.get_json(silent=True) or {}
    alert_ids = data.get("alert_ids")
    db = get_db()
    if alert_ids:
        placeholders = ",".join(["?"] * len(alert_ids))
        db.execute(
            f"""UPDATE alerts SET acknowledged = 1
                WHERE id IN ({placeholders}) AND user_id = ?""",
            alert_ids + [session["user_id"]]
        )
    else:
        db.execute(
            "UPDATE alerts SET acknowledged = 1 WHERE user_id = ?",
            (session["user_id"],)
        )
    db.commit()
    return jsonify({"success": True})


@app.route("/api/alerts/count")
@login_required
def api_alerts_count():
    """获取当前用户未确认告警数量（速率限制：每个用户每分钟 60 次）"""
    if session.get("user_id"):
        allowed, remaining, retry = _check_rate_limit("api_alert", f"u{session['user_id']}")
        if not allowed:
            return jsonify({"count": 0}), 429
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM alerts WHERE user_id = ? AND acknowledged = 0",
        (session["user_id"],)
    ).fetchone()
    return jsonify({"count": row["cnt"] if row else 0})


@app.route("/alerts")
@login_required
def alerts_history():
    """历史告警页面（支持分页和筛选）"""
    page = request.args.get("page", "1")
    event_filter = request.args.get("type", "all")
    per_page = 30

    try:
        page = int(page)
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    db = get_db()

    query_where = "WHERE a.user_id = ?"
    params = [session["user_id"]]

    if event_filter in ("offline", "online"):
        query_where += " AND a.event_type = ?"
        params.append(event_filter)

    count_row = db.execute(
        "SELECT COUNT(*) AS cnt FROM alerts a " + query_where,
        params
    ).fetchone()
    total = count_row["cnt"] if count_row else 0

    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    alerts = db.execute(
        """SELECT a.*, s.name AS server_name, s.host, s.port
           FROM alerts a
           LEFT JOIN servers s ON a.server_id = s.id
           """ + query_where + """
           ORDER BY a.created_at DESC
           LIMIT ? OFFSET ?""",
        params + [per_page, offset]
    ).fetchall()

    # 统计数据（SQLite 不支持 FILTER，使用 SUM(CASE WHEN)）
    stats_row = db.execute(
        """SELECT
           SUM(CASE WHEN a.acknowledged = 0 AND a.event_type = 'offline' THEN 1 ELSE 0 END) AS unread_offline,
           SUM(CASE WHEN a.acknowledged = 0 AND a.event_type = 'online' THEN 1 ELSE 0 END) AS unread_online,
           SUM(CASE WHEN a.event_type = 'offline' THEN 1 ELSE 0 END) AS total_offline,
           SUM(CASE WHEN a.event_type = 'online' THEN 1 ELSE 0 END) AS total_online
           FROM alerts a
           WHERE a.user_id = ?""",
        (session["user_id"],)
    ).fetchone()

    stats = {
        "unread_offline": stats_row["unread_offline"] if stats_row else 0,
        "unread_online": stats_row["unread_online"] if stats_row else 0,
        "total_offline": stats_row["total_offline"] if stats_row else 0,
        "total_online": stats_row["total_online"] if stats_row else 0,
        "total": total,
    }

    return render_template(
        "alerts.html",
        alerts=alerts,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=per_page,
        event_filter=event_filter,
        stats=stats,
        username=session.get("username", ""),
    )


# ============================================================
# 后台调度器启动
# ============================================================
def _start_scheduler():
    """启动后台调度器，每 60 秒采集一次所有服务器状态"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        return

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # 每 60 秒执行一次全量采集
    scheduler.add_job(
        _poll_all_servers,
        "interval",
        seconds=60,
        id="poll_all_servers",
        replace_existing=True,
        max_instances=1,
    )
    # 每天 03:00 清理一次过期数据
    scheduler.add_job(
        _cleanup_old_data,
        "cron",
        hour=3,
        minute=0,
        id="cleanup_old_data",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logging.info("[Scheduler] 后台定时采集任务已启动（每 60 秒），每日 03:00 自动清理过期数据")


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    # 启动检测：确保 requests 已安装（麦块联机 API 依赖）
    try:
        import requests  # noqa: F401
    except ImportError:
        print("⚠  缺少 requests 模块，正在安装…")
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
        print("✅ requests 安装完成，重新启动后即可使用麦块联机 API。")
        sys.exit(0)

    # 启动检测：确保 APScheduler 已安装
    _check_apscheduler()

    init_db()

    # Session 密钥持久化：环境变量优先，否则从数据库读取，都没有则生成并存入
    if not os.environ.get("MCMONITOR_SECRET_KEY"):
        db = get_db()
        saved_key = get_setting("secret_key", "")
        if saved_key:
            app.config["SECRET_KEY"] = saved_key
        else:
            generated = secrets.token_hex(32)
            set_setting("secret_key", generated)
            app.config["SECRET_KEY"] = generated
            print("[MC-Monitor] 已生成并保存 Session 密钥到数据库")

    debug_mode = os.environ.get("MCMONITOR_DEBUG", "0") == "1"

    # 启动后台定时采集调度器（reloader 模式下只在子进程中启动，避免重复）
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if not debug_mode or is_reloader_child:
        _start_scheduler()
    else:
        print("[DEBUG] 热加载监控进程启动，等待子进程...")

    host = os.environ.get("MCMONITOR_HOST", "0.0.0.0")
    port = int(os.environ.get("MCMONITOR_PORT", "5000"))

    if IS_PRODUCTION and not debug_mode:
        try:
            from waitress import serve
            serve(app, host=host, port=port, threads=4)
        except ImportError:
            print("WARNING: waitress not installed, falling back to Flask dev server")
            app.run(host=host, port=port, debug=False, use_reloader=False)
    else:
        if debug_mode:
            print("[DEBUG] 热加载模式已开启，代码修改后自动重启")
        app.run(host=host, port=port, debug=debug_mode, use_reloader=debug_mode)
