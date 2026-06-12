/* MiMo Code Deep Integration v0.6.0 — Enhanced Frontend SPA */
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const host = location.hostname;
const content = $('#content');
let currentView = 'dashboard';

// Toast notification
function toast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  const icon = { success: '✅', error: '❌', info: 'ℹ️', warn: '⚠️' }[type] || '';
  t.innerHTML = icon + ' ' + msg;
  t.onclick = () => t.remove();
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// API fetch helper
async function api(path, opts) {
  try {
    const r = await fetch('/api/' + path, opts);
    if (!r.ok) {
      const err = await r.text().catch(() => '');
      return { error: `HTTP ${r.status}: ${err.slice(0, 200)}` };
    }
    return await r.json();
  } catch (e) {
    return { error: e.message };
  }
}

// Router
function navigate(view) {
  currentView = view;
  $$('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.view === view);
  });
  const fns = {
    dashboard: renderDashboard,
    providers: renderProviders,
    sessions: renderSessions,
    stats: renderStats,
    settings: renderSettings,
    upgrade: renderUpgrade,
    logs: renderLogs,
    agents: renderAgents,
    mcp: renderMcp,
    acp: renderAcp,
    debug: renderDebug,
  };
  if (view === 'chat') {
    content.innerHTML = '';
    const iframe = document.createElement('iframe');
    iframe.className = 'chat-container';
    iframe.src = 'http://' + host + ':5669/';
    content.appendChild(iframe);
    return;
  }
  const fn = fns[view];
  if (fn) fn();
}

// Init nav
$$('.nav-item').forEach(n => {
  n.addEventListener('click', () => navigate(n.dataset.view));
});

// =================== Dashboard ===================
async function renderDashboard() {
  content.innerHTML = '<div class="dashboard"><div class="loading">加载中...</div></div>';
  const data = await api('status');
  const running = data.mimo_web;

  const dot = $('#statusDot');
  dot.className = 'status-dot' + (running ? ' running' : '');

  content.innerHTML = `
    <div class="dashboard">
      <div class="dash-grid">
        <div class="dash-card ${running ? 'green' : 'red'}">
          <h3>服务状态</h3>
          <div class="value">${running ? '运行中' : '已停止'}</div>
          <div class="sub">PID: ${data.mimo_web_pid || '-'} | 端口 ${data.mimo_port_open ? '✓ 5669' : '✗ 5669'}</div>
        </div>
        <div class="dash-card accent">
          <h3>MiMo Code 版本</h3>
          <div class="value">v${data.version || '?'}</div>
          <div class="sub">包装器 v0.5.0 | 运行 ${data.uptime || '-'}</div>
        </div>
        <div class="dash-card yellow">
          <h3>可用模型</h3>
          <div class="value">${data.models_count || 0}</div>
          <div class="sub">已加载 Provider 模型数量</div>
        </div>
        <div class="dash-card">
          <h3>快捷操作</h3>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
            <button class="btn btn-primary btn-sm" onclick="navigate('chat')">💬 新建会话</button>
            <button class="btn btn-ghost btn-sm" onclick="navigate('sessions')">📋 历史会话</button>
            <button class="btn btn-ghost btn-sm" onclick="navigate('providers')">🔑 Provider</button>
            <button class="btn btn-ghost btn-sm" onclick="navigate('upgrade')">⬆ 检查更新</button>
          </div>
        </div>
      </div>
      <div class="info-banner">
        <strong>💡 提示：</strong>需要帮助？会话按钮、查看文档。
        <button class="btn btn-ghost btn-xs" onclick="navigate('settings')">⚙ 设置</button>
      </div>
    </div>`;
}

