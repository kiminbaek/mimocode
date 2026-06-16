/* MiMo Code fnOS App v0.11.9 */
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

async function init(){
  bindStaticEvents();
  try{
    const s=await api('auth/status'); state.setup=!!s.setup;
    if(!state.setup || !state.token) return showAuth();
    await refreshAll(); showMain(); ensureSessionCookie(); navigate('workspace');
  }catch(e){ showAuth(e.message); }
}
function bindStaticEvents(){
  $('#authBtn').onclick=handleAuth;
  $('#passwordInput').addEventListener('keydown',e=>{if(e.key==='Enter')handleAuth();});
  $('#clearTokenBtn').onclick=()=>{localStorage.removeItem('mimocode_token');state.token='';toast('本机登录缓存已清除');};
  $('#logoutBtn').onclick=async()=>{try{await api('auth/logout',{method:'POST',body:'{}'});}catch(e){} localStorage.removeItem('mimocode_token');state.token='';showAuth('已退出登录');};
  $$('.tab').forEach(t=>t.onclick=()=>navigate(t.dataset.view));
}
async function handleAuth(){
  const password=$('#passwordInput').value;
  try{
    const path=state.setup?'auth/login':'auth/setup';
    const r=await api(path,{method:'POST',body:JSON.stringify({password})});
    state.token=r.token; localStorage.setItem('mimocode_token',r.token); await refreshAll(); showMain(); ensureSessionCookie(); navigate('workspace');
  }catch(e){ $('#authMsg').textContent=e.data?.suggestion||e.message; $('#authMsg').className='msg err'; }
}
async function refreshAll(){
  state.status=await api('status');
  const p=await api('providers'); state.providers=p.providers||[]; state.presets=p.presets||[]; state.config=p.config||{};
  try{ state.sessions=(await api('sessions')).sessions||[]; }catch(e){ state.sessions=[]; }
  $('#statusLine').innerHTML=`${state.status.mimo_open?'<span class="dot ok"></span>':'<span class="dot bad"></span>'} 服务${esc(state.status.friendly.service)} · Provider ${esc(state.status.friendly.provider)} · Wrapper v${esc(state.status.wrapper_version)}`;
  const toolTab=document.querySelector('[data-view="toolbox"]'); if(toolTab) toolTab.classList.toggle('hidden', !state.config.toolbox_enabled);
}
function officialDirectUrl(){
  const rawHost=location.hostname || (location.host||'').split(':')[0];
  const host=(rawHost.includes(':') && !rawHost.startsWith('[')) ? '['+rawHost+']' : rawHost;
  const protocol = location.protocol === 'https:' ? 'https:' : 'http:';
  return protocol + '//' + host + ':5669/';
}
function rememberOfficialFrameUrl(){ /* 直连官方页面跨端口不同源，不能可靠读取 iframe 内部路由；保持 no-op，避免缓存错误路径。 */ }
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
  ${card('当前模型',f.model,state.status?.default_model?'ok':'warn')}
  ${card('CLI',f.cli,state.status?.cli_ok?'ok':'warn')}
