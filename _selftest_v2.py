#!/usr/bin/env python -u
"""自测脚本：完整端到端测试 (登录+添加服务器+切换公开+主页可见)"""
import sys, os, time, socket, threading, struct, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as a

# 用临时 SQLite 数据库，避免污染用户数据
TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_selfcheck.db')
a.app.config['TESTING'] = True
a.app.config['DATABASE'] = TEST_DB

# 清理旧数据库
try: os.remove(TEST_DB)
except FileNotFoundError: pass

# 初始化新数据库（确保 is_public 列存在）
a.init_db()

client = a.app.test_client()

# ========== 启动一个模拟的 MC 服务器 ==========
mock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
mock_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
mock_sock.bind(('127.0.0.1', 0))
mock_sock.listen(5)
mock_port = mock_sock.getsockname()[1]

def mock_mc_server():
    while True:
        try:
            conn, _ = mock_sock.accept()
        except:
            break
        try:
            conn.recv(4096)
            response = {
                "version": {"name": "Paper 1.20.4", "protocol": 765},
                "players": {"max": 100, "online": 42,
                            "sample": [{"id": "a", "name": "Notch"}]},
                "description": {"text": "Self-check test server"},
                "favicon": "",
            }
            response_bytes = json.dumps(response).encode('utf-8')
            # 手动 VarInt 编码
            def encvi(v):
                out = bytearray()
                u = v & 0xFFFFFFFF
                while True:
                    b = u & 0x7F
                    u >>= 7
                    if u: out.append(b | 0x80)
                    else: out.append(b); break
                return bytes(out)
            payload = encvi(0x00) + encvi(len(response_bytes)) + response_bytes
            pkt = encvi(len(payload)) + payload
            conn.sendall(pkt)

            # ping-pong
            try:
                conn.settimeout(1.5)
                _ = conn.recv(1024)
                conn.sendall(encvi(1) + encvi(0x01) + b'\x00' * 4 + struct.pack('>I', 0x12345678))
            except: pass
        except Exception:
            pass
        finally:
            try: conn.close()
            except: pass

threading.Thread(target=mock_mc_server, daemon=True).start()
time.sleep(0.15)

# ========== 测试函数 ==========
PASS = 0
FAIL = 0

def check(desc, cond):
    global PASS, FAIL
    if cond:
        print('  ✓', desc); PASS += 1
    else:
        print('  ✗', desc); FAIL += 1

def r_status(desc, r, expected_code=200):
    check(f'{desc} HTTP {expected_code} (got {r.status_code})', r.status_code == expected_code)

# ========== 测试 1：公共主页（未登录） ==========
print('\n[测试 1] 公共主页（无需登录）')
r = client.get('/')
check('GET / 返回 200', r.status_code == 200)
check('包含 "公共" 字样', b'\xe5\x85\xac\xe5\x85\xb1' in r.data or '公共'.encode('utf-8') in r.data)
check('包含 "Minecraft" 字样', b'Minecraft' in r.data or 'MC '.encode() in r.data or b'MC' in r.data)

r2 = client.get('/api/public_status')
check('GET /api/public_status 返回 200', r2.status_code == 200)
data = r2.get_json()
check('api_public_status 返回 total/online/offline/total_players',
      all(k in data for k in ('total', 'online', 'offline', 'total_players')))
print('    初始空状态:', {k: data.get(k) for k in ('total', 'online', 'offline', 'total_players')})

# ========== 测试 2：登录受限路由 ==========
print('\n[测试 2] 受保护页面应重定向到登录页')
r3 = client.get('/dashboard', follow_redirects=False)
check('GET /dashboard -> 302', r3.status_code == 302)
r4 = client.get('/api/status', follow_redirects=False)
check('GET /api/status -> 302', r4.status_code == 302)

# ========== 测试 3：注册 & 登录 ==========
print('\n[测试 3] 注册 & 登录')
USER = f'admin_tester_{int(time.time())}'
PASSWD = 'Secret123'

r = client.post('/register',
                data={'username': USER, 'password': PASSWD, 'confirm': PASSWD},
                follow_redirects=False)
check(f'注册用户 {USER} -> 302', r.status_code == 302)

r = client.post('/login',
                data={'username': USER, 'password': PASSWD},
                follow_redirects=False)
check(f'登录 -> 302', r.status_code == 302)

# ========== 测试 4：dashboard 与 添加服务器 ==========
print('\n[测试 4] Dashboard + 添加服务器')
r = client.get('/dashboard')
check('GET /dashboard 返回 200', r.status_code == 200)
check('dashboard 包含 username', USER.encode() in r.data)

r = client.post('/server/add', data={'name': 'Test Public Server', 'host': '127.0.0.1', 'port': str(mock_port)},
                follow_redirects=False)
check('POST /server/add (公网模拟服务器) -> 302', r.status_code == 302)

r = client.post('/server/add', data={'name': 'Test Private Server', 'host': '127.0.0.1', 'port': str(mock_port + 1)},
                follow_redirects=False)
check('POST /server/add (离线服务器) -> 302', r.status_code == 302)

