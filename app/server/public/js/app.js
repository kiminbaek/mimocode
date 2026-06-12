/* MiMo Code Deep Integration v0.4.0 — Frontend SPA */
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const host = location.hostname;
const content = $('#content');
let currentView = 'dashboard';

// Toast
function toast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  t.onclick = () => t.remove();
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// API fetch helper
async function api(path, opts) {
  try {
    const r = await fetch('/api/' + path, opts);
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
  if (view === 'chat') {
    content.innerHTML = '';
    const iframe = document.createElement('iframe');
    iframe.className = 'chat-container';
    iframe.src = 'http://' + host + ':5669/';
    content.appendChild(iframe);
    return;
  }
  const fn = { dashboard: renderDashboard, providers: renderProviders,
               sessions: renderSessions, stats: renderStats,
               settings: renderSettings, upgrade: renderUpgrade }[view];
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
  const models = data.models || [];
  const ver = data.version || 'unknown';
  const running = data.mimo_web;

  const dot = $('#statusDot');
  dot.className = 'status-dot' + (running ? ' running' : '');

  content.innerHTML = `
    <div class="dashboard">
      <div class="dash-grid">
        <div class="dash-card ${running ? 'green' : 'red'}">
          <h3>服务状态</h3>
          <div class="value">${running ? '运行中' : '已停止'}</div>
          <div class="sub">PID: ${data.mimo_web_pid || '-'} | 端口 5669</div>
        </div>
        <div class="dash-card accent">
          <h3>版本</h3>
          <div class="value">v${ver}</div>
          <div class="sub">MiMo Code</div>
        </div>
        <div class="dash-card yellow">
          <h3>可用模型</h3>
          <div class="value">${data.models_count || 0}</div>
          <div class="sub">已加载模型数量</div>
        </div>
        <div class="dash-card">
          <h3>快捷操作</h3>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
            <button class="btn btn-primary btn-sm" onclick="navigate('chat')">💬 新建会话</button>
            <button class="btn btn-ghost btn-sm" onclick="navigate('sessions')">📋 历史会话</button>
            <button class="btn btn-ghost btn-sm" onclick="navigate('providers')">🔑 Provider</button>
          </div>
        </div>
      </div>
      <div class="section-title">可用模型</div>
      <div class="model-list">
        ${models.length === 0 ? '<div style="color:var(--text-muted);padding:12px;">暂无模型信息</div>' :
          models.slice(0, 10).map(m => {
            const d = m.details || {};
            const tags = (d.tags || []).join(' ');
            const costInfo = d.cost ? `输入 \$${d.cost.input}/M • 输出 \$${d.cost.output}/M` : '';
            return `<div class="model-item">
              <div class="model-name">${m.id}</div>
              <div class="model-meta">
                ${d.provider ? `<span>${d.provider}</span>` : ''}
                <span>${Math.round((d.limit?.context || 0) / 1000)}K ctx</span>
                ${costInfo ? `<span>${costInfo}</span>` : ''}
                ${d.free ? '<span class="model-tag free">免费</span>' : ''}
              </div>
            </div>`;
          }).join('')
        }
        ${models.length > 10 ? `<div style="color:var(--text-muted);font-size:12px;padding:8px 0;">…还有 ${models.length - 10} 个模型</div>` : ''}
      </div>
    </div>
  `;
}

// =================== Providers ===================
async function renderProviders() {
  content.innerHTML = '<div class="dashboard"><div class="loading">加载中...</div></div>';
  const data = await api('providers');
  const providers = data.providers || [];
  const configProviders = data.config_providers || {};

  content.innerHTML = `
    <div class="dashboard">
      <div class="page-header">
        <div class="page-title">Provider 管理</div>
        <div class="page-sub">管理 AI 服务商和 API 密钥（共 ${providers.length} 个）</div>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <h3 style="margin-bottom:12px;">添加服务商</h3>
        <form id="add-provider-form" style="display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:10px;align-items:end;">
          <div class="form-group" style="margin:0;">
            <label class="form-label">服务商</label>
            <select id="new-provider-name" class="form-input" required>
              <option value="">选择…</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="azure">Azure OpenAI</option>
              <option value="google">Google Gemini</option>
              <option value="deepseek">DeepSeek</option>
              <option value="moonshot">Moonshot</option>
              <option value="openrouter">OpenRouter</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          <div class="form-group" style="margin:0;">
            <label class="form-label">API 密钥</label>
            <input type="password" id="new-provider-key" class="form-input" placeholder="sk-..." required>
          </div>
          <div class="form-group" style="margin:0;">
            <label class="form-label">自定义地址（可选）</label>
            <input type="text" id="new-provider-url" class="form-input" placeholder="https://api.example.com/v1">
          </div>
          <button type="submit" class="btn btn-primary">添加</button>
        </form>
      </div>

      <div class="card" style="margin-bottom:16px;">
        <h3 style="margin-bottom:12px;">已配置的 Provider</h3>
        ${providers.length === 0 ? '<div style="color:var(--text-muted);padding:12px 0;">尚未添加任何 Provider</div>' : ''}
        <table class="data-table">
          <thead><tr>
            <th>服务商</th>
            <th>API Key</th>
            <th>地址</th>
            <th style="text-align:right">操作</th>
          </tr></thead>
          <tbody>
            ${providers.map(p => `
              <tr>
                <td><strong>${p.provider || p.name || '-'}</strong></td>
                <td style="color:var(--text-muted);font-family:monospace;font-size:12px;">
                  ${(p.apiKey || '').substring(0, 12)}...
                </td>
                <td style="color:var(--text-muted);font-size:12px;">${p.baseURL || p.api || '-'}</td>
                <td style="text-align:right">
                  <button class="btn btn-danger btn-sm" onclick="removeProvider('${p.provider || p.name || ''}')">删除</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      <div class="card">
        <h3 style="margin-bottom:12px;">内置 Provider（系统配置）</h3>
        <table class="data-table">
          <thead><tr><th>名称</th><th>API 地址</th></tr></thead>
          <tbody>
            ${Object.entries(configProviders).map(([k, v]) => `
              <tr>
                <td><strong>${k}</strong></td>
                <td style="color:var(--text-muted);font-size:12px;">${v.api || '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;

  // Bind add form
  $('#add-provider-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const provider = $('#new-provider-name').value;
    const apiKey = $('#new-provider-key').value;
    const baseUrl = $('#new-provider-url').value;
    if (!provider || !apiKey) { toast('请填写服务商和 API 密钥', 'error'); return; }
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = '添加中…';
    const r = await api('providers/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({provider, api_key: apiKey, base_url: baseUrl || undefined}),
    });
    btn.disabled = false;
    btn.textContent = '添加';
    if (r.ok) {
      toast(r.output || '添加成功');
      renderProviders();
    } else {
      toast(r.error || '添加失败', 'error');
    }
  });
}

async function removeProvider(name) {
  if (!name || !confirm(`确定删除 Provider "${name}"？`)) return;
  const r = await api('providers/remove/' + encodeURIComponent(name), { method: 'DELETE' });
  toast(r.ok ? (r.output || '已删除') : (r.error || '删除失败'), r.ok ? 'success' : 'error');
  if (r.ok) renderProviders();
}

// =================== Sessions ===================
async function renderSessions() {
  content.innerHTML = '<div class="dashboard"><div class="loading">加载中...</div></div>';
  const data = await api('sessions');
  const sessions = data.sessions || [];

  content.innerHTML = `
    <div class="dashboard">
      <div class="page-header">
        <div class="page-title">历史会话</div>
        <div class="page-sub">共 ${sessions.length} 个会话${sessions.length > 0 ? '（点击导出下载 JSON）' : ''}</div>
      </div>
      ${sessions.length === 0 ? '<div class="empty"><div class="empty-icon">📋</div>暂无会话记录</div>' : `
        <table class="data-table">
          <thead><tr>
            <th>会话标题</th>
            <th>项目</th>
            <th>更新时间</th>
            <th style="text-align:right">操作</th>
          </tr></thead>
          <tbody>
            ${sessions.map(s => {
              const d = new Date(s.updated);
              const t = `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
              return `<tr>
                <td><strong>${s.title || '无标题'}</strong></td>
                <td style="color:var(--text-muted)">${s.projectId || '-'}</td>
                <td style="color:var(--text-muted)">${t}</td>
                <td style="text-align:right">
                  <button class="btn btn-ghost btn-sm" onclick="exportSession('${s.id}')">导出</button>
                  <button class="btn btn-danger btn-sm" onclick="deleteSession('${s.id}','${(s.title||'').replace(/'/g,"\\'")}')">删除</button>
                </td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      `}
    </div>
  `;
}

async function deleteSession(id, title) {
  if (!confirm('确定删除会话 "' + title + '"？')) return;
  const r = await api('sessions/' + id + '/delete');
  toast(r.ok ? '已删除' : '删除失败', r.ok ? 'success' : 'error');
  if (r.ok) renderSessions();
}

async function exportSession(id) {
  const data = await api('sessions/' + id + '/export');
  if (data.ok) {
    const content = data.output || '';
    const isJson = (data.message || '').indexOf('JSON') === -1;
    const blob = new Blob([content], { type: isJson ? 'application/json' : 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = id + (isJson ? '.json' : '.txt');
    a.click();
    toast('导出成功');
  } else {
    toast(data.error || '导出失败', 'error');
  }
}

// =================== Stats ===================
async function renderStats() {
  content.innerHTML = '<div class="dashboard"><div class="loading">加载中...</div></div>';
  const data = await api('stats');
  const stats = data.stats || {};
  const days = data.days || 30;

  content.innerHTML = `
    <div class="dashboard">
      <div class="page-header">
        <div class="page-title">用量统计</div>
        <div class="page-sub">最近 ${days} 天使用情况</div>
      </div>
      <div class="dash-grid">
        <div class="dash-card">
          <h3>会话数</h3>
          <div class="stat-highlight">${stats['Sessions'] || '0'}</div>
        </div>
        <div class="dash-card">
          <h3>消息数</h3>
          <div class="stat-highlight">${stats['Messages'] || '0'}</div>
        </div>
        <div class="dash-card green">
          <h3>总费用</h3>
          <div class="stat-highlight">${stats['Total Cost'] || '$0.00'}</div>
        </div>
        <div class="dash-card accent">
          <h3>平均 Token/会话</h3>
          <div class="stat-highlight">${stats['Avg Tokens/Session'] || '-'}</div>
        </div>
      </div>
      <div class="dash-card">
        <h3>Token 明细</h3>
        <div class="stat-row"><span class="stat-label">输入 (Input)</span><span class="stat-value">${stats['Input'] || '-'}</span></div>
        <div class="stat-row"><span class="stat-label">输出 (Output)</span><span class="stat-value">${stats['Output'] || '-'}</span></div>
        <div class="stat-row"><span class="stat-label">缓存读取 (Cache Read)</span><span class="stat-value">${stats['Cache Read'] || '-'}</span></div>
        <div class="stat-row"><span class="stat-label">缓存写入 (Cache Write)</span><span class="stat-value">${stats['Cache Write'] || '-'}</span></div>
        <div class="stat-row"><span class="stat-label">平均费用/天</span><span class="stat-value">${stats['Avg Cost/Day'] || '-'}</span></div>
      </div>
      <div class="dash-card">
        <h3>工具调用统计</h3>
        <div id="toolStats">${data.models_raw ? '<pre style="font-size:12px;color:var(--text-secondary);white-space:pre-wrap;">' + data.models_raw + '</pre>' : '<div style="color:var(--text-muted)">无工具调用数据</div>'}</div>
      </div>
    </div>
  `;
}

// =================== Settings ===================
async function renderSettings() {
  content.innerHTML = '<div class="dashboard"><div class="loading">加载中...</div></div>';
  const data = await api('config');
  const config = data.config || {};

  content.innerHTML = `
    <div class="dashboard">
      <div class="page-header">
        <div class="page-title">系统设置</div>
        <div class="page-sub">MiMo Code 配置与路径信息</div>
      </div>
      <div class="dash-card">
        <h3>路径信息</h3>
        <div style="font-size:12px;color:var(--text-secondary);margin-top:8px;">
          <pre style="white-space:pre-wrap;font-family:monospace;">${data.paths || '-'}</pre>
        </div>
      </div>
      <div class="dash-card">
        <h3>当前配置</h3>
        <div class="config-box">${JSON.stringify(config, null, 2)}</div>
      </div>
    </div>
  `;
}

// =================== Upgrade ===================
async function renderUpgrade() {
  content.innerHTML = '<div class="dashboard"><div class="loading">加载中...</div></div>';
  const data = await api('upgrade');

  content.innerHTML = `
    <div class="dashboard">
      <div class="upgrade-card">
        <div class="upgrade-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="48" height="48" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 18 13 8 3 18"></polyline>
            <line x1="21" y1="16" x2="21" y2="2"></line>
          </svg>
        </div>
        <h2>升级 MiMo Code</h2>
        <p>当前版本: <strong>${data.current_version || '未知'}</strong></p>
        <div style="margin-top:12px;font-size:12px;color:var(--text-secondary);">
          <p>升级将从 GitHub 下载最新版本替换二进制。</p>
          <p style="color:var(--yellow);margin-top:6px;">⚠️ 注意：升级后二进制被替换，但下次重装 fpk 会恢复为打包版本。</p>
        </div>
        <button id="do-upgrade-btn" class="btn btn-primary" style="margin-top:16px;" onclick="doUpgrade()">升级到最新版</button>
        <div id="upgrade-status" style="margin-top:12px;"></div>
      </div>
    </div>
  `;
}

async function doUpgrade() {
  const btn = $('#do-upgrade-btn');
  const status = $('#upgrade-status');
  btn.disabled = true;
  btn.textContent = '升级中…';
  status.innerHTML = '<div class="loading">正在升级，预计 2 分钟…</div>';
  const r = await api('upgrade/do', { method: 'POST' });
  btn.disabled = false;
  btn.textContent = '升级到最新版';
  if (r.ok) {
    status.innerHTML = '<div style="color:var(--green);">升级成功！建议重启应用。</div>';
    toast('升级成功');
  } else {
    status.innerHTML = '<div style="color:var(--red);">升级失败：' + (r.error || r.output || '未知错误') + '</div>';
    toast('升级失败', 'error');
  }
}
