#!/usr/bin/env python3
"""MiMo Code fnOS App Wrapper v0.12.6

设计原则：
- 不再做反向代理（之前的 /mimo-web/ 路径重写完全弃用）
- 「官方会话」由飞牛网关挂在 5669 端口，桌面独立图标直接打开
- 本 wrapper 只负责：登录鉴权、Provider 配置、状态展示、日志诊断
- 简洁 / 离线 / 0 第三方依赖（仅标准库）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_NAME = 'mimocode'
WRAPPER_VERSION = '0.12.6'

LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5670
MIMO_PORT = int(os.environ.get('MIMO_PORT', '5669'))

APP_DEST = Path(os.environ.get('TRIM_APPDEST', f'/vol3/@appcenter/{APP_NAME}'))
PKG_VAR = Path(os.environ.get('TRIM_PKGVAR', f'/vol3/@appdata/{APP_NAME}'))
SERVER_DIR = APP_DEST / 'server'
MIMO_BIN = SERVER_DIR / 'mimo'
MIMO_ASSETS = SERVER_DIR / 'mimo_assets'
PUBLIC_DIR = SERVER_DIR / 'public'

VAR_DIR = PKG_VAR / 'var'
ETC_DIR = PKG_VAR / 'etc'
MIMO_HOME = PKG_VAR / 'mimo_home'
MIMO_CACHE = MIMO_HOME / '.cache' / 'mimocode'
MIMO_DATA = MIMO_HOME / '.local' / 'share' / 'mimocode'
MIMO_CONFIG = MIMO_HOME / '.config' / 'mimocode'

WRAPPER_LOG_PATH = VAR_DIR / 'wrapper.log'
MIMO_LOG_PATH = VAR_DIR / 'mimo.log'
MIMO_PID_PATH = VAR_DIR / 'mimo.pid'
TOKEN_TTL_SECONDS = 12 * 60 * 60
DISABLED_PROVIDERS = {'opencode', 'opencode-go'}

AUTH_PATH = ETC_DIR / 'wrapper_auth.json'
CONFIG_PATH = ETC_DIR / 'wrapper_config.json'

DEFAULT_CONFIG: Dict[str, Any] = {
    'auto_restart_mimo': True,
    'theme': 'dark',
    'project_dir': str(MIMO_HOME / 'workspace'),
    'toolbox_enabled': False,
}

FREE_MODEL_PRESETS = [
    {'provider':'Kilo Code','provider_id':'kilo','base_url':'https://api.kilo.ai/api/gateway','model':'kilo-auto/free','display_name':'Kilo Auto Free','free_type':'免费','requires_key':True,'region':'Global','note':'官方会话未禁用；通常仍需 Kilo API Key。'},
    {'provider':'OpenRouter','provider_id':'openrouter','base_url':'https://openrouter.ai/api/v1','model':'qwen/qwen3-coder:free','display_name':'Qwen3 Coder Free','free_type':'免费模型 / 需 Key','requires_key':True,'region':'Global','note':'官方会话支持；需 OpenRouter API Key。'},
    {'provider':'OpenRouter','provider_id':'openrouter','base_url':'https://openrouter.ai/api/v1','model':'openrouter/free','display_name':'OpenRouter Free Router','free_type':'免费模型 / 需 Key','requires_key':True,'region':'Global','note':'官方会话支持；免费状态以 OpenRouter 实时列表为准。'},
    {'provider':'Groq','provider_id':'groq','base_url':'','model':'llama-3.1-8b-instant','display_name':'Llama 3.1 8B Instant','free_type':'免费额度 / 需 Key','requires_key':True,'region':'Global','note':'官方会话支持 Groq provider；需 API Key。'},
    {'provider':'Google Gemini','provider_id':'google','base_url':'','model':'gemini-2.5-flash','display_name':'Gemini 2.5 Flash','free_type':'免费额度 / 需 Key','requires_key':True,'region':'Global','note':'官方会话支持 Google provider；需 GEMINI/GOOGLE API Key。'},
    {'provider':'DeepSeek','provider_id':'deepseek','base_url':'https://api.deepseek.com','model':'deepseek-v4-flash','display_name':'DeepSeek V4 Flash','free_type':'低价 / 需 Key','requires_key':True,'region':'CN','note':'官方会话支持；需 DeepSeek API Key。'},
    {'provider':'SiliconFlow','provider_id':'siliconflow','base_url':'https://api.siliconflow.com/v1','model':'THUDM/GLM-4-9B-0414','display_name':'GLM-4-9B','free_type':'免费/低价额度 / 需 Key','requires_key':True,'region':'CN','note':'官方会话支持；需 SiliconFlow API Key。'},
]

BACKUP_DIR = VAR_DIR / 'config_backups'


START_TIME = time.time()


def log(msg: str) -> None:
    line = f'[{time.strftime("%Y-%m-%dT%H:%M:%S")}] {msg}\n'
    try:
        WRAPPER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WRAPPER_LOG_PATH, 'a', encoding='utf-8', errors='replace') as f:
            f.write(line)
    except Exception:
        pass
    sys.stderr.write(line)
    sys.stderr.flush()


def safe_json_load(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def safe_json_dump(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)


def port_open(port: int, host: str = '127.0.0.1', timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def read_tail(p: Path, lines: int = 200) -> str:
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return ''.join(f.readlines()[-lines:])
    except Exception:
        return ''


def load_auth() -> Dict[str, Any]:
    return safe_json_load(AUTH_PATH)


def save_auth(data: Dict[str, Any]) -> None:
    safe_json_dump(AUTH_PATH, data)


def hash_password(password: str, salt: bytes) -> str:
    return base64.b64encode(hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)).decode('ascii')


def auth_setup(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hash_password(password, salt)
    secret = secrets.token_hex(32)
    save_auth({
        'salt_b64': base64.b64encode(salt).decode('ascii'),
        'hash': h,
        'secret': secret,
        'created_at': int(time.time()),
    })
    return generate_token(secret)


def auth_login(password: str) -> Optional[str]:
    a = load_auth()
    if not a:
        return None
    salt = base64.b64decode(a.get('salt_b64', ''))
    if hmac.compare_digest(hash_password(password, salt), a.get('hash', '')):
        return generate_token(a.get('secret', ''))
    return None


def generate_token(secret: str) -> str:
    now = int(time.time())
    payload = {'iat': now, 'exp': now + TOKEN_TTL_SECONDS, 'nonce': secrets.token_hex(8)}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8')).rstrip(b'=').decode('ascii')
    sig = hmac.new(secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{body}.{sig}'


def _decode_token_body(body: str) -> Dict[str, Any]:
    pad = '=' * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode((body + pad).encode('ascii')).decode('utf-8'))


def validate_token(token: str) -> bool:
    if not token or '.' not in token:
        return False
    a = load_auth()
    secret = a.get('secret', '')
    if not secret:
        return False
    body, _, sig = token.partition('.')
    expected = hmac.new(secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        payload = _decode_token_body(body)
        exp = int(payload.get('exp') or 0)
        if exp <= int(time.time()):
            return False
    except Exception:
        return False
    return True


def load_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(safe_json_load(CONFIG_PATH))
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    safe_json_dump(CONFIG_PATH, cfg)


def ensure_mimo_home() -> None:
    """确保 MIMO_HOME 存在 + 预下载资源已铺到位。"""
    for d in [MIMO_HOME, MIMO_CACHE, MIMO_DATA, MIMO_CONFIG, MIMO_HOME / 'workspace']:
        d.mkdir(parents=True, exist_ok=True)
    asset_cache = MIMO_ASSETS / 'cache'
    if asset_cache.is_dir():
        for src in asset_cache.rglob('*'):
            if not src.is_file():
                continue
            rel = src.relative_to(asset_cache)
            dst = MIMO_CACHE / rel
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if dst.parent.name == 'bin':
                try:
                    dst.chmod(0o755)
                except Exception:
                    pass


def mimo_env() -> Dict[str, str]:
    env = os.environ.copy()
    env['HOME'] = str(MIMO_HOME)
    env['XDG_CACHE_HOME'] = str(MIMO_HOME / '.cache')
    env['XDG_DATA_HOME'] = str(MIMO_HOME / '.local' / 'share')
    env['XDG_CONFIG_HOME'] = str(MIMO_HOME / '.config')
    env['XDG_STATE_HOME'] = str(MIMO_HOME / '.local' / 'state')
    return env


def mimo_pid() -> Optional[int]:
    try:
        return int(MIMO_PID_PATH.read_text().strip())
    except Exception:
        return None


def mimo_alive() -> bool:
    pid = mimo_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_mimo() -> Tuple[bool, str]:
    if mimo_alive() and port_open(MIMO_PORT):
        return True, 'already running'
    if not MIMO_BIN.exists():
        return False, f'mimo binary missing: {MIMO_BIN}'
    ensure_mimo_home()
    workspace = MIMO_HOME / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)
    env = mimo_env()
    log_f = open(MIMO_LOG_PATH, 'a', buffering=1)
    log_f.write(f'\n=== [{time.strftime("%F %T")}] starting mimo web on {MIMO_PORT} ===\n')
    proc = subprocess.Popen(
        [str(MIMO_BIN), 'web',
         '--hostname', '0.0.0.0',
         '--port', str(MIMO_PORT),
         '--print-logs', '--log-level', 'INFO'],
        cwd=str(workspace),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_f,
        stderr=log_f,
        start_new_session=True,
    )
    MIMO_PID_PATH.write_text(str(proc.pid))
    log(f'mimo started pid={proc.pid}')
    for _ in range(60):
        if port_open(MIMO_PORT):
            return True, f'mimo listening on {MIMO_PORT}'
        if proc.poll() is not None:
            return False, f'mimo exited early rc={proc.returncode}'
        time.sleep(0.5)
    return False, 'mimo did not open port within 30s'


def stop_mimo() -> None:
    pid = mimo_pid()
    if pid:
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        time.sleep(1)
        try:
            os.killpg(pid, signal.SIGKILL)
        except Exception:
            pass
    try:
        MIMO_PID_PATH.unlink()
    except Exception:
        pass
    subprocess.run(['pkill', '-f', f'mimo web.*--port {MIMO_PORT}'], timeout=5, check=False)


def mimo_supervisor():
    while True:
        try:
            cfg = load_config()
            if cfg.get('auto_restart_mimo', True) and not port_open(MIMO_PORT):
                log('[supervisor] mimo down, restarting...')
                start_mimo()
        except Exception as e:
            log(f'[supervisor] error: {e}')
        time.sleep(10)


def run_mimo(args: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    if not MIMO_BIN.exists():
        return -1, '', 'mimo binary missing'
    try:
        p = subprocess.run([str(MIMO_BIN)] + args,
                           env=mimo_env(),
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, '', str(e)


def list_models() -> Dict[str, Any]:
    f = MIMO_CACHE / 'models.json'
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return {}



def official_provider_id(provider_id: str) -> str:
    base = re.sub(r'[^a-zA-Z0-9_]+', '_', str(provider_id or 'custom').strip().lower()).strip('_') or 'custom'
    if base.startswith('fnos_'):
        return base[:64]
    return ('fnos_' + base)[:64]


def read_official_config() -> Dict[str, Any]:
    ensure_mimo_home()
    data = safe_json_load(provider_config_file())
    return data if isinstance(data, dict) else {}


def write_official_config(data: Dict[str, Any]) -> None:
    safe_json_dump(provider_config_file(), data)


def sync_official_model(model: str) -> Dict[str, Any]:
    cfg = read_official_config()
    if model:
        cfg['model'] = model
        cfg.setdefault('small_model', model)
    write_official_config(cfg)
    return {'id': model.split('/', 1)[0] if '/' in model else '', 'model': model, 'path': str(provider_config_file())}


def sync_official_provider(provider_id: str, name: str, base_url: str, api_key: str, model: str) -> Dict[str, Any]:
    cfg = read_official_config()
    official_id = official_provider_id(provider_id)
    provider = cfg.get('provider') if isinstance(cfg.get('provider'), dict) else {}
    models: Dict[str, Any] = {}
    if model:
        models[model] = {'name': model, 'temperature': True, 'tool_call': True}
    provider[official_id] = {
        'npm': '@ai-sdk/openai-compatible',
        'name': name or official_id,
        'options': {'baseURL': base_url, 'apiKey': api_key or 'EMPTY'},
        'models': models,
    }
    cfg['provider'] = provider
    if model:
        cfg['model'] = f'{official_id}/{model}'
        cfg.setdefault('small_model', f'{official_id}/{model}')
    disabled = cfg.get('disabled_providers') if isinstance(cfg.get('disabled_providers'), list) else []
    out: List[str] = []
    for item in list(disabled) + ['opencode', 'opencode-go']:
        if isinstance(item, str) and item not in out and item != official_id:
            out.append(item)
    cfg['disabled_providers'] = out
    write_official_config(cfg)
    return {'id': official_id, 'model': f'{official_id}/{model}' if model else '', 'path': str(provider_config_file())}


def sync_provider_for_official(provider_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    model = str(cfg.get('model') or '').strip()
    name = str(cfg.get('name') or provider_id).strip()
    base_url = str(cfg.get('base_url') or cfg.get('baseURL') or '').strip()
    api_key = str(cfg.get('api_key') or cfg.get('apiKey') or '').strip()
    if provider_id == 'mimo_official' or model.startswith('mimo/') or model.startswith('xiaomi/'):
        return sync_official_model(model)
    return sync_official_provider(provider_id, name, base_url, api_key, model)

def provider_config_file() -> Path:
    return MIMO_CONFIG / 'mimocode.json'


def load_providers() -> Dict[str, Any]:
    cfg = safe_json_load(provider_config_file())
    return cfg.get('provider', {})


def build_official_provider(provider_id: str, cfg: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    provider_id = provider_id.strip()
    model_id = str(cfg.get('model') or '').strip()
    if not model_id:
        return None, '缺少模型 ID'
    models_db = list_models()
    pdata = models_db.get(provider_id, {}) if isinstance(models_db, dict) else {}
    if not isinstance(pdata, dict) or not pdata:
        return None, f'模型库中不存在 Provider: {provider_id}'
    all_models = pdata.get('models') or {}
    if model_id not in all_models:
        return None, f'Provider {provider_id} 不包含模型 {model_id}'
    base_url = str(cfg.get('base_url') or pdata.get('api') or '').strip()
    item: Dict[str, Any] = {
        'name': cfg.get('name') or pdata.get('name') or provider_id,
        'npm': pdata.get('npm') or '@ai-sdk/openai-compatible',
        'models': {model_id: all_models[model_id]},
    }
    if base_url:
        item['api'] = base_url
    api_key = str(cfg.get('api_key') or cfg.get('apiKey') or '').strip()
    if api_key:
        item['options'] = {'apiKey': api_key}
    # 保留工作台可读字段，但用 _wrapper 命名避免污染官方 schema
    item['_wrapper'] = {'model': model_id, 'base_url': base_url, 'requires_key': bool(cfg.get('requires_key', True))}
    return item, None


def save_provider(provider_id: str, cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    built, err = build_official_provider(provider_id, cfg)
    if err:
        return False, err
    model_id = str(cfg.get('model') or '').strip()
    # Official MiMo disables built-in opencode/opencode-go ids in managed config.
    # Keep them visible by writing a fnOS custom alias provider instead:
    #   opencode    -> fnos_opencode
    #   opencode-go -> fnos_opencode_go
    official_id = official_provider_id(provider_id) if provider_id in DISABLED_PROVIDERS else provider_id
    f = provider_config_file()
    full = safe_json_load(f)
    full.setdefault('provider', {})
    # Remove stale direct/alias entries for this logical provider before writing.
    full['provider'].pop(provider_id, None)
    full['provider'].pop(official_provider_id(provider_id), None)
    full['provider'][official_id] = built
    if model_id:
        selected = f'{official_id}/{model_id}'
        full['model'] = selected
        full['small_model'] = selected
    if provider_id in DISABLED_PROVIDERS:
        disabled = full.get('disabled_providers') if isinstance(full.get('disabled_providers'), list) else []
        out: List[str] = []
        for item in list(disabled) + ['opencode', 'opencode-go']:
            if isinstance(item, str) and item not in out and item != official_id:
                out.append(item)
        full['disabled_providers'] = out
    safe_json_dump(f, full)
    return True, None


def delete_provider(provider_id: str) -> bool:
    f = provider_config_file()
    full = safe_json_load(f)
    changed = False
    if 'provider' in full and isinstance(full['provider'], dict):
        for key in {provider_id, official_provider_id(provider_id)}:
            if key in full['provider']:
                del full['provider'][key]
                changed = True
    if changed:
        safe_json_dump(f, full)
    return changed



def free_models_payload() -> Dict[str, Any]:
    models_db = list_models()
    dynamic: List[Dict[str, Any]] = []
    if isinstance(models_db, dict):
        for provider_id, pdata in models_db.items():
            if not isinstance(pdata, dict):
                continue
            models = pdata.get('models', {}) or {}
            provider_name = pdata.get('name') or provider_id
            base_url = pdata.get('api') or pdata.get('base_url') or ''
            if not isinstance(models, dict):
                continue
            for mid, meta in models.items():
                text = (str(mid) + ' ' + str((meta or {}).get('name','') if isinstance(meta, dict) else '')).lower()
                if ':free' in text or 'free' in text:
                    dynamic.append({'provider': provider_name, 'provider_id': provider_id, 'base_url': base_url, 'model': mid, 'display_name': (meta or {}).get('name') or mid if isinstance(meta, dict) else mid, 'free_type': 'models.json 标记免费', 'requires_key': True, 'region': 'Auto', 'note': '从预置模型库自动识别；是否需 Key 以服务商为准。'})
                if len(dynamic) >= 80:
                    break
            if len(dynamic) >= 80:
                break
    items = FREE_MODEL_PRESETS + dynamic
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(item.get('provider', '其他'), []).append(item)
    return {'items': items, 'groups': groups, 'count': len(items), 'warning': '免费模型/免费额度不等于免 API Key；除明确免 Key 的模板外，请按服务商要求填写 Key。'}


def project_overview_payload() -> Dict[str, Any]:
    cfg = load_config()
    root = Path(cfg.get('project_dir') or (MIMO_HOME / 'workspace'))
    root.mkdir(parents=True, exist_ok=True)
    files: List[Dict[str, Any]] = []
    total = 0
    exts: Dict[str, int] = {}
    markers: List[str] = []
    try:
        for item in root.rglob('*'):
            if len(files) >= 300:
                break
            if not item.is_file():
                continue
            st = item.stat(); total += st.st_size
            rel = str(item.relative_to(root))
            files.append({'path': rel, 'size': st.st_size, 'mtime': int(st.st_mtime)})
            ext = item.suffix.lower() or '(无扩展名)'
            exts[ext] = exts.get(ext, 0) + 1
            if item.name in ('package.json','pyproject.toml','go.mod','Cargo.toml','README.md','.gitignore'):
                markers.append(rel)
    except Exception as e:
        return {'root': str(root), 'error': str(e), 'files': [], 'exts': {}, 'markers': []}
    return {'root': str(root), 'file_count': len(files), 'total_size': total, 'exts': exts, 'markers': markers[:50], 'files': files[:120]}


def health_payload() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
    add('Wrapper 端口', port_open(LISTEN_PORT), f'0.0.0.0:{LISTEN_PORT}')
    add('官方会话端口', port_open(MIMO_PORT), f'127.0.0.1:{MIMO_PORT}')
    add('mimo 二进制', MIMO_BIN.exists() and os.access(MIMO_BIN, os.X_OK), str(MIMO_BIN))
    rc, out, err = run_mimo(['--version'], timeout=5)
    add('mimo CLI', rc == 0, (out or err or '').strip()[:200])
    add('预置 models.json', (MIMO_CACHE / 'models.json').exists(), str(MIMO_CACHE / 'models.json'))
    add('预置 rg', (MIMO_CACHE / 'bin' / 'rg').exists(), str(MIMO_CACHE / 'bin' / 'rg'))
    add('Provider 配置', len(load_providers()) > 0, f'{len(load_providers())} 个 Provider')
    return {'ok': all(c['ok'] for c in checks), 'checks': checks, 'status': status_payload()}


def security_payload() -> Dict[str, Any]:
    return {'items': [
        {'title': 'API Key 只保存在本机 NAS', 'level': 'ok', 'detail': str(provider_config_file())},
        {'title': '免费模型不等于免 Key', 'level': 'warn', 'detail': '除明确免 Key 模板外，多数服务商仍需 Key。'},
        {'title': '官方会话独立端口', 'level': 'ok', 'detail': '不走 /mimo-web/ 反向代理，避免路径兼容问题。'},
        {'title': '工具箱白名单', 'level': 'ok', 'detail': '仅执行内置 mimo 命令，不开放任意 shell。'},
        {'title': '项目目录边界', 'level': 'warn', 'detail': '项目概览只扫描配置的 project_dir。'},
    ]}


def list_backups() -> List[Dict[str, Any]]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []
    for item in sorted(BACKUP_DIR.glob('*.json'), reverse=True)[:30]:
        st = item.stat()
        out.append({'name': item.name, 'size': st.st_size, 'mtime': int(st.st_mtime)})
    return out


def create_backup() -> Dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / time.strftime('mimocode-config-%Y%m%d-%H%M%S.json')
    safe_json_dump(target, {'created_at': int(time.time()), 'config': load_config(), 'providers': load_providers()})
    st = target.stat()
    return {'ok': True, 'backup': {'name': target.name, 'size': st.st_size, 'mtime': int(st.st_mtime)}}


def restore_backup(name: str) -> Dict[str, Any]:
    target = (BACKUP_DIR / name).resolve()
    if BACKUP_DIR.resolve() not in target.parents or not target.exists():
        return {'ok': False, 'error': '备份不存在'}
    data = safe_json_load(target)
    if isinstance(data.get('config'), dict):
        save_config({**DEFAULT_CONFIG, **data['config']})
    if isinstance(data.get('providers'), dict):
        full = safe_json_load(provider_config_file())
        full['provider'] = data['providers']
        safe_json_dump(provider_config_file(), full)
    return {'ok': True}


def run_tool(command: str) -> Dict[str, Any]:
    allowed = {'mimo-version': ['--version'], 'mimo-help': ['--help'], 'mimo-web-help': ['web', '--help'], 'mimo-providers': ['providers']}
    if command not in allowed:
        return {'ok': False, 'error': '命令不在白名单'}
    rc, out, err = run_mimo(allowed[command], timeout=12)
    return {'ok': rc == 0, 'rc': rc, 'stdout': out[-4000:], 'stderr': err[-4000:]}


def status_payload() -> Dict[str, Any]:
    cfg = load_config()
    mimo_open = port_open(MIMO_PORT)
    rc, out, err = run_mimo(['--version'], timeout=5)
    cli_ok = rc == 0
    providers = load_providers()
    models_db = list_models()
    return {
        'wrapper_version': WRAPPER_VERSION,
        'mimo_version': (out or err or '').strip()[:60],
        'mimo_open': mimo_open,
        'mimo_port': MIMO_PORT,
        'wrapper_port': LISTEN_PORT,
        'uptime_sec': int(time.time() - START_TIME),
        'providers_count': len(providers),
        'provider_configured': len(providers) > 0,
        'project_dir': cfg.get('project_dir', ''),
        'cli_ok': cli_ok,
        'models_db_count': sum(len(v.get('models', {})) for v in models_db.values()) if isinstance(models_db, dict) else 0,
        'friendly': {
            'service': '运行中' if mimo_open else '未运行',
            'web': '可访问' if mimo_open else '不可访问',
            'provider': '已配置' if providers else '未配置',
            'cli': '可用' if cli_ok else '不可用',
        }
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = f'MiMoWrapper/{WRAPPER_VERSION}'

    def log_message(self, fmt: str, *args: Any) -> None:
        log('%s %s' % (self.client_address[0], fmt % args))

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except Exception:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get('Content-Length') or '0')
        if n <= 0:
            return {}
        raw = self.rfile.read(min(n, 2 * 1024 * 1024)).decode('utf-8', 'replace')
        try:
            return json.loads(raw or '{}')
        except Exception:
            return {}

    def _token(self) -> str:
        auth = self.headers.get('Authorization') or ''
        if auth.lower().startswith('bearer '):
            return auth.split(' ', 1)[1].strip()
        return ''

    def _require_auth(self) -> bool:
        if not validate_token(self._token()):
            self._send_json({'error': '未登录或登录已过期'}, 401)
            return False
        return True

    def do_GET(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path in {'', '/'}:
                self._send_static(PUBLIC_DIR / 'index.html', 'text/html; charset=utf-8')
                return
            if path == '/api/status':
                self._send_json(status_payload())
                return
            if path == '/api/auth/state':
                self._send_json({'setup': bool(load_auth()), 'token_valid': validate_token(self._token())})
                return
            if path == '/api/providers':
                if not self._require_auth():
                    return
                self._send_json({'providers': load_providers(), 'models': list_models(), 'presets': FREE_MODEL_PRESETS})
                return
            if path == '/api/config':
                if not self._require_auth():
                    return
                self._send_json(load_config())
                return
            if path == '/api/free-models':
                if not self._require_auth():
                    return
                self._send_json(free_models_payload())
                return
            if path == '/api/overview':
                if not self._require_auth():
                    return
                self._send_json(project_overview_payload())
                return
            if path == '/api/health':
                if not self._require_auth():
                    return
                self._send_json(health_payload())
                return
            if path == '/api/security':
                if not self._require_auth():
                    return
                self._send_json(security_payload())
                return
            if path == '/api/backups':
                if not self._require_auth():
                    return
                self._send_json({'backups': list_backups()})
                return
            if path == '/api/logs/wrapper':
                if not self._require_auth():
                    return
                self._send_json({'log': read_tail(WRAPPER_LOG_PATH, 200)})
                return
            if path == '/api/logs/mimo':
                if not self._require_auth():
                    return
                self._send_json({'log': read_tail(MIMO_LOG_PATH, 200)})
                return
            if path.startswith('/css/') or path.startswith('/js/') or path.startswith('/images/'):
                rel = path.lstrip('/')
                local = (PUBLIC_DIR / rel).resolve()
                try:
                    local.relative_to(PUBLIC_DIR.resolve())
                except ValueError:
                    self.send_response(403)
                    self.end_headers()
                    return
                if not local.exists():
                    self.send_response(404)
                    self.end_headers()
                    return
                ext = local.suffix.lower()
                ct = {
                    '.css': 'text/css; charset=utf-8',
                    '.js': 'application/javascript; charset=utf-8',
                    '.png': 'image/png',
                    '.svg': 'image/svg+xml',
                    '.ico': 'image/x-icon',
                }.get(ext, 'application/octet-stream')
                self._send_static(local, ct)
                return
            self.send_response(404)
            self.end_headers()
        except Exception as e:
            log(f'GET error: {e}')
            self._send_json({'error': str(e)}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path == '/api/auth/setup':
                if load_auth():
                    self._send_json({'error': '已初始化，请使用登录'}, 409)
                    return
                data = self._read_json()
                pwd = data.get('password', '')
                if not pwd or len(pwd) < 4:
                    self._send_json({'error': '密码至少 4 位'}, 400)
                    return
                token = auth_setup(pwd)
                self._send_json({'token': token})
                return
            if path == '/api/auth/login':
                data = self._read_json()
                token = auth_login(data.get('password', ''))
                if not token:
                    self._send_json({'error': '密码错误'}, 401)
                    return
                self._send_json({'token': token})
                return
            if path == '/api/providers/save':
                if not self._require_auth():
                    return
                data = self._read_json()
                pid = data.get('id', '').strip()
                if not pid:
                    self._send_json({'error': '缺少 id'}, 400)
                    return
                cfg = {k: v for k, v in data.items() if k != 'id'}
                ok, err = save_provider(pid, cfg)
                if not ok:
                    self._send_json({'error': err or '保存 Provider 失败'}, 400)
                    return
                stop_mimo()
                restarted, restart_msg = start_mimo()
                self._send_json({'ok': True, 'restarted': restarted, 'restart_msg': restart_msg, 'msg': 'Provider 已写入官方配置并已重启官方会话'})
                return
            if path == '/api/providers/delete':
                if not self._require_auth():
                    return
                data = self._read_json()
                pid = data.get('id', '').strip()
                ok = delete_provider(pid)
                self._send_json({'ok': ok})
                return
            if path == '/api/config/save':
                if not self._require_auth():
                    return
                data = self._read_json()
                cfg = load_config()
                cfg.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
                save_config(cfg)
                self._send_json({'ok': True, 'config': cfg})
                return
            if path == '/api/mimo/restart':
                if not self._require_auth():
                    return
                stop_mimo()
                ok, msg = start_mimo()
                self._send_json({'ok': ok, 'msg': msg})
                return
            if path == '/api/backups/create':
                if not self._require_auth():
                    return
                self._send_json(create_backup())
                return
            if path == '/api/backups/restore':
                if not self._require_auth():
                    return
                data = self._read_json()
                self._send_json(restore_backup(data.get('name', '')))
                return
            if path == '/api/tool/run':
                if not self._require_auth():
                    return
                data = self._read_json()
                self._send_json(run_tool(data.get('command', '')))
                return
            self.send_response(404)
            self.end_headers()
        except Exception as e:
            log(f'POST error: {e}')
            self._send_json({'error': str(e)}, 500)


class ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> int:
    for d in [VAR_DIR, ETC_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    log(f'wrapper {WRAPPER_VERSION} starting on 0.0.0.0:{LISTEN_PORT} (mimo on {MIMO_PORT})')
    log(f'  APP_DEST={APP_DEST}')
    log(f'  PKG_VAR={PKG_VAR}')
    log(f'  MIMO_BIN={MIMO_BIN} exists={MIMO_BIN.exists()}')
    log(f'  MIMO_HOME={MIMO_HOME}')

    ensure_mimo_home()

    # 启动 mimo（5669）
    ok, msg = start_mimo()
    log(f'start_mimo: ok={ok} msg={msg}')

    # 后台 supervisor 看着 mimo
    threading.Thread(target=mimo_supervisor, daemon=True).start()

    server = ThreadingHTTPServer(('0.0.0.0', LISTEN_PORT), Handler)

    def shutdown(_sig, _frame):
        log('wrapper shutting down...')
        try:
            stop_mimo()
        except Exception:
            pass
        try:
            server.shutdown()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        shutdown(None, None)
    return 0


if __name__ == '__main__':
    sys.exit(main())