// =================== Providers ===================
async function renderProviders() {
  content.innerHTML = '<div class="page"><div class="loading">加载中...</div></div>';
  const data = await api('providers');
  const providers = data.providers || [];

  let html = '<div class="page"><h2>🔑 Provider 管理</h2>';

  // Add form
  html += `<div class="card">
    <h3>添加 / 更新 Provider</h3>
    <div class="form-row">
      <input id="provName" class="input" placeholder="Provider 名称 (如 openai, deepseek)" style="flex:1;">
      <input id="provKey" class="input" type="password" placeholder="API Key" style="flex:1.5;">
    </div>
    <div class="form-row">
      <input id="provUrl" class="input" placeholder="Base URL (可选的)" style="flex:1;">
    </div>
    <button class="btn btn-primary" onclick="addProvider()">添加</button>
    <span id="provMsg" style="margin-left:12px;font-size:13px;"></span>
  </div>`;

  // List
  html += '<div class="card"><h3>已配置 Provider</h3>';
  if (providers.length === 0) {
    html += '<p class="muted">暂无 Provider，请添加 API Key</p>';
  } else {
    html += '<table class="table"><thead><tr><th>ID</th><th>Base URL</th><th>API Key</th><th>操作</th></tr></thead><tbody>';
    for (const p of providers) {
      const masked = p.key ? p.key.slice(0, 8) + '...' + p.key.slice(-4) : '-';
      html += `<tr>
        <td><strong>${p.id}</strong></td>
        <td class="muted">${p.url || '-'}</td>
        <td><code>${masked}</code></td>
        <td>
          <button class="btn btn-sm btn-ghost" onclick="testProvider('${p.id}')">测试</button>
          <button class="btn btn-sm btn-danger" onclick="removeProvider('${p.id}')">删除</button>
        </td>
      </tr>`;
    }
    html += '</tbody></table>';
  }
  html += '</div></div>';
  content.innerHTML = html;
}

window.addProvider = async function() {
  const name = $('#provName').value.trim();
  const key = $('#provKey').value.trim();
  const url = $('#provUrl').value.trim();
  if (!name || !key) { $('#provMsg').textContent = '名称和 API Key 必填'; return; }
  const r = await api('providers/add', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({provider: name, api_key: key, base_url: url || undefined}),
  });
  $('#provMsg').textContent = r.message || r.error;
  if (r.success) { $('#provKey').value = ''; $('#provUrl').value = ''; setTimeout(renderProviders, 1000); }
};

window.removeProvider = async function(id) {
  if (!confirm(`确定删除 Provider: ${id}？`)) return;
  const r = await api('providers/remove', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({provider: id}),
  });
  if (r.success) toast(r.message); else toast(r.error, 'error');
  renderProviders();
};

window.testProvider = async function(id) {
  const btn = event.target;
  btn.disabled = true; btn.textContent = '测试中...';
  const r = await api('providers/test/' + id);
  btn.disabled = false;
  if (r.success) {
    toast(`${id}: ${r.message}`, 'success');
    btn.textContent = '✓ 已连接';
    setTimeout(() => btn.textContent = '测试', 3000);
  } else {
    toast(`${id}: ${r.error || '连接失败'}`, 'error');
    btn.textContent = '✗ 失败';
    setTimeout(() => btn.textContent = '测试', 3000);
  }
};

// =================== Sessions ===================
async function renderSessions() {
  content.innerHTML = '<div class="page"><div class="loading">加载中...</div></div>';
  const data = await api('sessions');
  const sessions = data.sessions || [];

  let html = '<div class="page"><h2>📋 历史会话</h2><div class="card">';
  if (sessions.length === 0) {
    html += '<p class="muted">暂无会话记录</p>';
  } else {
    html += '<table class="table"><thead><tr><th>名称</th><th>ID</th><th>模型</th><th>创建时间</th><th>操作</th></tr></thead><tbody>';
    for (const s of sessions) {
      html += `<tr>
        <td>${s.name}</td>
        <td><code>${(s.id || '').slice(0, 12)}...</code></td>
        <td>${s.model || '-'}</td>
        <td class="muted">${s.created || '-'}</td>
        <td>
          <button class="btn btn-sm btn-ghost" onclick="exportSession('${s.id}')">导出</button>
          <button class="btn btn-sm btn-danger" onclick="deleteSession('${s.id}')">删除</button>
        </td>
      </tr>`;
    }
    html += '</tbody></table>';
  }
  html += '</div></div>';
  content.innerHTML = html;
}

