/* MiMo Code fnOS App v0.10.4 */
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
const state = { token: localStorage.getItem('mimocode_token') || '', setup: false, status: null, providers: [], presets: [], config: {}, view: 'workspace', sessions: [], toolbox: {} };
const OFFICIAL_MODELS = ['mimo/mimo-auto','xiaomi/mimo-v2-flash','xiaomi/mimo-v2-omni','xiaomi/mimo-v2-pro','xiaomi/mimo-v2.5','xiaomi/mimo-v2.5-pro','xiaomi/mimo-v2.5-pro-ultraspeed'];

function esc(s){ return String(s ?? '').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function toast(msg,type='ok'){ const el=document.createElement('div'); el.className='toast '+type; el.textContent=msg; document.body.appendChild(el); setTimeout(()=>el.remove(),4200); }
async function copyText(text){ await navigator.clipboard.writeText(text); toast('已复制到剪贴板'); }
function timeText(ts){ if(!ts)return '-'; return new Date(ts*1000).toLocaleString('zh-CN'); }

async function api(path, opts={}){
  const headers=Object.assign({'Content-Type':'application/json'},opts.headers||{});
  if(state.token) headers.Authorization='Bearer '+state.token;
  const res=await fetch('/api/'+path,Object.assign({},opts,{headers}));
  const text=await res.text(); let data;
  try{data=text?JSON.parse(text):{};}catch(e){data={error:text||e.message};}
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
    await refreshAll(); showMain(); navigate('workspace');
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
    state.token=r.token; localStorage.setItem('mimocode_token',r.token); await refreshAll(); showMain(); navigate('workspace');
  }catch(e){ $('#authMsg').textContent=e.data?.suggestion||e.message; $('#authMsg').className='msg err'; }
}
async function refreshAll(){
  state.status=await api('status');
  const p=await api('providers'); state.providers=p.providers||[]; state.presets=p.presets||[]; state.config=p.config||{};
  try{ state.sessions=(await api('sessions')).sessions||[]; }catch(e){ state.sessions=[]; }
  $('#statusLine').innerHTML=`${state.status.mimo_open?'<span class="dot ok"></span>':'<span class="dot bad"></span>'} 服务${esc(state.status.friendly.service)} · Provider ${esc(state.status.friendly.provider)} · Wrapper v${esc(state.status.wrapper_version)}`;
  const toolTab=document.querySelector('[data-view="toolbox"]'); if(toolTab) toolTab.classList.toggle('hidden', !state.config.toolbox_enabled);
}
function navigate(view){ if(view==='toolbox' && !state.config.toolbox_enabled) view='advanced'; state.view=view; const content=$('#content'); if(content) content.classList.toggle('official-content', view==='official'); $$('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view)); ({workspace:renderWorkspace,official:renderOfficialChat,providers:renderProviders,sessions:renderSessions,logs:renderLogs,advanced:renderAdvanced,toolbox:renderToolbox}[view]||renderWorkspace)(); }

function statusCards(){ const f=state.status?.friendly||{}; return `<div class="status-grid">
  ${card('MiMo 服务',f.service,state.status?.mimo_open?'ok':'warn')}
  ${card('Web 入口',f.web,state.status?.mimo_open?'ok':'warn')}
  ${card('Provider',f.provider,state.status?.provider_configured?'ok':'warn')}
  ${card('当前模型',f.model,state.status?.default_model?'ok':'warn')}
  ${card('CLI',f.cli,state.status?.cli_ok?'ok':'warn')}
</div>`; }
function card(k,v,type=''){ return `<div class="stat ${type}"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`; }
function providerGuide(){
  if(state.providers.length || state.config.default_model) return '';
  const opts=state.presets.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  return `<section class="panel guide"><div class="panel-head"><div><h2>首次配置向导</h2><p>推荐先用 MiMo 官方默认模型 <b>mimo/mimo-auto</b>，限时免费；第三方服务商再填写 Key。</p></div></div>
    <div class="form three">
      <label>服务商<select id="guidePreset">${opts}</select></label>
      <label>接口地址 Base URL<input id="guideBase" class="input" placeholder="官方模型无需填写"></label>
      <label>默认模型<select id="guideModelSelect"></select><input id="guideModel" class="input hidden" placeholder="模型名"></label>
      <label class="span2">API Key<input id="guideKey" class="input" type="password" placeholder="官方模型无需填写；第三方 Key 只保存在本机 NAS"></label>
      <label>显示名称<input id="guideName" class="input" placeholder="服务商显示名称"></label>
    </div>
    <div class="actions"><button class="btn primary" onclick="saveGuideProvider()">保存并开始使用</button><span id="guideHint" class="hint"></span></div>
  </section>`;
}
function fillPreset(){
  const id=$('#guidePreset')?.value; const p=state.presets.find(x=>x.id===id)||{};
  const official=!!p.official || id==='mimo_official';
  if($('#guideBase')){ $('#guideBase').value=p.base_url||''; $('#guideBase').disabled=official; $('#guideBase').placeholder=official?'官方模型无需 Base URL':'https://api.example.com/v1'; }
  if($('#guideKey')){ $('#guideKey').value=''; $('#guideKey').disabled=official; $('#guideKey').placeholder=official?'官方模型无需 API Key':'只保存在本机 NAS'; }
  if($('#guideName')) $('#guideName').value=p.name||'';
  const sel=$('#guideModelSelect'), inp=$('#guideModel');
  if(sel){
    const models=p.models||OFFICIAL_MODELS;
    sel.innerHTML=models.map(m=>`<option value="${esc(m)}">${esc(m)}${m==='mimo/mimo-auto'?'（官方默认 / 限时免费）':''}</option>`).join('');
    sel.value=p.model||models[0]||''; sel.classList.toggle('hidden', !official); inp.classList.toggle('hidden', official); if(!official) inp.value=p.model||'';
  }
  if($('#guideHint')) $('#guideHint').textContent=p.hint||'';
}
async function saveGuideProvider(){
  const id=$('#guidePreset').value; const p=state.presets.find(x=>x.id===id)||{}; const official=!!p.official || id==='mimo_official';
  const model=official?$('#guideModelSelect').value:$('#guideModel').value;
  try{
    await api('providers/save',{method:'POST',body:JSON.stringify({id,name:$('#guideName').value||p.name,base_url:$('#guideBase').value,api_key:$('#guideKey').value,model})});
    toast('已保存配置'); await refreshAll(); renderWorkspace();
  }catch(e){toast(e.data?.suggestion||e.message,'err');}
}
function renderWorkspace(){
  const model=state.config.default_model||'mimo/mimo-auto';
  const nativeUrl=state.status?.native_web_url||`${location.protocol}//${location.hostname}:5669/`;
  $('#content').innerHTML=`${providerGuide()}<section class="panel hero-panel"><div class="hero-layout"><div><h1>MiMo Code 工作台</h1><p>这里负责服务状态、模型配置和诊断；真正聊天请进入独立的「官方会话」页面。</p><div class="hero-actions"><button class="btn primary" onclick="navigate('official')">进入官方会话</button><button class="btn ghost" onclick="openNativeWeb()">新窗口打开</button><button class="btn ghost" onclick="copyText('${esc(nativeUrl)}')">复制会话地址</button></div></div><div class="hero-status">${statusCards()}</div></div></section>
  <div class="dashboard-grid"><section class="panel"><h3>当前模型</h3><p><code>${esc(model)}</code></p><p class="hint">首次使用推荐 MiMo 官方模型 <b>mimo/mimo-auto</b>。</p><button class="btn ghost" onclick="navigate('providers')">模型与服务商</button></section><section class="panel"><h3>官方 Web</h3><p>${esc(nativeUrl)}</p><p class="hint">如果应用内页面显示异常，用新窗口打开官方会话。</p><button class="btn ghost" onclick="navigate('official')">进入官方会话页面</button></section><section class="panel"><h3>诊断</h3><p class="hint">服务异常、模型无响应、官方页打不开时，先看日志与建议。</p><button class="btn ghost" onclick="navigate('logs')">日志与建议</button></section><section class="panel"><h3>开发者工具箱</h3><p class="hint">文件、ACP、Agent、CLI 测试默认隐藏。</p><button class="btn ghost" onclick="enableToolboxAndOpenCli()">打开 CLI 快速测试</button></section></div>`;
  fillPreset();
}
function renderOfficialChat(){
  const embedUrl=state.status?.native_web_embed_url||`//${location.hostname}:5669/`;
  const content=$('#content');
  content.innerHTML='';
  content.classList.add('official-content');
  const iframe=document.createElement('iframe');
  iframe.id='nativeFrame';
  iframe.className='official-native-frame';
  iframe.src=embedUrl;
  iframe.title='MiMo 官方会话';
  content.appendChild(iframe);
}
function openNativeWeb(){ window.open(state.status?.native_web_url||`${location.protocol}//${location.hostname}:5669/`,'_blank'); }
function reloadNativeFrame(){ const f=$('#nativeFrame'); if(f) f.src=f.src; }
async function enableToolboxAndOpenCli(){ if(!state.config.toolbox_enabled){ await api('config',{method:'POST',body:JSON.stringify({toolbox_enabled:true})}); await refreshAll(); } navigate('toolbox'); setTimeout(toolCommand,80); }
function appendBubble(role, html){ const box=$('#chatThread'); if(!box){ toolCommand(); setTimeout(()=>appendBubble(role, html),50); return null; } const div=document.createElement('div'); div.className='bubble '+role; div.innerHTML=html; box.appendChild(div); box.scrollTop=box.scrollHeight; return div; }
function quickAsk(text){ $('#cmdKey').value='run'; $('#cmdMsg').value=text; runToolCommand(); }
function copyCurrentCli(){ const msg=$('#cmdMsg')?.value || '你的问题'; const model=state.config.default_model || 'mimo/mimo-auto'; copyText(`mimo run --model ${model} ${JSON.stringify(msg)}`); }
function emptyOutputHtml(r){ return `<b>MiMo</b><div class="empty-reply">MiMo 命令执行成功，但没有返回可显示内容。</div><div class="suggest">${esc(r.suggestion||'建议先测试模型，或查看日志与建议。')}</div><ol>${(r.next_steps||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ol>`; }
async function runChat(){
  const input=$('#chatInput'); const msg=(input?.value||'').trim(); if(!msg){toast('先输入一句话'); return;}
  const project_dir=$('#projectDir')?.value || state.config.project_dir, model=$('#chatModel')?.value||'mimo/mimo-auto';
  appendBubble('user', `<b>你</b><div>${esc(msg).replaceAll('\n','<br>')}</div>`); input.value='';
  const pending=appendBubble('assistant thinking', '<b>MiMo</b><div>正在思考...</div>'); if($('#sendBtn')) $('#sendBtn').disabled=true;
  try{
    const r=await api('chat/run',{method:'POST',body:JSON.stringify({message:msg,project_dir,model,session_id:state.config.last_session_id||''})});
    if(pending){ pending.className='bubble assistant'; pending.innerHTML=r.empty_output?emptyOutputHtml(r):`<b>MiMo</b><pre>${esc(r.output||'')}</pre>`; }
    await refreshAll();
  }catch(e){
    if(pending){ pending.className='bubble assistant error'; pending.innerHTML=`<b>MiMo</b><div>${esc(e.data?.suggestion||e.message)}</div><pre>${esc(e.data?.error||'')}</pre>`; }
  }finally{ if($('#sendBtn')) $('#sendBtn').disabled=false; }
}
async function validateProject(){ try{const r=await api('project/validate',{method:'POST',body:JSON.stringify({path:$('#projectDir').value})}); if(r.ok){toast('项目目录已保存'); await refreshAll();} else toast(r.error,'err');}catch(e){toast(e.message,'err');} }
async function loadCli(){ try{const r=await api('cli'); $('#cliBox').innerHTML=(r.commands||[]).map(c=>`<div class="cli-line"><div><b>${esc(c.title)}</b><code>${esc(c.command)}</code></div><button class="btn compact" onclick="copyText('${esc(c.command).replaceAll('&#39;','\\&#39;')}')">复制</button></div>`).join('');}catch(e){} }
function renderProviders(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>模型与服务商</h2><p>官方模型可直接选用；第三方服务商需要填写 API Key。</p></div><button class="btn ghost" onclick="refreshAll().then(renderProviders)">刷新</button></div>${providerGuide()}<div class="provider-list">${state.providers.map(p=>`<div class="provider-card"><h3>${esc(p.name)}</h3><p>模型：${esc(p.model||'-')}</p><p>Key：${p.has_key?'已保存':'未保存/无需 Key'}</p></div>`).join('')||'<div class="empty">还没有第三方 Provider；官方模型可直接使用。</div>'}</div><details open><summary>官方模型</summary><div class="tag-grid">${OFFICIAL_MODELS.map(m=>`<button class="btn ghost compact" onclick="saveOfficialModel('${m}')">${esc(m)}${m==='mimo/mimo-auto'?' · 默认限免':''}</button>`).join('')}</div></details></section>`; fillPreset(); }
async function saveOfficialModel(model){ try{await api('providers/save',{method:'POST',body:JSON.stringify({id:'mimo_official',name:'MiMo 官方模型',model})}); toast('已切换到 '+model); await refreshAll(); renderProviders();}catch(e){toast(e.message,'err');} }
function renderSessions(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>会话历史</h2><p>本应用记录你从工作台发起的会话，便于继续使用。</p></div></div>${state.sessions.map(s=>`<div class="row"><div><b>${esc(s.title)}</b><p>${esc(s.project_dir)} · ${esc(s.model||'-')} · ${timeText(s.updated_at)}</p></div><button class="btn compact danger" onclick="deleteSession('${esc(s.id)}')">删除</button></div>`).join('')||'<div class="empty">暂无会话</div>'}</section>`; }
async function deleteSession(id){ if(!confirm('删除这条会话记录？'))return; await api('sessions/delete',{method:'POST',body:JSON.stringify({id})}); await refreshAll(); renderSessions(); }
async function renderLogs(){ $('#content').innerHTML='<section class="panel"><h2>日志与建议</h2><p>只展示和用户操作相关的错误建议。</p><div id="logBox" class="output">加载中...</div></section>'; try{const r=await api('logs'); $('#logBox').innerHTML=(r.issues||[]).map(i=>`<div class="issue"><b>${esc(i.title)}</b><div>${esc(i.detail)}</div><div class="suggest">建议：${esc(i.suggestion)}</div></div>`).join('')+`<details><summary>原始日志</summary><pre>${esc(r.raw||'')}</pre></details>`;}catch(e){$('#logBox').textContent=e.message;} }
function renderAdvanced(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>高级设置</h2><p>MCP、配置导入导出和开发者工具箱默认隐藏，避免主界面变成后台管理系统。</p></div></div><div class="form two"><label>自动守护 MiMo Web<select id="autoRestart"><option value="true">开启</option><option value="false">关闭</option></select></label><label>开发者工具箱<select id="toolboxEnabled"><option value="false">隐藏</option><option value="true">显示</option></select></label></div><div class="actions"><button class="btn primary" onclick="saveAdvanced()">保存设置</button><button class="btn ghost" onclick="exportConfig(false)">导出脱敏配置</button><button class="btn danger" onclick="exportConfig(true)">导出含 Key 配置</button><button class="btn ghost" onclick="checkUpdate()">检查更新</button><button class="btn ghost" onclick="loadMcp()">查看 MCP</button></div><pre id="advancedOut" class="output small">高级能力默认只读或需二次确认。</pre></section>`; $('#autoRestart').value=String(!!state.config.auto_restart_mimo); $('#toolboxEnabled').value=String(!!state.config.toolbox_enabled); }
async function saveAdvanced(){ await api('config',{method:'POST',body:JSON.stringify({auto_restart_mimo:$('#autoRestart').value==='true',toolbox_enabled:$('#toolboxEnabled').value==='true'})}); toast('已保存'); await refreshAll(); renderAdvanced(); }
async function exportConfig(include_keys){ const r=await api('config/export?include_keys='+(include_keys?'true':'false')); $('#advancedOut').textContent=JSON.stringify(r,null,2); }
async function checkUpdate(){ const r=await api('update/check'); $('#advancedOut').textContent=JSON.stringify(r,null,2); }
async function loadMcp(){ const r=await api('mcp'); $('#advancedOut').textContent=r.raw||JSON.stringify(r,null,2); }
async function renderToolbox(){ $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>开发者工具箱</h2><p>默认隐藏；只提供项目内文件预览、轻量状态、ACP/Agent 只读和 MiMo 命令白名单。</p></div><button class="btn ghost" onclick="navigate('advanced')">返回高级设置</button></div><div class="tool-grid"><button class="btn primary" onclick="toolFiles()">项目文件</button><button class="btn" onclick="toolPerf()">运行状态</button><button class="btn" onclick="toolAcp()">ACP 服务</button><button class="btn" onclick="toolAgents()">Agent 配置</button><button class="btn" onclick="toolCommand()">MiMo 命令助手</button></div><div id="toolBox" class="output small">请选择一个工具。所有高风险能力均受限。</div></section>`; }
async function toolFiles(path=''){ const r=await api('toolbox/files?path='+encodeURIComponent(path)); if(r.type==='dir') $('#toolBox').innerHTML=`<b>根目录：</b>${esc(r.root)}<br><b>当前：</b>${esc(r.path)}<div class="file-list">${r.entries.map(e=>`<button class="file-row" onclick="toolFiles('${esc(e.path)}')">${e.type==='dir'?'📁':'📄'} ${esc(e.name)} <span>${e.type} · ${e.size}</span></button>`).join('')}</div>`; else $('#toolBox').textContent=r.text||r.error; }
async function toolPerf(){ const r=await api('toolbox/perf'); $('#toolBox').textContent=JSON.stringify(r,null,2); }
async function toolAcp(){ const r=await api('toolbox/acp'); $('#toolBox').textContent=r.help||JSON.stringify(r,null,2); }
async function toolAgents(){ const r=await api('toolbox/agents'); $('#toolBox').textContent=r.raw||JSON.stringify(r,null,2); }
async function toolCommand(){ $('#toolBox').innerHTML=`<div class="form two"><label>白名单命令<select id="cmdKey"><option value="models">mimo models</option><option value="providers list">mimo providers list</option><option value="mcp list">mimo mcp list</option><option value="debug">mimo debug</option><option value="version">mimo --version</option><option value="run">mimo run</option></select></label><label>run 消息<input id="cmdMsg" class="input" placeholder="仅 mimo run 使用"></label></div><div class="quick-prompts"><button class="btn compact ghost" onclick="quickAsk('在不？请用一句话回复。')">测试模型</button><button class="btn compact ghost" onclick="quickAsk('你是谁？你能帮我做什么？')">你是谁？</button><button class="btn compact ghost" onclick="copyCurrentCli()">复制本次 CLI</button></div><button class="btn primary" onclick="runToolCommand()">执行白名单命令</button><pre id="cmdOut" class="output small"></pre>`; }
async function runToolCommand(){ try{const r=await api('toolbox/command',{method:'POST',body:JSON.stringify({command:$('#cmdKey').value,message:$('#cmdMsg').value})}); $('#cmdOut').textContent=r.output||JSON.stringify(r,null,2);}catch(e){$('#cmdOut').textContent=e.data?.suggestion||e.message;} }

init();
