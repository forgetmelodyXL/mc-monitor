"""
MC Monitor 命令行工具

用法:
  python cli.py monitor reset-password [密码]   重置 admin 密码
  python cli.py monitor create-user <用户名> [密码]  创建用户
  python cli.py monitor list-users                     列出所有用户
  python cli.py monitor version                        查看版本

交互式模式（Web 服务运行时）:
  直接在控制台输入 monitor <命令> 即可执行
"""

import os
import sys
import secrets
import hashlib
import threading
from datetime import datetime, timezone


def _ensure_app_context():
    """确保 app 模块和 db 模块可用，初始化数据库路径"""
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    if _this_dir not in sys.path:
        sys.path.insert(0, _this_dir)

    import app as _app

    if not os.environ.get("MCMONITOR_DATABASE"):
        os.environ["MCMONITOR_DATABASE"] = _app.DB_PATH

    import db as _db
    return _app, _db


def hash_password(password: str) -> str:
    """与 app.py 中一致的密码哈希算法"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000
    ).hex()
    return f"pbkdf2:sha256:200000${salt}${digest}"


def cmd_reset_password(args):
    """重置 admin 密码"""
    _app, _db = _ensure_app_context()

    if args:
        new_pass = args[0]
        if len(new_pass) < 8:
            print("错误: 密码长度至少 8 位")
            return 1
    else:
        new_pass = secrets.token_urlsafe(12)

    db = _db.get_db()
    try:
        existing = db.fetchone("SELECT id, username FROM users WHERE username = ?", ("admin",))
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        if not existing:
            pw_hash = hash_password(new_pass)
            db.execute(
                "INSERT INTO users (username, password_hash, role, is_admin, created_at) VALUES (?, ?, 'super_admin', 1, ?)",
                ("admin", pw_hash, now),
            )
            db.commit()
            print("=" * 50)
            print("  admin 用户不存在，已创建新账号")
            print("=" * 50)
            print(f"  用户名: admin")
            print(f"  密  码: {new_pass}")
            print("=" * 50)
        else:
            pw_hash = hash_password(new_pass)
            db.execute(
                "UPDATE users SET password_hash = ? WHERE username = 'admin'",
                (pw_hash,),
            )
            db.commit()
            print("=" * 50)
            print("  admin 密码重置成功")
            print("=" * 50)
            print(f"  用户名: admin")
            print(f"  密  码: {new_pass}")
            print("=" * 50)
        return 0
    except Exception as e:
        print(f"错误: {e}")
        return 1
    finally:
        _db.close_db()


def cmd_create_user(args):
    """创建用户"""
    _app, _db = _ensure_app_context()

    if len(args) < 1:
        print("用法: python cli.py monitor create-user <用户名> [密码]")
        return 1

    username = args[0]
    if len(args) >= 2:
        password = args[1]
        if len(password) < 8:
            print("错误: 密码长度至少 8 位")
            return 1
    else:
        password = secrets.token_urlsafe(12)

    db = _db.get_db()
    try:
        existing = db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
        if existing:
            print(f"错误: 用户 '{username}' 已存在")
            return 1

        pw_hash = hash_password(password)
        now = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
        db.execute(
            "INSERT INTO users (username, password_hash, role, is_admin, created_at) VALUES (?, ?, 'user', 0, ?)",
            (username, pw_hash, now),
        )
        db.commit()
        print("=" * 50)
        print("  用户创建成功")
        print("=" * 50)
        print(f"  用户名: {username}")
        print(f"  密  码: {password}")
        print(f"  角  色: user")
        print("=" * 50)
        return 0
    except Exception as e:
        print(f"错误: {e}")
        return 1
    finally:
        _db.close_db()


def cmd_list_users(args):
    """列出所有用户"""
    _app, _db = _ensure_app_context()

    db = _db.get_db()
    try:
        rows = db.fetchall(
            "SELECT id, username, role, is_admin, created_at FROM users ORDER BY id"
        )
        if not rows:
            print("暂无用户")
            return 0

        print("=" * 70)
        print(f"  {'ID':<4} {'用户名':<20} {'角色':<15} {'管理员':<6} {'创建时间'}")
        print("-" * 70)
        for row in rows:
            admin_flag = "是" if row["is_admin"] else "否"
            print(f"  {row['id']:<4} {row['username']:<20} {row['role']:<15} {admin_flag:<6} {row['created_at']}")
        print("=" * 70)
        print(f"  共 {len(rows)} 个用户")
        return 0
    except Exception as e:
        print(f"错误: {e}")
        return 1
    finally:
        _db.close_db()


def cmd_version(args):
    """查看版本"""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    version = "unknown"
    try:
        app_path = os.path.join(app_dir, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("APP_VERSION"):
                    version = line.split("=")[1].strip().strip('"').strip("'")
                    break
    except Exception:
        pass
    print(f"MC Monitor v{version}")
    return 0


COMMANDS = {
    "reset-password": cmd_reset_password,
    "create-user": cmd_create_user,
    "list-users": cmd_list_users,
    "version": cmd_version,
}


def print_help():
    print("MC Monitor 命令行工具")
    print("")
    print("用法: python cli.py monitor <命令> [参数]")
    print("      mcmonitor.exe monitor <命令> [参数]  (Windows EXE)")
    print("")
    print("可用命令:")
    print("  reset-password [密码]   重置 admin 密码（不指定则随机生成）")
    print("  create-user <用户名> [密码]  创建普通用户")
    print("  list-users              列出所有用户")
    print("  version                 查看版本号")
    print("  help                    显示帮助")


def run_cli(argv=None):
    """运行 CLI 工具，可被 main.py 直接调用"""
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) == 0 or argv[0] == "help" or argv[0] == "--help" or argv[0] == "-h":
        print_help()
        return 0

    if argv[0] != "monitor":
        print(f"未知指令: {argv[0]}")
        print("提示: 指令前缀为 monitor，例如: python cli.py monitor reset-password")
        return 1

    if len(argv) < 2 or argv[1] == "help":
        print_help()
        return 0

    cmd = argv[1]
    args = argv[2:]

    if cmd in COMMANDS:
        return COMMANDS[cmd](args)
    else:
        print(f"未知命令: {cmd}")
        print("")
        print_help()
        return 1


def print_interactive_help():
    print("")
    print("  MC Monitor 交互式命令行")
    print("  " + "=" * 50)
    print("  输入 monitor <命令> [参数] 执行操作")
    print("  输入 help              显示此帮助")
    print("  输入 clear / cls       清屏")
    print("  " + "=" * 50)
    print("  可用命令:")
    print("    monitor reset-password [密码]   重置 admin 密码")
    print("    monitor create-user <用户名> [密码]  创建用户")
    print("    monitor list-users              列出所有用户")
    print("    monitor version                 查看版本号")
    print("  " + "=" * 50)
    print("")


def _run_interactive_command(line):
    """执行一行交互式命令，返回 True 表示继续，False 表示退出"""
    line = line.strip()
    if not line:
        return True

    if line in ("exit", "quit", "退出"):
        print("  提示: 输入不会终止服务，关闭窗口或按 Ctrl+C 停止服务")
        print("  继续输入 monitor 命令可执行管理操作，输入 help 查看帮助")
        return True

    if line in ("clear", "cls", "清屏"):
        os.system("cls" if os.name == "nt" else "clear")
        return True

    if line in ("help", "帮助"):
        print_interactive_help()
        return True

    parts = line.split()
    if parts and parts[0] == "monitor":
        try:
            run_cli(parts)
        except Exception as e:
            print(f"  执行出错: {e}")
        return True

    print(f"  未知输入: {line}")
    print("  提示: 输入 monitor help 查看可用命令")
    return True


def _input_loop():
    """后台输入监听循环"""
    print("")
    print("  💡 交互式命令行已启用，可直接输入 monitor 命令进行管理")
    print("  输入 help 查看可用命令")
    print("")

    while True:
        try:
            line = input()
            _run_interactive_command(line)
        except EOFError:
            break
        except KeyboardInterrupt:
            break
        except Exception:
            break


def start_interactive_shell():
    """启动交互式命令行（后台线程）"""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return
    except Exception:
        return

    t = threading.Thread(target=_input_loop, name="cli-interactive", daemon=True)
    t.start()


def main():
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
