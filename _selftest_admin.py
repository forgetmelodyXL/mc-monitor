#!/usr/bin/env python -u
"""管理员功能端到端自测"""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as a

TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_admin.db')
a.app.config['TESTING'] = True
a.app.config['DATABASE'] = TEST_DB

# 确保每次测之前是干净的
try: os.remove(TEST_DB)
except FileNotFoundError: pass

a.init_db()

client = a.app.test_client()

PASS = 0
FAIL = 0
def check(desc, cond):
    global PASS, FAIL
    if cond:
        print('  ✓', desc); PASS += 1
    else:
        print('  ✗', desc); FAIL += 1

# ============ 1. admin/admin 自动创建 & 可登录 ============
print('\n[1] admin/admin 登录')
r = client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
check('admin 登录 -> 302', r.status_code == 302)

# 访问 dashboard
r = client.get('/dashboard')
check('admin 访问 dashboard -> 200', r.status_code == 200)

# ============ 2. 管理后台 ============
print('\n[2] 管理后台访问')
r = client.get('/admin')
check('GET /admin -> 200', r.status_code == 200)
body = r.data.decode('utf-8', errors='replace')
check('管理页面包含"admin"', 'admin' in body)
check('管理页面包含"用户列表"', '用户列表' in body)
check('管理页面包含"所有服务器"', '所有服务器' in body)

# ============ 3. 注册普通用户 ============
print('\n[3] 注册普通用户 testuser')
r = client.post('/register',
                data={'username': 'testuser', 'password': 'Pass123!', 'confirm': 'Pass123!'},
                follow_redirects=False)
check('注册 testuser -> 302', r.status_code == 302)

# ============ 4. 非管理员访问管理后台 -> 403 ============
print('\n[4] 非管理员访问管理后台 -> 403')
r = client.get('/logout', follow_redirects=False)
r = client.post('/login', data={'username': 'testuser', 'password': 'Pass123!'}, follow_redirects=False)
check('普通用户 testuser 登录 -> 302', r.status_code == 302)

r = client.get('/admin')
check('普通用户访问 /admin -> 403', r.status_code == 403)

# ============ 5. 重新登录为 admin ============
print('\n[5] 重新登录为 admin')
client.get('/logout')
r = client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
check('再次登录 admin -> 302', r.status_code == 302)

# ============ 6. 为 testuser 重置密码 ============
print('\n[6] 重置 testuser 密码为 NewPass999')
r = client.get('/admin')
# 从 HTML 中提取 testuser 的用户 id
body = r.data.decode('utf-8', errors='replace')
import re
user_ids = re.findall(r'/admin/users/(\d+)/reset-password', body)
testuser_id = None
for uid in user_ids:
    # 判断它是不是 testuser (我们传 uid 到 action 中)
    # 简单起见：取所有 user id，逐个尝试找 testuser
    testuser_id = uid

with a.app.app_context():
    db = a.get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    testuser_row = next((u for u in users if u["username"] == "testuser"), None)
    check('数据库中有 testuser 记录', testuser_row is not None)
    testuser_id = testuser_row["id"]

r = client.post(f'/admin/users/{testuser_id}/reset-password',
                data={'new_password': 'NewPass999'}, follow_redirects=False)
check('重置密码 -> 302', r.status_code == 302)

# 用新密码登录
client.get('/logout')
r = client.post('/login', data={'username': 'testuser', 'password': 'NewPass999'}, follow_redirects=False)
check('用新密码登录 testuser -> 302', r.status_code == 302)

# ============ 7. 升级 testuser 为管理员 ============
print('\n[7] 升级 testuser 为管理员')
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})

r = client.post(f'/admin/users/{testuser_id}/toggle-admin', follow_redirects=False)
check('升级为管理员 -> 302', r.status_code == 302)

# testuser 现在应能访问 /admin
client.get('/logout')
client.post('/login', data={'username': 'testuser', 'password': 'NewPass999'})
r = client.get('/admin')
check('升级后 testuser 能访问 /admin -> 200', r.status_code == 200)

# 再降级
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})
r = client.post(f'/admin/users/{testuser_id}/toggle-admin', follow_redirects=False)
check('降级为普通用户 -> 302', r.status_code == 302)

# ============ 8. 为用户添加服务器 ============
print('\n[8] 管理员为 testuser 添加服务器')
r = client.post(f'/admin/users/{testuser_id}/create-server',
                data={'name': 'Admin-Added Server', 'host': '127.0.0.1', 'port': '25565',
                      'is_public': 'on'},
                follow_redirects=False)