window.exportSession = async function(id) {
  const r = await api('sessions/' + id + '/export');
  if (r.success) {
    const blob = new Blob([JSON.stringify(r.data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `session_${id.slice(0, 8)}.json`; a.click();
    URL.revokeObjectURL(url);
    toast('导出成功');
  } else {
    toast(r.error || '导出失败', 'error');
  }
};

window.deleteSession = async function(id) {
  if (!confirm('确定删除此会话？')) return;
  const r = await api('sessions/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({session_id: id}),
  });
  if (r.success) toast(r.message); else toast(r.error, 'error');
  renderSessions();
};

// =================== Stats ===================
async function renderStats() {
  content.innerHTML = '<div class="page"><div class="loading">加载中...</div></div>';
  const data = await api('stats');
  const stats = data.stats || {};

  let html = '<div class="page"><h2>📊 用量统计</h2><div class="card">';
  const entries = Object.entries(stats);
  if (entries.length === 0) {
    html += '<p class="muted">暂无统计数据，请先使用会话</p>';
  } else {
    html += '<table class="table"><tbody>';
    for (const [k, v] of entries) {
      html += `<tr><td><strong>${k}</strong></td><td>${v}</td></tr>`;
    }
    html += '</tbody></table>';
  }
  html += '</div></div>';
  content.innerHTML = html;
}

// =================== Settings ===================
async function renderSettings() {
  content.innerHTML = '<div class="page"><div class="loading">加载中...</div></div>';
  const data = await api('config');
  const cfg = data.config || {};
  const mirrors = data.mirrors || {};

  let html = '<div class="page"><h2>⚙ 设置</h2>';

  // Mirror selection
  html += '<div class="card"><h3>🌐 镜像源设置（用于检查更新和升级）</h3>';
  html += '<div class="form-row">';
  html += '<select id="cfgMirror" class="input" style="flex:1;">';
  for (const [key, label] of Object.entries({
    direct: 'github.com (直连)',
    ghproxy: 'ghproxy.com (推荐)',
    ghproxy2: 'mirror.ghproxy.com',
    custom: '自定义',
  })) {
    html += `<option value="${key}" ${cfg.mirror === key ? 'selected' : ''}>${label}</option>`;
  }
  html += '</select></div>';
  html += '<div class="form-row" id="customMirrorRow" style="' + (cfg.mirror === 'custom' ? '' : 'display:none') + '">';
  html += '<input id="cfgCustomUrl" class="input" placeholder="自定义镜像源 URL (如 https://your-mirror.com)" value="' + (cfg.mirror_custom_url || '') + '" style="flex:1;">';
  html += '</div>';
  html += `<button class="btn btn-primary" onclick="saveSettings()">保存设置</button>`;
  html += '<span id="cfgMsg" style="margin-left:12px;font-size:13px;"></span>';
  html += '</div>';

  // Dark mode toggle
  html += '<div class="card"><h3>🎨 主题</h3>';
  const dark = cfg.dark_mode !== false;
  html += `<label class="toggle-label"><input type="checkbox" id="cfgDark" ${dark ? 'checked' : ''} onchange="toggleDarkMode(this.checked)"> 深色模式</label>`;
  html += '</div>';

  // App info
  html += '<div class="card"><h3>📄 应用信息</h3>';
  html += '<table class="table"><tbody>';
  html += `<tr><td>应用名称</td><td>MiMo Code</td></tr>`;
  html += `<tr><td>包装器版本</td><td>v0.5.0</td></tr>`;
  html += `<tr><td>数据目录</td><td><code>/var/apps/mimocode</code></td></tr>`;
  html += `<tr><td>日志文件</td><td><code>/var/apps/mimocode/var/mimo.log</code></td></tr>`;
  html += '</tbody></table>';
  html += '</div>';

  html += '</div>';
  content.innerHTML = html;

  // Mirror change handler
  $('#cfgMirror').addEventListener('change', function() {
    $('#customMirrorRow').style.display = this.value === 'custom' ? '' : 'none';
  });
}

window.saveSettings = async function() {
  const cfg = {
    mirror: $('#cfgMirror').value,
    mirror_custom_url: $('#cfgCustomUrl') ? $('#cfgCustomUrl').value : '',
    dark_mode: $('#cfgDark') ? $('#cfgDark').checked : true,
  };
  const r = await api('config/save', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(cfg),
  });
  $('#cfgMsg').textContent = r.message || r.error;
  if (r.success) toast('设置已保存');
};

window.toggleDarkMode = function(checked) {
  document.documentElement.style.setProperty('--bg', checked ? '#0a0a0f' : '#f5f5f7');
  document.documentElement.style.setProperty('--bg-surface', checked ? '#12121a' : '#ffffff');
  document.documentElement.style.setProperty('--bg-elevated', checked ? '#1a1a24' : '#f0f0f2');
  document.documentElement.style.setProperty('--bg-hover', checked ? '#22222e' : '#e8e8ec');
  document.documentElement.style.setProperty('--border', checked ? '#2a2a38' : '#dddde0');
  document.documentElement.style.setProperty('--text', checked ? '#e4e4ec' : '#1a1a2e');
  document.documentElement.style.setProperty('--text-secondary', checked ? '#8888a0' : '#666680');
  document.documentElement.style.setProperty('--text-muted', checked ? '#555568' : '#9999a0');
  saveSettings();
};

// =================== Upgrade ===================
async function renderUpgrade() {
  content.innerHTML = '<div class="page"><div class="loading">加载中...</div></div>';
  const [statusData, cfgData] = await Promise.all([
    api('upgrade/status'),
    api('config'),
  ]);
  const cfg = cfgData.config || {};
  const currentVer = statusData.current_version || '?';
  const mirror = cfg.mirror || 'direct';

  let html = '<div class="page"><h2>⬆ 检查更新</h2>';

  html += '<div class="card"><h3>当前版本</h3>';
  html += `<p style="font-size:24px;font-weight:700;">v${currentVer}</p>`;
  html += `<p class="muted">包装器 v0.5.0</p>`;
  html += '</div>';

  // Mirror info
  html += '<div class="card"><h3>🌐 镜像源</h3>';
  html += `<p>当前使用: <strong>${mirror === 'custom' ? (cfg.mirror_custom_url || '自定义') : mirror}</strong></p>`;
  html += `<button class="btn btn-ghost btn-sm" onclick="navigate('settings')">修改镜像源</button>`;
  html += '</div>';

  // Check update button
  html += '<div class="card"><h3>检查更新</h3>';
  html += `<button class="btn btn-primary" id="checkUpdateBtn" onclick="checkUpdate()">🔍 检查新版本</button>`;
  html += '<div id="updateResult" style="margin-top:12px;"></div>';
  html += '</div>';

  // Upgrade button (hidden until new version found)
  html += '<div id="upgradePanel" class="card" style="display:none;">';
  html += '<h3>⬇ 升级</h3>';
  html += '<div id="upgradeInfo"></div>';
  html += '<button class="btn btn-primary btn-lg" id="doUpgradeBtn" onclick="doUpgrade()" style="display:none;">⬇ 立即升级</button>';
  html += '<div id="upgradeProgress" style="margin-top:12px;"></div>';
  html += '</div>';

  html += '</div>';
  content.innerHTML = html;
}

let _latestVersionInfo = null;

window.checkUpdate = async function() {
  const btn = $('#checkUpdateBtn');
  const result = $('#updateResult');
  btn.disabled = true; btn.textContent = '检查中...';
  result.innerHTML = '<span class="loading" style="display:inline-block;width:20px;height:20px;"></span> 正在查询...';

  const cfg = (await api('config')).config || {};
  const mirror = cfg.mirror || 'direct';
  const custom = cfg.mirror_custom_url || '';

  const r = await api('check-update?mirror=' + encodeURIComponent(mirror) + '&custom_url=' + encodeURIComponent(custom));

  if (r.error) {
    result.innerHTML = `<div class="alert alert-error">❌ 检查失败：${r.error}</div>`;
    btn.disabled = false; btn.textContent = '🔍 重试';
    return;
  }

  const current = r.current_version || '0.1.0';
  const latest = r.version || '0.1.0';

  if (r.version && r.version !== current && r.version !== '0.1.0') {
    _latestVersionInfo = r;
    result.innerHTML = `<div class="alert alert-success">🎉 发现新版本！v${current} → <strong>v${latest}</strong></div>`;
    $('#upgradePanel').style.display = '';
    $('#upgradeInfo').innerHTML = `
      <p>发布日期：${r.published || '未知'}</p>
      <p>下载地址：<code style="font-size:11px;word-break:break-all;">${(r.download_url || '').slice(0, 100)}...</code></p>
    `;
    $('#doUpgradeBtn').style.display = '';
    btn.textContent = '✓ 已检查';
  } else {
    result.innerHTML = `<div class="alert alert-info">✅ 已是最新版本 v${current}</div>`;
    btn.disabled = false; btn.textContent = '🔍 再检查';
  }
};

window.doUpgrade = async function() {
  if (!_latestVersionInfo) return;
  const btn = $('#doUpgradeBtn');
  const progress = $('#upgradeProgress');
  btn.disabled = true; btn.textContent = '正在下载升级...';
  progress.innerHTML = '<span class="loading" style="display:inline-block;width:20px;height:20px;"></span> 下载中（约 135MB，可能需要几分钟）...';

  const r = await api('upgrade/do', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      download_url: _latestVersionInfo.download_url,
      version: _latestVersionInfo.version,
    }),
  });

  if (r.success) {
    progress.innerHTML = `<div class="alert alert-success">${r.message}</div>`;
    btn.textContent = '✅ 升级完成';
    setTimeout(() => renderUpgrade(), 2000);
  } else {
    progress.innerHTML = `<div class="alert alert-error">❌ 升级失败：${r.error}</div>`;
    btn.disabled = false; btn.textContent = '重新尝试';
  }
};

