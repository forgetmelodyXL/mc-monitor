import os
import sys
import webbrowser

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

import app as app_module


def main():
    app_module.init_db()

    host = os.environ.get("MCMONITOR_HOST", "0.0.0.0")
    port = int(os.environ.get("MCMONITOR_PORT", "5000"))
    open_browser = os.environ.get("MCMONITOR_NOBROWSER", "0") == "0"

    # 如果监听 0.0.0.0 或所有网卡，浏览器仍然用 127.0.0.1 本机打开即可
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::", "0.0.0.0/0") else host
    url = f"http://{browser_host}:{port}"
    print("=" * 60)
    print("  MC 服务器监控面板")
    print("  数据库文件:", app_module.DB_PATH)
    print("  访问地址:", url)
    print("  提示: 首次打开请点击『立即注册』创建账号")
    print("  关闭: 按 Ctrl+C 或直接关闭此窗口")
    print("=" * 60)
    print()

    if open_browser:
        try:
            if not any(a in sys.argv for a in ("--no-browser", "-n")):
                webbrowser.open(url, new=2)
        except Exception:
            pass

    try:
        if app_module.IS_PRODUCTION:
            try:
                from waitress import serve
                serve(app_module.app, host=host, port=port, threads=4)
            except ImportError:
                print("WARNING: waitress not installed, falling back to Flask dev server")
                app_module.app.run(host=host, port=port, debug=False, use_reloader=False)
        else:
            app_module.app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n已停止服务。")


if __name__ == "__main__":
    main()
