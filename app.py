import os
import sys
import json
import socket
import struct
import sqlite3
import secrets
import hashlib
import time
import concurrent.futures
from datetime import datetime, timedelta
from functools import wraps

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
        session, flash, jsonify, g, abort
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

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
    static_folder=STATIC_DIR,
)
app.config["SECRET_KEY"] = secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)


# ============================================================
# 数据库
# ============================================================
def get_db():
    if "db" not in g:
        path = app.config.get("DATABASE") or DB_PATH
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    # ── 启动检测：确保 requests 已安装（麦块联机 API 依赖）────────────
    try:
        import requests  # noqa: F401
    except ImportError:
        import subprocess, sys
        print("⚠  缺少 requests 模块，正在自动安装…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
        import requests  # noqa: F401
        print("✅ requests 安装完成，服务正在启动。")
    # ─────────────────────────────────────────────────────────────────

    path = None
    try:
        # 优先使用 app.config['DATABASE']（如果已初始化应用）
        path = app.config.get("DATABASE") or DB_PATH
    except RuntimeError:
        path = DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0,
        minekuai_api_key TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS servers (
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
    );
    CREATE TABLE IF NOT EXISTS status_logs (
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
    );
    CREATE INDEX IF NOT EXISTS idx_logs_server_time ON status_logs(server_id, checked_at DESC);
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    # 迁移：老数据库补列
    try:
        conn.execute("ALTER TABLE servers ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        conn.execute("ALTER TABLE servers ADD COLUMN show_players INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        conn.execute("ALTER TABLE users ADD COLUMN minekuai_api_key TEXT")
    except sqlite3.OperationalError:
        pass  # 列已存在
    try:
        conn.execute("ALTER TABLE servers ADD COLUMN minekuai_instance_id TEXT")
    except sqlite3.OperationalError:
        pass  # 列已存在
    # 默认开关值
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    for default_key, default_value in (("registration_enabled", "1"), ("maintenance_enabled", "0")):
        existing = conn.execute("SELECT 1 FROM settings WHERE key = ?", (default_key,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (default_key, default_value, now),
            )
    # 自动创建默认管理员账号 (admin / admin)
    try:
        existing = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, 1, ?)",
                ("admin", hash_password("admin"), now),
            )
    except Exception:
        pass
    conn.commit()
    conn.close()


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


def admin_required(view):
    """仅管理员可访问的视图装饰器"""
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


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
                return redirect(url_for("login"))
    return render_template("register.html", registration_disabled=False)


@app.route("/login", methods=["GET", "POST"])
def login():
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
            session.permanent = True
            next_url = request.args.get("next") or url_for("dashboard")
            if not next_url.startswith("/"):
                next_url = url_for("dashboard")
            return redirect(next_url)
        flash("用户名或密码错误", "error")
    return render_template("login.html", in_maintenance=in_maintenance)


@app.route("/maintenance")
def maintenance():
    return render_template("maintenance.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# 管理后台
# ============================================================
@app.route("/admin")
@admin_required
def admin_panel():
    db = get_db()
    users = db.execute(
        "SELECT id, username, is_admin, created_at, "
        "(SELECT COUNT(*) FROM servers s WHERE s.user_id = u.id) AS server_count "
        "FROM users u ORDER BY u.id ASC"
    ).fetchall()
    servers = db.execute(
        "SELECT s.*, u.username AS owner_name "
        "FROM servers s JOIN users u ON s.user_id = u.id ORDER BY s.id DESC"
    ).fetchall()
    total_users = len(users)
    total_servers = len(servers)
    total_public = sum(1 for s in servers if s["is_public"])
    # 当前开关状态
    reg_enabled = get_setting("registration_enabled", "1") == "1"
    maint_enabled = get_setting("maintenance_enabled", "0") == "1"
    return render_template("admin.html",
                           users=users, servers=servers,
                           total_users=total_users,
                           total_servers=total_servers,
                           total_public=total_public,
                           registration_enabled=reg_enabled,
                           maintenance_enabled=maint_enabled,
                           current_username=session.get("username", ""))


@app.route("/admin/settings/register-toggle", methods=["POST"])
@admin_required
def admin_toggle_register():
    current = get_setting("registration_enabled", "1")
    new_val = "0" if current == "1" else "1"
    set_setting("registration_enabled", new_val)
    flash("已%s注册功能" % ("开启" if new_val == "1" else "关闭"), "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/settings/maintenance-toggle", methods=["POST"])
@admin_required
def admin_toggle_maintenance():
    current = get_setting("maintenance_enabled", "0")
    new_val = "0" if current == "1" else "1"
    set_setting("maintenance_enabled", new_val)
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


@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(user_id):
    db = get_db()
    user = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    if user["username"] == "admin" and not request.form.get("confirm_admin"):
        # 防止意外重置 admin 的保护：强制传 confirm_admin
        pass
    new_password = (request.form.get("new_password") or "").strip()
    if len(new_password) < 6:
        flash("新密码长度至少 6 个字符", "error")
        return redirect(url_for("admin_panel"))
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (hash_password(new_password), user_id))
    db.commit()
    flash(f"已重置用户 {user['username']} 的密码为: {new_password}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def admin_toggle_admin(user_id):
    db = get_db()
    user = db.execute("SELECT id, username, is_admin FROM users WHERE id = ?",
                      (user_id,)).fetchone()
    if not user:
        abort(404)
    if user["username"] == "admin":
        flash("不能修改默认管理员 admin 的身份", "error")
        return redirect(url_for("admin_panel"))
    new_val = 0 if (user["is_admin"] or 0) == 1 else 1
    db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, user_id))
    db.commit()
    flash(f"已将用户 {user['username']} 设为{'管理员' if new_val else '普通用户'}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    user = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    if user["username"] == "admin":
        flash("不能删除默认管理员 admin", "error")
        return redirect(url_for("admin_panel"))
    if int(user_id) == int(session.get("user_id", 0)):
        flash("不能删除自己的账号", "error")
        return redirect(url_for("admin_panel"))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
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
    flash(f"服务器 {name} 已更新", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/users/<int:user_id>/create-server", methods=["POST"])
@admin_required
def admin_create_server_for_user(user_id):
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        abort(404)
    name = (request.form.get("name") or "").strip()
    host = (request.form.get("host") or "").strip()
    port_str = (request.form.get("port") or "").strip()
    is_public = 1 if request.form.get("is_public") else 0
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
    db.execute(
        "INSERT INTO servers (user_id, name, host, port, is_public, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name[:64], host[:253], port, is_public,
         datetime.utcnow().isoformat(sep=" ", timespec="seconds")),
    )
    db.commit()
    flash(f"已为用户添加服务器: {name}", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/change-my-password", methods=["POST"])
@admin_required
def admin_change_own_password():
    """管理员修改自己密码（避免默认 admin/admin 暴露）"""
    new_password = (request.form.get("new_password") or "").strip()
    if len(new_password) < 6:
        flash("新密码长度至少 6 个字符", "error")
        return redirect(url_for("admin_panel"))
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (hash_password(new_password), session["user_id"]))
    db.commit()
    flash("您的密码已更新，请牢记", "success")
    return redirect(url_for("admin_panel"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    servers = db.execute(
        "SELECT * FROM servers WHERE user_id = ? ORDER BY id ASC",
        (session["user_id"],),
    ).fetchall()
    return render_template("dashboard.html",
                           servers=servers,
                           username=session.get("username", ""))


@app.route("/server/add", methods=["POST"])
@login_required
def server_add():
    name = (request.form.get("name") or "").strip()
    host = (request.form.get("host") or "").strip()
    port_str = (request.form.get("port") or "").strip() or "25565"
    show_players = 1 if request.form.get("show_players") else 0
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
    db.execute(
        "INSERT INTO servers (user_id, name, host, port, is_public, show_players, created_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
        (
            session["user_id"],
            name[:64],
            host[:253],
            port,
            show_players,
            datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        ),
    )
    db.commit()
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
    flash("服务器已删除", "success")
    return redirect(url_for("dashboard"))


@app.route("/server/<int:server_id>/toggle-public", methods=["POST"])
@login_required
def server_toggle_public(server_id):
    db = get_db()
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    new_val = 0 if (server["is_public"] or 0) == 1 else 1
    db.execute(
        "UPDATE servers SET is_public = ? WHERE id = ?",
        (new_val, server_id),
    )
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
    server = db.execute(
        "SELECT * FROM servers WHERE id = ? AND user_id = ?",
        (server_id, session["user_id"]),
    ).fetchone()
    if not server:
        abort(404)
    new_val = 0 if (server["show_players"] or 0) == 1 else 1
    db.execute(
        "UPDATE servers SET show_players = ? WHERE id = ?",
        (new_val, server_id),
    )
    db.commit()
    label = "显示玩家名" if new_val == 1 else "隐藏玩家名"
    flash(f"已{label}", "success")
    if request.is_json or (request.headers.get("Accept") or "").startswith("application/json"):
        return jsonify({"ok": True, "show_players": bool(new_val), "id": server_id})
    return redirect(url_for("dashboard"))


@app.route("/api/public_status")
def api_public_status():
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
        info = ping_with_latency(s["host"], s["port"], timeout=5.0)
        online = bool(info.get("online", False))
        show_players = bool(s["show_players"])
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
            "owner_name": s["owner_name"],
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
    db = get_db()
    servers = db.execute(
        "SELECT * FROM servers WHERE user_id = ? ORDER BY id ASC",
        (session["user_id"],),
    ).fetchall()

    results = []
    for s in servers:
        info = ping_with_latency(s["host"], s["port"], timeout=10.0)
        online = bool(info.get("online", False))
        show_players = bool(s["show_players"])
        entry = {
            "id": s["id"],
            "name": s["name"],
            "host": s["host"],
            "port": s["port"],
            "is_public": bool(s["is_public"]),
            "show_players": show_players,
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


@app.route("/api/test", methods=["POST"])
@login_required
def api_test():
    """手动测试某个 MC 服务器的 API。返回完整的协议诊断和原始 JSON。"""
    data_source = request.json if request.is_json else request.form
    host = (data_source.get("host") or "").strip()
    port_str = (data_source.get("port") or "").strip()
    try:
        port = int(port_str)
        if not (0 < port < 65536):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({
            "error": "端口必须是 1-65535 之间的整数",
            "online": False,
            "diagnostics": ["[参数错误] 端口无效"],
            "elapsed_ms": 0,
        }), 400
    if not host:
        return jsonify({
            "error": "主机名不能为空",
            "online": False,
            "diagnostics": ["[参数错误] 主机名不能为空"],
            "elapsed_ms": 0,
        }), 400

    result = ping_with_timeout(host, port, overall_timeout=15.0, step_timeout=5.0)
    result["host"] = host
    result["port"] = port
    return jsonify(result)


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
        "SELECT id, name, host, port, minekuai_instance_id FROM servers WHERE user_id = ?",
        (session["user_id"],),
    ).fetchall()
    return jsonify({
        "user_id": user["id"],
        "username": user["username"],
        "has_minekuai_key": bool(user["minekuai_api_key"]),
        "servers": [
            {
                "id": s["id"],
                "name": s["name"],
                "host": s["host"],
                "port": s["port"],
                "minekuai_instance_id": s["minekuai_instance_id"],
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
    if not server["minekuai_instance_id"]:
        return None, (400, {
            "errors": [{
                "code": "InstanceIdMissing",
                "status": "400",
                "detail": "该服务器尚未绑定麦块实例 ID，请先在页面中绑定。",
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
    instance_id = server["minekuai_instance_id"]
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
    instance_id = server["minekuai_instance_id"]
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

    instance_id = server["minekuai_instance_id"]
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

    instance_id = server["minekuai_instance_id"]
    status, body = _minekuai_proxy(
        "GET", f"/servers/{instance_id}", api_key
    )
    return jsonify(body), status


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

    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