// =================== Logs ===================
async function renderLogs() {
  content.innerHTML = '<div class="page"><div class="loading">加载中...</div></div>';
  const data = await api('logs?limit=100');
  const logs = data.logs || [];

  let html = '<div class="page"><h2>📋 运行日志</h2>';
  html += '<div class="card" style="max-height:600px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.6;">';
  if (logs.length === 0) {
    html += '<p class="muted">暂无日志</p>';
  } else {
    for (const l of logs) {
      const cls = l.source === 'wrapper' ? 'log-wrapper' : 'log-mimo';
      html += `<div class="${cls}">${escapeHtml(l.text)}</div>`;
    }
  }
  html += '</div>';
  html += '<div style="margin-top:8px;">';
  html += `<button class="btn btn-ghost btn-sm" onclick="renderLogs()">🔄 刷新</button>`;
  html += `<button class="btn btn-ghost btn-sm" onclick="clearLogs()">🗑 清空</button>`;
  html += '</div>';
  html += '</div>';
  content.innerHTML = html;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

window.clearLogs = function() {
  // Log clearing is not implemented on backend, just reload
  toast('请在设置中管理日志文件', 'info');
};

// =================== Agent Management ===================
async function renderAgents() {
  content.innerHTML = '<div class="page"><div class="loading">加载Agent列表...</div></div>';
  const data = await api('agents');
  if (data.error) {
    content.innerHTML = '<div class="page"><div class="panel warn">加载失败: ' + data.error + '</div></div>';
    return;
  }
  const ag = data.agents || [];
  let cards = '';
  for (const a of ag) {
    const perms = a.permissions || [];
    let permHtml = '';
    for (const p of perms) {
      const cls = p.action === 'allow' ? 'tag-green' : 'tag-yellow';
      permHtml += `<div class="tag ${cls}">${p.permission || p.pattern || '?'} → ${p.action}</div>`;
    }
    cards += `
      <div class="panel">
        <div class="panel-h"><strong>${a.name}</strong> <span class="tag tag-blue">${a.type}</span></div>
        <div class="panel-b" style="margin-top:8px">
          ${permHtml || '<span class="muted">无权限条目</span>'}
        </div>
      </div>`;
  }

  content.innerHTML = `
    <div class="page">
      <h2>🤖 Agent 管理</h2>
      <p class="desc">管理 MiMo Code 的 AI Agent（角色与权限）</p>
      <div class="dash-grid" style="grid-template-columns:1fr 1fr">
        <div class="dash-card accent">
          <h3>Agent 数量</h3>
          <div class="value">${ag.length}</div>
        </div>
      </div>
      <div class="section-title">Agent 列表</div>
      ${cards || '<div class="panel muted">暂无 Agent</div>'}
      <div class="section-title">创建新 Agent</div>
      <div class="panel">
        <div class="form-row">
          <input id="agentName" placeholder="Agent 名称 (如 my-assistant)" class="inp" />
          <input id="agentDesc" placeholder="描述 (如 编程助手)" class="inp" />
        </div>
        <div class="form-row">
          <select id="agentMode" class="inp" style="flex:1">
            <option value="subagent">子 Agent (subagent)</option>
            <option value="primary">主要 Agent (primary)</option>
            <option value="all">全部 (all)</option>
          </select>
          <input id="agentTools" placeholder="工具 (如 bash,read,write 留空=全部)" class="inp" style="flex:2" />
        </div>
        <div class="form-row">
          <input id="agentModel" placeholder="模型 (如 openai/gpt-4o, 留空=默认)" class="inp" style="flex:3" />
          <button class="btn" onclick="createAgent()">创建 Agent</button>
        </div>
      </div>
    </div>`;
}

async function createAgent() {
  const name = $('#agentName').value.trim();
  const desc = $('#agentDesc').value.trim();
  const mode = $('#agentMode').value;
  const tools = $('#agentTools').value.trim();
  const model = $('#agentModel').value.trim();
  if (!name) { toast('请输入 Agent 名称', 'warn'); return; }
  const btn = content.querySelector('.btn');
  btn.disabled = true; btn.textContent = '创建中...';
  const r = await api('agents/create', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, description: desc, mode, tools, model}),
  });
  btn.disabled = false; btn.textContent = '创建 Agent';
  if (r.success) {
    toast('Agent 创建成功！');
    renderAgents();
  } else {
    toast('创建失败: ' + (r.output || r.error || '未知错误'), 'error');
  }
}