</div>`; }
function card(k,v,type=''){ return `<div class="stat ${type}"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`; }
function runtimeCards(){ const st=state.status||{}, f=st.friendly||{}; const uptime=st.uptime_sec?Math.floor(st.uptime_sec/60)+' 分钟':'-'; return `${card('Wrapper','运行中 · '+uptime,'ok')}${card('官方 Web',f.web||'-',st.mimo_open?'ok':'warn')}${card('Provider',f.provider||'-',st.provider_configured?'ok':'warn')}${card('CLI',f.cli||'-',st.cli_ok?'ok':'warn')}${card('服务端口','Wrapper '+(st.wrapper_port||'-')+' / Web '+(st.mimo_port||'-'),'ok')}${card('当前模型',st.default_model||'未选择',st.default_model?'ok':'warn')}`; }
function presetFromFreeModel(m){ return {id:m.provider_id||'custom', name:m.provider||m.provider_id||'自定义服务商', base_url:m.base_url||'', model:m.model||'', models:[m.model].filter(Boolean), requires_key:m.requires_key!==false, hint:(m.requires_key===false?'该服务商可不填写 API Key；':'该服务商通常需要 API Key；')+'免费/限免状态以平台实时政策为准。'}; }
function ensurePresetOption(p){ if(!p||!p.id) return; if(!state.presets.find(x=>x.id===p.id)) state.presets.unshift(p); const sel=$('#guidePreset'); if(sel && ![...sel.options].some(o=>o.value===p.id)){ sel.insertAdjacentHTML('afterbegin', `<option value="${esc(p.id)}">${esc(p.name||p.id)}</option>`); } }
function applyCurrentProviderConfig(){ const cfg=state.config||{}, sel=$('#guidePreset'); if(!sel || !cfg.default_provider){ fillPreset(); return; } const p=state.presets.find(x=>x.id===cfg.default_provider); if(p) ensurePresetOption(p); if([...sel.options].some(o=>o.value===cfg.default_provider)){ sel.value=cfg.default_provider; } fillPreset(); if(cfg.default_model){ const ms=$('#guideModelSelect'), mi=$('#guideModel'); if(ms && !ms.classList.contains('hidden')){ if(![...ms.options].some(o=>o.value===cfg.default_model)) ms.insertAdjacentHTML('afterbegin', `<option value="${esc(cfg.default_model)}">${esc(cfg.default_model)}</option>`); ms.value=cfg.default_model; } if(mi) mi.value=cfg.default_model; } }
function providerGuide(){
  const opts=state.presets.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  return `<section class="panel guide"><div class="panel-head"><div><h2>模型配置</h2><p>这里始终显示当前待保存配置。免费模型库点“填入配置”后，会自动回到这里；无需 Key 的模型可直接保存，需要 Key 的平台再填写 API Key。</p></div></div>
    <div class="form three">
      <label>服务商<select id="guidePreset">${opts}</select></label>
      <label>接口地址 Base URL<input id="guideBase" class="input" placeholder="官方模型无需填写"></label>
      <label>默认模型<select id="guideModelSelect"></select><input id="guideModel" class="input hidden" placeholder="模型名"></label>
      <label class="span2">API Key<input id="guideKey" class="input" type="password" placeholder="官方模型无需填写；第三方 Key 只保存在本机 NAS"></label>
      <label>显示名称<input id="guideName" class="input" placeholder="服务商显示名称"></label>
    </div>
    <div class="actions"><button class="btn primary" onclick="saveGuideProvider()">保存为默认配置</button><button class="btn ghost" onclick="navigate('freeModels')">去免费模型库选择</button><span id="guideHint" class="hint"></span></div>
  </section>`;
}
function fillPreset(){
  const id=$('#guidePreset')?.value; const p=state.presets.find(x=>x.id===id)||{};
  const official=!!p.official || id==='mimo_official'; const noKey=p.requires_key===false;
  if($('#guideBase')){ $('#guideBase').value=p.base_url||''; $('#guideBase').disabled=official; $('#guideBase').placeholder=official?'官方模型无需 Base URL':'https://api.example.com/v1'; }
  if($('#guideKey')){ $('#guideKey').value=''; $('#guideKey').disabled=official||noKey; $('#guideKey').placeholder=official?'官方模型无需 API Key':(noKey?'该免费服务商可不填写 API Key':'只保存在本机 NAS'); }
  if($('#guideName')) $('#guideName').value=p.name||'';
  const sel=$('#guideModelSelect'), inp=$('#guideModel');
  if(sel){
    const models=p.models||OFFICIAL_MODELS;
    sel.innerHTML=models.map(m=>`<option value="${esc(m)}">${esc(m)}${m==='mimo/mimo-auto'?'（官方默认 / 限时免费）':''}</option>`).join('');
    sel.value=p.model||models[0]||''; const useSelect=official || (Array.isArray(p.models)&&p.models.length>0); sel.classList.toggle('hidden', !useSelect); inp.classList.toggle('hidden', useSelect); if(!useSelect) inp.value=p.model||'';
  }
  if($('#guideHint')) $('#guideHint').textContent=p.hint||'';
  if($('#guidePreset')) $('#guidePreset').onchange=fillPreset;
}
async function saveGuideProvider(){
  const id=$('#guidePreset').value; const p=state.presets.find(x=>x.id===id)||{}; const official=!!p.official || id==='mimo_official';
  const model=official?$('#guideModelSelect').value:$('#guideModel').value;
  try{
    await api('providers/save',{method:'POST',body:JSON.stringify({id,name:$('#guideName').value||p.name,base_url:$('#guideBase').value,api_key:$('#guideKey').value,model})});
    toast('已保存配置，已设为默认模型'); await refreshAll(); renderProviders();
  }catch(e){toast(e.data?.suggestion||e.message,'err');}
}

function renderWorkspace(){
  const model=state.config.default_model||'mimo/mimo-auto';
  const nativeUrl=officialDirectUrl();
  $('#content').innerHTML=`<section class="panel hero-panel"><div class="hero-layout"><div><h1>MiMo Code 工作台</h1><p>工作台负责状态、模型、诊断和配置。真正聊天进入独立「官方会话」页面，由官方 mimo web 接管。</p><div class="hero-actions"><button class="btn primary" onclick="navigate('official')">进入官方会话</button><button class="btn ghost" onclick="openNativeWeb()">新窗口打开</button><button class="btn ghost" onclick="copyText('${esc(nativeUrl)}')">复制会话地址</button></div></div><div class="hero-status">${statusCards()}</div></div></section>
  <section class="panel runtime-panel"><div class="panel-head"><div><h2>运行状态</h2><p>图形化展示 Wrapper、官方 Web、Provider 和 CLI 状态。</p></div><button class="btn ghost" onclick="refreshAll().then(renderWorkspace)">刷新状态</button></div><div class="status-grid">${runtimeCards()}</div></section>
  <div class="dashboard-grid">
    <section class="panel"><h3>项目概览</h3><p class="hint">查看当前项目目录、文件类型和识别标记。</p><button class="btn ghost" onclick="navigate('overview')">打开项目概览</button></section>
    <section class="panel"><h3>当前模型</h3><p><code>${esc(model)}</code></p><p class="hint">需要切换模型或填写 Key 时进入模型与服务商。</p><button class="btn ghost" onclick="navigate('providers')">配置模型</button></section>
    <section class="panel"><h3>免费模型库</h3><p class="hint">内置常见免费/限免/试用模型入口，可一键填入 Provider 表单。</p><button class="btn ghost" onclick="navigate('freeModels')">打开免费模型库</button></section>
    <section class="panel"><h3>健康检查</h3><p class="hint">一眼检查 Web、CLI、Provider、项目目录和日志。</p><button class="btn ghost" onclick="navigate('health')">立即检查</button></section>
    <section class="panel"><h3>安全边界说明</h3><p class="hint">说明二进制、凭据、命令、文件访问边界。</p><button class="btn ghost" onclick="navigate('security')">查看说明</button></section>
    <section class="panel"><h3>日志诊断</h3><p class="hint">按错误类型给中文建议，并保留原始日志。</p><button class="btn ghost" onclick="navigate('logs')">日志与建议</button></section>
    <section class="panel"><h3>配置备份</h3><p class="hint">手动备份、导出脱敏配置，导入前自动备份。</p><button class="btn ghost" onclick="navigate('backup')">配置备份</button></section>
  </div>`;
  fillPreset();
}
async function renderOverview(){
  $('#content').innerHTML='<section class="panel"><h2>项目概览</h2><div id="overviewBox" class="output">加载中...</div></section>';
  try{ const r=await api('overview'); $('#overviewBox').innerHTML=`<div class="status-grid">${card('目录',r.project_dir,r.ok?'ok':'warn')}${card('文件扫描',String(r.files_scanned||0),r.ok?'ok':'warn')}${card('目录扫描',String(r.dirs_scanned||0),r.ok?'ok':'warn')}${card('扫描截断',r.truncated?'是':'否',r.truncated?'warn':'ok')}</div><h3>项目标记</h3><p>${(r.markers||[]).map(x=>`<span class="pill">${esc(x)}</span>`).join('')||'未识别到常见项目标记'}</p><h3>文件类型 Top 10</h3><div class="provider-list">${(r.top_extensions||[]).map(x=>`<div class="provider-card"><b>${esc(x[0])}</b><p>${esc(x[1])} 个文件</p></div>`).join('')||'<div class="empty">暂无数据</div>'}</div>`; }catch(e){ $('#overviewBox').textContent=e.message; }
}
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
  $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>模型与服务商</h2><p>选择模型、填写 Key、保存默认配置。官方模型和部分免费 Provider 可不填 Key。</p></div><button class="btn ghost" onclick="refreshAll().then(renderProviders)">刷新</button></div>${providerGuide()}<div id="modelGroups" class="output">加载模型中...</div><h3>已保存 Provider</h3><div class="provider-list">${state.providers.map(p=>`<div class="provider-card"><h3>${esc(p.name)}</h3><p>模型：${esc(p.model||'-')}</p><p>Key：${p.has_key?'已保存':'未保存/无需 Key'}</p></div>`).join('')||'<div class="empty">还没有第三方 Provider；官方模型可直接使用。</div>'}</div></section>`;
  applyCurrentProviderConfig();
  try{
    const r=await api('models?provider=mimo_official');
    const groups=r.groups||{};
    $('#modelGroups').innerHTML=Object.keys(groups).map(g=>`<div class="model-group"><h3>${esc(g)}</h3><div class="provider-list">${groups[g].map(m=>`<div class="provider-card"><h3>${esc(m.name)} ${modelBadge(m)}</h3><p>${esc(m.desc||'')}</p><button class="btn compact ghost" onclick="saveOfficialModel('${esc(m.name)}')">设为默认</button></div>`).join('')}</div></div>`).join('');
  }catch(e){ $('#modelGroups').textContent=e.message; }
}
async function saveOfficialModel(model){ try{await api('providers/save',{method:'POST',body:JSON.stringify({id:'mimo_official',name:'MiMo 官方模型',model})}); toast('已切换到 '+model); await refreshAll(); renderProviders();}catch(e){toast(e.message,'err');} }
async function renderFreeModels(){
  $('#content').innerHTML='<section class="panel"><div class="panel-head"><div><h2>免费模型库</h2><p>常见免费/限免/试用模型入口。免费状态会变化，最终以各平台控制台为准。</p></div><button class="btn ghost" onclick="renderFreeModels()">刷新</button></div><div id="freeModelNotice" class="hint"></div><div id="freeModelBox" class="output">加载中...</div></section>';
  try{
    const r=await api('free-models');
    $('#freeModelNotice').textContent=r.notice||'';
    const groups=r.groups||{};
    $('#freeModelBox').innerHTML=Object.keys(groups).map(g=>`<div class="model-group"><h3>${esc(g)}</h3><div class="provider-list compact-cards">${groups[g].map(m=>`<div class="provider-card free-card"><div class="card-title"><h3>${esc(m.display_name||m.model)}</h3><span class="pill free">${esc(m.free_type)}</span></div><p>${esc(m.note)}</p><p class="hint"><b>模型</b>：${esc(m.model||'动态发现')}<br><b>接口</b>：${esc(m.base_url||'官方内置')}<br><b>Key</b>：${m.requires_key?'需要 API Key':'无需 API Key'} · ${esc(m.region||'')}</p><div class="actions"><button class="btn compact primary" onclick='useFreeModel(${JSON.stringify(JSON.stringify(m))})'>填入配置</button><button class="btn compact ghost" onclick="copyText('${esc(m.model)}')">复制模型名</button></div></div>`).join('')}</div></div>`).join('');
  }catch(e){ $('#freeModelBox').textContent=e.message; }
}
function useFreeModel(raw){
  const m=JSON.parse(raw);
  navigate('providers');
  setTimeout(()=>{
    const p=presetFromFreeModel(m);
    ensurePresetOption(p);
    const preset=$('#guidePreset');
    if(preset){ preset.value=p.id; fillPreset(); }
    if($('#guideName')) $('#guideName').value=m.provider||m.provider_id||'免费模型';
    if($('#guideBase')) { $('#guideBase').disabled=false; $('#guideBase').value=m.base_url||''; }
    if($('#guideModelSelect') && !$('#guideModelSelect').classList.contains('hidden')){
      const sel=$('#guideModelSelect');
      if(![...sel.options].some(o=>o.value===m.model)) sel.insertAdjacentHTML('afterbegin', `<option value="${esc(m.model)}">${esc(m.model)}</option>`);
      sel.value=m.model||'';
    }
    if($('#guideModel')) $('#guideModel').value=m.model||'';
    if($('#guideKey')) { $('#guideKey').disabled=m.requires_key===false; $('#guideKey').placeholder=m.requires_key?'填写该平台 API Key':'无需 API Key'; }
    const hint=$('#guideHint'); if(hint) hint.textContent=m.requires_key?'需要到对应平台申请 API Key，填入后点保存。':'该 Provider 标记为无需 API Key，直接点保存为默认配置。';
    toast(m.requires_key?'已填入配置，请填写 API Key 后保存':'已填入配置，该模型无需 Key，可直接保存');
  },80);
}
async function renderHealth(){
  $('#content').innerHTML='<section class="panel"><div class="panel-head"><div><h2>健康检查</h2><p>检查 Wrapper、官方 Web、CLI、模型配置、项目目录和日志。</p></div><button class="btn ghost" onclick="renderHealth()">重新检查</button></div><div id="healthBox" class="output">检查中...</div></section>';
  try{ const r=await api('health'); $('#healthBox').innerHTML=`<h3>评分：${esc(r.score)}/${esc(r.total)}</h3><div class="provider-list">${(r.checks||[]).map(c=>`<div class="provider-card ${c.ok?'ok':'warn'}"><h3>${c.ok?'✅':'⚠️'} ${esc(c.name)}</h3><p>${esc(c.detail)}</p><p>${yesNo(c.ok)}</p></div>`).join('')}</div><h3>建议</h3><ul>${(r.suggestions||[]).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>当前没有额外建议。</li>'}</ul>`; }catch(e){ $('#healthBox').textContent=e.message; }
}
async function renderSecurity(){
  $('#content').innerHTML='<section class="panel"><h2>安全边界说明</h2><div id="securityBox" class="output">加载中...</div></section>';
  try{ const r=await api('security'); $('#securityBox').innerHTML=`<div class="provider-list">${(r.items||[]).map(x=>`<div class="provider-card"><h3>${esc(x.title)}</h3><p>${esc(x.text)}</p></div>`).join('')}</div>`; }catch(e){ $('#securityBox').textContent=e.message; }
}
async function renderBackup(){
  $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>配置备份</h2><p>手动生成配置备份；导入配置前后端会自动生成脱敏备份。</p></div><button class="btn ghost" onclick="renderBackup()">刷新</button></div><div class="actions"><button class="btn primary" onclick="createBackup(false)">创建脱敏备份</button><button class="btn danger" onclick="createBackup(true)">创建含 Key 备份</button><button class="btn ghost" onclick="exportConfigToBackup(false)">查看脱敏导出</button></div><pre id="backupOut" class="output small">加载中...</pre></section>`;
  await loadBackups();
}
async function loadBackups(){ try{ const r=await api('config/backups'); $('#backupOut').innerHTML=`备份目录：${esc(r.dir)}\n\n`+(r.backups||[]).map(b=>`${timeText(b.mtime)}  ${b.filename}  ${b.size} bytes`).join('\n') || '暂无备份'; }catch(e){ $('#backupOut').textContent=e.message; } }
async function createBackup(include_keys){ if(include_keys && !confirm('含 Key 备份会把 API Key 写入本机备份文件，确认继续？')) return; const r=await api('config/backup',{method:'POST',body:JSON.stringify({include_keys,reason:'manual from UI'})}); toast('已创建备份：'+r.filename); await loadBackups(); }
async function exportConfigToBackup(include_keys){ const r=await api('config/export?include_keys='+(include_keys?'true':'false')); $('#backupOut').textContent=JSON.stringify(r,null,2); }

function appendBubble(role, html){ const box=$('#chatThread'); if(!box){ toolCommand(); setTimeout(()=>appendBubble(role, html),50); return null; } const div=document.createElement('div'); div.className='bubble '+role; div.innerHTML=html; box.appendChild(div); box.scrollTop=box.scrollHeight; return div; }
function quickAsk(text){ $('#cmdKey').value='run'; $('#cmdMsg').value=text; runToolCommand(); }
function copyCurrentCli(){ const msg=$('#cmdMsg')?.value || '你的问题'; const model=state.config.default_model || 'mimo/mimo-auto'; copyText(`mimo run --model ${model} ${JSON.stringify(msg)}`); }
async function validateProject(){ try{const r=await api('project/validate',{method:'POST',body:JSON.stringify({path:$('#projectDir').value})}); if(r.ok){toast('项目目录已保存'); await refreshAll();} else toast(r.error,'err');}catch(e){toast(e.message,'err');} }
function renderSessions(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>会话历史</h2><p>本应用记录你从工具箱 CLI 测试发起的会话。正式聊天历史以官方会话为准。</p></div></div>${state.sessions.map(s=>`<div class="row"><div><b>${esc(s.title)}</b><p>${esc(s.project_dir)} · ${esc(s.model||'-')} · ${timeText(s.updated_at)}</p></div><button class="btn compact danger" onclick="deleteSession('${esc(s.id)}')">删除</button></div>`).join('')||'<div class="empty">暂无会话</div>'}</section>`; }
async function deleteSession(id){ if(!confirm('删除这条会话记录？'))return; await api('sessions/delete',{method:'POST',body:JSON.stringify({id})}); await refreshAll(); renderSessions(); }
async function renderLogs(){
  $('#content').innerHTML='<section class="panel"><div class="panel-head"><div><h2>日志诊断</h2><p>展示用户相关错误、中文建议和原始日志。</p></div><button class="btn ghost" onclick="renderLogs()">刷新</button></div><div id="logBox" class="output">加载中...</div></section>';
  try{const r=await api('logs'); $('#logBox').innerHTML=(r.issues||[]).map(i=>`<div class="issue"><b>${esc(i.title)}</b><div>${esc(i.detail)}</div><div class="suggest">建议：${esc(i.suggestion)}</div></div>`).join('')+`<details open><summary>原始日志</summary><pre>${esc(r.raw||'')}</pre></details>`;}catch(e){$('#logBox').textContent=e.message;}
}
function renderAdvanced(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>高级设置</h2><p>MCP、开发者工具箱等高级能力默认隐藏，避免主界面变成后台管理系统。</p></div></div><div class="form two"><label>自动守护 MiMo Web<select id="autoRestart"><option value="true">开启</option><option value="false">关闭</option></select></label><label>开发者工具箱<select id="toolboxEnabled"><option value="false">隐藏</option><option value="true">显示</option></select></label></div><div class="actions"><button class="btn primary" onclick="saveAdvanced()">保存设置</button><button class="btn ghost" onclick="navigate('backup')">配置备份</button><button class="btn ghost" onclick="checkUpdate()">检查更新</button><button class="btn ghost" onclick="loadMcp()">查看 MCP</button></div><pre id="advancedOut" class="output small">高级能力默认只读或需二次确认。</pre></section>`; $('#autoRestart').value=String(!!state.config.auto_restart_mimo); $('#toolboxEnabled').value=String(!!state.config.toolbox_enabled); }
async function saveAdvanced(){ await api('config',{method:'POST',body:JSON.stringify({auto_restart_mimo:$('#autoRestart').value==='true',toolbox_enabled:$('#toolboxEnabled').value==='true'})}); toast('已保存'); await refreshAll(); renderAdvanced(); }
async function exportConfig(include_keys){ const r=await api('config/export?include_keys='+(include_keys?'true':'false')); $('#advancedOut').textContent=JSON.stringify(r,null,2); }
async function checkUpdate(){ const r=await api('update/check'); $('#advancedOut').textContent=JSON.stringify(r,null,2); }
async function loadMcp(){ const r=await api('mcp'); $('#advancedOut').textContent=r.raw||JSON.stringify(r,null,2); }
async function renderToolbox(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>开发者工具箱</h2><p>默认隐藏；只提供项目内文件预览、轻量状态、ACP/Agent 只读和 MiMo 命令白名单。</p></div><button class="btn ghost" onclick="navigate('advanced')">返回高级设置</button></div><div class="tool-grid"><button class="btn primary" onclick="toolFiles()">项目文件</button><button class="btn" onclick="toolPerf()">运行状态</button><button class="btn" onclick="toolAcp()">ACP 服务</button><button class="btn" onclick="toolAgents()">Agent 配置</button><button class="btn" onclick="toolCommand()">MiMo 命令助手</button></div><div id="toolBox" class="output small">请选择一个工具。所有高风险能力均受限。</div></section>`; }
async function toolFiles(path=''){ const r=await api('toolbox/files?path='+encodeURIComponent(path)); if(r.type==='dir') $('#toolBox').innerHTML=`<b>根目录：</b>${esc(r.root)}<br><b>当前：</b>${esc(r.path)}<div class="file-list">${r.entries.map(e=>`<button class="file-row" onclick="toolFiles('${esc(e.path)}')">${e.type==='dir'?'[目录]':'[文件]'} ${esc(e.name)} <span>${e.type} · ${e.size}</span></button>`).join('')}</div>`; else $('#toolBox').textContent=r.text||r.error; }
async function toolPerf(){ const r=await api('toolbox/perf'); $('#toolBox').textContent=JSON.stringify(r,null,2); }
async function toolAcp(){ const r=await api('toolbox/acp'); $('#toolBox').textContent=r.help||JSON.stringify(r,null,2); }
async function toolAgents(){ const r=await api('toolbox/agents'); $('#toolBox').textContent=r.raw||JSON.stringify(r,null,2); }
async function toolCommand(){ $('#toolBox').innerHTML=`<div class="form two"><label>白名单命令<select id="cmdKey"><option value="models">mimo models</option><option value="providers list">mimo providers list</option><option value="mcp list">mimo mcp list</option><option value="debug">mimo debug</option><option value="version">mimo --version</option><option value="run">mimo run</option></select></label><label>run 消息<input id="cmdMsg" class="input" placeholder="仅 mimo run 使用"></label></div><div class="quick-prompts"><button class="btn compact ghost" onclick="quickAsk('在不？请用一句话回复。')">测试模型</button><button class="btn compact ghost" onclick="quickAsk('你是谁？你能帮我做什么？')">你是谁？</button><button class="btn compact ghost" onclick="copyCurrentCli()">复制本次 CLI</button></div><button class="btn primary" onclick="runToolCommand()">执行白名单命令</button><pre id="cmdOut" class="output small"></pre>`; }
async function runToolCommand(){ try{const r=await api('toolbox/command',{method:'POST',body:JSON.stringify({command:$('#cmdKey').value,message:$('#cmdMsg').value})}); $('#cmdOut').textContent=r.output||JSON.stringify(r,null,2);}catch(e){$('#cmdOut').textContent=e.data?.suggestion||e.message;} }

init();
