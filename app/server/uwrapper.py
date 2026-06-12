#!/usr/bin/env python3
"""MiMo Code fnOS Desktop App — Deep Integration Wrapper v0.4.1
Provides: Dashboard, Provider Management, Session Management, Stats, Settings, Chat
All API calls route to `mimo` CLI commands, parsed to JSON for the frontend.
"""
import http.server
import json
import os
import subprocess
import sys
import urllib.parse
import threading
import time

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5670
MIMO_BIN = '/usr/local/bin/mimo'
AUTH_PATH = '/root/.local/share/mimocode/auth.json'
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'public')


# ============================================================
# helpers
# ============================================================

def run_mimo(*args, timeout=30):
    """Run mimo CLI command and return (stdout, returncode)."""
    try:
        r = subprocess.run(
            [MIMO_BIN] + list(args),
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return 'Command timed out', 1
    except Exception as e:
        return str(e), 1


def parse_box_stats(text):
    """Parse box-style stats output (like mimo stats) into key-value dict."""
    result = {}
    for line in text.strip().split('\n'):
        line = line.strip()
        if '│' in line:
            parts = [p.strip() for p in line.split('│')[1:-1]]
            if len(parts) >= 2 and parts[0] and parts[1]:
                result[parts[0]] = parts[1]
    return result


def parse_models_verbose(output):
    """Parse `mimo models --verbose` output into list of model dicts."""
    models = []
    current = None
    brace_depth = 0
    current_json = ''
    for line in output.split('\n'):
        if not line.strip():
            continue
        if line.strip().startswith('{'):
            brace_depth += line.count('{') - line.count('}')
            current_json += line + '\n'
            if brace_depth == 0:
                try:
                    if current:
                        current['details'] = json.loads(current_json)
                        models.append(current)
                except json.JSONDecodeError:
                    pass
                current_json = ''
                current = None
        elif brace_depth == 0 and not line.strip().startswith('}'):
            if current:
                try:
                    current['details'] = json.loads(current_json)
                    models.append(current)
                except json.JSONDecodeError:
                    pass
                current_json = ''
            current = {'id': line.strip(), 'details': None}
        else:
            current_json += line + '\n'
    if current and current_json:
        try:
            current['details'] = json.loads(current_json)
            models.append(current)
        except json.JSONDecodeError:
            pass
    return models


def get_status():
    """Check if mimo processes are running and return status info."""
    status = {
        'mimo_web': False, 'mimo_web_pid': None,
        'wrapper': True, 'wrapper_pid': os.getpid(),
    }
    try:
        r = subprocess.run(['pgrep', '-f', 'mimo web'], capture_output=True, text=True)
        pids = [p.strip() for p in r.stdout.strip().split('\n') if p.strip()]
        if pids:
            status['mimo_web'] = True
            status['mimo_web_pid'] = pids[0]
    except Exception:
        pass
    return status


def _read_auth():
    """Read auth.json and return list of providers."""
    try:
        if os.path.exists(AUTH_PATH):
            with open(AUTH_PATH, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        return []
    except Exception:
        return []


def _write_auth(providers):
    """Write provider list to auth.json."""
    os.makedirs(os.path.dirname(AUTH_PATH), exist_ok=True)
    with open(AUTH_PATH, 'w', encoding='utf-8') as f:
        json.dump(providers, f, indent=2, ensure_ascii=False)


# ============================================================
# fnOS DB status sync
# ============================================================

def sync_db_status():
    """Sync appcenter DB status to 'running'.
    Retries up to 30s because during install_callback the app record
    hasn't been created yet (M99/M100 deadlock fix).
    """
    app_name = 'mimocode'
    for i in range(10):
        try:
            r = subprocess.run(
                ['sudo', '-u', 'postgres', 'psql', '-d', 'appcenter',
                 '-c', f"UPDATE app SET status='running' WHERE app_name='{app_name}';"],
                capture_output=True, text=True, timeout=5
            )
            if 'UPDATE 1' in r.stdout:
                sys.stderr.write(f'[mimo] DB status synced to running (attempt {i+1})\n')
                return True
            elif i == 0:
                sys.stderr.write('[mimo] DB record not ready yet, will retry...\n')
        except Exception as e:
            if i == 0:
                sys.stderr.write(f'[mimo] DB sync attempt failed: {e}\n')
        time.sleep(3)
    sys.stderr.write('[mimo] WARN: DB status sync failed after 10 attempts\n')
    return False


# ============================================================
# heartbeat monitor (background thread)
# ============================================================

def heartbeat_check():
    """Check mimo web health every 30s; log warnings (no auto-restart)."""
    while True:
        time.sleep(30)
        try:
            r = subprocess.run(['pgrep', '-f', 'mimo web'], capture_output=True, text=True)
            if not r.stdout.strip():
                sys.stderr.write('[mimo] WARN: mimo web process not found (OK if stopped via fnOS)\n')
        except Exception:
            pass


# ============================================================
# API router
# ============================================================

def handle_api(path, method, body):
    """Route API requests and return JSON response."""
    # ---- status / dashboard ----
    if path == '/api/status':
        proc = get_status()
        ver_out, _ = run_mimo('--version')
        models_out, _ = run_mimo('models', '--verbose', timeout=10)
        models = parse_models_verbose(models_out)
        return {
            'version': ver_out,
            'mimo_web': proc['mimo_web'],
            'mimo_web_pid': proc['mimo_web_pid'],
            'wrapper_pid': proc['wrapper_pid'],
            'models': models,
            'models_count': len(models),
        }

    # ---- models ----
    elif path == '/api/models':
        out, rc = run_mimo('models', '--verbose', timeout=10)
        models = parse_models_verbose(out)
        return {'models': models}

    # ---- providers ----
    elif path == '/api/providers':
        out, rc = run_mimo('providers', 'list', timeout=10)
        providers = _read_auth()
        config_out, _ = run_mimo('debug', 'config', timeout=10)
        config_providers = {}
        try:
            config = json.loads(config_out)
            config_providers = config.get('provider', {})
        except json.JSONDecodeError:
            pass
        return {
            'providers': providers,
            'config_providers': config_providers,
            'list_output': out,
        }

    elif path == '/api/providers/add' and method == 'POST':
        # Expect JSON body: {"provider":"openai","api_key":"sk-...","base_url":"https://..."}
        try:
            data = json.loads(body) if body else {}
            provider_name = data.get('provider', '').strip()
            api_key = data.get('api_key', '').strip()
            base_url = data.get('base_url', '').strip() or None
            if not provider_name or not api_key:
                return {'ok': False, 'error': 'provider 和 api_key 不能为空'}, 400

            providers = _read_auth()
            # Check duplicate
            for p in providers:
                if p.get('provider') == provider_name:
                    return {'ok': False, 'error': f'Provider "{provider_name}" 已存在'}, 409

            entry = {'provider': provider_name, 'apiKey': api_key}
            if base_url:
                entry['baseURL'] = base_url
            providers.append(entry)
            _write_auth(providers)
            return {'ok': True, 'output': f'已添加 {provider_name}'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}, 500

    elif path.startswith('/api/providers/remove/') and method == 'DELETE':
        provider_name = path.split('/api/providers/remove/')[1]
        try:
            providers = _read_auth()
            before = len(providers)
            providers = [p for p in providers
                         if p.get('provider') != provider_name
                         and p.get('name') != provider_name]
            if len(providers) == before:
                return {'ok': False, 'error': f'未找到 {provider_name}'}, 404
            _write_auth(providers)
            return {'ok': True, 'output': f'已删除 {provider_name}'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}, 500

    elif path == '/api/providers/logout':
        out, rc = run_mimo('providers', 'logout', timeout=10)
        return {'ok': rc == 0, 'output': out}

    elif path == '/api/providers/whoami':
        out, rc = run_mimo('providers', 'whoami', timeout=10)
        return {'output': out, 'ok': rc == 0}

    # ---- sessions ----
    elif path == '/api/sessions':
        out, rc = run_mimo('session', 'list', '--format', 'json', timeout=10)
        try:
            sessions = json.loads(out)
            return {'sessions': sessions}
        except json.JSONDecodeError:
            return {'sessions': [], 'error': '解析失败', 'raw': out}

    elif path.startswith('/api/sessions/') and '/delete' in path:
        sid = path.split('/')[3]
        out, rc = run_mimo('session', 'delete', sid, timeout=10)
        return {'ok': rc == 0, 'output': out}

    elif path.startswith('/api/sessions/') and '/export' in path:
        sid = path.split('/')[3]
        out, rc = run_mimo('export', sid, timeout=10)
        if rc != 0:
            return {'ok': False, 'output': out}, 500
        # Check if output is a file path
        if os.path.exists(out):
            try:
                with open(out, encoding='utf-8') as f:
                    content = f.read()
                return {'ok': True, 'output': content}
            except Exception as e:
                return {'ok': False, 'error': f'读取导出文件失败: {e}'}, 500
        # Check if it's already JSON
        try:
            json.loads(out)
            return {'ok': True, 'output': out}
        except json.JSONDecodeError:
            # Plain text message
            return {'ok': True, 'output': out, 'message': '文本输出（非 JSON 格式）'}

    # ---- stats ----
    elif path.startswith('/api/stats'):
        days = 30
        if '?' in path:
            qs = urllib.parse.parse_qs(path.split('?', 1)[1])
            days = int(qs.get('days', [30])[0])
        out, rc = run_mimo('stats', '--days', str(days), timeout=10)
        stats = parse_box_stats(out)
        models_out, _ = run_mimo('stats', '--days', str(days), '--models', '5', timeout=10)
        return {'stats': stats, 'raw': out, 'models_raw': models_out, 'days': days}

    # ---- config ----
    elif path == '/api/config':
        out, rc = run_mimo('debug', 'config', timeout=10)
        paths_out, _ = run_mimo('debug', 'paths', timeout=10)
        try:
            config = json.loads(out)
        except json.JSONDecodeError:
            config = {'raw': out}
        return {'config': config, 'paths': paths_out}

    # ---- upgrade ----
    elif path == '/api/upgrade':
        out, rc = run_mimo('upgrade', '--help', timeout=10)
        current_ver, _ = run_mimo('--version', timeout=10)
        return {'current_version': current_ver, 'help': out}

    elif path == '/api/upgrade/do' and method == 'POST':
        out, rc = run_mimo('upgrade', timeout=120)
        return {
            'ok': rc == 0,
            'output': out,
            'note': 'upgrade 会替换二进制文件，但下次重装 fpk 会恢复为打包版本'
        }

    return {'error': 'Not found', 'path': path}, 404


# ============================================================
# HTTP handler
# ============================================================

class WrapperHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if '/api/' not in str(args):
            sys.stderr.write('[mimo] %s\n' % (fmt % args))

    def _set_headers(self, code=200, content_type='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200, 'text/plain')
        self.wfile.write(b'')

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/':
            path = '/index.html'
        if path.startswith('/api/'):
            try:
                result = handle_api(path, 'GET', None)
                code = 200
                if isinstance(result, tuple):
                    result, code = result
            except Exception as e:
                result = {'error': str(e)}
                code = 500
            self._set_headers(code, 'application/json; charset=utf-8')
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
            return
        # Serve static files
        file_path = os.path.join(PUBLIC_DIR, path.lstrip('/'))
        if not os.path.exists(file_path):
            file_path = os.path.join(PUBLIC_DIR, 'index.html')
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            ext = os.path.splitext(file_path)[1].lower()
            ct = {'.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
                  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
                  '.ico': 'image/x-icon'}.get(ext, 'text/plain')
            self._set_headers(200, f'{ct}; charset=utf-8')
            self.wfile.write(content)
        except Exception:
            self._set_headers(404)
            self.wfile.write(b'Not Found')

    def do_POST(self):
        path = self.path.split('?')[0]
        if not path.startswith('/api/'):
            self._set_headers(404)
            self.wfile.write(b'{"error":"Not Found"}')
            return
        body = ''
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length:
                body = self.rfile.read(length).decode()
        except Exception:
            pass
        try:
            result = handle_api(path, 'POST', body)
            code = 200
            if isinstance(result, tuple):
                result, code = result
        except Exception as e:
            result = {'error': str(e)}
            code = 500
        self._set_headers(code, 'application/json; charset=utf-8')
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())

    def do_DELETE(self):
        path = self.path.split('?')[0]
        if not path.startswith('/api/'):
            self._set_headers(404)
            self.wfile.write(b'{"error":"Not Found"}')
            return
        try:
            result = handle_api(path, 'DELETE', None)
            code = 200
            if isinstance(result, tuple):
                result, code = result
        except Exception as e:
            result = {'error': str(e)}
            code = 500
        self._set_headers(code, 'application/json; charset=utf-8')
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode())


# ============================================================
# entry
# ============================================================

if __name__ == '__main__':
    sys.stderr.write(f'[mimo] Deep Integration Wrapper v0.4.1 starting on 0.0.0.0:{LISTEN_PORT}\n')
    t = threading.Thread(target=heartbeat_check, daemon=True)
    t.start()
    # Sync DB status in background (retries until app record exists)
    threading.Thread(target=sync_db_status, daemon=True).start()
    server = http.server.HTTPServer(('0.0.0.0', LISTEN_PORT), WrapperHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write('[mimo] Shutting down\n')
        server.shutdown()
