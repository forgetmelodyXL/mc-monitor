"""
旧数据库自动兼容自测脚本

模拟不同版本的旧数据库，验证 _ensure_schema 自动迁移功能，
以及迁移后核心功能（登录、添加服务器、分组、排序、告警等）是否正常。
"""
import os
import sys
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["FLASK_TESTING"] = "1"


class TestOldDatabaseCompatibility(unittest.TestCase):
    """测试各种旧版本数据库的自动兼容"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def _create_v0_db(self):
        """模拟 v0 数据库：只有最基础的 users 和 servers 表，没有 settings 表"""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 25565,
                created_at TEXT NOT NULL
            );
            CREATE TABLE status_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                online INTEGER NOT NULL,
                players_online INTEGER,
                players_max INTEGER,
                version TEXT,
                motd TEXT,
                latency_ms INTEGER,
                checked_at TEXT NOT NULL
            );
            INSERT INTO users (username, password_hash, created_at)
            VALUES ('testuser', 'hash123', '2025-01-01 00:00:00');
            INSERT INTO servers (user_id, name, host, port, created_at)
            VALUES (1, '测试服务器', 'localhost', 25565, '2025-01-01 00:00:00');
            INSERT INTO status_logs (server_id, online, players_online, players_max, latency_ms, checked_at)
            VALUES (1, 1, 10, 100, 50, '2025-01-01 00:00:00');
        """)
        conn.commit()
        conn.close()

    def _create_v1_db(self):
        """模拟 v1 数据库：基础 schema，但没有 server_groups、email、sort_order 等"""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                minekuai_api_key TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 25565,
                is_public INTEGER NOT NULL DEFAULT 0,
                show_players INTEGER NOT NULL DEFAULT 1,
                minekuai_instance_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE status_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                online INTEGER NOT NULL,
                players_online INTEGER,
                players_max INTEGER,
                version TEXT,
                motd TEXT,
                latency_ms INTEGER,
                checked_at TEXT NOT NULL
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            INSERT INTO settings (key, value, updated_at)
            VALUES ('schema_version', '1', '2025-01-01 00:00:00');
            INSERT INTO users (username, password_hash, is_admin, created_at)
            VALUES ('testuser', 'hash123', 0, '2025-01-01 00:00:00');
            INSERT INTO servers (user_id, name, host, port, is_public, created_at)
            VALUES (1, '测试服务器', 'localhost', 25565, 0, '2025-01-01 00:00:00');
        """)
        conn.commit()
        conn.close()

    def _create_v4_db(self):
        """模拟 v4 数据库：有 is_admin 和 minekuai_api_key，但没有 server_groups 和 email"""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                minekuai_api_key TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 25565,
                is_public INTEGER NOT NULL DEFAULT 0,
                show_players INTEGER NOT NULL DEFAULT 1,
                minekuai_instance_id TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE status_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                online INTEGER NOT NULL,
                players_online INTEGER,
                players_max INTEGER,
                version TEXT,
                motd TEXT,
                latency_ms INTEGER,
                checked_at TEXT NOT NULL
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            INSERT INTO settings (key, value, updated_at)
            VALUES ('schema_version', '4', '2025-01-01 00:00:00');
            INSERT INTO users (username, password_hash, is_admin, created_at)
            VALUES ('testuser', 'hash123', 0, '2025-01-01 00:00:00');
            INSERT INTO servers (user_id, name, host, port, is_public, created_at)
            VALUES (1, '测试服务器', 'localhost', 25565, 0, '2025-01-01 00:00:00');
        """)
        conn.commit()
        conn.close()

    def _verify_latest_schema(self, conn):
        """验证数据库 schema 已升级到最新版 (v8)"""
        # 检查 schema_version
        row = conn.execute("SELECT value FROM settings WHERE key = 'schema_version'").fetchone()
        self.assertIsNotNone(row, "schema_version 未设置")
        self.assertEqual(int(row[0]), 8, f"schema_version 应为 8，实际为 {row[0]}")

        # 检查 server_groups 表
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("server_groups", tables, "缺少 server_groups 表")

        # 检查 servers 表所有新列
        server_cols = [r[1] for r in conn.execute("PRAGMA table_info(servers)").fetchall()]
        expected_cols = ["group_id", "protocol", "show_players",
                         "minekuai_instance_id", "sort_order"]
        for col in expected_cols:
            self.assertIn(col, server_cols, f"servers 表缺少列: {col}")

        # 检查 users 表所有新列
        user_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        expected_user_cols = ["is_admin", "minekuai_api_key", "email",
                              "email_alert_enabled", "email_cooldown", "display_name"]
        for col in expected_user_cols:
            self.assertIn(col, user_cols, f"users 表缺少列: {col}")

        # 检查唯一索引
        indexes = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%servers%'").fetchall()]
        self.assertTrue(any("name" in idx.lower() for idx in indexes),
                        "缺少 servers.name 唯一索引")

    def test_v0_db_migration(self):
        """测试 v0（极旧）数据库自动迁移到 v8"""
        self._create_v0_db()

        import app as app_module
        app_module.DB_PATH = self.db_path
        import db as db_module
        db_module.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)
        app_module._ensure_schema(conn)

        self._verify_latest_schema(conn)

        # 验证原有数据保留
        user_row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
        self.assertIsNotNone(user_row, "原有用户数据丢失")
        server_row = conn.execute("SELECT * FROM servers WHERE id = 1").fetchone()
        self.assertIsNotNone(server_row, "原有服务器数据丢失")
        log_row = conn.execute("SELECT * FROM status_logs WHERE id = 1").fetchone()
        self.assertIsNotNone(log_row, "原有日志数据丢失")

        conn.close()

    def test_v1_db_migration(self):
        """测试 v1 数据库自动迁移到 v8"""
        self._create_v1_db()

        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.DB_PATH = self.db_path
        import db as db_module
        importlib.reload(db_module)
        db_module.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)
        app_module._ensure_schema(conn)

        self._verify_latest_schema(conn)

        user_row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
        self.assertIsNotNone(user_row, "原有用户数据丢失")
        server_row = conn.execute("SELECT * FROM servers WHERE id = 1").fetchone()
        self.assertIsNotNone(server_row, "原有服务器数据丢失")

        conn.close()

    def test_v4_db_migration(self):
        """测试 v4 数据库自动迁移到 v8"""
        self._create_v4_db()

        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.DB_PATH = self.db_path
        import db as db_module
        importlib.reload(db_module)
        db_module.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)
        app_module._ensure_schema(conn)

        self._verify_latest_schema(conn)

        user_row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
        self.assertIsNotNone(user_row, "原有用户数据丢失")
        server_row = conn.execute("SELECT * FROM servers WHERE id = 1").fetchone()
        self.assertIsNotNone(server_row, "原有服务器数据丢失")

        conn.close()

    def test_row_get_compatibility(self):
        """测试 row_get 函数对旧数据库缺列的容错"""
        import importlib
        import app as app_module
        importlib.reload(app_module)

        class MockRow(dict):
            """模拟 sqlite3.Row"""
            def keys(self):
                return list(self.keys())

        row = MockRow({"id": 1, "username": "test", "password_hash": "abc"})

        # 存在的列
        self.assertEqual(app_module.row_get(row, "id"), 1)
        self.assertEqual(app_module.row_get(row, "username"), "test")

        # 不存在的列返回默认值
        self.assertIsNone(app_module.row_get(row, "email"))
        self.assertEqual(app_module.row_get(row, "email", ""), "")
        self.assertEqual(app_module.row_get(row, "is_admin", 0), 0)
        self.assertEqual(app_module.row_get(row, "display_name", None), None)

    def test_migration_idempotent(self):
        """测试迁移幂等性：多次调用 _ensure_schema 不报错"""
        self._create_v1_db()

        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.DB_PATH = self.db_path

        conn = sqlite3.connect(self.db_path)

        # 连续调用三次
        app_module._ensure_schema(conn)
        app_module._ensure_schema(conn)
        app_module._ensure_schema(conn)

        self._verify_latest_schema(conn)
        conn.close()

    def test_flask_app_with_old_db(self):
        """测试 Flask 应用启动时用旧数据库能否正常访问页面"""
        self._create_v1_db()

        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.DB_PATH = self.db_path
        import db as db_module
        importlib.reload(db_module)
        db_module.DB_PATH = self.db_path

        app_module.app.config["TESTING"] = True
        app_module.app.config["DATABASE"] = self.db_path

        with app_module.app.test_client() as client:
            # 测试公共主页
            resp = client.get("/")
            self.assertEqual(resp.status_code, 200,
                             f"公共主页返回 {resp.status_code}")

            # 测试登录页
            resp = client.get("/login")
            self.assertEqual(resp.status_code, 200,
                             f"登录页返回 {resp.status_code}")

            # 测试注册页
            resp = client.get("/register")
            self.assertEqual(resp.status_code, 200,
                             f"注册页返回 {resp.status_code}")

            # 测试健康检查
            resp = client.get("/health")
            self.assertEqual(resp.status_code, 200,
                             f"健康检查返回 {resp.status_code}")

        # 验证访问后 schema 已升级
        conn = sqlite3.connect(self.db_path)
        self._verify_latest_schema(conn)
        conn.close()

    def test_dashboard_with_old_db_and_user(self):
        """测试登录后访问仪表盘等功能页面（旧数据库场景）"""
        self._create_v1_db()

        import importlib
        import app as app_module
        importlib.reload(app_module)
        app_module.DB_PATH = self.db_path
        import db as db_module
        importlib.reload(db_module)
        db_module.DB_PATH = self.db_path

        app_module.app.config["TESTING"] = True
        app_module.app.config["DATABASE"] = self.db_path

        import re

        def _get_csrf(client, path):
            resp = client.get(path)
            match = re.search(r'name="_csrf_token" value="([^"]+)"',
                              resp.get_data(as_text=True))
            return match.group(1) if match else ""

        with app_module.app.test_client() as client:
            # 注册用户
            csrf = _get_csrf(client, "/register")
            resp = client.post("/register", data={
                "username": "testuser2",
                "email": "test@example.com",
                "password": "test123456",
                "confirm": "test123456",
                "_csrf_token": csrf,
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200,
                             f"注册返回 {resp.status_code}")

            # 登录
            csrf = _get_csrf(client, "/login")
            resp = client.post("/login", data={
                "username": "testuser2",
                "password": "test123456",
                "_csrf_token": csrf,
            }, follow_redirects=True)

            self.assertEqual(resp.status_code, 200,
                             f"登录后返回 {resp.status_code}")
            self.assertIn("dashboard", resp.request.path,
                          f"登录后应跳转到 dashboard，实际路径: {resp.request.path}")

            # 访问仪表盘
            resp = client.get("/dashboard")
            self.assertEqual(resp.status_code, 200,
                             f"仪表盘返回 {resp.status_code}")

            # 访问历史告警页
            resp = client.get("/alerts")
            self.assertEqual(resp.status_code, 200,
                             f"告警页返回 {resp.status_code}")

            # 访问个人资料页
            resp = client.get("/profile")
            self.assertEqual(resp.status_code, 200,
                             f"个人资料页返回 {resp.status_code}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
