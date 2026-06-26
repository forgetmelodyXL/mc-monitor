import os
import sys

# PyInstaller 打包检测：frozen 状态下强制关闭 debug
if getattr(sys, "frozen", False):
    os.environ["MCMONITOR_DEBUG"] = "0"

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

# 检查是否为 CLI 命令模式
_cli_args = sys.argv[1:]
if _cli_args and _cli_args[0] == "monitor":
    import cli
    sys.exit(cli.run_cli(_cli_args))

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

import app as app_module


def main():
    try:
        import requests  # noqa: F401
    except ImportError:
        print("⚠  缺少 requests 模块，正在安装…")
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
        print("✅ requests 安装完成，重新启动后即可使用麦块联机 API。")

    app_module.init_db()
    app_module._check_apscheduler()

    if not os.environ.get("MCMONITOR_SECRET_KEY"):
        saved_key = app_module.get_setting("secret_key", "")
        if saved_key:
            app_module.app.config["SECRET_KEY"] = saved_key
        else:
            import secrets
            generated = secrets.token_hex(32)
            app_module.set_setting("secret_key", generated)
            app_module.app.config["SECRET_KEY"] = generated
            print("[MC-Monitor] 已生成并保存 Session 密钥到数据库")

    debug_mode = os.environ.get("MCMONITOR_DEBUG", "0") == "1"
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if not debug_mode or is_reloader_child:
        app_module._start_scheduler()

    host = os.environ.get("MCMONITOR_HOST", "0.0.0.0")
    port = int(os.environ.get("MCMONITOR_PORT", "5000"))

    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::", "0.0.0.0/0") else host
    url = f"http://{browser_host}:{port}"

    # debug 模式下的父进程（监控进程）不打印启动信息
    if not debug_mode or is_reloader_child:
        print("=" * 60)
        print("  MC 服务器监控面板")
        print("  数据库文件:", app_module.DB_PATH)
        print("  访问地址:", url)
        print("  提示: 首次打开请点击『立即注册』创建账号")
        print("  关闭: 按 Ctrl+C 或直接关闭此窗口")
        print("=" * 60)

        import db as db_module
        admin_info = db_module.get_first_run_admin_info()
        if admin_info:
            print()
            print("=" * 60)
            if admin_info["type"] == "temporary":
                print("  首次启动，已自动创建临时管理员账号")
            else:
                print("  已通过环境变量创建管理员账号")
            print("=" * 60)
            print(f"  用户名: {admin_info['username']}")
            print(f"  密  码: {admin_info['password']}")
            print("-" * 60)
            print("  ⚠️  请立即登录并修改密码！此密码仅显示一次。")
            print("=" * 60)
        print()
    else:
        print("[DEBUG] 热加载监控进程启动，等待子进程...")
        print()

    # 交互式命令行只在真正运行服务的进程中启动
    if not debug_mode or is_reloader_child:
        import cli
        cli.start_interactive_shell()

    try:
        if debug_mode:
            if is_reloader_child:
                print("[DEBUG] 热加载模式已开启，代码修改后自动重启")
            app_module.app.run(host=host, port=port, debug=True, use_reloader=True)
        else:
            try:
                from waitress import serve
                serve(app_module.app, host=host, port=port, threads=4)
            except ImportError:
                print("WARNING: waitress not installed, falling back to Flask dev server")
                app_module.app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n已停止服务。")


if __name__ == "__main__":
    main()
