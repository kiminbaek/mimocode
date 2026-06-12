#!/usr/bin/env python3
"""MiMo Code fnOS Desktop App — Deep Integration Wrapper v0.5.0
Provides: Dashboard, Provider Management, Session Management, Stats, 
Settings, Upgrade, Auto-Restart, Log Viewer, Chat
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
import re
import shutil
import signal

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5670
MIMO_BIN = '/usr/local/bin/mimo'
MIMO_PORT = 5669
AUTH_PATH = '/root/.local/share/mimocode/auth.json'
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'public')
VAR_DIR = '/var/apps/mimocode/var'
CONFIG_PATH = os.path.join(VAR_DIR, 'wrapper_config.json')
LOG_PATH = os.path.join(VAR_DIR, 'mimo.log')
WRAPPER_LOG_PATH = os.path.join(VAR_DIR, 'wrapper.log')
PID_DIR = VAR_DIR

# Default mirrors
MIRRORS = {
    'direct': 'https://github.com',
    'ghproxy': 'https://ghproxy.com/https://github.com',
    'ghproxy2': 'https://mirror.ghproxy.com/https://github.com',
    'custom': '',
}

os.makedirs(VAR_DIR, exist_ok=True)
START_TIME = time.time()


# ============================================================
# helpers
# ============================================================

def log(msg):
    """Write to wrapper log with timestamp."""
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}\n'
    try:
        with open(WRAPPER_LOG_PATH, 'a') as f:
            f.write(line)
    except Exception:
        pass
    sys.stderr.write(line)


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
    """Parse box-style stats output into key-value dict."""
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


def get_mimo_version():
    """Get current mimo version string."""
    try:
        r = subprocess.run([MIMO_BIN, '--version'], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or r.stderr.strip() or 'unknown'
    except Exception:
        return 'unknown'


def get_uptime():
    """Return wrapper uptime formatted string."""
    elapsed = int(time.time() - START_TIME)
    h, m = divmod(elapsed, 3600)
    m, s = divmod(m, 60)
    if h > 0:
        return f'{h}h {m}m {s}s'
    elif m > 0:
        return f'{m}m {s}s'
    return f'{s}s'


# ============================================================
# Status check
# ============================================================

def get_status():
    """Check if mimo processes are running and return detailed status."""
    mimo_web_pid = None
    mimo_web_running = False

    # Check mimo web process
    try:
        r = subprocess.run(['pgrep', '-f', 'mimo web'], capture_output=True, text=True)
        pids = [p.strip() for p in r.stdout.strip().split('\n') if p.strip()]
        if pids:
            mimo_web_running = True
            mimo_web_pid = pids[0]
    except Exception:
        pass

    # Check port listening (more reliable)
    port_open = False
    try:
        r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True)
        port_open = f':{MIMO_PORT}' in r.stdout
    except Exception:
        pass

    # Check PID file
    mimo_pid_file = os.path.join(PID_DIR, 'mimo.pid')
    pid_from_file = None
    if os.path.exists(mimo_pid_file):
        try:
            with open(mimo_pid_file) as f:
                pid_from_file = f.read().strip()
        except Exception:
            pass

    return {
        'mimo_web': mimo_web_running,
        'mimo_web_pid': mimo_web_pid,
        'mimo_port_open': port_open,
        'mimo_pid_file': pid_from_file,
        'wrapper': True,
        'wrapper_pid': os.getpid(),
        'uptime': get_uptime(),
        'version': get_mimo_version(),
    }


# ============================================================
# Logging
# ============================================================

def get_recent_logs(limit=50):
    """Return recent log lines from unified log."""
    lines = []
    try:
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
                lines = all_lines[-limit:]
        # Also include wrapper log
        wrapper_lines = []
        if os.path.exists(WRAPPER_LOG_PATH):
            with open(WRAPPER_LOG_PATH, encoding='utf-8', errors='replace') as f:
                wl = f.readlines()
                wrapper_lines = [f'[wrapper] {l.strip()}' for l in wl[-limit//2:]]
        # Merge and sort by timestamp
        combined = []
        for l in lines:
            stripped = l.rstrip('\n')
            if stripped:
                combined.append(('mimo', stripped))
        for l in wrapper_lines:
            if l.strip():
                combined.append(('wrapper', l.strip()))
        # Simple sort by timestamp prefix
        combined.sort(key=lambda x: x[1][:20] if x[1].startswith('[') else '')
        return [{'source': s, 'text': t} for s, t in combined[-limit:]]
    except Exception as e:
        return [{'source': 'system', 'text': f'Failed to read logs: {e}'}]


# ============================================================
# Upgrade & Mirror support
# ============================================================

def check_latest_version(mirror_key='direct', custom_url=''):
    """Check GitHub for latest mimo release version."""
    base_url = MIRRORS.get(mirror_key, 'direct')
    if mirror_key == 'custom' and custom_url:
        base_url = custom_url.rstrip('/')
    
    api_url = f'{base_url}/XiaomiMiMo/MiMo-Code/releases/latest'
    
    try:
        r = subprocess.run(
            ['/usr/bin/curl', '-sL', '--connect-timeout', '10', '--max-time', '15',
             '-H', 'Accept: application/json', api_url],
            capture_output=True, text=True, timeout=20
        )
        if r.returncode != 0:
            return {'error': f'curl failed: {r.stderr[:200]}'}
        
        data = json.loads(r.stdout)
        tag = data.get('tag_name', '')
        published = data.get('published_at', '')
        # Find linux amd64 asset
        download_url = ''
        for asset in data.get('assets', []):
            name = asset.get('name', '')
            if 'linux' in name.lower() and ('amd64' in name.lower() or 'x86_64' in name.lower()):
                # Rewrite to use mirror
                raw_url = asset.get('browser_download_url', '')
                if mirror_key == 'direct':
                    download_url = raw_url
                elif mirror_key == 'custom' and custom_url:
                    download_url = f'{base_url}/{raw_url.replace("https://github.com/", "")}'
                else:
                    download_url = f'{base_url}/{raw_url.replace("https://github.com/", "")}'
                break
        
        return {
            'tag': tag,
            'version': tag.lstrip('v'),
            'published': published,
            'download_url': download_url,
            'current_version': get_mimo_version(),
        }
    except json.JSONDecodeError as e:
        return {'error': f'API response not JSON: {r.stdout[:200]}'}
    except Exception as e:
        return {'error': str(e)}


def perform_upgrade(download_url, target_version):
    """Download new binary from URL, replace old one, restart service."""
    tmp_bin = '/tmp/mimo_new'
    try:
        # Download
        log(f'Downloading v{target_version} from {download_url[:80]}...')
        r = subprocess.run(
            ['/usr/bin/curl', '-sL', '--connect-timeout', '15', '--max-time', '120',
             '-o', tmp_bin, download_url],
            capture_output=True, text=True, timeout=130
        )
        if r.returncode != 0:
            return {'success': False, 'error': f'Download failed: {r.stderr[:200]}'}
        
        # Verify
        if not os.path.exists(tmp_bin) or os.path.getsize(tmp_bin) < 1024:
            return {'success': False, 'error': 'Downloaded file too small or missing'}
        
        os.chmod(tmp_bin, 0o755)
        
        # Verify it's executable
        r2 = subprocess.run([tmp_bin, '--version'], capture_output=True, text=True, timeout=10)
        new_ver = (r2.stdout.strip() or r2.stderr.strip() or 'unknown')[:50]
        log(f'Downloaded binary version: {new_ver}')
        
        # Check if currently running and kill
        subprocess.run(['pkill', '-f', 'mimo web'], capture_output=True, timeout=5)
        time.sleep(1)
        
        # Replace binary
        target_bin = MIMO_BIN
        # MIMO_BIN is /usr/local/bin/mimo symlink → resolve to real path
        if os.path.islink(target_bin):
            real_path = os.path.realpath(target_bin)
        else:
            real_path = '/var/apps/mimocode/target/bin/mimo'
        
        shutil.copy2(tmp_bin, real_path)
        os.chmod(real_path, 0o755)
        log(f'Binary replaced at {real_path}')
        
        # Clean up temp
        try:
            os.remove(tmp_bin)
        except Exception:
            pass
        
        # Restart mimo web
        _start_mimo_web()
        
        return {
            'success': True,
            'version': target_version,
            'new_version': new_ver,
            'message': f'升级到 v{target_version} 成功！服务已重启。',
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Download timed out (120s)'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _start_mimo_web():
    """Start mimo web process in background."""
    try:
        mimo_pid_file = os.path.join(PID_DIR, 'mimo.pid')
        env = os.environ.copy()
        env['MIMOCODE_PORT'] = str(MIMO_PORT)
        proc = subprocess.Popen(
            [MIMO_BIN, 'web', '--port', str(MIMO_PORT), '--pure'],
            stdout=open(LOG_PATH, 'a'), stderr=subprocess.STDOUT,
            env=env, start_new_session=True
        )
        with open(mimo_pid_file, 'w') as f:
            f.write(str(proc.pid))
        log(f'mimo web started (PID {proc.pid}, port {MIMO_PORT})')
        return True
    except Exception as e:
        log(f'Failed to start mimo web: {e}')
        return False


# ============================================================
# fnOS DB status sync
# ============================================================

def sync_db_status():
    """Sync appcenter DB status to 'running'.
    Retries up to 30s because during install_callback the app record
    hasn't been created yet.
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
                log(f'DB status synced to running (attempt {i+1})')
                return True
            elif i == 0:
                log('DB record not ready yet, will retry...')
        except Exception as e:
            if i == 0:
                log(f'DB sync attempt failed: {e}')
        time.sleep(3)
    log('WARN: DB status sync failed after 10 attempts')
    return False