check('管理员添加服务器 -> 302', r.status_code == 302)

# 切回 testuser，dashboard 能看到服务器
client.get('/logout')
client.post('/login', data={'username': 'testuser', 'password': 'NewPass999'})
r = client.get('/dashboard')
check('testuser dashboard 能看到 Admin-Added Server',
      'Admin-Added Server' in r.data.decode('utf-8', errors='replace'))

# ============ 9. 管理员切换服务器公开状态 ============
print('\n[9] 管理员切换服务器公开状态')
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})

db = a.get_db()
servers = db.execute("SELECT * FROM servers WHERE name = 'Admin-Added Server'").fetchall()
assert servers
server_id = servers[0]["id"]

r = client.post(f'/admin/servers/{server_id}/toggle-public', follow_redirects=False)
check('切换公开状态 -> 302', r.status_code == 302)

# ============ 10. 管理员编辑服务器 ============
print('\n[10] 管理员编辑服务器')
r = client.post(f'/admin/servers/{server_id}/edit',
                data={'name': 'Edited Server', 'host': '192.168.1.100', 'port': '25566'},
                follow_redirects=False)
check('编辑服务器 -> 302', r.status_code == 302)
s = db.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
check('名称已更新为 Edited Server', s and s["name"] == 'Edited Server')
check('host 已更新为 192.168.1.100', s and s["host"] == '192.168.1.100')
check('port 已更新为 25566', s and s["port"] == 25566)

# ============ 11. 管理员删除服务器 ============
print('\n[11] 管理员删除服务器')
r = client.post(f'/admin/servers/{server_id}/delete', follow_redirects=False)
check('删除服务器 -> 302', r.status_code == 302)
s = db.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
check('服务器已从数据库消失', s is None)

# ============ 12. 管理员删除用户 ============
print('\n[12] 管理员删除用户 testuser（及其服务器）')
# 先加一个服务器便于确认级联删除
r = client.post(f'/admin/users/{testuser_id}/create-server',
                data={'name': 'To-Be-Deleted', 'host': '10.0.0.1', 'port': '25565'},
                follow_redirects=False)
check('添加测试服务器 -> 302', r.status_code == 302)

r = client.post(f'/admin/users/{testuser_id}/delete', follow_redirects=False)
check('删除 testuser -> 302', r.status_code == 302)
u = db.execute("SELECT * FROM users WHERE username = 'testuser'").fetchone()
check('testuser 已删除', u is None)
s = db.execute("SELECT * FROM servers WHERE name = 'To-Be-Deleted'").fetchone()
check('级联删除了 testuser 的服务器', s is None)

# ============ 13. 保护: 不能删除自己 ============
print('\n[13] 保护: admin 不能删除自己')
r = client.post('/admin/users/1/delete', follow_redirects=False)
# 1 号用户应该就是 admin
u = db.execute("SELECT * FROM users WHERE id = 1").fetchone()
check('admin 用户仍然存在', u is not None and u["username"] == 'admin')

# ============ 14. 保护: 不能操作 admin 的管理员身份 ============
print('\n[14] 保护: 不能把默认 admin 降为普通用户')
r = client.post('/admin/users/1/toggle-admin', follow_redirects=False)
# 返回 302 但 flash 了错误
u = db.execute("SELECT * FROM users WHERE id = 1").fetchone()
check('admin 仍是管理员', u and (u["is_admin"] or 0) == 1)

# ============ 15. 修改自己的密码 ============
print('\n[15] admin 修改自己密码')
r = client.post('/admin/change-my-password',
                data={'new_password': 'BetterPass987!'}, follow_redirects=False)
check('修改自己密码 -> 302', r.status_code == 302)
# 用新密码登录
client.get('/logout')
r = client.post('/login', data={'username': 'admin', 'password': 'BetterPass987!'}, follow_redirects=False)
check('用新密码登录 admin -> 302', r.status_code == 302)

# ============ 汇总 ============
print('\n' + '=' * 60)
print(f'自测结果: {PASS} 通过, {FAIL} 失败')
if FAIL == 0:
    print('全部通过 ✓')
else:
    print(f'有 {FAIL} 项失败，请检查')
print('=' * 60)

try: os.remove(TEST_DB)
except FileNotFoundError: pass
sys.exit(0 if FAIL == 0 else 1)
