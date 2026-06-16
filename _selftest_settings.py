#!/usr/bin/env python -u
"""自测：注册开关 & 维护模式"""
import sys, os, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as a

TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_selftest2.db')
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

def assert_text_in(r, text):
    body = r.data.decode('utf-8', errors='replace')
    return text in body

# ============ 1. 默认状态：开启注册，未维护 ============
print('\n[1] 默认状态 - 注册开启，维护关闭')
r = client.get('/')
check('GET / 返回 200', r.status_code == 200)
check('/ 可正常进入主页', assert_text_in(r, 'MC服务器') or assert_text_in(r, '公开') or assert_text_in(r, '服务器'))

r = client.get('/register')
check('GET /register -> 200', r.status_code == 200)
check('注册页显示表单', assert_text_in(r, '<form') and assert_text_in(r, '注册'))

# ============ 2. 关闭注册功能 ============
print('\n[2] 关闭注册功能')
# 先登录 admin
r = client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
check('admin 登录 -> 302', r.status_code == 302)

# 切换注册
r = client.post('/admin/settings/register-toggle', follow_redirects=False)
check('切换注册 -> 302', r.status_code == 302)

r = client.get('/register')
check('关闭后 GET /register -> 200', r.status_code == 200)
check('显示"已关闭注册"字样', assert_text_in(r, '已关闭'))

# 尝试 POST 注册（应返回页面而不是写入数据库）
r = client.post('/register',
                data={'username': 'should_not_work', 'password': '123456', 'confirm': '123456'},
                follow_redirects=False)
check('POST /register 在关闭时仍返回 200', r.status_code == 200)
# 数据库中不应存在此用户
with a.app.app_context():
    row = a.get_db().execute("SELECT 1 FROM users WHERE username = ?", ('should_not_work',)).fetchone()
    check('未写入数据库', row is None)

# ============ 3. 开启维护模式 ============
print('\n[3] 开启维护模式')
r = client.post('/admin/settings/maintenance-toggle', follow_redirects=False)
check('切换维护 -> 302', r.status_code == 302)

# admin 仍可访问主页
r = client.get('/')
check('admin 仍可访问主页', r.status_code == 200)

# admin 可访问管理后台
r = client.get('/admin')
check('admin 仍可访问 /admin -> 200', r.status_code == 200)

# ============ 4. 普通用户登录 - 维护模式下被拒绝 ============
print('\n[4] 普通用户在维护模式下无法登录')
# 创建一个普通用户
with a.app.app_context():
    db = a.get_db()
    db.execute(
        "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, 0, ?)",
        ("normal_user", a.hash_password("UserPass999"), "2026-06-14 00:00:00")
    )
    db.commit()

# 退出 admin
client.get('/logout')

# 普通用户登录 -> 被拦截 -> 转到 maintenance
r = client.post('/login',
                data={'username': 'normal_user', 'password': 'UserPass999'},
                follow_redirects=True)
# 最终页面 URL 应该是 maintenance
# 查看返回的 HTML 中是否含有"维护中"或在 URL 中
body = r.data.decode('utf-8', errors='replace')
check('普通用户登录被拦截', '维护中' in body or '维护' in body or '系统维护' in body)

# 直接访问 /maintenance
r = client.get('/maintenance')
check('GET /maintenance -> 200', r.status_code == 200)
check('maintenance 页含"系统维护中"', assert_text_in(r, '系统维护中') or assert_text_in(r, '维护'))

# ============ 5. 维护模式下访问主页 -> 被重定向到维护页 ============
print('\n[5] 未登录用户访问主页 -> 维护页')
client.get('/logout')
r = client.get('/', follow_redirects=True)
check('GET / -> 被重定向到维护页', '系统维护中' in r.data.decode('utf-8', errors='replace'))

# ============ 6. 维护模式下 /register -> 维护页 ============
print('\n[6] 维护模式下 /register -> 维护页')
r = client.get('/register', follow_redirects=True)
check('GET /register 在维护下 -> 维护页', '系统维护中' in r.data.decode('utf-8', errors='replace') or '维护' in r.data.decode('utf-8', errors='replace'))

# ============ 7. 管理员在维护模式下登录，其他用户被拒绝 ============
print('\n[7] 管理员在维护模式下可登录并进入 /admin')
r = client.post('/login', data={'username': 'admin', 'password': 'admin'}, follow_redirects=False)
check('admin 登录 302', r.status_code == 302)
r = client.get('/admin')
check('admin 可访问 /admin -> 200', r.status_code == 200)

# ============ 8. 关闭维护模式 ============
print('\n[8] 关闭维护模式')
r = client.post('/admin/settings/maintenance-toggle', follow_redirects=False)
check('关闭维护 -> 302', r.status_code == 302)

r = client.get('/')
check('关闭维护后主页可正常访问 -> 200', r.status_code == 200)
body = r.data.decode('utf-8', errors='replace')
check('主页不含"维护中"', '系统维护中' not in body)

# ============ 9. 普通用户现在能正常登录 ============
print('\n[9] 普通用户可正常登录')
client.get('/logout')
r = client.post('/login',
                data={'username': 'normal_user', 'password': 'UserPass999'},
                follow_redirects=False)
check('普通用户登录 -> 302', r.status_code == 302)

# ============ 10. 再次开启注册 -> 用户能重新注册 ============
print('\n[10] 开启注册功能')
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})
r = client.post('/admin/settings/register-toggle', follow_redirects=False)
check('再次切换（现在应为开启注册）-> 302', r.status_code == 302)

client.get('/logout')
r = client.post('/register',
                data={'username': 'fresh_user', 'password': 'FreshPass1', 'confirm': 'FreshPass1'},
                follow_redirects=False)
check('新用户 POST /register 成功 -> 302', r.status_code == 302)
with a.app.app_context():
    row = a.get_db().execute("SELECT 1 FROM users WHERE username = ?", ('fresh_user',)).fetchone()
    check('fresh_user 已写入数据库', row is not None)

# ============ 11. 管理后台页面上的开关卡片显示正确 ============
print('\n[11] /admin 页面含开关卡片')
client.get('/logout')
client.post('/login', data={'username': 'admin', 'password': 'admin'})
r = client.get('/admin')
body = r.data.decode('utf-8', errors='replace')
check('管理后台含"用户注册"卡片', '用户注册' in body)
check('管理后台含"维护模式"卡片', '维护模式' in body)
check('管理后台含切换按钮', '/admin/settings/register-toggle' in body or '/admin/settings/register-toggle' in body)

# ============ 汇总 ============
print('\n' + '=' * 60)
print(f'自测结果: {PASS} 通过, {FAIL} 失败')
if FAIL == 0:
    print('全部通过 ✓')
else:
    print(f'有 {FAIL} 项失败')
print('=' * 60)

try: os.remove(TEST_DB)
except FileNotFoundError: pass
sys.exit(0 if FAIL == 0 else 1)