# ========== 测试 5：/api/status 私有 API ==========
print('\n[测试 5] /api/status')
r = client.get('/api/status')
check('GET /api/status (已登录) -> 200', r.status_code == 200)
data = r.get_json()
check('返回 2 台服务器', data.get('total') == 2 or len(data.get('servers', [])) == 2)
# 第一台应在线（模拟服务器），第二台应离线
servers = data.get('servers', [])
online_any = any(s.get('online') for s in servers)
offline_any = any(not s.get('online') for s in servers)
check('至少 1 台在线', online_any)
check('至少 1 台离线', offline_any)
check('每台服务器含 is_public 字段', all('is_public' in s for s in servers))
# 默认应均为私有（False）
check('默认 is_public=False', all(s.get('is_public') is False for s in servers))

# ========== 测试 6：切换公开状态 ==========
print('\n[测试 6] 切换公开状态')
srv1_id = servers[0]['id']
srv2_id = servers[1]['id']

# 设第一台为公开 (AJAX 请求，带 Accept: application/json)
r = client.post(f'/server/{srv1_id}/toggle-public',
                headers={'Accept': 'application/json'})
check(f'POST /server/{srv1_id}/toggle-public -> 200', r.status_code == 200)
data = r.get_json()
check(f'返回 is_public=True', data.get('is_public') is True)

# 设第二台为公开
r = client.post(f'/server/{srv2_id}/toggle-public',
                headers={'Accept': 'application/json'})
check(f'POST /server/{srv2_id}/toggle-public -> 200', r.status_code == 200)

# 再次切换第一台回私有
r = client.post(f'/server/{srv1_id}/toggle-public',
                headers={'Accept': 'application/json'})
data = r.get_json()
check(f'再次切换第一台 -> is_public=False', data.get('is_public') is False)

# 确认 /api/status 返回正确的状态
r = client.get('/api/status')
data = r.get_json()
check('第一台 is_public=False', any(s['id'] == srv1_id and not s.get('is_public') for s in data['servers']))
check('第二台 is_public=True', any(s['id'] == srv2_id and s.get('is_public') for s in data['servers']))

# ========== 测试 7：公共主页 API 只返回公开的服务器 ==========
print('\n[测试 7] /api/public_status 只返回公开的服务器')
r = client.get('/api/public_status')
data = r.get_json()
print(f'    公开总数={data.get("total")} 在线={data.get("online")} 离线={data.get("offline")} 总玩家={data.get("total_players")}')
check('public 返回 1 台服务器', data.get('total') == 1 and len(data.get('servers', [])) == 1)
check('这台是 srv2_id', data['servers'][0]['id'] == srv2_id)

# ========== 测试 8：登出后仍能访问公共主页 ==========
print('\n[测试 8] 登出后仍然可以访问公共主页')
r = client.get('/logout', follow_redirects=False)
check('GET /logout -> 302', r.status_code == 302)

r = client.get('/')
check('GET / -> 200 (未登录仍可访问)', r.status_code == 200)
r = client.get('/api/public_status')
check('GET /api/public_status -> 200 (未登录仍可访问)', r.status_code == 200)

# 未登录的 dashboard 应重定向
r = client.get('/dashboard', follow_redirects=False)
check('GET /dashboard 未登录 -> 302', r.status_code == 302)

# ========== 测试 9：尝试用另一个账号操作他人的服务器 ==========
print('\n[测试 9] 其他账号无法操作他人的服务器')
r = client.post('/register',
                data={'username': 'otheruser', 'password': 'Pass1234', 'confirm': 'Pass1234'},
                follow_redirects=False)
r = client.post('/login',
                data={'username': 'otheruser', 'password': 'Pass1234'},
                follow_redirects=False)
check('登录其他账号成功', r.status_code == 302)

# 尝试切换他人服务器的公开状态 -> 应 404（因为不是自己的）
r = client.post(f'/server/{srv2_id}/toggle-public',
                headers={'Accept': 'application/json'})
check(f'切换他人服务器公开状态 -> 404', r.status_code == 404)

# 尝试删除他人服务器 -> 应 404
r = client.post(f'/server/{srv2_id}/delete', follow_redirects=False)
check(f'删除他人服务器 -> 404', r.status_code == 404)

# ========== 测试 10：错误的参数 ==========
print('\n[测试 10] 参数错误处理')
r = client.post('/server/add', data={'name': 'Bad', 'host': '', 'port': '999999'}, follow_redirects=False)
check('空 host + 大 port -> 302 (flash 错误后回到 dashboard)', r.status_code == 302)

# ========== 测试 11：api/test ==========
print('\n[测试 11] /api/test')
r = client.post('/api/test', data={'host': '127.0.0.1', 'port': str(mock_port)})
data = r.get_json()
check(f'POST /api/test 在线服务器 -> online=True', data.get('online') is True)
check(f'players_online=42', data.get('players_online') == 42)

r = client.post('/api/test', data={'host': '127.0.0.1', 'port': str(mock_port + 100)})
data = r.get_json()
check(f'POST /api/test 离线服务器 -> online=False', data.get('online') is False)

# ========== 汇总 ==========
print('\n' + '=' * 60)
print(f'自测结果：{PASS} 通过, {FAIL} 失败')
if FAIL == 0:
    print('全部通过 ✓')
else:
    print(f'有 {FAIL} 项失败，请检查')
print('=' * 60)

mock_sock.close()
try: os.remove(TEST_DB)
except FileNotFoundError: pass

sys.exit(0 if FAIL == 0 else 1)