// =================== MCP Management ===================
async function renderMcp() {
  content.innerHTML = '<div class="page"><div class="loading">加载 MCP 服务器列表...</div></div>';
  const data = await api('mcp');
  if (data.error) {
    content.innerHTML = '<div class="page"><div class="panel warn">加载失败: ' + data.error + '</div></div>';
    return;
  }
  const servers = data.servers || [];
  let listHtml = servers.map(s =>
    `<div class="tag tag-blue" style="padding:6px 12px">${s.name}</div>`
  ).join(' ') || '<span class="muted">暂无 MCP 服务器</span>';

  content.innerHTML = `
    <div class="page">
      <h2>🔌 MCP 服务器管理</h2>
      <p class="desc">Model Context Protocol — 外部工具/数据集成</p>
      <div class="dash-grid" style="grid-template-columns:1fr 1fr">
        <div class="dash-card accent">
          <h3>已配置</h3>
          <div class="value">${servers.length}</div>
        </div>
      </div>
      <div class="section-title">已添加的 MCP 服务器</div>
      <div class="panel" style="display:flex;flex-wrap:wrap;gap:8px">${listHtml}</div>
      <div class="section-title">添加 MCP 服务器</div>
      <div class="panel">
        <div class="form-row">
          <input id="mcpName" placeholder="名称 (如 filesystem-server)" class="inp" />
          <input id="mcpUrl" placeholder="URL/命令 (如 npx @modelcontextprotocol/server-filesystem /path)" class="inp" style="flex:2" />
          <button class="btn" onclick="addMcp()">添加</button>
        </div>
      </div>
      <details style="margin-top:8px">
        <summary class="muted" style="cursor:pointer">原始输出</summary>
        <pre class="code-block">${escHtml(data.raw || '')}</pre>
      </details>
    </div>`;
}