# ============================================================
# Heartbeat monitor with auto-restart
# ============================================================

def heartbeat_monitor():
    """Monitor mimo web process every 30s; auto-restart if crashed."""
    consecutive_failures = 0
    while True:
        time.sleep(30)
        try:
            r = subprocess.run(['pgrep', '-f', 'mimo web'], capture_output=True, text=True)
            is_running = bool(r.stdout.strip())
            # Also check port
            port_r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True)
            port_open = f':{MIMO_PORT}' in port_r.stdout

            if is_running and port_open:
                consecutive_failures = 0
            elif not is_running and not port_open:
                consecutive_failures += 1
                log(f'mimo web not running (failure #{consecutive_failures}), attempting restart...')
                if _start_mimo_web():
                    consecutive_failures = 0
                    log('Auto-restart successful')
                else:
                    log('Auto-restart failed, will retry')
            else:
                # One of them is OK, probably starting/stopping
                consecutive_failures = 0
        except Exception as e:
            log(f'Heartbeat check error: {e}')


# ============================================================
# Config persistence
# ============================================================

def load_config():
    """Load wrapper config from file."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(config):
    """Save wrapper config to file."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log(f'Config save failed: {e}')
        return False


# ============================================================
# Auth / Provider helpers
# ============================================================

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
# API router
# ============================================================

class APIHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler with JSON API routing.
    Static files are served from PUBLIC_DIR; no directory listing.
    """

    def translate_path(self, path):
        """Map URL paths to PUBLIC_DIR files."""
        path = path.split('?', 1)[0].split('#', 1)[0]
        if path.startswith('/api/'):
            return super().translate_path(path)  # won't be used (handled by do_GET)
        relative = path.lstrip('/')
        if not relative:
            relative = 'index.html'
        result = os.path.join(PUBLIC_DIR, relative)
        # Guard against directory listing
        if os.path.isdir(result):
            return os.path.join(result, 'index.html')
        return result

    def list_directory(self, path):
        """Disable directory listing — return 404."""
        self.send_error(404, 'Not found')
        return None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == '/api/status':
                self._json_response(self._handle_status())
            elif path == '/api/providers':
                self._json_response(self._handle_list_providers())
            elif path == '/api/sessions':
                self._json_response(self._handle_list_sessions(params))
            elif path.startswith('/api/sessions/') and path.endswith('/export'):
                sid = path.split('/')[3]
                self._json_response(self._handle_session_export(sid))
            elif path.startswith('/api/sessions/'):
                sid = path.split('/')[3]
                self._json_response(self._handle_get_session(sid))
            elif path == '/api/stats':
                self._json_response(self._handle_stats())
            elif path == '/api/models':
                self._json_response(self._handle_models())
            elif path == '/api/config':
                self._json_response(self._handle_get_config())
            elif path == '/api/logs':
                limit = int(params.get('limit', [50])[0])
                self._json_response({'logs': get_recent_logs(limit)})
            elif path == '/api/check-update':
                mirror = params.get('mirror', ['direct'])[0]
                custom = params.get('custom_url', [''])[0]
                self._json_response(check_latest_version(mirror, custom))
            elif path == '/api/upgrade/status':
                # Return current upgrade status
                self._json_response({
                    'current_version': get_mimo_version(),
                    'last_check': None,
                    'downloading': False,
                })
            elif path.startswith('/api/upgrade/download-url'):
                # Generate download URL for a given mirror + version
                version = params.get('version', [''])[0]
                mirror = params.get('mirror', ['direct'])[0]
                custom = params.get('custom_url', [''])[0]
                if not version:
                    self._json_response({'error': 'version required'})
                    return
                base_url = MIRRORS.get(mirror, 'direct')
                if mirror == 'custom' and custom:
                    base_url = custom.rstrip('/')
                gh_path = f'XiaomiMiMo/MiMo-Code/releases/download/v{version}/mimo-linux-amd64'
                if mirror == 'direct':
                    url = f'{base_url}/{gh_path}'
                elif mirror == 'custom':
                    url = f'{base_url}/{gh_path}'
                else:
                    url = f'{base_url}/{gh_path}'
                self._json_response({'download_url': url, 'version': version})
            elif path.startswith('/api/providers/test/'):
                provider_id = path.split('/')[4]
                self._json_response(self._handle_test_provider(provider_id))
            else:
                # Static files
                super().do_GET()
        except Exception as e:
            self._json_response({'error': str(e)}, 500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8') if length else '{}'
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        try:
            if path == '/api/providers/add':
                self._json_response(self._handle_add_provider(data))
            elif path == '/api/providers/remove':
                self._json_response(self._handle_remove_provider(data))
            elif path == '/api/sessions/delete':
                self._json_response(self._handle_delete_session(data))
            elif path == '/api/config/save':
                self._json_response(self._handle_save_config(data))
            elif path == '/api/upgrade/do':
                self._json_response(self._handle_upgrade(data))
            elif path == '/api/chat':
                self._json_response(self._handle_chat(data))
            elif path == '/api/restart':
                # Restart the mimo web service
                subprocess.run(['pkill', '-f', 'mimo web'], capture_output=True, timeout=5)
                time.sleep(1)
                ok = _start_mimo_web()
                self._json_response({'success': ok, 'message': '服务已重启' if ok else '重启失败'})
            else:
                self._json_response({'error': 'Not found'}, 404)
        except Exception as e:
            self._json_response({'error': str(e)}, 500)

    # ==========================================================
    # Handler implementations
    # ==========================================================

    def _handle_status(self):
        s = get_status()
        # Get config for mirror info
        cfg = load_config()
        s['mirror'] = cfg.get('mirror', 'direct')
        s['mirror_custom_url'] = cfg.get('mirror_custom_url', '')
        s['dark_mode'] = cfg.get('dark_mode', True)
        # Models count
        models_out, _ = run_mimo('models', timeout=15)
        model_count = len([l for l in models_out.strip().split('\n') if l.strip() and '│' not in l])
        s['models_count'] = model_count
        return s

    def _handle_list_providers(self):
        providers = _read_auth()
        return {'providers': providers}

    def _handle_add_provider(self, data):
        providers = _read_auth()
        api_key = (data.get('api_key') or '').strip()
        if not api_key:
            return {'success': False, 'error': 'API Key 不能为空'}
        new_entry = {'id': data.get('provider', 'openai'), 'key': api_key}
        if data.get('base_url'):
            new_entry['url'] = data['base_url'].strip().rstrip('/')
        # Check for duplicate
        for i, p in enumerate(providers):
            if p.get('id') == new_entry['id']:
                providers[i] = new_entry
                _write_auth(providers)
                return {'success': True, 'message': f'已更新 Provider: {new_entry["id"]}'}
        providers.append(new_entry)
        _write_auth(providers)
        return {'success': True, 'message': f'已添加 Provider: {new_entry["id"]}'}

    def _handle_remove_provider(self, data):
        providers = _read_auth()
        provider_id = data.get('provider', '').strip()
        providers = [p for p in providers if p.get('id') != provider_id]
        _write_auth(providers)
        return {'success': True, 'message': f'已删除 Provider: {provider_id}'}

    def _handle_test_provider(self, provider_id):
        """Test provider connectivity by listing models."""
        providers = _read_auth()
        provider = next((p for p in providers if p.get('id') == provider_id), None)
        if not provider:
            return {'success': False, 'error': f'Provider {provider_id} 未找到'}
        # Set env and run a quick model list
        env = os.environ.copy()
        if provider.get('key'):
            env[provider['id'].upper() + '_API_KEY'] = provider['key']
        if provider.get('url'):
            env[provider['id'].upper() + '_BASE_URL'] = provider['url']
        try:
            start = time.time()
            r = subprocess.run(
                [MIMO_BIN, 'models', provider_id],
                capture_output=True, text=True, timeout=20, env=env
            )
            elapsed = time.time() - start
            if r.returncode == 0 and r.stdout.strip():
                return {'success': True, 'message': f'连接成功！({elapsed:.1f}s)', 'elapsed': round(elapsed, 1)}
            else:
                err = r.stderr.strip()[:200] or '无响应'
                return {'success': False, 'error': err, 'elapsed': round(elapsed, 1)}
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': '连接超时(20s)'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_list_sessions(self, params):
        limit = params.get('limit', ['50'])[0]
        out, _ = run_mimo('ls', '--limit', limit, timeout=15)
        sessions = []
        for line in out.strip().split('\n')[1:]:
            parts = [p.strip() for p in line.split('│') if p.strip()]
            if len(parts) >= 3:
                sessions.append({
                    'id': parts[1] if len(parts) > 1 else parts[0],
                    'name': parts[0],
                    'model': parts[2] if len(parts) > 2 else '',
                    'created': parts[3] if len(parts) > 3 else '',
                })
        return {'sessions': sessions}

    def _handle_get_session(self, sid):
        out, _ = run_mimo('ls')
        for line in out.strip().split('\n')[1:]:
            parts = [p.strip() for p in line.split('│') if p.strip()]
            if len(parts) >= 2 and parts[1] == sid:
                return {'session': {'id': sid, 'name': parts[0]}}
        return {'session': None}

    def _handle_session_export(self, sid):
        out, rc = run_mimo('export', sid, timeout=30)
        if rc != 0:
            return {'success': False, 'error': out[:500]}
        try:
            data = json.loads(out)
            return {'success': True, 'data': data}
        except json.JSONDecodeError:
            return {'success': True, 'data': out}

    def _handle_delete_session(self, data):
        sid = data.get('session_id', '')
        out, rc = run_mimo('delete', sid, timeout=15)
        return {'success': rc == 0, 'message': '已删除' if rc == 0 else out[:200]}

    def _handle_stats(self):
        out, rc = run_mimo('stats', timeout=15)
        stats = parse_box_stats(out) if rc == 0 else {}
        return {'stats': stats}

    def _handle_models(self):
        out, rc = run_mimo('models', '--verbose', timeout=30)
        models = parse_models_verbose(out) if rc == 0 else []
        return {'models': models}

    def _handle_get_config(self):
        cfg = load_config()
        return {
            'config': cfg,
            'mirrors': MIRRORS,
        }

    def _handle_save_config(self, data):
        current = load_config()
        for key in ('mirror', 'mirror_custom_url', 'dark_mode', 'log_limit'):
            if key in data:
                current[key] = data[key]
        ok = save_config(current)
        return {'success': ok, 'message': '设置已保存' if ok else '保存失败'}

    def _handle_upgrade(self, data):
        download_url = data.get('download_url', '')
        version = data.get('version', '')
        if not download_url or not version:
            return {'success': False, 'error': '缺少下载地址或版本号'}
        # Run upgrade in background thread to avoid timeout
        result = perform_upgrade(download_url, version)
        return result

    def _handle_chat(self, data):
        message = data.get('message', '').strip()
        if not message:
            return {'success': False, 'error': '消息不能为空'}
        session_id = data.get('session_id', '')
        provider = data.get('provider', '')
        args = ['run', message]
        if session_id:
            args = ['run', '--session', session_id, message]
        out, rc = run_mimo(*args, timeout=120)
        return {'success': rc == 0, 'response': out, 'returncode': rc}

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    # Suppress default logging
    def log_message(self, fmt, *args):
        pass


# ============================================================
# Entry point
# ============================================================

if __name__ == '__main__':
    log(f'Deep Integration Wrapper v0.5.0 starting on 0.0.0.0:{LISTEN_PORT}')
    sync_db_status()

    # Start heartbeat monitor thread (auto-restart)
    threading.Thread(target=heartbeat_monitor, daemon=True).start()

    # Start HTTP server
    server = http.server.HTTPServer(('0.0.0.0', LISTEN_PORT), APIHandler)
    log(f'HTTP server listening on port {LISTEN_PORT}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log('Shutting down...')
        server.shutdown()
