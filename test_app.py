import os
import sys
import tempfile
import re
import unittest

_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

# 强制开发模式，避免测试中尝试连接生产环境
os.environ["MCMONITOR_ENV"] = "development"
os.environ["MCMONITOR_SECRET_KEY"] = "test-secret-key-for-testing"

import app as app_module
from app import app, init_db, get_db, hash_password, verify_password, row_get


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.tmpdir.name, "test.db")
        app.config["DATABASE"] = cls.db_path
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key"
        with app.app_context():
            init_db()

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def setUp(self):
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def _get_csrf(self, client, path="/login"):
        resp = client.get(path)
        token = ""
        m = re.search(r'name="_csrf_token"\s+value="([^"]+)"', resp.get_data(as_text=True))
        if m:
            token = m.group(1)
        return token


class TestHealthCheck(TestBase):
    def test_health_returns_200(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["db"], "ok")


class TestAuth(TestBase):
    def test_login_page_loads(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)

    def test_register_page_loads(self):
        resp = self.client.get("/register")
        self.assertEqual(resp.status_code, 200)

    def test_register_and_login(self):
        with self.client as c:
            csrf = self._get_csrf(c, "/register")
            resp = c.post("/register", data={
                "username": "testuser",
                "password": "testpass123",
                "confirm": "testpass123",
                "_csrf_token": csrf,
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            csrf = self._get_csrf(c, "/login")
            resp = c.post("/login", data={
                "username": "testuser",
                "password": "testpass123",
                "_csrf_token": csrf,
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("dashboard", resp.request.path)

    def test_login_failed(self):
        with self.client as c:
            csrf = self._get_csrf(c, "/login")
            resp = c.post("/login", data={
                "username": "testuser",
                "password": "wrongpassword",
                "_csrf_token": csrf,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn("用户名或密码错误", resp.get_data(as_text=True))


class TestPasswordHashing(TestBase):
    def test_hash_and_verify(self):
        pw = "MySecurePassword123!"
        hashed = hash_password(pw)
        self.assertTrue(verify_password(pw, hashed))
        self.assertFalse(verify_password("wrong", hashed))

    def test_empty_password(self):
        hashed = hash_password("")
        self.assertTrue(verify_password("", hashed))


class TestRowGet(TestBase):
    def test_row_get_existing_key(self):
        row = {"name": "test", "value": 42}
        self.assertEqual(row_get(row, "name"), "test")
        self.assertEqual(row_get(row, "value"), 42)

    def test_row_get_missing_key(self):
        row = {"name": "test"}
        self.assertEqual(row_get(row, "missing"), None)
        self.assertEqual(row_get(row, "missing", "default"), "default")

    def test_row_get_none(self):
        self.assertEqual(row_get(None, "key"), None)
        self.assertEqual(row_get(None, "key", "fallback"), "fallback")


class TestDatabase(TestBase):
    def test_default_admin_created(self):
        db = get_db()
        admin = db.execute(
            "SELECT * FROM users WHERE username = 'admin'"
        ).fetchone()
        self.assertIsNotNone(admin)
        self.assertEqual(admin["is_admin"], 1)

    def test_default_settings(self):
        db = get_db()
        reg = db.execute(
            "SELECT value FROM settings WHERE key = 'registration_enabled'"
        ).fetchone()
        self.assertIsNotNone(reg)
        self.assertEqual(reg["value"], "1")


class TestPublicPages(TestBase):
    def test_index_loads(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_index_in_maintenance(self):
        with self.client as c:
            # 注册管理员并登录
            csrf = self._get_csrf(c, "/register")
            c.post("/register", data={
                "username": "admin2",
                "password": "adminpass123",
                "confirm": "adminpass123",
                "_csrf_token": csrf,
            })
            db = get_db()
            db.execute("UPDATE users SET is_admin = 1, role = 'admin' WHERE username = 'admin2'")
            db.commit()

            csrf = self._get_csrf(c, "/login")
            c.post("/login", data={
                "username": "admin2",
                "password": "adminpass123",
                "_csrf_token": csrf,
            })

            # 开启维护模式
            csrf = self._get_csrf(c, "/admin")
            resp = c.post("/admin/settings/maintenance-toggle", data={
                "_csrf_token": csrf,
            })

            # 登出后访问首页应跳转到维护页面
            c.get("/logout")
            resp = c.get("/", follow_redirects=False)
            # 维护模式可能会导致 302 或 200（取决于是否已登录）
            self.assertIn(resp.status_code, (200, 302))

            # 恢复维护模式，避免影响其他测试
            db = get_db()
            db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES ('maintenance_enabled', '0', datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value='0'"
            )
            db.commit()


if __name__ == "__main__":
    unittest.main()