async function addMcp() {
  const name = $('#mcpName').value.trim();
  const url = $('#mcpUrl').value.trim();
  if (!name) { toast('请输入名称', 'warn'); return; }
  const btn = content.querySelector('.btn');
  btn.disabled = true; btn.textContent = '添加中...';
  const r = await api('mcp/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name, url}),
  });
  btn.disabled = false; btn.textContent = '添加';
  if (r.success) {
    toast('MCP 服务器已添加');
    renderMcp();
  } else {
    toast('添加失败: ' + (r.output || r.error || '未知错误'), 'error');
  }
}

// =================== ACP Server ===================
async function renderAcp() {
  content.innerHTML = '<div class="page"><div class="loading">加载 ACP 状态...</div></div>';
  const status = await api('acp/status');
  const running = status.running;
  content.innerHTML = `
    <div class="page">
      <h2>🌐 ACP 服务</h2>
      <p class="desc">Agent Client Protocol — 让外部程序通过 API 连接 MiMo Code</p>
      <div class="dash-grid" style="grid-template-columns:1fr 1fr 1fr">
        <div class="dash-card ${running ? 'green' : 'red'}">
          <h3>服务状态</h3>
          <div class="value">${running ? '运行中' : '已停止'}</div>
          <div class="sub">PID: ${status.pid || '-'}</div>
        </div>
        <div class="dash-card accent">
          <h3>端口</h3>
          <div class="value">${status.port || 5671}</div>
        </div>
        <div class="dash-card">
          <h3>操作</h3>
          <div style="display:flex;gap:8px;margin-top:8px">
            ${running
              ? `<button class="btn btn-danger" onclick="toggleAcp('stop')">停止 ACP</button>`
              : `<button class="btn" onclick="toggleAcp('start')">启动 ACP</button>`
            }
          </div>
        </div>
      </div>
      <div class="panel muted" style="margin-top:8px">
        启动后，外部程序可通过 <code>http://${host}:${status.port || 5671}</code> 连接 ACP 服务
      </div>
    </div>`;
}

