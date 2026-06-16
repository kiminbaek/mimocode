#!/usr/bin/env python3
"""MiMo Code fnOS App Wrapper v0.11.9

User-first wrapper around the official `mimo` binary.
- opens to the main conversation workspace
- first-run Provider guide
- Chinese, actionable status/errors
- session/project/model helpers
- safe config import/export and diagnostic bundle
- no binary replacement from the UI
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
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
import tarfile
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

APP_NAME = 'mimocode'
WRAPPER_VERSION = '0.11.14'
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5670
MIMO_PORT = int(os.environ.get('MIMO_PORT', '5669'))
MIMO_BIN = os.environ.get('MIMO_BIN', '/usr/local/bin/mimo')
VAR_DIR = Path(os.environ.get('MIMOCODE_VAR_DIR', '/var/apps/mimocode/var'))
ETC_DIR = Path(os.environ.get('MIMOCODE_ETC_DIR', '/var/apps/mimocode/etc'))
PUBLIC_DIR = Path(__file__).resolve().parent / 'public'
AUTH_PATH = ETC_DIR / 'wrapper_auth.json'
CONFIG_PATH = ETC_DIR / 'wrapper_config.json'
MIMO_HOME = Path(os.environ.get('MIMOCODE_HOME_DIR', str(VAR_DIR / 'mimo_home')))
MIMO_CONFIG_PATH = MIMO_HOME / 'config' / 'config.json'
MIMO_AUTH_PATH = Path(os.environ.get('MIMOCODE_AUTH_PATH', str(MIMO_HOME / 'data' / 'auth.json')))
MIMO_LOG_PATH = VAR_DIR / 'mimo.log'
WRAPPER_LOG_PATH = VAR_DIR / 'wrapper.log'
MIMO_PID_PATH = VAR_DIR / 'mimo.pid'
SESSIONS_PATH = VAR_DIR / 'sessions.json'
DIAG_PATH = VAR_DIR / 'diagnostic_bundle.json'
BACKUP_DIR = VAR_DIR / 'config_backups'
MIMO_WEB_ROOT_PROXY_PREFIXES = (
    '/provider', '/project', '/path', '/agent', '/config', '/session',
    '/command', '/question', '/permission', '/vcs', '/mcp', '/global',
    '/assets', '/file',
)

SAFE_TEXT_LIMIT = 160 * 1024
DEFAULT_CONFIG: Dict[str, Any] = {
    'auto_restart_mimo': True,
    'theme': 'dark',
    'provider_key_visible': False,
    'native_web_enabled': True,
    'github_mirror': 'direct',
    'default_provider': '',
    'default_model': '',
    'project_dir': str(Path.home()),
    'last_session_id': '',
    'advanced_visible': False,
    'toolbox_enabled': False,
}
OFFICIAL_MODELS = [
    'mimo/mimo-auto',
    'xiaomi/mimo-v2-flash',
    'xiaomi/mimo-v2-omni',
    'xiaomi/mimo-v2-pro',
    'xiaomi/mimo-v2.5',
    'xiaomi/mimo-v2.5-pro',
    'xiaomi/mimo-v2.5-pro-ultraspeed',
]

MODEL_META: Dict[str, Dict[str, Any]] = {
    'mimo/mimo-auto': {'group': 'MiMo 官方', 'tier': 'free_limited', 'free': True, 'badge': '官方默认 / 限时免费', 'desc': '首次使用推荐，自动选择合适的 MiMo 官方模型。'},
    'xiaomi/mimo-v2-flash': {'group': 'MiMo 官方', 'tier': 'free_limited', 'free': True, 'badge': '限时免费', 'desc': '轻量快速，适合日常问答和代码解释。'},
    'xiaomi/mimo-v2-omni': {'group': 'MiMo 官方', 'tier': 'standard', 'free': False, 'badge': '多模态', 'desc': '官方 omni 模型，是否免费以官方账号权益为准。'},
    'xiaomi/mimo-v2-pro': {'group': 'MiMo 官方', 'tier': 'paid_or_quota', 'free': False, 'badge': 'Pro', 'desc': '更强推理能力，适合复杂代码任务。'},
    'xiaomi/mimo-v2.5': {'group': 'MiMo 官方', 'tier': 'paid_or_quota', 'free': False, 'badge': '2.5', 'desc': '新版通用模型，额度以官方为准。'},
    'xiaomi/mimo-v2.5-pro': {'group': 'MiMo 官方', 'tier': 'paid_or_quota', 'free': False, 'badge': '2.5 Pro', 'desc': '新版 Pro 模型，适合复杂项目分析。'},
    'xiaomi/mimo-v2.5-pro-ultraspeed': {'group': 'MiMo 官方', 'tier': 'paid_or_quota', 'free': False, 'badge': '极速', 'desc': '低延迟 Pro 变体。'},
}

def model_meta(name: str) -> Dict[str, Any]:
    meta = MODEL_META.get(name, {})
    group = meta.get('group') or ('MiMo 官方' if name in OFFICIAL_MODELS else '第三方 / 自定义')
    return {'name': name, 'group': group, 'free': bool(meta.get('free', False)), 'tier': meta.get('tier', 'unknown'), 'badge': meta.get('badge', ''), 'desc': meta.get('desc', '')}

def grouped_models(models: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for m in models:
        item = model_meta(m)
        groups.setdefault(str(item['group']), []).append(item)
    return groups

FREE_MODEL_LIBRARY: List[Dict[str, Any]] = [
    # MiMo official
    {'provider': 'MiMo 官方', 'provider_id': 'mimo_official', 'base_url': '', 'model': 'mimo/mimo-auto', 'display_name': 'mimo/mimo-auto', 'free_type': '官方默认 / 限时免费', 'requires_key': False, 'region': 'CN', 'source': 'MiMo 官方模型列表', 'note': '官方默认模型，推荐首次使用；免费状态以 MiMo 官方账号权益为准。'},
    {'provider': 'MiMo 官方', 'provider_id': 'mimo_official', 'base_url': '', 'model': 'xiaomi/mimo-v2-flash', 'display_name': 'xiaomi/mimo-v2-flash', 'free_type': '限时免费', 'requires_key': False, 'region': 'CN', 'source': 'MiMo 官方模型列表', 'note': '轻量快速，适合日常代码问答；额度以官方为准。'},

    # QwenPaw provider_manager.py: OPENCODE_MODELS / PROVIDER_OPENCODE
    {'provider': 'OpenCode', 'provider_id': 'opencode', 'base_url': 'https://opencode.ai/zen/v1', 'model': 'deepseek-v4-flash-free', 'display_name': 'DeepSeek V4 Flash', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'OpenCode 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'OpenCode', 'provider_id': 'opencode', 'base_url': 'https://opencode.ai/zen/v1', 'model': 'mimo-v2.5-free', 'display_name': 'Mimo V2.5', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'OpenCode 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'OpenCode', 'provider_id': 'opencode', 'base_url': 'https://opencode.ai/zen/v1', 'model': 'nemotron-3-ultra-free', 'display_name': 'Nemotron 3 Ultra', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'OpenCode 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'OpenCode', 'provider_id': 'opencode', 'base_url': 'https://opencode.ai/zen/v1', 'model': 'nemotron-3-super-free', 'display_name': 'Nemotron 3 Super', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'OpenCode 免费 Provider，QwenPaw 标记 require_api_key=False。'},

    # QwenPaw provider_manager.py: KILO_MODELS / PROVIDER_KILO
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'kilo-auto/free', 'display_name': 'Kilo Auto (Free Router)', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'nvidia/nemotron-3-ultra-550b-a55b:free', 'display_name': 'Nemotron 3 Ultra 550B', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'nvidia/nemotron-3-super-120b-a12b:free', 'display_name': 'Nemotron 3 Super 120B', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'poolside/laguna-m.1:free', 'display_name': 'Poolside Laguna M.1', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'poolside/laguna-xs.2:free', 'display_name': 'Poolside Laguna XS.2', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'stepfun/step-3.7-flash:free', 'display_name': 'Step 3.7 Flash', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},
    {'provider': 'Kilo Code', 'provider_id': 'kilo', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'nex-agi/nex-n2-pro:free', 'display_name': 'Nex N2 Pro', 'free_type': '免费', 'requires_key': False, 'region': 'Global', 'source': '参考 QwenPaw provider_manager.py', 'note': 'Kilo Code 免费 Provider，QwenPaw 标记 require_api_key=False。'},

    # QwenPaw free-tier providers that require API Key / OAuth
    {'provider': 'OpenRouter', 'provider_id': 'openrouter', 'base_url': 'https://openrouter.ai/api/v1', 'model': ':free', 'display_name': '连接 OpenRouter 以使用免费模型', 'free_type': '免费模型入口 / 需 Key 或 OAuth', 'requires_key': True, 'region': 'Global', 'source': '参考 QwenPaw PROVIDER_OPENROUTER', 'note': 'OpenRouter 免费模型动态变化；QwenPaw 使用模型发现并按免费标记筛选。'},
    {'provider': 'GitHub Models', 'provider_id': 'github-models', 'base_url': 'https://models.inference.ai.azure.com', 'model': 'gpt-4o-mini', 'display_name': 'GPT-4o Mini', 'free_type': '免费/试用额度 / 需 GitHub Token', 'requires_key': True, 'region': 'Global', 'source': '参考 QwenPaw GITHUB_MODELS_MODELS', 'note': 'GitHub Models 免费额度以 GitHub 官方政策为准。'},
    {'provider': 'GitHub Models', 'provider_id': 'github-models', 'base_url': 'https://models.inference.ai.azure.com', 'model': 'gpt-4o', 'display_name': 'GPT-4o', 'free_type': '免费/试用额度 / 需 GitHub Token', 'requires_key': True, 'region': 'Global', 'source': '参考 QwenPaw GITHUB_MODELS_MODELS', 'note': 'GitHub Models 免费额度以 GitHub 官方政策为准。'},
    {'provider': 'GitHub Models', 'provider_id': 'github-models', 'base_url': 'https://models.inference.ai.azure.com', 'model': 'Meta-Llama-3.1-405B-Instruct', 'display_name': 'Llama 3.1 405B', 'free_type': '免费/试用额度 / 需 GitHub Token', 'requires_key': True, 'region': 'Global', 'source': '参考 QwenPaw GITHUB_MODELS_MODELS', 'note': 'GitHub Models 免费额度以 GitHub 官方政策为准。'},
    {'provider': 'GitHub Models', 'provider_id': 'github-models', 'base_url': 'https://models.inference.ai.azure.com', 'model': 'Meta-Llama-3.1-8B-Instruct', 'display_name': 'Llama 3.1 8B', 'free_type': '免费/试用额度 / 需 GitHub Token', 'requires_key': True, 'region': 'Global', 'source': '参考 QwenPaw GITHUB_MODELS_MODELS', 'note': 'GitHub Models 免费额度以 GitHub 官方政策为准。'},
    {'provider': 'Zhipu (BigModel)', 'provider_id': 'zhipu-cn', 'base_url': 'https://open.bigmodel.cn/api/paas/v4', 'model': 'GLM-5-Flash', 'display_name': 'GLM-5 Flash', 'free_type': '免费/试用额度 / 需 API Key', 'requires_key': True, 'region': 'CN', 'source': '参考 QwenPaw PROVIDER_ZHIPU_CN', 'note': 'QwenPaw 标记 is_free_tier=True；具体额度以智谱控制台为准。'},
    {'provider': 'SiliconFlow (China)', 'provider_id': 'siliconflow-cn', 'base_url': 'https://api.siliconflow.cn/v1', 'model': '', 'display_name': '连接 SiliconFlow (China) 以使用免费模型', 'free_type': '免费模型入口 / 需 API Key', 'requires_key': True, 'region': 'CN', 'source': '参考 QwenPaw PROVIDER_SILICONFLOW_CN', 'note': 'SiliconFlow 免费模型动态变化；模型名以平台模型列表为准。'},
    {'provider': 'SiliconFlow (International)', 'provider_id': 'siliconflow-intl', 'base_url': 'https://api.siliconflow.com/v1', 'model': '', 'display_name': '连接 SiliconFlow (International) 以使用免费模型', 'free_type': '免费模型入口 / 需 API Key', 'requires_key': True, 'region': 'Global', 'source': '参考 QwenPaw PROVIDER_SILICONFLOW_INTL', 'note': 'SiliconFlow 免费模型动态变化；模型名以平台模型列表为准。'},
]

def free_model_library() -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in FREE_MODEL_LIBRARY:
        groups.setdefault(str(item.get('provider') or '其他'), []).append(item)
    return {
        'ok': True,
        'updated_at': '2026-06-16',
        'notice': '免费/限免/试用状态会随平台策略变化；本页参考 QwenPaw provider 配置结构整理常见入口和模型名预设，不复制其运行时代码，不保证长期免费。',
        'models': FREE_MODEL_LIBRARY,
        'groups': groups,
    }

PROVIDER_PRESETS = [
    {'id': 'mimo_official', 'name': 'MiMo 官方模型', 'base_url': '', 'model': 'mimo/mimo-auto', 'models': OFFICIAL_MODELS, 'official': True, 'requires_key': False, 'hint': '官方默认/限时免费，推荐首次使用；不需要在这里填写 Base URL 和 API Key。'},
    {'id': 'opencode', 'name': 'OpenCode', 'base_url': 'https://opencode.ai/zen/v1', 'model': 'deepseek-v4-flash-free', 'models': ['deepseek-v4-flash-free', 'mimo-v2.5-free', 'nemotron-3-ultra-free', 'nemotron-3-super-free'], 'requires_key': False, 'hint': '免费 Provider，可不填写 API Key；免费状态以平台实时政策为准。'},
    {'id': 'kilo', 'name': 'Kilo Code', 'base_url': 'https://api.kilo.ai/api/gateway', 'model': 'kilo-auto/free', 'models': ['kilo-auto/free', 'nvidia/nemotron-3-ultra-550b-a55b:free', 'nvidia/nemotron-3-super-49b-v1.5:free', 'poolside/laguna-m.1:free', 'poolside/laguna-xs.2:free', 'stepfun/step-3.7-flash:free', 'nex-agi/nex-n2-pro:free'], 'requires_key': False, 'hint': '免费 Provider，可不填写 API Key；免费状态以平台实时政策为准。'},
    {'id': 'openrouter', 'name': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1', 'model': 'google/gemini-2.0-flash-exp:free', 'models': ['google/gemini-2.0-flash-exp:free', 'meta-llama/llama-3.1-8b-instruct:free'], 'requires_key': True, 'hint': '可选择免费模型，但通常仍需要 OpenRouter API Key 或账号授权。'},
    {'id': 'github_models', 'name': 'GitHub Models', 'base_url': 'https://models.inference.ai.azure.com', 'model': 'gpt-4o-mini', 'requires_key': True, 'hint': 'GitHub Models 试用/免费额度以 GitHub 官方政策为准，通常需要 Token。'},
    {'id': 'zhipu', 'name': '智谱 GLM', 'base_url': 'https://open.bigmodel.cn/api/paas/v4', 'model': 'glm-4-flash', 'requires_key': True, 'hint': 'glm-4-flash 等免费/试用政策以智谱平台实时政策为准。'},
    {'id': 'openai', 'name': 'OpenAI 兼容', 'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini', 'requires_key': True, 'hint': '适合所有兼容 OpenAI Chat Completions 的服务。'},
    {'id': 'deepseek', 'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com/v1', 'model': 'deepseek-chat', 'requires_key': True, 'hint': '国产常用，Key 从 DeepSeek 控制台获取。'},
    {'id': 'siliconflow', 'name': '硅基流动 SiliconFlow', 'base_url': 'https://api.siliconflow.cn/v1', 'model': 'deepseek-ai/DeepSeek-V3', 'requires_key': True, 'hint': '国内访问友好，模型名以控制台为准。'},
    {'id': 'siliconflow_intl', 'name': 'SiliconFlow International', 'base_url': 'https://api.siliconflow.com/v1', 'model': 'Qwen/Qwen2.5-7B-Instruct', 'requires_key': True, 'hint': '国际站免费/试用模型以平台实时政策为准。'},
    {'id': 'kimi', 'name': 'Kimi / Moonshot', 'base_url': 'https://api.moonshot.cn/v1', 'model': 'moonshot-v1-8k', 'requires_key': True, 'hint': '长上下文模型，Key 从 Moonshot 控制台获取。'},
    {'id': 'custom', 'name': '自定义 OpenAI 兼容', 'base_url': '', 'model': '', 'requires_key': True, 'hint': '填写服务商给你的 Base URL、API Key 和模型名。'},
]

VAR_DIR.mkdir(parents=True, exist_ok=True)
ETC_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
START_TIME = time.time()


def log(msg: str) -> None:
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    try:
        with WRAPPER_LOG_PATH.open('a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    try:
        sys.stderr.write(line + '\n')
    except Exception:
        pass


def json_load(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f'json_load failed {path}: {e}')
        return default


def json_save(path: Path, data: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    saved = json_load(CONFIG_PATH, {})
    if isinstance(saved, dict):
        cfg.update(saved)
    return cfg


def save_config_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    cfg = load_config()
    for k in DEFAULT_CONFIG:
        if k in patch:
            cfg[k] = patch[k]
    json_save(CONFIG_PATH, cfg)
    return cfg


def pbkdf2_hash(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 200_000)
    return salt, base64.b64encode(dk).decode('ascii')


def auth_state() -> Dict[str, Any]:
    data = json_load(AUTH_PATH, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault('sessions', {})
    return data


def is_setup() -> bool:
    data = auth_state()
    return bool(data.get('password_hash') and data.get('salt'))


def verify_password(password: str) -> bool:
    data = auth_state()
    salt = data.get('salt')
    expected = data.get('password_hash')
    if not salt or not expected:
        return False
    _, got = pbkdf2_hash(password, salt)
    return hmac.compare_digest(got, expected)


def create_session() -> str:
    data = auth_state()
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    data.setdefault('sessions', {})[hashlib.sha256(token.encode()).hexdigest()] = {
        'created_at': now,
        'last_seen': now,
        'expires_at': now + 7 * 24 * 3600,
    }
    json_save(AUTH_PATH, data)
    return token


def validate_token(token: str) -> bool:
    if not token:
        return False
    data = auth_state()
    sessions = data.get('sessions') or {}
    key = hashlib.sha256(token.encode()).hexdigest()
    sess = sessions.get(key)
    now = int(time.time())
    if not sess or int(sess.get('expires_at', 0)) < now:
        if key in sessions:
            sessions.pop(key, None)
            data['sessions'] = sessions
            json_save(AUTH_PATH, data)
        return False
    sess['last_seen'] = now
    if now % 20 == 0:
        data['sessions'] = sessions
        json_save(AUTH_PATH, data)
    return True


def revoke_token(token: str) -> None:
    data = auth_state()
    sessions = data.get('sessions') or {}
    sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
    data['sessions'] = sessions
    json_save(AUTH_PATH, data)


def make_env() -> Dict[str, str]:
    env = os.environ.copy()
    # Do not force HOME when MIMOCODE_HOME is set. MiMo Code v0.2x returns
    # HTTP 500 on /config when HOME=/root and MIMOCODE_HOME points to an
    # isolated profile. MIMOCODE_HOME is the official single profile root.
    env['MIMOCODE_HOME'] = str(MIMO_HOME)
    env['MIMOCODE_DISABLE_AUTOUPDATE'] = 'true'
    return env


def run_cmd(args: List[str], timeout: int = 30, cwd: Optional[str] = None) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=make_env(), cwd=cwd)
        return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()
    except subprocess.TimeoutExpired:
        return 124, '', f'Command timed out after {timeout}s'
    except Exception as e:
        return 1, '', str(e)


def run_mimo(*args: str, timeout: int = 30, cwd: Optional[str] = None) -> Tuple[int, str, str]:
    return run_cmd([MIMO_BIN] + list(args), timeout=timeout, cwd=cwd)

def ensure_mimo_home() -> None:
    for sub in ('config', 'data', 'state', 'cache'):
        (MIMO_HOME / sub).mkdir(parents=True, exist_ok=True)


def official_provider_id(provider_id: str) -> str:
    """Use a custom provider id so MiMo's managed disabled_providers cannot hide it.

    The official managed config disables built-in "opencode". Using fnos_<id>
    makes the configured free provider visible in /provider and /models.
    """
    base = re.sub(r'[^a-zA-Z0-9_]+', '_', str(provider_id or 'custom').strip().lower()).strip('_') or 'custom'
    if base.startswith('fnos_'):
        return base[:64]
    return ('fnos_' + base)[:64]


def read_official_config() -> Dict[str, Any]:
    ensure_mimo_home()
    data = json_load(MIMO_CONFIG_PATH, {})
    return data if isinstance(data, dict) else {}


def write_official_config(data: Dict[str, Any]) -> None:
    ensure_mimo_home()
    json_save(MIMO_CONFIG_PATH, data, 0o600)


def sync_official_provider(provider_id: str, name: str, base_url: str, api_key: str, model: str) -> Dict[str, Any]:
    """Synchronize Wrapper provider settings into official MiMo config.json."""
    ensure_mimo_home()
    official_id = official_provider_id(provider_id)
    cfg = read_official_config()
    provider = cfg.get('provider') if isinstance(cfg.get('provider'), dict) else {}
    models = {}
    if model:
        models[model] = {
            'name': model,
            'temperature': True,
            'tool_call': True,
        }
    provider[official_id] = {
        'npm': '@ai-sdk/openai-compatible',
        'name': name or official_id,
        'options': {
            'baseURL': base_url,
            'apiKey': api_key or '',
        },
        'models': models,
    }
    cfg['provider'] = provider
    if model:
        cfg['model'] = f'{official_id}/{model}'
        cfg.setdefault('small_model', f'{official_id}/{model}')
    # Keep MiMo's known broken/blocked built-in opencode ids disabled, but never
    # disable our fnos_* custom ids.
    disabled = cfg.get('disabled_providers') if isinstance(cfg.get('disabled_providers'), list) else []
    disabled_out = []
    for item in list(disabled) + ['opencode', 'opencode-go']:
        if isinstance(item, str) and item not in disabled_out and item != official_id:
            disabled_out.append(item)
    cfg['disabled_providers'] = disabled_out
    write_official_config(cfg)
    return {'id': official_id, 'model': f'{official_id}/{model}' if model else '', 'path': str(MIMO_CONFIG_PATH)}


def sync_official_model(model: str) -> Dict[str, Any]:
    """Set an official MiMo model in the official config without touching providers."""
    ensure_mimo_home()
    cfg = read_official_config()
    if model:
        cfg['model'] = model
        cfg.setdefault('small_model', model)
    write_official_config(cfg)
    return {'id': model.split('/', 1)[0] if '/' in model else '', 'model': model, 'path': str(MIMO_CONFIG_PATH)}


def official_config_ready(timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection('127.0.0.1', MIMO_PORT, timeout=2)
            conn.request('GET', '/config', headers={'Accept': 'application/json'})
            resp = conn.getresponse()
            body = resp.read(200)
            conn.close()
            if resp.status == 200 and body.strip().startswith(b'{'):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def restart_mimo_web() -> bool:
    stop_mimo_web()
    started = start_mimo_web()
    return bool(started and official_config_ready(25.0))



def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0


def read_pid(path: Path) -> Optional[int]:
    try:
        pid = int(path.read_text().strip())
        os.kill(pid, 0)
        return pid
    except Exception:
        return None


def get_mimo_version() -> str:
    rc, out, err = run_mimo('--version', timeout=8)
    return (out or err or 'unknown').strip()[:120]


def start_mimo_web() -> bool:
    ensure_mimo_home()
    if port_open(MIMO_PORT):
        return True
    if read_pid(MIMO_PID_PATH):
        return True
    log(f'starting mimo web on 0.0.0.0:{MIMO_PORT} with MIMOCODE_HOME={MIMO_HOME}')
    try:
        with MIMO_LOG_PATH.open('ab') as logf:
            proc = subprocess.Popen(
                [MIMO_BIN, 'web', '--hostname', '0.0.0.0', '--port', str(MIMO_PORT)],
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=make_env(),
            )
        MIMO_PID_PATH.write_text(str(proc.pid))
        for _ in range(80):
            if port_open(MIMO_PORT):
                return True
            if proc.poll() is not None:
                log(f'mimo web exited early: rc={proc.returncode}')
                return False
            time.sleep(0.5)
    except Exception as e:
        log(f'start_mimo_web failed: {e}')
    return port_open(MIMO_PORT)


def stop_mimo_web() -> None:
    pid = read_pid(MIMO_PID_PATH)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        for _ in range(10):
            if not read_pid(MIMO_PID_PATH):
                break
            time.sleep(0.2)
        if read_pid(MIMO_PID_PATH):
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
    MIMO_PID_PATH.unlink(missing_ok=True)
    run_cmd(['pkill', '-f', f'mimo web.*--port {MIMO_PORT}'], timeout=5)


def heartbeat() -> None:
    while True:
        try:
            cfg = load_config()
            if cfg.get('auto_restart_mimo', True) and not port_open(MIMO_PORT):
                log('heartbeat: mimo web port closed, restarting')
                start_mimo_web()
        except Exception as e:
            log(f'heartbeat error: {e}')
        time.sleep(20)


def mask_secret(value: Any, keep: int = 4) -> str:
    s = str(value or '')
    if not s:
        return ''
    if len(s) <= keep * 2:
        return '*' * len(s)
    return s[:keep] + '...' + s[-keep:]


def sanitize_text(text: str, limit: int = SAFE_TEXT_LIMIT) -> str:
    text = text or ''
    text = re.sub(r'(sk-[A-Za-z0-9_\-]{12,})', 'sk-***REDACTED***', text)
    text = re.sub(r'([A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{12,}\.[A-Za-z0-9_\-]{12,})', '***TOKEN***', text)
    text = re.sub(r'(?i)(api[_-]?key|token|password|secret)(["\'\s:=]+)([^\s,"\'}]+)', r'\1\2***REDACTED***', text)
    if len(text) > limit:
        return text[-limit:]
    return text


def classify_error(text: str, rc: int = 0) -> Dict[str, str]:
    t = (text or '').lower()
    if rc == 124 or 'timed out' in t or 'timeout' in t:
        return {'category': 'timeout', 'title': '执行超时', 'suggestion': '任务耗时过长。请缩短提示词、换更小的项目目录，或稍后再试。'}
    if 'eaddrinuse' in t or 'address already in use' in t or '端口' in text and '占用' in text:
        return {'category': 'port_in_use', 'title': '端口被占用', 'suggestion': f'请在设置里重启 MiMo Web，或检查 {MIMO_PORT} 端口占用。'}
    if 'unauthorized' in t or 'invalid api key' in t or '401' in t or 'api key' in t and 'invalid' in t:
        return {'category': 'bad_key', 'title': 'API Key 无效或未授权', 'suggestion': '请进入首次配置向导/Provider 设置，确认 API Key、Base URL 和模型名正确。'}
    if 'provider' in t and ('not' in t or 'missing' in t or '未' in text):
        return {'category': 'provider_missing', 'title': 'Provider 未配置', 'suggestion': '请先完成首页顶部的 Provider 首次配置向导。'}
    if 'model' in t and ('not found' in t or 'invalid' in t or '404' in t):
        return {'category': 'model_unavailable', 'title': '模型不可用', 'suggestion': '请在模型切换里选择服务商支持的模型，或检查模型名拼写。'}
    if 'network' in t or 'connection refused' in t or 'enotfound' in t or 'eai_again' in t or 'connect' in t:
        return {'category': 'network', 'title': '网络连接失败', 'suggestion': '请检查 NAS 网络、代理设置、Base URL 是否可访问。'}
    if not port_open(MIMO_PORT):
        return {'category': 'mimo_web_down', 'title': 'MiMo Web 未运行', 'suggestion': '请在设置里重启 MiMo Web，或查看日志里的启动错误。'}
    return {'category': 'unknown', 'title': '执行失败', 'suggestion': '请查看下方“技术细节”，把诊断包发给开发者排查。'}


def user_error(text: str, rc: int = 0) -> Dict[str, Any]:
    clean = sanitize_text(text)
    info = classify_error(clean, rc)
    info.update({'raw': clean[-4000:], 'rc': rc})
    return info


def read_tail(path: Path, limit: int = 80_000) -> str:
    try:
        if not path.exists():
            return ''
        with path.open('rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - limit))
            return f.read().decode('utf-8', 'replace')
    except Exception as e:
        return str(e)


def read_mimo_auth() -> Dict[str, Any]:
    data = json_load(MIMO_AUTH_PATH, {})
    if not isinstance(data, dict):
        data = {}
    return data


def write_mimo_auth(data: Dict[str, Any]) -> None:
    json_save(MIMO_AUTH_PATH, data, 0o600)


def provider_items(raw: Optional[Dict[str, Any]] = None, reveal: bool = False) -> List[Dict[str, Any]]:
    data = raw if raw is not None else read_mimo_auth()
    items: List[Dict[str, Any]] = []
    if isinstance(data.get('providers'), list):
        for p in data.get('providers') or []:
            if isinstance(p, dict):
                items.append(p)
    elif isinstance(data.get('credentials'), list):
        for p in data.get('credentials') or []:
            if isinstance(p, dict):
                items.append(p)
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict) and any(x in v for x in ('apiKey', 'api_key', 'key', 'baseURL', 'base_url')):
                vv = v.copy(); vv.setdefault('id', k); items.append(vv)
    result = []
    for p in items:
        key = p.get('apiKey') or p.get('api_key') or p.get('key') or p.get('token') or ''
        base = p.get('baseURL') or p.get('base_url') or p.get('url') or ''
        name = p.get('name') or p.get('title') or p.get('provider') or p.get('id') or 'Provider'
        model = p.get('model') or p.get('defaultModel') or p.get('default_model') or ''
        result.append({
            'id': p.get('id') or name,
            'name': name,
            'base_url': base,
            'model': model,
            'api_key': key if reveal else mask_secret(key),
            'has_key': bool(key),
        })
    return result


def save_provider(payload: Dict[str, Any]) -> Dict[str, Any]:
    provider_id = str(payload.get('id') or payload.get('provider') or 'custom').strip()[:64]
    name = str(payload.get('name') or provider_id or '自定义 Provider').strip()[:80]
    base_url = str(payload.get('base_url') or payload.get('baseURL') or '').strip()
    api_key = str(payload.get('api_key') or payload.get('apiKey') or '').strip()
    model = str(payload.get('model') or '').strip()
    official = provider_id == 'mimo_official' or model in OFFICIAL_MODELS
    if not name:
        raise ValueError('请填写服务商名称')
    if official:
        model = model or 'mimo/mimo-auto'
        official_sync = sync_official_model(model)
        cfg = save_config_patch({'default_provider': 'mimo_official', 'default_model': model})
        official_ready = restart_mimo_web()
        official_sync['ready'] = official_ready
        return {'ok': True, 'provider': {'id': 'mimo_official', 'name': 'MiMo 官方模型', 'model': model, 'has_key': False, 'official': True, 'official_id': official_sync.get('id'), 'official_model': official_sync.get('model')}, 'official': official_sync, 'config': cfg}
    if not base_url:
        raise ValueError('请填写接口地址 Base URL')
    preset = next((p for p in PROVIDER_PRESETS if p.get('id') == provider_id), {})
    free_no_key = (not api_key) and (provider_id in {'opencode', 'kilo'} or preset.get('requires_key') is False)
    if not api_key and not free_no_key:
        raise ValueError('请填写 API Key')
    data = read_mimo_auth()
    providers = data.get('providers') if isinstance(data.get('providers'), list) else []
    new_item = {'id': provider_id, 'name': name, 'baseURL': base_url, 'apiKey': api_key, 'model': model}
    if free_no_key:
        new_item['requireApiKey'] = False
        new_item['isFreeTier'] = True
    replaced = False
    out = []
    for p in providers:
        if isinstance(p, dict) and (p.get('id') == provider_id or p.get('name') == name):
            out.append(new_item); replaced = True
        else:
            out.append(p)
    if not replaced:
        out.append(new_item)
    data['providers'] = out
    write_mimo_auth(data)
    official_sync = sync_official_provider(provider_id, name, base_url, api_key, model)
    cfg = save_config_patch({'default_provider': provider_id, 'default_model': model})
    official_ready = restart_mimo_web()
    official_sync['ready'] = official_ready
    item = provider_items({'providers': [new_item]})[0]
    item['official_id'] = official_sync.get('id')
    item['official_model'] = official_sync.get('model')
    return {'ok': True, 'provider': item, 'official': official_sync, 'config': cfg}

def delete_provider(pid: str) -> bool:
    data = read_mimo_auth()
    providers = data.get('providers') if isinstance(data.get('providers'), list) else []
    new = [p for p in providers if not (isinstance(p, dict) and str(p.get('id') or p.get('name')) == pid)]
    data['providers'] = new
    write_mimo_auth(data)
    return len(new) != len(providers)


def status_payload() -> Dict[str, Any]:
    cfg = load_config()
    mimo_open = port_open(MIMO_PORT)
    providers = provider_items()
    rc_v, out_v, err_v = run_mimo('--version', timeout=8)
    cli_ok = rc_v == 0
    project_dir = cfg.get('project_dir') or str(Path.home())
    project_ok = Path(project_dir).exists() and Path(project_dir).is_dir()
    return {
        'wrapper_version': WRAPPER_VERSION,
        'mimo_version': (out_v or err_v or '').strip()[:120],
        'mimo_version_rc': rc_v,
        'mimo_open': mimo_open,
        'mimo_port': MIMO_PORT,
        'wrapper_port': LISTEN_PORT,
        'uptime_sec': int(time.time() - START_TIME),
        'providers_count': len(providers),
        'provider_configured': len(providers) > 0,
        'default_provider': cfg.get('default_provider', ''),
        'default_model': cfg.get('default_model', ''),
        'project_dir': project_dir,
        'project_ok': project_ok,
        'cli_ok': cli_ok,
        'native_web_proxy_url': '/mimo-web/',
        'native_web_note': '官方会话默认由浏览器直连当前主机的 5669 端口；/mimo-web/ 仅保留为备用代理入口。',
        'friendly': {
            'service': '运行中' if mimo_open else '未运行',
            'web': '可访问' if mimo_open else '不可访问',
            'provider': '已配置' if providers else '未配置',
            'model': cfg.get('default_model') or '未选择',
            'cli': '可用' if cli_ok else '不可用',
        }
    }


def parse_lines(text: str) -> List[str]:
    lines = [x.strip() for x in sanitize_text(text, 40_000).splitlines() if x.strip()]
    return lines[-120:]


def smart_logs() -> Dict[str, Any]:
    raw = '\n'.join([read_tail(WRAPPER_LOG_PATH), read_tail(MIMO_LOG_PATH)])
    lines = parse_lines(raw)
    issues = []
    for line in lines[-80:]:
        low = line.lower()
        if any(k in low for k in ['error', 'failed', 'exception', 'unauthorized', 'timeout', 'eaddrinuse', 'invalid']):
            issues.append({'message': line, **classify_error(line)})
    return {'issues': issues[-30:], 'raw': sanitize_text(raw[-60_000:])}


def load_sessions() -> List[Dict[str, Any]]:
    data = json_load(SESSIONS_PATH, [])
    return data if isinstance(data, list) else []


def save_sessions(items: List[Dict[str, Any]]) -> None:
    json_save(SESSIONS_PATH, items[-80:])


def upsert_session(session_id: str, title: str, message: str, project_dir: str, model: str) -> None:
    now = int(time.time())
    items = [x for x in load_sessions() if x.get('id') != session_id]
    items.append({'id': session_id, 'title': title or message[:28] or '新会话', 'last_message': message[:160], 'project_dir': project_dir, 'model': model, 'updated_at': now})
    save_sessions(sorted(items, key=lambda x: int(x.get('updated_at', 0))))


def validate_project(path: str) -> Tuple[bool, str]:
    if not path:
        return False, '请填写项目目录'
    p = Path(path).expanduser()
    if not p.exists():
        return False, f'目录不存在：{p}'
    if not p.is_dir():
        return False, f'不是目录：{p}'
    return True, str(p)


def run_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    message = str(payload.get('message') or '').strip()
    if not message:
        raise ValueError('请输入要发送给 MiMo 的内容')
    cfg = load_config()
    project_dir = str(payload.get('project_dir') or cfg.get('project_dir') or str(Path.home()))
    ok, project_msg = validate_project(project_dir)
    if not ok:
        return {'ok': False, 'error': project_msg, **user_error(project_msg, 1)}
    model = str(payload.get('model') or cfg.get('default_model') or '').strip()
    session_id = str(payload.get('session_id') or cfg.get('last_session_id') or '').strip()
    title = str(payload.get('title') or '').strip()
    args = ['run', '--dir', project_msg]
    if model:
        args += ['--model', model]
    if session_id:
        args += ['--session', session_id]
    if title:
        args += ['--title', title]
    args.append(message)
    rc, out, err = run_mimo(*args, timeout=180, cwd=project_msg)
    raw = out or err
    if rc != 0:
        return {'ok': False, 'output': sanitize_text(raw), **user_error(raw, rc)}
    sid = session_id or hashlib.sha1(f'{time.time()}:{message}'.encode()).hexdigest()[:12]
    upsert_session(sid, title or message[:30], message, project_msg, model)
    save_config_patch({'project_dir': project_msg, 'default_model': model, 'last_session_id': sid})
    clean = sanitize_text(raw, 120_000).strip()
    if not clean:
        return {
            'ok': True,
            'session_id': sid,
            'output': '',
            'empty_output': True,
            'suggestion': 'MiMo 命令执行成功，但没有返回可显示内容。请先用「测试模型」确认当前模型是否会回复；如果仍为空，查看日志与建议，或在 SSH 中运行复制出来的 CLI 命令定位。',
            'next_steps': ['点击「测试模型」', '确认模型为 mimo/mimo-auto 或可用第三方模型', '查看「日志与建议」', '复制 CLI 到 SSH 中验证']
        }
    return {'ok': True, 'session_id': sid, 'output': clean, 'empty_output': False}


def list_models(provider: str = '') -> Dict[str, Any]:
    if provider in ('mimo_official', 'official', 'mimo'):
        return {'ok': True, 'models': OFFICIAL_MODELS, 'groups': grouped_models(OFFICIAL_MODELS), 'meta': [model_meta(x) for x in OFFICIAL_MODELS], 'raw': '\n'.join(OFFICIAL_MODELS), 'official': True}
    args = ['models'] + ([provider] if provider else [])
    rc, out, err = run_mimo(*args, timeout=25)
    raw = out or err
    models = list(OFFICIAL_MODELS)
    for line in raw.splitlines():
        s = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if not s or s.startswith(('Usage', 'Commands', 'Options')):
            continue
        if re.match(r'^[A-Za-z0-9_.:/\-]+$', s) and len(s) > 2:
            models.append(s)
    final = sorted(set(models))[:200]
    return {'ok': rc == 0, 'models': final, 'groups': grouped_models(final), 'meta': [model_meta(x) for x in final], 'raw': sanitize_text(raw), 'official_models': OFFICIAL_MODELS, **({} if rc == 0 else user_error(raw, rc))}

def check_update() -> Dict[str, Any]:
    current = get_mimo_version()
    rc, out, err = run_mimo('upgrade', '--help', timeout=15)
    return {
        'ok': True,
        'current': current,
        'note': '已按要求禁用自动替换二进制。这里仅展示当前版本和官方升级命令。',
        'manual_command': 'mimo upgrade',
        'help': sanitize_text(out or err, 8000),
        'rc': rc,
    }


def mcp_status() -> Dict[str, Any]:
    rc, out, err = run_mimo('mcp', 'list', timeout=25)
    raw = out or err
    return {'ok': rc == 0, 'raw': sanitize_text(raw), 'friendly': 'MCP 管理默认隐藏在高级设置。当前仅做查看，不执行新增/删除。', **({} if rc == 0 else user_error(raw, rc))}


def _safe_project_root() -> Path:
    cfg = load_config()
    root = Path(str(cfg.get('project_dir') or Path.home())).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        root = Path.home().resolve()
    return root


def _safe_child(path_text: str = '') -> Path:
    root = _safe_project_root()
    target = (root / path_text.lstrip('/')).resolve() if path_text else root
    if root != target and root not in target.parents:
        raise ValueError('只能访问当前项目目录内的文件')
    return target


def file_browser(path_text: str = '') -> Dict[str, Any]:
    target = _safe_child(path_text)
    if target.is_file():
        if target.stat().st_size > 256 * 1024:
            return {'ok': False, 'error': '文件超过 256KB，仅支持小文本预览', 'path': str(target)}
        raw = target.read_bytes()
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            text = raw.decode('utf-8', 'replace')
        return {'ok': True, 'type': 'file', 'path': str(target), 'text': sanitize_text(text, 256 * 1024), 'size': len(raw)}
    if not target.is_dir():
        return {'ok': False, 'error': '路径不存在或不是目录'}
    entries = []
    for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:200]:
        try:
            st = item.stat()
            entries.append({'name': item.name, 'path': str(item.relative_to(_safe_project_root())), 'type': 'dir' if item.is_dir() else 'file', 'size': st.st_size, 'mtime': int(st.st_mtime)})
        except Exception:
            continue
    return {'ok': True, 'type': 'dir', 'root': str(_safe_project_root()), 'path': str(target), 'entries': entries, 'readonly': True}


def process_metrics() -> Dict[str, Any]:
    pids = []
    pid = read_pid(MIMO_PID_PATH)
    if pid:
        pids.append(pid)
    wrapper_pid = os.getpid()
    rows = []
    for p in [wrapper_pid] + pids:
        rc, out, err = run_cmd(['ps', '-p', str(p), '-o', 'pid,comm,%cpu,%mem,rss,etime,args', '--no-headers'], timeout=5)
        if rc == 0 and out.strip():
            rows.append(out.strip())
    return {'ok': True, 'uptime_sec': int(time.time() - START_TIME), 'wrapper_pid': wrapper_pid, 'mimo_pid': pid, 'mimo_port_open': port_open(MIMO_PORT), 'processes': rows, 'note': '轻量运行状态，仅用于判断 MiMo 是否正常运行。'}


def acp_status() -> Dict[str, Any]:
    rc, out, err = run_mimo('acp', '--help', timeout=15)
    return {'ok': True, 'available': rc == 0, 'help': sanitize_text(out or err, 12000), 'friendly': 'ACP 服务默认关闭，仅在外部编辑器/客户端接入时使用。'}


def acp_control(action: str) -> Dict[str, Any]:
    if action not in ('status', 'start', 'stop', 'restart'):
        raise ValueError('ACP 只允许 status/start/stop/restart')
    if action == 'status':
        return acp_status()
    return {'ok': False, 'error': 'v0.10.0 仅提供 ACP 状态查看；启停需要确认具体端口和官方命令后再开放。', 'suggestion': '请先使用状态页确认 MiMo 当前 ACP 支持参数。'}


def agent_config() -> Dict[str, Any]:
    rc, out, err = run_mimo('agent', 'list', timeout=20)
    return {'ok': rc == 0, 'raw': sanitize_text(out or err, 16000), 'readonly': True, 'friendly': 'Agent 权限默认只读展示；导入配置前会自动备份。', **({} if rc == 0 else user_error(out or err, rc))}


def agent_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get('confirm') != 'EDIT_AGENT':
        raise ValueError('导入 Agent 配置需要 confirm=EDIT_AGENT')
    backup = VAR_DIR / f'agent-config-backup-{int(time.time())}.json'
    json_save(backup, {'exported_at': int(time.time()), 'note': 'v0.10.0 自动备份占位；实际 Agent 配置由官方 mimo 管理', 'current': agent_config()}, 0o600)
    return {'ok': False, 'backup': str(backup), 'error': 'v0.10.0 暂不直接写 Agent 权限，已生成备份占位。', 'suggestion': '为避免破坏官方配置，本版本只读展示 Agent 权限。'}


ALLOWED_MIMO_COMMANDS = {
    'models': ['models'],
    'providers list': ['providers', 'list'],
    'mcp list': ['mcp', 'list'],
    'debug': ['debug'],
    'version': ['--version'],
}


def mimo_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    key = str(payload.get('command') or '').strip()
    message = str(payload.get('message') or '').strip()
    if key == 'run':
        if not message:
            raise ValueError('mimo run 需要输入消息')
        return run_chat({'message': message, 'model': payload.get('model') or load_config().get('default_model') or 'mimo/mimo-auto', 'project_dir': payload.get('project_dir') or load_config().get('project_dir')})
    if key == 'models':
        return {'ok': True, 'command': 'mimo models', 'output': '\n'.join(OFFICIAL_MODELS), 'models': OFFICIAL_MODELS}
    args = ALLOWED_MIMO_COMMANDS.get(key)
    if not args:
        raise ValueError('只允许执行白名单内的 MiMo 命令')
    rc, out, err = run_mimo(*args, timeout=60)
    raw = out or err
    return {'ok': rc == 0, 'command': 'mimo ' + ' '.join(args), 'output': sanitize_text(raw, 80000), **({} if rc == 0 else user_error(raw, rc))}


def export_config(include_keys: bool = False) -> Dict[str, Any]:
    data = {
        'wrapper_version': WRAPPER_VERSION,
        'exported_at': int(time.time()),
        'config': load_config(),
        'providers': provider_items(reveal=include_keys),
        'include_keys': include_keys,
    }
    return data


def import_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get('confirm') != 'IMPORT_CONFIG':
        raise ValueError('导入配置需要 confirm=IMPORT_CONFIG')
    cfg = payload.get('config') if isinstance(payload.get('config'), dict) else {}
    save_config_patch(cfg)
    providers = payload.get('providers')
    imported = 0
    if isinstance(providers, list):
        for p in providers:
            if isinstance(p, dict) and (p.get('api_key') or p.get('apiKey')):
                save_provider(p)
                imported += 1
    return {'ok': True, 'imported_providers': imported, 'config': load_config()}


def diagnostic_bundle() -> Dict[str, Any]:
    bundle = {
        'generated_at': int(time.time()),
        'wrapper_version': WRAPPER_VERSION,
        'status': status_payload(),
        'config': {k: ('***REDACTED***' if 'key' in k.lower() or 'token' in k.lower() else v) for k, v in load_config().items()},
        'providers': provider_items(reveal=False),
        'logs': smart_logs()['issues'],
        'paths': {
            'mimo_bin': {'path': MIMO_BIN, 'exists': Path(MIMO_BIN).exists()},
            'public': {'path': str(PUBLIC_DIR), 'exists': PUBLIC_DIR.exists()},
            'auth': {'path': str(MIMO_AUTH_PATH), 'exists': MIMO_AUTH_PATH.exists()},
            'official_config': {'path': str(MIMO_CONFIG_PATH), 'exists': MIMO_CONFIG_PATH.exists()},
            'official_home': {'path': str(MIMO_HOME), 'exists': MIMO_HOME.exists()},
            'config': {'path': str(CONFIG_PATH), 'exists': CONFIG_PATH.exists()},
        }
    }
    json_save(DIAG_PATH, bundle, 0o600)
    return {'ok': True, 'bundle': bundle, 'path': str(DIAG_PATH)}


def project_overview() -> Dict[str, Any]:
    cfg = load_config()
    root = Path(cfg.get('project_dir') or str(Path.home())).expanduser()
    ok = root.exists() and root.is_dir()
    files = 0
    dirs = 0
    markers: List[str] = []
    languages: Dict[str, int] = {}
    max_scan = 2500
    if ok:
        for name in ['package.json', 'pyproject.toml', 'requirements.txt', 'go.mod', 'Cargo.toml', 'pubspec.yaml', '.git']:
            if (root / name).exists():
                markers.append(name)
        for current, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ('.git', 'node_modules', 'vendor', '__pycache__', '.venv', 'dist', 'build')]
            dirs += len(dirnames)
            for fn in filenames:
                files += 1
                ext = Path(fn).suffix.lower() or '[无后缀]'
                languages[ext] = languages.get(ext, 0) + 1
                if files >= max_scan:
                    break
            if files >= max_scan:
                break
    top_ext = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:10]
    return {'ok': ok, 'project_dir': str(root), 'markers': markers, 'files_scanned': files, 'dirs_scanned': dirs, 'truncated': files >= max_scan, 'top_extensions': top_ext, 'summary': '项目目录可访问' if ok else '项目目录不可访问'}


def health_check() -> Dict[str, Any]:
    st = status_payload()
    logs = smart_logs()
    checks = [
        {'id': 'wrapper', 'name': 'Wrapper 服务', 'ok': True, 'detail': f'v{WRAPPER_VERSION} 已运行 {st.get("uptime_sec", 0)} 秒'},
        {'id': 'mimo_web', 'name': '官方 Web 服务', 'ok': bool(st.get('mimo_open')), 'detail': st.get('friendly', {}).get('web', '')},
        {'id': 'mimo_cli', 'name': 'MiMo CLI', 'ok': bool(st.get('cli_ok')), 'detail': st.get('mimo_version') or 'CLI 不可用'},
        {'id': 'provider', 'name': '模型配置', 'ok': bool(st.get('provider_configured') or st.get('default_model')), 'detail': st.get('friendly', {}).get('model', '')},
        {'id': 'project', 'name': '项目目录', 'ok': bool(st.get('project_ok')), 'detail': st.get('project_dir', '')},
        {'id': 'logs', 'name': '错误日志', 'ok': len(logs.get('issues', [])) == 0, 'detail': f'{len(logs.get("issues", []))} 条需关注日志'},
    ]
    score = sum(1 for c in checks if c['ok'])
    return {'ok': True, 'score': score, 'total': len(checks), 'checks': checks, 'suggestions': [i.get('suggestion') for i in logs.get('issues', [])[:5] if i.get('suggestion')]}


def security_boundary() -> Dict[str, Any]:
    return {'ok': True, 'items': [
        {'title': '官方二进制边界', 'text': '应用保留官方 mimo 二进制，不在 UI 中提供替换或反编译能力。'},
        {'title': '凭据存储', 'text': 'Provider Key 仅保存在本机 NAS 配置文件中；导出默认脱敏，含 Key 导出需显式选择。'},
        {'title': '命令执行边界', 'text': '工具箱命令助手使用白名单，不提供任意 shell 输入。'},
        {'title': '文件访问边界', 'text': '项目文件浏览为只读，限制在已选择的项目目录内。'},
        {'title': '高级功能边界', 'text': 'MCP、ACP、Agent 权限等高级功能默认隐藏，操作前需要明确确认。'},
        {'title': '网络边界', 'text': '官方会话由 mimo web 提供；第三方模型请求由官方 CLI/配置处理，工作台只负责配置和状态展示。'},
    ]}


def create_config_backup(include_keys: bool = False, reason: str = '') -> Dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%d-%H%M%S')
    path = BACKUP_DIR / f'config-backup-{ts}.json'
    data = export_config(include_keys)
    data['reason'] = sanitize_text(reason, 300)
    json_save(path, data, 0o600)
    return {'ok': True, 'path': str(path), 'filename': path.name, 'include_keys': include_keys}


def list_config_backups() -> Dict[str, Any]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for fp in sorted(BACKUP_DIR.glob('config-backup-*.json'), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        items.append({'filename': fp.name, 'path': str(fp), 'size': fp.stat().st_size, 'mtime': int(fp.stat().st_mtime)})
    return {'ok': True, 'backups': items, 'dir': str(BACKUP_DIR)}


def cli_commands() -> Dict[str, Any]:
    cfg = load_config()
    p = cfg.get('project_dir') or '/path/to/project'
    model = cfg.get('default_model') or '<模型名>'
    return {'commands': [
        {'title': '进入 MiMo 终端界面', 'cmd': 'mimo'},
        {'title': '在当前项目提问', 'cmd': f'cd {sh_quote(p)} && mimo run "分析这个项目结构"'},
        {'title': '指定模型执行', 'cmd': f'cd {sh_quote(p)} && mimo run --model {sh_quote(model)} "帮我解释这个报错"'},
        {'title': '启动原生 Web', 'cmd': f'mimo web --hostname 0.0.0.0 --port {MIMO_PORT}'},
    ]}


def sh_quote(s: str) -> str:
    return "'" + str(s).replace("'", "'\''") + "'"


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = f'MiMoWrapper/{WRAPPER_VERSION}'

    def log_message(self, fmt: str, *args: Any) -> None:
        log('%s %s' % (self.client_address[0], fmt % args))

    def translate_path(self, path: str) -> str:
        rel = urllib.parse.urlparse(path).path.lstrip('/') or 'index.html'
        return str((PUBLIC_DIR / rel).resolve())

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get('Content-Length') or '0')
        if n <= 0:
            return {}
        raw = self.rfile.read(min(n, 2 * 1024 * 1024)).decode('utf-8', 'replace')
        return json.loads(raw or '{}')

    def _token(self) -> str:
        auth = self.headers.get('Authorization') or ''
        if auth.lower().startswith('bearer '):
            return auth.split(' ', 1)[1].strip()
        return ''

    def _require_auth(self) -> bool:
        if not validate_token(self._token()):
            self._send_json({'error': '未登录或登录已过期', 'suggestion': '请重新登录。'}, 401)
            return False
        return True

    def _cookie_token(self) -> str:
        cookie = self.headers.get('Cookie') or ''
        for part in cookie.split(';'):
            if '=' not in part:
                continue
            k, v = part.strip().split('=', 1)
            if k == 'mimocode_token':
                return urllib.parse.unquote(v)
        return ''

    def _proxy_auth_ok(self) -> bool:
        return validate_token(self._token()) or validate_token(self._cookie_token())

    def _is_local_public_path(self, path: str) -> bool:
        local = (PUBLIC_DIR / path.lstrip('/')).resolve()
        try:
            local.relative_to(PUBLIC_DIR.resolve())
        except ValueError:
            return False
        return local.exists()

    def _looks_like_mimo_spa_route(self, path: str) -> bool:
        # Official MiMo SPA routes can look like /<base64-project-dir>/session/<session_id>.
        # Example: /L3Jvb3QvaW50ZWw/session/ses_xxx where L3J... decodes to /root/intel.
        if path in {'/', '/index.html'} or path.startswith(('/api/', '/css/', '/js/')):
            return False
        if self._is_local_public_path(path):
            return False
        return bool(re.match(r'^/[A-Za-z0-9_-]{8,}(?:/|$)', path))

    def _should_proxy_mimo_root(self, path: str) -> bool:
        if path.startswith('/assets/'):
            return not self._is_local_public_path(path)
        if any(path == p or path.startswith(p + '/') for p in MIMO_WEB_ROOT_PROXY_PREFIXES):
            return True
        return self._looks_like_mimo_spa_route(path)

    def _send_json_with_token_cookie(self, data: Any, token: str, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Set-Cookie', f'mimocode_token={urllib.parse.quote(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age={7 * 24 * 3600}')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _clear_token_cookie(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Set-Cookie', 'mimocode_token=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_mimo_web(self) -> None:
        if not self._proxy_auth_ok():
            self.send_response(401)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('未登录或登录已过期，请返回 MiMo Code 重新登录。'.encode('utf-8'))
            return
        start_mimo_web()
        parsed = urllib.parse.urlparse(self.path)
        proxy_path = parsed.path
        if parsed.path.startswith('/mimo-web'):
            upstream_path = parsed.path[len('/mimo-web'):] or '/'
        else:
            upstream_path = parsed.path or '/'
        if parsed.query:
            upstream_path += '?' + parsed.query
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {'host', 'connection', 'content-length', 'accept-encoding'}}
        headers['Host'] = f'127.0.0.1:{MIMO_PORT}'
        body = None
        if self.command in {'POST', 'PUT', 'PATCH'}:
            n = int(self.headers.get('Content-Length') or '0')
            body = self.rfile.read(n) if n > 0 else None
        conn = None
        try:
            conn = http.client.HTTPConnection('127.0.0.1', MIMO_PORT, timeout=30)
            conn.request(self.command, upstream_path, body=body, headers=headers)
            resp = conn.getresponse()
            resp_headers = resp.getheaders()
            content_type = next((v for k, v in resp_headers if k.lower() == 'content-type'), '')
            is_event_stream = 'text/event-stream' in content_type.lower() or upstream_path.startswith('/global/event')

            self.send_response(resp.status, resp.reason)
            skip = {'transfer-encoding', 'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailers', 'upgrade', 'content-length'}
            has_cache_control = False
            for k, v in resp_headers:
                kl = k.lower()
                if kl in skip:
                    continue
                if kl == 'cache-control':
                    has_cache_control = True
                    if parsed.path.startswith('/mimo-web/assets/') or proxy_path.startswith('/assets/'):
                        continue
                self.send_header(k, v)
            if is_event_stream:
                try:
                    if conn.sock:
                        conn.sock.settimeout(None)
                except Exception:
                    pass
                if not has_cache_control:
                    self.send_header('Cache-Control', 'no-cache')
                self.send_header('X-Accel-Buffering', 'no')
                self.send_header('Connection', 'keep-alive')
                self.send_header('X-MiMo-Code-Proxy', 'mimo-web-stream')
                self.end_headers()
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                return

            data = resp.read()
            if resp.status == 200 and 'text/html' in content_type.lower():
                text = data.decode('utf-8', 'replace')
                if '<base ' not in text.lower():
                    if '<head>' in text:
                        text = text.replace('<head>', '<head><base href="/mimo-web/">', 1)
                    elif '<head ' in text.lower():
                        text = re.sub(r'(<head[^>]*>)', r'\1<base href="/mimo-web/">', text, count=1, flags=re.I)
                text = re.sub(r'((?:src|href|action)=(["\']))/(?!/|mimo-web/|api/)', r'\1/mimo-web/', text, flags=re.I)
                text = re.sub(r'url\(/(?!/|mimo-web/)', 'url(/mimo-web/', text, flags=re.I)
                data = text.encode('utf-8')
            if parsed.path.startswith('/mimo-web/assets/') or proxy_path.startswith('/assets/'):
                self.send_header('Cache-Control', 'public, max-age=86400')
            elif not has_cache_control:
                self.send_header('Cache-Control', 'no-store')
            self.send_header('X-MiMo-Code-Proxy', 'mimo-web')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            log(f'mimo web proxy failed: {e}')
            self.send_response(502)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f'官方会话代理失败：{e}'.encode('utf-8'))
        finally:
            if conn:
                conn.close()

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            if path.startswith('/mimo-web') or self._should_proxy_mimo_root(path):
                return self._proxy_mimo_web()
            if path == '/api/auth/status':
                return self._send_json({'setup': is_setup(), 'wrapper_version': WRAPPER_VERSION})
            if not path.startswith('/api/'):
                return super().do_GET()
            if not self._require_auth():
                return
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if path == '/api/status':
                return self._send_json(status_payload())
            if path == '/api/overview':
                return self._send_json(project_overview())
            if path == '/api/health':
                return self._send_json(health_check())
            if path == '/api/security':
                return self._send_json(security_boundary())
            if path == '/api/providers':
                return self._send_json({'providers': provider_items(), 'presets': PROVIDER_PRESETS, 'config': load_config()})
            if path == '/api/models':
                provider = (qs.get('provider') or [''])[0]
                return self._send_json(list_models(provider))
            if path == '/api/free-models':
                return self._send_json(free_model_library())
            if path == '/api/sessions':
                return self._send_json({'sessions': sorted(load_sessions(), key=lambda x: int(x.get('updated_at', 0)), reverse=True)})
            if path == '/api/logs':
                return self._send_json(smart_logs())
            if path == '/api/diagnostic':
                return self._send_json(diagnostic_bundle())
            if path == '/api/config/export':
                include = (qs.get('include_keys') or ['false'])[0] == 'true'
                return self._send_json(export_config(include))
            if path == '/api/config/backups':
                return self._send_json(list_config_backups())
            if path == '/api/update/check':
                return self._send_json(check_update())
            if path == '/api/mcp':
                return self._send_json(mcp_status())
            if path == '/api/cli':
                return self._send_json(cli_commands())
            if path == '/api/toolbox/files':
                rel = (qs.get('path') or [''])[0]
                return self._send_json(file_browser(rel))
            if path == '/api/toolbox/perf':
                return self._send_json(process_metrics())
            if path == '/api/toolbox/acp':
                return self._send_json(acp_status())
            if path == '/api/toolbox/agents':
                return self._send_json(agent_config())
            return self._send_json({'error': '接口不存在'}, 404)
        except Exception as e:
            log(f'GET {path} failed: {e}')
            return self._send_json({'error': str(e), **user_error(str(e), 1)}, 500)

    def do_PUT(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/mimo-web') or self._should_proxy_mimo_root(path):
            return self._proxy_mimo_web()
        return self._send_json({'error': '接口不存在'}, 404)

    def do_PATCH(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/mimo-web') or self._should_proxy_mimo_root(path):
            return self._proxy_mimo_web()
        return self._send_json({'error': '接口不存在'}, 404)

    def do_DELETE(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path.startswith('/mimo-web') or self._should_proxy_mimo_root(path):
            return self._proxy_mimo_web()
        return self._send_json({'error': '接口不存在'}, 404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            if path.startswith('/mimo-web') or self._should_proxy_mimo_root(path):
                return self._proxy_mimo_web()
            if path == '/api/auth/setup':
                data = self._read_json()
                if is_setup():
                    return self._send_json({'error': '已完成初始化'}, 400)
                password = str(data.get('password') or '')
                if len(password) < 8:
                    return self._send_json({'error': '管理密码至少 8 位'}, 400)
                salt, hashed = pbkdf2_hash(password)
                json_save(AUTH_PATH, {'salt': salt, 'password_hash': hashed, 'sessions': {}})
                token = create_session()
                return self._send_json_with_token_cookie({'ok': True, 'token': token}, token)
            if path == '/api/auth/login':
                data = self._read_json()
                password = str(data.get('password') or '')
                token = str(data.get('token') or '')
                if password and verify_password(password):
                    new_token = create_session()
                    return self._send_json_with_token_cookie({'ok': True, 'token': new_token}, new_token)
                if token and validate_token(token):
                    return self._send_json_with_token_cookie({'ok': True, 'token': token}, token)
                return self._send_json({'error': '管理密码错误', 'suggestion': '请确认输入的是初始化时设置的管理密码。'}, 401)
            if not self._require_auth():
                return
            data = self._read_json()
            if path == '/api/auth/session-cookie':
                token = self._token() or self._cookie_token()
                return self._send_json_with_token_cookie({'ok': True}, token)
            if path == '/api/auth/logout':
                revoke_token(self._token() or self._cookie_token())
                return self._clear_token_cookie({'ok': True})
            if path == '/api/chat/run':
                return self._send_json(run_chat(data))
            if path == '/api/providers/save':
                try:
                    return self._send_json(save_provider(data))
                except Exception as e:
                    return self._send_json({'error': str(e), **user_error(str(e), 1)}, 400)
            if path == '/api/providers/delete':
                pid = str(data.get('id') or '')
                return self._send_json({'ok': delete_provider(pid)})
            if path == '/api/config':
                return self._send_json({'ok': True, 'config': save_config_patch(data)})
            if path == '/api/project/validate':
                ok, msg = validate_project(str(data.get('path') or ''))
                if ok:
                    save_config_patch({'project_dir': msg})
                return self._send_json({'ok': ok, 'path': msg if ok else '', 'error': '' if ok else msg})
            if path == '/api/models/select':
                model = str(data.get('model') or '').strip()
                provider = str(data.get('provider') or '').strip()
                return self._send_json({'ok': True, 'config': save_config_patch({'default_model': model, 'default_provider': provider})})
            if path == '/api/config/import':
                try:
                    create_config_backup(False, 'before import')
                    return self._send_json(import_config(data))
                except Exception as e:
                    return self._send_json({'error': str(e), **user_error(str(e), 1)}, 400)
            if path == '/api/config/backup':
                include = bool(data.get('include_keys'))
                reason = str(data.get('reason') or 'manual')
                return self._send_json(create_config_backup(include, reason))
            if path == '/api/service/restart':
                if data.get('confirm') != 'RESTART':
                    return self._send_json({'error': '重启需要 confirm=RESTART'}, 400)
                stop_mimo_web()
                ok = start_mimo_web()
                return self._send_json({'ok': ok, 'status': status_payload()})
            if path == '/api/toolbox/acp/control':
                return self._send_json(acp_control(str(data.get('action') or 'status')) )
            if path == '/api/toolbox/agents/import':
                try:
                    return self._send_json(agent_import(data))
                except Exception as e:
                    return self._send_json({'error': str(e), **user_error(str(e), 1)}, 400)
            if path == '/api/toolbox/command':
                try:
                    return self._send_json(mimo_command(data))
                except Exception as e:
                    return self._send_json({'error': str(e), **user_error(str(e), 1)}, 400)
            if path == '/api/sessions/delete':
                sid = str(data.get('id') or '')
                save_sessions([x for x in load_sessions() if x.get('id') != sid])
                cfg = load_config()
                if cfg.get('last_session_id') == sid:
                    save_config_patch({'last_session_id': ''})
                return self._send_json({'ok': True})
            return self._send_json({'error': '接口不存在'}, 404)
        except Exception as e:
            log(f'POST {path} failed: {e}')
            return self._send_json({'error': str(e), **user_error(str(e), 1)}, 500)


def main() -> None:
    log(f'Wrapper v{WRAPPER_VERSION} starting on 0.0.0.0:{LISTEN_PORT}')
    start_mimo_web()
    threading.Thread(target=heartbeat, daemon=True).start()
    httpd = http.server.ThreadingHTTPServer(('0.0.0.0', LISTEN_PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
