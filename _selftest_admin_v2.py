#!/usr/bin/env python -u
"""管理员功能端到端自测"""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as a

TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_admin.db')
a.app.config['TESTING'] = True
a.app.config['DATABASE'] = TEST_DB

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

def q(sql, params=()):
    with a.app.app_context():
        return a.get_db().execute(sql, params).fetchall()

# ======== 1. admin/admin 自动创建 & 可登录
print('\n[1] admin/admin 登录')
r = client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
check('admin 登录 -> 302', r.status_code == 302)
r = client.get('/dashboard')
check('admin 访问 dashboard -> 200', r.status_code == 200)

# ======== 2. 管理后台
print('\n[2] 管理后台访问')
r = client.get('/admin')
check('GET /admin -> 200', r.status_code == 200)
body = r.data.decode('utf-8', errors='replace')
check('管理页面包含 admin', 'admin' in body)
check('管理页面包含用户列表', '用户列表' in body)
check('管理页面包含所有服务器', '所有服务器' in body)

# ======== 3. 注册普通用户
print('\n[3] 注册普通用户 testuser')
r = client.post('/register',
                data={'username': 'testuser', 'password': 'Pass123!', 'confirm': 'Pass123!'},
                follow_redirects=False)
check('注册 testuser -> 302', r.status_code == 302)

# ======== 4. 非管理员访问管理后台
print('\n[4] 非管理员访问管理后台 -> 403')
client.get('/logout')
client.post('/login', data={'username': 'testuser', 'password': 'Pass123!'})
r = client.get('/admin')
check('普通用户访问 /admin -> 403', r.status_code == 403)

# ======== 5. 重新登录 admin
print('\n[5] 重新登录为 admin')
client.get('/logout')
r = client.post('/login', data={'username': 'admin', 'password': 'admin'})
check('再次登录 admin -> 302', r.status_code in (200, 302))

# ======== 6. 重置 testuser 密码
print('\n[6] 重置 testuser 密码')
users = q("SELECT * FROM users WHERE username='testuser'")
testuser_id = users[0]['id']
r = client.post(f'/admin/users/{testuser_id}/reset-password',
                data={'new_password': 'NewPass999'}, follow_redirects=False)
check('重置密码 -> 302', r.status_code == 302)

# 用新密码登录
client.get('/logout')
client.post('/login', data={'username': 'testuser', 'password': 'NewPass999'})
r = client.get('/dashboard')
check('用新密码登录 testuser dashboard -> 200', r.status_code == 200)

# ======== 7. 升级 testuser 为管理员
print('\n[7] 升级 testuser 为管理员')
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})

r = client.post(f'/admin/users/{testuser_id}/toggle-admin', follow_redirects=False)
check('升级为管理员 -> 302', r.status_code == 302)

# 测试升级后能访问 /admin
client.get('/logout')
client.post('/login', data={'username': 'testuser', 'password': 'NewPass999'})
r = client.get('/admin')
check('升级后 testuser 能访问 /admin -> 200', r.status_code == 200)

# 再降级
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})
r = client.post(f'/admin/users/{testuser_id}/toggle-admin', follow_redirects=False)
check('降级为普通用户 -> 302', r.status_code == 302)

# ======== 8. 为用户添加服务器
print('\n[8] 管理员为 testuser 添加服务器')
r = client.post(f'/admin/users/{testuser_id}/create-server',
                data={'name': 'Admin-Added Server', 'host': '127.0.0.1', 'port': '25565',
                      'is_public': 'on'},
                follow_redirects=False)
check('管理员添加服务器 -> 302', r.status_code == 302)

# 切回 testuser 看看
client.get('/logout')
client.post('/login', data={'username': 'testuser', 'password': 'NewPass999'})
r = client.get('/dashboard')
check('testuser dashboard 能看到 Admin-Added Server',
      'Admin-Added Server' in r.data.decode('utf-8', errors='replace'))

# ======== 9. 管理员切换服务器公开状态
print('\n[9] 管理员切换服务器公开状态')
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})

servers = q("SELECT * FROM servers WHERE name = 'Admin-Added Server'")
assert servers
server_id = servers[0]["id"]

r = client.post(f'/admin/servers/{server_id}/toggle-public', follow_redirects=False)
check('切换公开状态 -> 302', r.status_code == 302)

# ======== 10. 编辑服务器
print('\n[10] 管理员编辑服务器')
r = client.post(f'/admin/servers/{server_id}/edit',
                data={'name': 'Edited Server', 'host': '192.168.1.100', 'port': '25566'},
                follow_redirects=False)
check('编辑服务器 -> 302', r.status_code == 302)
s = q("SELECT * FROM servers WHERE id = ?", (server_id,))
check('名称已更新为 Edited Server', s and s[0]["name"] == 'Edited Server')
check('host 已更新为 192.168.1.100', s and s[0]["host"] == '192.168.1.100')
check('port 已更新为 25566', s and s[0]["port"] == 25566)

# ======== 11. 删除服务器
print('\n[11] 管理员删除服务器')
r = client.post(f'/admin/servers/{server_id}/delete', follow_redirects=False)
check('删除服务器 -> 302', r.status_code == 302)
s = q("SELECT * FROM servers WHERE id = ?", (server_id,))
check('服务器已从数据库中消失', len(s) == 0)

# ======== 12. 删除用户
print('\n[12] 管理员删除用户 testuser')
# 加个服务器便于确认级联
r = client.post(f'/admin/users/{testuser_id}/create-server',
                data={'name': 'To-Be-Deleted', 'host': '10.0.0.1', 'port': '25565'},
                follow_redirects=False)
check('添加测试服务器 -> 302', r.status_code == 302)

r = client.post(f'/admin/users/{testuser_id}/delete', follow_redirects=False)
check('删除 testuser -> 302', r.status_code == 302)
u = q("SELECT * FROM users WHERE username = 'testuser'")
check('testuser 已删除', len(u) == 0)
s = q("SELECT * FROM servers WHERE name = 'To-Be-Deleted'")
check('级联删除了 testuser 的服务器', len(s) == 0)

# ======== 13. 保护: 不能删除 admin
print('\n[13] 保护: admin 不能删除自己')
admin_row = q("SELECT * FROM users WHERE id = 1")
admin_id = admin_row[0]["id"]
client.post(f'/admin/users/{admin_id}/delete')
u = q("SELECT * FROM users WHERE id = 1")
check('admin 用户仍然存在', len(u) == 1)

# ======== 14. 保护: 不能把默认 admin 降级
print('\n[14] 保护: 不能把默认 admin 降为普通用户')
client.post(f'/admin/users/1/toggle-admin')
u = q("SELECT * FROM users WHERE id = 1")
check('admin 仍是管理员', (u[0]["is_admin"] or 0) == 1)

# ======== 15. 修改自己的密码
print('\n[15] admin 修改自己密码')
r = client.post('/admin/change-my-password',
                data={'new_password': 'BetterPass987!'}, follow_redirects=False)
check('修改自己密码 -> 302', r.status_code == 302)
client.get('/logout')
r = client.post('/login', data={'username': 'admin', 'password': 'BetterPass987!'}, follow_redirects=False)
check('用新密码登录 admin -> 302', r.status_code == 302)

# ======== 汇总
print('\n' + '=' * 60)
print(f'自测结果: {PASS} 通过, {FAIL} 失败')
if FAIL == 0:
    print('全部通过 ✓')
else:
    print(f'有 {FAIL} 项失败, 请检查')
print('=' * 60)

try: os.remove(TEST_DB)
except FileNotFoundError: pass
sys.exit(0 if FAIL == 0 else 1)