async function toggleAcp(action) {
  const btn = content.querySelector('.btn, .btn-danger');
  if (btn) btn.disabled = true;
  const r = await api('acp/toggle', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({action}),
  });
  if (!r.error) {
    toast(r.message || (action === 'start' ? 'ACP 已启动' : 'ACP 已停止'));
  } else {
    toast('操作失败: ' + r.error, 'error');
  }
  renderAcp();
}

// =================== Debug Panel ===================
async function renderDebug() {
  content.innerHTML = '<div class="page"><div class="loading">收集诊断信息...</div></div>';
  const data = await api('debug');
  if (data.error) {
    content.innerHTML = '<div class="page"><div class="panel warn">加载失败: ' + data.error + '</div></div>';
    return;
  }
  content.innerHTML = `
    <div class="page">
      <h2>🔍 诊断面板</h2>
      <p class="desc">MiMo Code 运行环境与配置诊断</p>
      <div class="dash-grid" style="grid-template-columns:1fr 1fr">
        <div class="dash-card accent">
          <h3>Wrapper 版本</h3>
          <div class="value">${data.wrapper_version || '?'}</div>
          <div class="sub">监听端口 ${data.listening_port || '-'}</div>
        </div>
        <div class="dash-card">
          <h3>运行时间</h3>
          <div class="value">${fmtUptime(data.uptime || 0)}</div>
          <div class="sub">${data.var_dir || '-'}</div>
        </div>
      </div>
      ${renderDebugSection('⚙️ 运行配置 (config)', data.config)}
      ${renderDebugSection('📁 全局路径 (paths)', data.paths)}
      ${renderDebugSection('🧠 Agent 详情', data.agent_primary)}
      ${renderDebugSection('🛠️ 可用技能 (skills)', data.skills)}
      ${renderDebugSection('📂 已知项目 (scrap)', data.scrap)}
    </div>`;
}

function renderDebugSection(title, contentText) {
  if (!contentText) return '';
  return `
    <details class="debug-section">
      <summary><strong>${title}</strong></summary>
      <pre class="code-block">${escHtml(contentText)}</pre>
    </details>`;
}

function fmtUptime(secs) {
  if (!secs) return '-';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return h + 'h ' + m + 'm';
  if (m > 0) return m + 'm ' + s + 's';
  return s + 's';
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// =================== Init ===================
// Auto-refresh status dot
setInterval(async () => {
  if (currentView !== 'dashboard') return;
  const data = await api('status');
  const dot = $('#statusDot');
  if (dot) dot.className = 'status-dot' + (data.mimo_web ? ' running' : '');
}, 10000);

// Load dashboard on start
renderDashboard();
