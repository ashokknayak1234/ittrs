import {filterTickets, flag, settingsGroups} from './view-model.js';
const $ = s => document.querySelector(s);
const all = s => [...document.querySelectorAll(s)];
let signedIn = false, booting = true, pendingRoute = 'overview', tickets = [], stats = null;
let selectedId = null, createdId = null, highlightedId = null, toastTimer, loadingDashboard = null;
const workspaceRoutes = ['overview', 'tickets', 'new-ticket'];

function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (cls) node.className = cls;
  return node;
}
function toast(text) {
  $('#toast').textContent = text; $('#toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 4500);
}
function navigate(route) {
  if (location.hash === '#' + route) renderRoute();
  else location.hash = route;
}
function closeDialogs() {all('dialog[open]').forEach(d => d.close());}
function resetSession() {
  signedIn = false; tickets = []; stats = null; highlightedId = null;
  $('#tickets').replaceChildren(); $('#workload').replaceChildren();
  for (const id of ['total', 'critical', 'alerts', 'unsatisfied']) $('#' + id).textContent = '—';
  $('#nav-auth').textContent = 'Sign in ↗';
  $('#home-stat').textContent = '03'; $('#home-stat-eyebrow').textContent = 'A SIMPLER WAY THROUGH';
  $('#home-stat-label').textContent = 'steps from a complaint to a clear next action';
  closeDialogs();
}
async function api(path, method = 'GET', data) {
  let response;
  try {
    response = await fetch(path, {method, credentials:'same-origin', signal:AbortSignal.timeout(120000), headers:data === undefined ? {} : {'Content-Type':'application/json'}, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  } catch {
    throw new Error(method === 'GET' ? 'Could not reach the service. Check your connection and try again.' : 'The request could not be confirmed. Your text is kept here; check the queue before retrying.');
  }
  let result;
  try {result = await response.json();} catch {throw new Error('The service returned an unexpected response. Please try again shortly.');}
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/auth/login' && !booting) {
      const current = location.hash.slice(1);
      if (workspaceRoutes.includes(current)) pendingRoute = current;
      resetSession(); $('#login-error').textContent = 'Your session has ended. Sign in to continue.'; navigate('signin');
    }
    const error = new Error(result.detail || 'Request failed. Please try again.'); error.status = response.status; throw error;
  }
  return result;
}
function renderRoute() {
  if (booting) return;
  let route = location.hash.slice(1) || 'home';
  if (!['home','how-it-works','signin',...workspaceRoutes].includes(route)) route = 'home';
  if (workspaceRoutes.includes(route) && !signedIn) {pendingRoute = route; navigate('signin'); return;}
  if (route === 'signin' && signedIn) {navigate(pendingRoute); return;}
  closeDialogs();
  const home = route === 'home' || route === 'how-it-works';
  $('#home-view').hidden = !home; $('#signin-view').hidden = route !== 'signin'; $('#workspace-view').hidden = !workspaceRoutes.includes(route);
  all('[data-nav]').forEach(a => {const active = a.dataset.nav === (home ? route : route === 'signin' ? '' : 'workspace'); a.classList.toggle('active', active); if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  all('[data-workspace-nav]').forEach(a => {const active = a.dataset.workspaceNav === route; a.classList.toggle('active', active); if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  const titles = {overview:['A clearer view.','The right attention, in the right place.'],tickets:['Room for every issue.','Review, adjust, and help things move forward.'],'new-ticket':['Let’s find a way.','Start with the issue. We’ll help with the next step.']};
  document.title = (route === 'home' || route === 'how-it-works' ? 'A clearer way forward' : route === 'signin' ? 'Sign in' : route === 'new-ticket' ? 'New ticket' : route === 'tickets' ? 'Ticket queue' : 'Workspace') + ' · ITTRS';
  if (workspaceRoutes.includes(route)) {
    $('#workspace-title').textContent = titles[route][0]; $('#workspace-description').textContent = titles[route][1];
    $('#overview-panel').hidden = route !== 'overview'; $('#compose-panel').hidden = route !== 'new-ticket'; $('#queue-panel').hidden = route === 'new-ticket'; $('#new-ticket-link').hidden = route === 'new-ticket';
    $('#workspace-title').focus({preventScroll:true});
    refresh();
  } else if (route === 'signin') $('#signin-title').focus({preventScroll:true});
  if (route === 'how-it-works') $('#how-it-works').scrollIntoView(); else window.scrollTo({top:0,behavior:'instant'});
}
function renderWorkload(load) {
  const root = $('#workload'); root.replaceChildren();
  const names = [...new Set(['Team Alpha','Team Beta','Team Gamma','On-Call Team',...Object.keys(load)])];
  const max = Math.max(1,...Object.values(load).map(Number));
  for (const name of names) {
    const count = Number(load[name] || 0), row = element('div',undefined,'workload-row'), progress = document.createElement('progress');
    progress.max = max; progress.value = count; progress.setAttribute('aria-label',name + ': ' + count + ' tickets');
    row.append(element('span',name),progress,element('strong',count)); root.append(row);
  }
}
async function refresh() {
  if (!signedIn) return false;
  if (loadingDashboard) return loadingDashboard;
  $('#refresh').disabled = true;
  loadingDashboard = (async() => {
    try {
      const data = await api('/api/admin/dashboard');
      if (!signedIn) return false;
      if (!Array.isArray(data.tickets)) throw new Error('Ticket data could not be loaded. Please refresh.');
      tickets = data.tickets; stats = data;
      for (const [id,key] of [['total','total_tickets'],['critical','critical_tickets'],['alerts','sla_alerts'],['unsatisfied','not_satisfied']]) $('#' + id).textContent = Number(data[key] || 0).toLocaleString();
      $('#home-stat').textContent = Number(data.total_tickets || 0).toLocaleString(); $('#home-stat-label').textContent = 'tickets in your support workspace'; $('#home-stat-eyebrow').textContent = 'EVERY ISSUE HAS A PLACE';
      $('#dashboard-error').hidden = true; renderWorkload(data.workload || {}); renderTickets(); return true;
    } catch(error) {
      $('#dashboard-error').textContent = error.message + (stats ? ' Showing the last loaded data.' : ''); $('#dashboard-error').hidden = false;
      if (!stats) {$('#queue-count').textContent = 'Tickets could not be loaded.'; $('#tickets').replaceChildren();}
      return false;
    }
  })();
  try {return await loadingDashboard;} finally {loadingDashboard = null; $('#refresh').disabled = false;}
}
function renderTickets() {
  const root = $('#tickets'); root.replaceChildren();
  const visible = filterTickets(tickets, $('#filter').value, $('#severity-filter').value);
  $('#queue-count').textContent = `${visible.length} of ${tickets.length} loaded tickets · newest 100 shown`;
  if (!visible.length) {
    const box = element('div',undefined,'empty-state'); box.append(element('span',tickets.length ? '⌕' : '+','empty-symbol'),element('h3',tickets.length ? 'A little too quiet here.' : 'A fresh start.'),element('p',tickets.length ? 'Try a different search or filter.' : 'Your first ticket starts with a simple description.'));
    if(tickets.length) {const b=element('button','Clear filters','button light'); b.onclick=()=>{$('#filter').value='';$('#severity-filter').value='all';renderTickets();};box.append(b);} else {const a=element('a','Create a ticket ↗','button dark');a.href='#new-ticket';box.append(a);}
    root.append(box); return;
  }
  for (const ticket of visible) {
    const card = element('article',undefined,'ticket');card.dataset.ticketId=String(ticket.id);card.classList.toggle('highlighted',ticket.id===highlightedId);
    const head=element('div',undefined,'ticket-head');head.append(element('span','#'+String(ticket.id).slice(0,8),'ticket-id'));
    const date = new Date(ticket.created_at);if(!Number.isNaN(date.getTime()))head.append(element('span',date.toLocaleDateString(undefined,{month:'short',day:'numeric'}),'ticket-date'));
    const severityClass = ['Low','Medium','High','Critical'].includes(ticket.severity) ? ticket.severity : '';
    for(const [text,cls] of [[ticket.category,''],[ticket.severity,severityClass],...(flag(ticket.is_overridden)?[['Overridden','']]:[]),...(flag(ticket.sla_alerted)?[['SLA alert','alert']]:[]),...(ticket.satisfaction_status==='Not_Satisfied'?[['Not satisfied','alert']]:[])])head.append(element('span',text,'badge '+cls));
    card.append(head,element('p',ticket.complaint_text || 'No complaint text recorded.','complaint'));
    const meta=element('div',undefined,'ticket-meta');meta.append(element('span','Assigned to '+ticket.team),element('span','SLA risk: '+ticket.sla_risk_level),element('span',ticket.escalation_status));card.append(meta);
    const details=element('details');details.append(element('summary','Why this decision?'),element('p',ticket.decision_rationale || 'No rationale recorded.','rationale'));card.append(details);
    if(ticket.override_reason)card.append(element('p','Agent note: '+ticket.override_reason,'muted'));
    const actions=element('div',undefined,'ticket-actions');
    const override=element('button','Override decision ↗');override.onclick=()=>openTicketDialog(ticket,'override');
    const escalate=element('button','Customer not satisfied ↗');escalate.onclick=()=>openTicketDialog(ticket,'escalate');
    actions.append(override,escalate);card.append(actions);root.append(card);
  }
}
function openTicketDialog(ticket, type) {
  selectedId=ticket.id; const dialog=$('#'+type+'-dialog'), form=dialog.querySelector('form');form.reset();form.querySelector('.error').textContent='';
  if(type==='override') {
    const team=form.elements.team;team.querySelector('option[data-legacy]')?.remove();
    if(![...team.options].some(o=>o.value===ticket.team)){const option=element('option','Select a team (currently '+ticket.team+')');option.value='';option.disabled=true;option.dataset.legacy='true';team.prepend(option);team.value='';}else team.value=ticket.team;
    team.required=true;form.elements.severity.value=ticket.severity;form.elements.severity.required=true;
  }
  dialog.showModal();
}
function setBusy(form,busy) {
  form.setAttribute('aria-busy',String(busy));all('button').filter(b=>form.contains(b)).forEach(b=>b.disabled=busy);
}
async function submit(form,task,errorElement) {
  if(form.getAttribute('aria-busy')==='true')return;
  setBusy(form,true);errorElement.textContent='';
  try {await task();} catch(error) {errorElement.textContent=error.message;} finally {setBusy(form,false);}
}
$('#login-form').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{
  await api('/api/auth/login','POST',Object.fromEntries(new FormData(event.target)));
  signedIn=true;$('#password').value='';$('#password').type='password';$('#password-toggle').textContent='Show';$('#password-toggle').setAttribute('aria-label','Show password');$('#password-toggle').setAttribute('aria-pressed','false');$('#nav-auth').textContent='Sign out ↗';navigate(pendingRoute);
},$('#login-error'));};
$('#nav-auth').onclick=async()=>{
  if(!signedIn){pendingRoute='overview';navigate('signin');return;}
  $('#nav-auth').disabled=true;
  try{await api('/api/auth/logout','POST');resetSession();$('#complaint').value='';updateCharacterCount();navigate('home');toast('You’re signed out.');}catch(error){toast(error.message);}finally{$('#nav-auth').disabled=false;}
};
$('#password-toggle').onclick=()=>{const show=$('#password').type==='password';$('#password').type=show?'text':'password';$('#password-toggle').textContent=show?'Hide':'Show';$('#password-toggle').setAttribute('aria-label',show?'Hide password':'Show password');$('#password-toggle').setAttribute('aria-pressed',String(show));};
$('#refresh').onclick=()=>refresh();$('#filter').oninput=renderTickets;$('#severity-filter').onchange=renderTickets;
all('[data-stat-filter]').forEach(b=>b.onclick=()=>{$('#filter').value='';$('#severity-filter').value=b.dataset.statFilter;navigate('tickets');renderTickets();});
function updateCharacterCount(){$('#character-count').textContent=$('#complaint').value.length.toLocaleString()+' / 10,000';}
$('#complaint').oninput=updateCharacterCount;
$('#triage-form').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{
  $('#triage-progress').textContent='Finding a category, priority, and team. This may take a moment…';
  try {
    const data=await api('/api/triage','POST',{complaint_text:$('#complaint').value});
    if(data.status!=='success'||!data.ticket?.id)throw new Error('The ticket save was not confirmed. Please check the queue before retrying.');
    createdId=data.ticket.id;highlightedId=createdId;$('#complaint').value='';updateCharacterCount();
    $('#result-id').textContent='Ticket #'+createdId.slice(0,8)+' · Saved successfully';
    const summary=$('#result-summary');summary.replaceChildren();
    for(const [label,value] of [['Category',data.ticket.category],['Priority',data.ticket.severity],['Assigned team',data.ticket.team],['SLA risk',data.ticket.sla_risk_level]]){const dl=element('dl');dl.append(element('dt',label),element('dd',value));summary.append(dl);}
    summary.append(element('p',data.ticket.decision_rationale,'result-rationale'));
    $('#result-privacy').textContent=data.security_flags?.pii_redacted?'Personal information patterns were redacted before classification and storage.':'No common personal information patterns were detected.';
    if(signedIn)$('#result-dialog').showModal();await refresh();
  } finally {$('#triage-progress').textContent='';}
},$('#triage-error'));};
$('#result-another').onclick=()=>{$('#result-dialog').close();navigate('new-ticket');$('#complaint').focus();};
$('#result-view').onclick=()=>{$('#result-dialog').close();$('#filter').value=createdId;$('#severity-filter').value='all';navigate('tickets');renderTickets();};
for(const [id,action,method] of [['override','override','PUT'],['escalate','not-satisfied','POST']])$('#'+id+'-form').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{
  const data=await api('/api/tickets/'+encodeURIComponent(selectedId)+'/'+action,method,Object.fromEntries(new FormData(event.target)));
  if(data.status!=='success')throw new Error('The update was not confirmed. Refresh before retrying.');
  $('#'+id+'-dialog').close();highlightedId=selectedId;toast(id==='override'?'New direction saved.':'Ticket escalated for follow-up.');await refresh();
},event.target.querySelector('.error'));};
all('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
all('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(dialog.querySelector('form[aria-busy="true"]'))event.preventDefault();}));
function renderSettings(data) {
  const root=$('#settings-fields');root.replaceChildren();$('#settings-source').textContent=data.source==='admin_override'?'Custom rules are active':'Default rules are active';
  for(const [group,title] of Object.entries(settingsGroups)) {
    const values=data.config[group];const section=element('section',undefined,'settings-group');section.append(element('h3',title));
    for(const [key,value] of Object.entries(typeof values==='object'?values:{[group]:values})) {
      const label=element('label',group==='workload_bump_threshold'?'Tickets per team':key);const input=document.createElement('input');input.type='number';input.step=group==='workload_bump_threshold'?'1':'any';input.min=group==='workload_bump_threshold'?'0':'0.001';input.required=true;input.value=value;input.dataset.group=group;input.dataset.key=key;label.append(input);section.append(label);
    }
    root.append(section);
  }
}
async function openSettings() {
  const buttons=[$('#settings-open'),$('#settings-card-open')];buttons.forEach(b=>b.disabled=true);
  try{renderSettings(await api('/api/admin/sla-config'));$('#settings-form .error').textContent='';$('#settings-dialog').showModal();}catch(error){toast(error.message);}finally{buttons.forEach(b=>b.disabled=false);}
}
$('#settings-open').onclick=openSettings;$('#settings-card-open').onclick=openSettings;
$('#settings-form').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{
  const config={};all('#settings-fields input').forEach(input=>{if(input.dataset.group==='workload_bump_threshold')config.workload_bump_threshold=Number(input.value);else(config[input.dataset.group]??={})[input.dataset.key]=Number(input.value);});
  if(config.risk_thresholds_hours.high>config.risk_thresholds_hours.medium)throw new Error('The high-risk threshold must not exceed the medium-risk threshold.');
  await api('/api/admin/sla-config','PUT',config);$('#settings-dialog').close();toast('SLA rules saved for future decisions.');
},event.target.querySelector('.error'));};
$('#settings-reset').onclick=()=>submit($('#settings-form'),async()=>{renderSettings(await api('/api/admin/sla-config/reset','POST'));toast('Default SLA rules restored.');},$('#settings-form .error'));
$('.skip-link').onclick=event=>{event.preventDefault();$('#main').focus();$('#main').scrollIntoView();};
window.addEventListener('hashchange',renderRoute);
async function boot() {
  const [health,session]=await Promise.allSettled([api('/health'),api('/api/auth/me')]);
  if(health.status==='fulfilled') {
    const data=health.value, demo=data.mode==='local-demo', offline=data.database==='local-sqlite';
    $('#mode').textContent=demo?'Offline demo':data.mode==='ollama'?'Ollama · '+data.model:'Workers AI · '+data.model;
    $('#local-hint').hidden=!offline;
    if(demo||offline){$('#environment-banner').hidden=false;$('#environment-banner').textContent='Local preview · '+(demo?'classification uses offline demo rules':'classification uses '+data.model)+(offline?' · test data stays on this computer.':'.');}
  } else {$('#mode').textContent='Service unavailable';$('#environment-banner').hidden=false;$('#environment-banner').textContent='The service is unavailable. You can explore the site; workspace actions need a working connection.';}
  signedIn=session.status==='fulfilled';$('#nav-auth').textContent=signedIn?'Sign out ↗':'Sign in ↗';booting=false;renderRoute();
  if(signedIn&&!workspaceRoutes.includes(location.hash.slice(1)))refresh();
}
boot();
