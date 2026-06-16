/* MiMo Code fnOS App v0.11.21 */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const state = { token: localStorage.getItem('mimocode_token') || '', setup: false, status: null, providers: [], presets: [], config: {}, view: 'workspace', sessions: [], officialFrameReady: false };
const OFFICIAL_MODELS = ['mimo/mimo-auto','xiaomi/mimo-v2-flash','xiaomi/mimo-v2-omni','xiaomi/mimo-v2-pro','xiaomi/mimo-v2.5','xiaomi/mimo-v2.5-pro','xiaomi/mimo-v2.5-pro-ultraspeed'];

function esc(s){ return String(s ?? '').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function toast(msg,type='ok'){ const el=document.createElement('div'); el.className='toast '+type; el.textContent=msg; document.body.appendChild(el); setTimeout(()=>el.remove(),4200); }
async function copyText(text){ await navigator.clipboard.writeText(text); toast('已复制到剪贴板'); }
function timeText(ts){ if(!ts)return '-'; return new Date(ts*1000).toLocaleString('zh-CN'); }
function yesNo(v){ return v ? '正常' : '需处理'; }
async function ensureSessionCookie(){ try{ await api('auth/session-cookie',{method:'POST',body:JSON.stringify({})}); return true; }catch(e){ console.warn('session cookie refresh failed', e); return false; } }

async function api(path, opts={}){
  const headers=Object.assign({'Content-Type':'application/json'},opts.headers||{});
  if(state.token) headers.Authorization='Bearer '+state.token;
  const res=await fetch('/api/'+path,Object.assign({},opts,{headers}));
  const text=await res.text(); let data;
  try{ data=text?JSON.parse(text):{}; }catch(e){ data={error:text||e.message}; }
  if(!res.ok){
    if(res.status===401 && !path.startsWith('auth/')){ localStorage.removeItem('mimocode_token'); state.token=''; showAuth('登录已过期，请重新登录'); }
    throw Object.assign(new Error(data.error||('HTTP '+res.status)),{data,status:res.status});
  }
  return data;
}

function showAuth(msg=''){
  $('#mainView').classList.add('hidden'); $('#authView').classList.remove('hidden');
  $('#passwordInput').value=''; $('#authMsg').textContent=msg; $('#authMsg').className=msg?'msg err':'msg';
  $('#authHint').textContent=state.setup?'请输入管理密码进入 MiMo Code。':'首次使用：请设置一个至少 8 位的管理密码。';
  $('#passwordInput').placeholder=state.setup?'管理密码':'设置管理密码（至少 8 位）';
  $('#authBtn').textContent=state.setup?'登录':'初始化并进入';
}
function showMain(){ $('#authView').classList.add('hidden'); $('#mainView').classList.remove('hidden'); }

async function handleAuth(){
  const pw=$('#passwordInput').value.trim();
  if(state.setup){
    if(pw.length<8){ toast('密码至少 8 位'); return; }
    const res=await api('auth/setup',{method:'POST',body:JSON.stringify({password:pw})});
    if(res.error){ toast(res.error); return; }
    localStorage.setItem('mimocode_token', res.token);
    state.token=res.token;
  }else{
    const res=await api('auth/login',{method:'POST',body:JSON.stringify({password:pw})});
    if(res.error){ toast(res.error); return; }
    localStorage.setItem('mimocode_token', res.token);
    state.token=res.token;
  }
  await refreshAll(); showMain(); ensureSessionCookie(); navigate('workspace');
}
function bindStaticEvents(){
  $('#authBtn').onclick=handleAuth;
  $('#passwordInput').addEventListener('keypress',e=>{if(e.key==='Enter') handleAuth();});
}
async function init(){
  bindStaticEvents();
  try{
    const s=await api('auth/status'); state.setup=!!s.setup;
    if(!state.setup || !state.token) return showAuth();
    await refreshAll(); showMain(); navigate('workspace');
  }catch(e){ showAuth(e.message); }
}
function navigate(view){
  if(view==='toolbox' && !state.config.toolbox_enabled) view='advanced';
  if(state.view==='official' && view!=='official') rememberOfficialFrameUrl();
  state.view=view; const content=$('#content');
  if(content) content.classList.toggle('official-content', view==='official');
  $$('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view));
  ({workspace:renderWorkspace,overview:renderOverview,official:renderOfficialChat,providers:renderProviders,freeModels:renderFreeModels,health:renderHealth,security:renderSecurity,backup:renderBackup,sessions:renderSessions,logs:renderLogs,advanced:renderAdvanced,toolbox:renderToolbox}[view]||renderWorkspace)();
}

function statusCards(){ const f=state.status?.friendly||{}; return `<div class="status-grid">
  ${card('MiMo 服务',f.service,state.status?.mimo_open?'ok':'warn')}
  ${card('Web 入口',f.web,state.status?.mimo_open?'ok':'warn')}
  ${card('Provider',f.provider,state.status?.provider_configured?'ok':'warn')}
`;}

function card(title,text,status){ return `<div class="card ${status}"><div class="card-title">${esc(title)}</div><div class="card-text">${esc(text)}</div></div>`; }
async function refreshAll(){
  state.status=await api('status');
  const p=await api('providers'); state.providers=p.providers||[]; state.presets=p.presets||[]; state.config=p.config||{};
  try{ state.sessions=(await api('sessions')).sessions||[]; }catch(e){ state.sessions=[]; }
  $('#statusLine').innerHTML=`${state.status.mimo_open?'<span class="dot ok"></span>':'<span class="dot bad"></span>'} 服务${esc(state.status.friendly.service)} · Provider ${esc(state.status.friendly.provider)} · Wrapper v${esc(state.status.wrapper_version)}`;
  const toolTab=document.querySelector('[data-view="toolbox"]'); if(toolTab) toolTab.classList.toggle('hidden', !state.config.toolbox_enabled);
}
function officialDirectUrl(){
  // Go back to v0.5.0 pure direct connection: always connect to current host:5669 with same protocol
  // - If wrapper is HTTPS (official domain), iframe is HTTPS → no mixed content error
  // - If wrapper is HTTP (LAN), iframe is HTTP → works fine
  // - Official MiMo handles everything, no extra proxy shell
  const rawHost=location.hostname || (location.host||'').split(':')[0];
  const host=(rawHost.includes(':') && !rawHost.startsWith('[')) ? '['+rawHost+']' : rawHost;
  const protocol = location.protocol;
  return protocol + '//' + host + ':5669/';
}
function rememberOfficialFrameUrl(){ /* direct connection, cannot read url due to cross-origin, keep no-op */ }
async function renderOfficialChat(){
  const embedUrl=officialDirectUrl();
  const content=$('#content');
  const existing=$('#nativeFrame');
  if(existing){
    content.classList.add('official-content');
    return;
  }
  content.innerHTML='';
  content.classList.add('official-content');
  const iframe=document.createElement('iframe');
  iframe.id='nativeFrame'; iframe.className='official-native-frame'; iframe.src=embedUrl; iframe.title='MiMo 官方会话';
  content.appendChild(iframe);
}
async function openNativeWeb(){ window.open(officialDirectUrl(),'_blank'); }
function reloadNativeFrame(){ const f=$('#nativeFrame'); if(f) f.src=f.src; }

async function enableToolboxAndOpenCli(){ if(!state.config.toolbox_enabled){ await api('config',{method:'POST',body:JSON.stringify({toolbox_enabled:true})}); await refreshAll(); } navigate('toolbox'); setTimeout(toolCommand,80); }
function modelBadge(m){ if(m.free) return '<span class="pill free">免费/限免</span>'; if(m.badge) return `<span class="pill">${esc(m.badge)}</span>`; return ''; }
async function renderProviders(){
  let html=`
  <div class="panel">
    <div class="panel-head"><h2>模型与服务商</h2></div>
    <div class="provider-list">
  `;
  const grouped=Object.fromEntries([...new Set(state.providers.map(p=>p.group || '其它'))].map(g=>[g,[]]));
  state.providers.forEach(p=>grouped[p.group || '其它'].push(p));
  for(const group in grouped){
html+=`
<div class="provider-group"><div class="group-name">${esc(group)}</div><div class="group-items">
`;
grouped[group].forEach(p=>{
const free=p.free?'free':'';
html+=`
<div class="provider-item ${free}" data-id="${esc(p.id)}">
  <div class="provider-name">${esc(p.name)} ${modelBadge(p)}</div>
  <div class="provider-desc">${esc(p.desc || '')}</div>
</div>
`;
});
html+=`</div></div>`;
  }
  html+=`
    </div>
    <div class="pad-actions">
      <button class="btn" id="addProviderBtn">添加 Provider</button>
    </div>
  </div>
  `;
  $('#content').innerHTML=html;
  $('#addProviderBtn').onclick=()=>showAddProvider();
}
async function renderFreeModels(){
  let html=`
  <div class="panel">
    <div class="panel-head"><h2>免费模型库</h2><p>以下模型官方承诺免费/限免使用，无需 API Key 即可调用（以平台实时政策为准）。直接使用官方 MiMo 会话即可加载。</p></div>
    <div class="provider-list">
  `;
  const grouped=Object.fromEntries([...new Set(OFFICIAL_MODELS.map(p=>p.split('/')[0])]).map(g=>[g,[]]));
  OFFICIAL_MODELS.forEach(m=>{
const meta=MODEL_META[m]||{};
grouped[meta.group || 'MiMo 官方'].push({id:m, ...meta});
  });
  for(const group in grouped){
html+=`
<div class="provider-group"><div class="group-name">${esc(group)}</div><div class="group-items">
`;
grouped[group].forEach(p=>{
html+=`
<div class="provider-item ${p.free?'free':''}" data-id="${esc(p.id)}">
  <div class="provider-name">${esc(p.name || p.id)} ${modelBadge(p)}</div>
  <div class="provider-desc">${esc(p.desc || '')}</div>
</div>
`;
});
html+=`</div></div>`;
  }
  html+=`
    </div>
  </div>
  `;
  $('#content').innerHTML=html;
}
function renderWorkspace(){
  const html=`
<div class="hero-panel">
  <h1>欢迎来到 MiMo Code</h1>
  <p>MiMo Code 是小米推出的 AI 编程助手，原生支持在你的飞牛 NAS 本地运行。</p>
  <p>本 wrapper 提供了便捷的中文工作台、Provider 管理、运行状态检查和配置备份，官方会话保持直连原汁原味。</p>
  <div class="actions">
    <button class="btn btn-primary" onclick="navigate('official')">打开官方会话 ▶️</button>
    <button class="btn" onclick="navigate('providers')">管理 Provider / API Key</button>
    <button class="btn" onclick="openNativeWeb()">新窗口打开官方会话</button>
  </div>
  <div class="status-grid">${statusCards()}</div>
</div>
${renderOverviewCard()}
</div>
`;
  $('#content').innerHTML=html;
}
function renderOverviewCard(){
if(!state.status?.project_overview) return '';
const o=state.status.project_overview;
return `
<div class="panel">
  <div class="panel-head"><h3>当前项目</h3></div>
  <div class="overview">
    <div><span>路径:</span> <code>${esc(o.path||'-')}</code></div>
    <div><span>模型:</span> ${esc(o.model||'-')}</div>
    <div><span>tokens:</span> ${esc(o.tokens||'-')}</div>
  </div>
</div>
`;
}
async function renderHealth(){
  const s=state.status;
  const html=`
<div class="panel">
  <div class="panel-head"><h3>健康检查</h3></div>
  <div class="status-table">
    <div class="tr"><div class="td">Wrapper 版本</div><div class="td">v${esc(state.status.wrapper_version)}</div></div>
    <div class="tr"><div class="td">MiMo 二进制</div><div class="td">${esc(s.mimo_binary? '✅ 存在' : '❌ 不存在')}</div></div>
    <div class="tr"><div class="td">MiMo 端口 5669</div><div class="td">${s.mimo_open? '✅ 监听中' : '❌ 未监听'}</div></div>
    <div class="tr"><div class="td">Provider 配置</div><div class="td">${esc(s.provider_configured? '✅ 已配置' : '❌ 未配置')}</div></div>
  </div>
</div>
`;
  $('#content').innerHTML=html;
}
async function renderSecurity(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>安全信息</h3></div>
  <p>wrapper 不会存储你的 API Key 明文，加密保存在配置文件中。</p>
  <p>官方 MiMo 会将你的项目和对话存储在 ~/.config/mimocode 目录下，请妥善保管。</p>
</div>
`;
  $('#content').innerHTML=html;
}
function renderBackup(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>配置备份</h3></div>
  <p>你可以导出当前配置（不含加密的 API Key），或者导入配置。</p>
  <div class="pad-actions">
    <button class="btn" id="exportConfigBtn">导出配置</button>
    <button class="btn btn-danger" id="resetAllBtn">重置全部数据</button>
  </div>
</div>
`;
  $('#content').innerHTML=html;
  $('#exportConfigBtn').onclick=async ()=>{
    const res=await api('config/export');
    const json=JSON.stringify(res, null, 2);
    const blob=new Blob([json], {type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url; a.download=`mimocode-wrapper-backup-${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    toast('导出成功');
  };
  $('#resetAllBtn').onclick=async ()=>{
    if(!confirm('确定要重置全部 wrapper 数据吗？这不会删除你的官方 MiMo 配置。')) return;
    const res=await api('config/reset',{method:'POST'});
    if(res.error){ toast(res.error); return; }
    localStorage.removeItem('mimocode_token');
    toast('重置成功');
    location.reload();
  };
}
function renderLogs(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>最新日志</h3></div>
  <div class="logs"><pre id="logsPre"></pre></div>
  <div class="pad-actions">
    <button class="btn" id="refreshLogsBtn">刷新</button>
  </div>
</div>
`;
  $('#content').innerHTML=html;
  refreshLogs();
  $('#refreshLogsBtn').onclick=refreshLogs;
}
async function refreshLogs(){
  const res=await api('logs');
  $('#logsPre').textContent=res.logs || '(无日志)';
}
function renderSecurity(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>安全说明</h3></div>
  <p>wrapper 对你的 API Key 加密存储，不会明文泄露。</p>
</div>
`;
  $('#content').innerHTML=html;
}
async function renderSessions(){
  if(!state.sessions.length){
    $('#content').innerHTML='<div class="panel"><div class="panel-head"><h3>最近会话</h3><p>暂无会话记录</p></div></div>';
    return;
  }
  let html=`
<div class="panel">
  <div class="panel-head"><h3>最近会话</h3></div>
  <div class="sessions-list">
  `;
  state.sessions.forEach(s=>{
html+=`
<div class="session-item" data-id="${esc(s.id)}">
  <div class="session-title">${esc(s.title || 'Untitled')}</div>
  <div class="session-date">${timeText(s.updated_at)}</div>
</div>
`;
  });
  html+=`
  </div>
</div>
`;
  $('#content').innerHTML=html;
}
function renderAdvanced(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>高级设置</h3></div>
  <div class="form-item">
    <label>自动重启 MiMo Web</label>
    <div class="checkbox">
      <input type="checkbox" id="autoRestartMiMo" ${state.config.auto_restart_mimo?'checked':''}>
      <label for="autoRestartMiMo">开启包装器每隔 5 分钟检查 MiMo Web 是否运行，崩溃自动重启</label>
    </div>
  </div>
  <div class="form-item">
    <label>启用 CLI 工具箱</label>
    <div class="checkbox">
      <input type="checkbox" id="enableToolbox" ${state.config.toolbox_enabled?'checked':''}>
      <label for="enableToolbox">启用左侧边栏工具箱入口，可以直接在 wrapper 运行 MiMo CLI 命令</label>
    </div>
  </div>
  <div class="pad-actions">
    <button class="btn" id="saveAdvancedBtn">保存设置</button>
  </div>
</div>
`;
  $('#content').innerHTML=html;
  $('#saveAdvancedBtn').onclick=async ()=>{
    const autoRestart = $('#autoRestartMiMo').checked;
    const toolboxEnabled = $('#enableToolbox').checked;
    await api('config',{method:'POST',body:JSON.stringify({auto_restart_mimo:autoRestart, toolbox_enabled:toolboxEnabled})});
    await refreshAll();
    toast('设置已保存');
    navigate('workspace');
  };
}
function renderToolbox(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>MiMo CLI 工具箱</h3></div>
  <div id="toolOutput"></div>
  <div class="tool-input">
    <input type="text" id="toolInput" placeholder="输入 mimocode 命令，例如 models / providers" />
    <button class="btn btn-primary" id="toolRunBtn">运行</button>
  </div>
</div>
`;
  $('#content').innerHTML=html;
  $('#toolRunBtn').onclick=toolCommand;
  $('#toolInput').addEventListener('keypress',e=>{if(e.key==='Enter') toolCommand();});
}
async function toolCommand(){
  const cmd=$('#toolInput').value.trim();
  if(!cmd) return;
  const out=$('#toolOutput');
  out.innerHTML+='$ <span class="cmd">'+esc(cmd)+'</span>\n';
  const res=await api('toolbox/run',{method:'POST',body:JSON.stringify({command:cmd})});
  out.innerHTML+=esc(res.output || '(no output)')+'\n';
  out.scrollTop=out.scrollHeight;
  $('#toolInput').value='';
}
function showAddProvider(){
  const html=`
<div class="panel">
  <div class="panel-head"><h3>添加 Provider</h3></div>
  <div class="form-item">
    <label>Provider ID</label>
    <input type="text" id="p-id" placeholder="my-provider">
  </div>
  <div class="form-item">
    <label>Provider 名称</label>
    <input type="text" id="p-name" placeholder="我的提供商">
  </div>
  <div class="form-item">
    <label>API Base URL</label>
    <input type="text" id="p-base-url" placeholder="https://api.openai.com/v1">
  </div>
  <div class="form-item">
    <label>API Key</label>
    <input type="password" id="p-api-key" placeholder="sk-xxx">
  </div>
  <div class="form-item">
    <label>描述</label>
    <textarea id="p-desc" placeholder="你的 Provider 描述"></textarea>
  </div>
  <div class="pad-actions">
    <button class="btn" id="p-cancel">取消</button>
    <button class="btn btn-primary" id="p-save">保存</button>
  </div>
</div>
`;
  $('#content').innerHTML=html;
  $('#p-cancel').onclick=()=>navigate('providers');
  $('#p-save').onclick=async ()=>{
    const id=($('#p-id').value||'').trim();
    const name=($('#p-name').value||'').trim();
    const baseUrl=($('#p-base-url').value||'').trim();
    const apiKey=($('#p-api-key').value||'').trim();
    const desc=($('#p-desc').value||'').trim();
    if(!id || !name || !baseUrl || !apiKey){ toast('请填写所有字段'); return; }
    const res=await api('providers/add',{method:'POST',body:JSON.stringify({id,name,group:'自定义',base_url:baseUrl,api_key:apiKey,desc,free:false})});
    if(res.error){ toast(res.error); return; }
    await refreshAll();
    navigate('providers');
    toast('添加成功');
  };
}
const MODEL_META={
'mimo/mimo-auto': {'group': 'MiMo 官方', 'name': 'MiMo Auto', 'desc': '自动选择最合适的模型', 'free': true},
'xiaomi/mimo-v2-flash': {'group': 'MiMo 官方', 'name': 'MiMo V2 Flash', 'desc': '轻量快速，适合日常问答', 'free': true},
'xiaomi/mimo-v2-omni': {'group': 'MiMo 官方', 'name': 'MiMo V2 Omni', 'desc': '全能模型', 'free': true},
'xiaomi/mimo-v2-pro': {'group': 'MiMo 官方', 'name': 'MiMo V2 Pro', 'desc': '更强能力', 'free': false},
'xiaomi/mimo-v2.5': {'group': 'MiMo 官方', 'name': 'MiMo V2.5', 'desc': '最新改进版本', 'free': true},
'xiaomi/mimo-v2.5-pro': {'group': 'MiMo 官方', 'name': 'MiMo V2.5 Pro', 'desc': '最强全能模型', 'free': false},
'xiaomi/mimo-v2.5-pro-ultraspeed': {'group': 'MiMo 官方', 'name': 'MiMo V2.5 Pro 超速', 'desc': '极速响应，轻度任务', 'free': false},
};

init();
