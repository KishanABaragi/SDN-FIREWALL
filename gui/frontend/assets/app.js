(() => {
  const API = '/api';
  const pages = {
    overview: ['Overview', 'CONTROL ROOM / LIVE MONITORING', 'A clear view of your network, firewall activity and system health.'],
    topology: ['Network map', 'NETWORK / TOPOLOGY', 'See how the six virtual hosts, switch and controller fit together.'],
    firewall: ['Firewall controls', 'ACCESS CONTROL / FIREWALL', 'Choose a host, apply a timed block and watch for the controller’s recovery event.'],
    tests: ['Test centre', 'VALIDATION / TEST SUITE', 'Run any scenario yourself. Each result explains what was checked and what the output means.'],
    events: ['Event timeline', 'AUDIT / SECURITY EVENTS', 'Review real controller and network-logger records.'],
    performance: ['Performance', 'OBSERVABILITY / MEASUREMENTS', 'View measurements collected by tests. No sample values are presented as live results.'],
    guide: ['Quick guide', 'HELP / GETTING STARTED', 'A short explanation of the dashboard and the project workflow.']
  };
  const state = { page: 'overview', status: null, hosts: [], events: [], tests: [], lastResults: [], selectedHost: 'h2', seconds: 30, busy: false, lastAction: null, timer: null, search: '' };
  const $ = (s, root=document) => root.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(path, options={}) {
    const response = await fetch(API + path, { ...options, headers: { 'Content-Type':'application/json', ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({detail:`Server returned HTTP ${response.status}`}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }
  function toast(message, error=false) {
    const el = document.createElement('div'); el.className = 'toast' + (error ? ' error' : ''); el.textContent = message;
    $('#toast-area').append(el); setTimeout(() => el.remove(), 4200);
  }
  function setAlert(message) {
    const el = $('#global-alert'); if (!message) { el.classList.add('hidden'); el.textContent=''; return; }
    el.textContent = message; el.classList.remove('hidden');
  }
  function navigate(page) {
    if (!pages[page]) return;
    state.page = page;
    document.querySelectorAll('.nav-link').forEach(b => b.classList.toggle('active', b.dataset.page === page));
    $('#crumb-page').textContent = pages[page][0]; $('#page-title').textContent = pages[page][0];
    $('#page-eyebrow').textContent = pages[page][1]; $('#page-description').textContent = pages[page][2];
    render();
  }
  function serviceCard(name, detail, online, icon) {
    return `<div class="service-row"><div class="service-icon">${icon}</div><div class="service-name"><b>${esc(name)}</b><span>${esc(detail)}</span></div><span class="status-pill ${online?'good':'bad'}">${online?'ONLINE':'OFFLINE'}</span></div>`;
  }
  function eventRows(events, limit=5) {
    if (!events.length) return '<div class="empty-note">No event records have been found yet. Run a test or refresh after generating traffic.</div>';
    return `<div class="activity-list">${events.slice(0,limit).map(e => {
      const action=(e.action||'EVENT').toUpperCase(); const kind=action==='BLOCK'?'block':action==='UNBLOCK'?'unblock':'';
      return `<div class="activity-item"><i class="activity-mark ${kind}"></i><div class="activity-copy"><b>${esc(action)} ${e.mac ? '· '+esc(e.mac) : ''}</b><span>${esc(e.detail||e.source||'Event recorded')} · ${esc(e.timestamp||'time unavailable')}</span></div></div>`;
    }).join('')}</div>`;
  }
  function overview() {
    const s=state.status||{}; const online=[s.mininet,s.controller,s.app_server,s.logger].filter(Boolean).length;
    const blocks=state.events.filter(e=>(e.action||'').toUpperCase()==='BLOCK').length;
    return `<div class="overview-hero"><div class="hero-text"><div class="hero-kicker">YOUR NETWORK. YOUR CONTROLS.</div><h2>Understand what’s happening.<br>Take control with confidence.</h2><p>Monitor the six-host SDN lab, control host access and run evidence-based checks — with plain-language results at every step.</p><div class="hero-actions"><button class="btn btn-light" data-go="tests">Run a test <span>→</span></button><button class="btn btn-outline" data-go="firewall">Open firewall controls</button></div></div><div class="hero-art"><div class="hero-ring"><span>⬡</span></div><i class="hero-orbit one"></i><i class="hero-orbit two"></i></div></div>
    <div class="stat-grid"><div class="stat-card ${online===4?'good':'warn'}"><div class="stat-top">Services online <span class="stat-icon">◉</span></div><div class="stat-value">${online}<small style="font-size:12px;color:#9aa5b2"> / 4</small></div><div class="stat-sub">Mininet · Ryu · App · Logger</div></div><div class="stat-card ${s.switch_connected?'good':'bad'}"><div class="stat-top">OpenFlow switch <span class="stat-icon">⌘</span></div><div class="stat-value">${s.switch_connected?'Connected':'Not connected'}</div><div class="stat-sub">s1 ↔ Ryu · OpenFlow 1.3</div></div><div class="stat-card"><div class="stat-top">Hosts configured <span class="stat-icon">▦</span></div><div class="stat-value">${state.hosts.length || 6}</div><div class="stat-sub">One switch · six virtual hosts</div></div><div class="stat-card ${blocks?'warn':''}"><div class="stat-top">Block events recorded <span class="stat-icon">⬡</span></div><div class="stat-value">${blocks}</div><div class="stat-sub">Records currently in event history</div></div></div>
    <div class="content-grid"><section class="panel"><div class="panel-head"><div><h3 class="panel-title">System health</h3><p class="panel-sub">Live checks against the running project services.</p></div><button class="text-link" data-action="refresh">Refresh ↻</button></div><div class="service-list">${serviceCard('Mininet network','Six-host virtual topology',!!s.mininet,'⌘')}${serviceCard('Ryu controller','Control API :6001 · OpenFlow :6653',!!s.controller,'⬡')}${serviceCard('Application server','h3 · 10.0.0.3:5000',!!s.app_server,'▣')}${serviceCard('Security event logger','h4 · 10.0.0.4:6000',!!s.logger,'≋')}</div></section>
    <section class="panel"><div class="panel-head"><div><h3 class="panel-title">Network at a glance</h3><p class="panel-sub">Controller → switch → six hosts.</p></div><button class="text-link" data-go="topology">Explore map →</button></div><div class="mini-topology"><div class="mini-node controller"><b>RYU</b><span>Controller</span></div><i class="mini-line"></i><div class="mini-node switch"><b>s1</b><span>OVS switch</span></div><i class="mini-line"></i><div class="mini-node"><b>h1–h6</b><span>6 hosts</span><div class="host-dots"><i></i><i></i><i></i><i></i><i></i><i></i></div></div></div><div class="inline-note">h3 runs the TCP application server. h4 receives security events. h1, h2, h5 and h6 act as clients.</div></section></div>
    <section class="panel"><div class="panel-head"><div><h3 class="panel-title">Recent security activity</h3><p class="panel-sub">Latest entries collected from the controller and logger.</p></div><button class="text-link" data-go="events">View timeline →</button></div>${eventRows(state.events,5)}</section>`;
  }
  function topology() {
    return `<section class="panel"><div class="panel-head"><div><h3 class="panel-title">Live network layout</h3><p class="panel-sub">The logical layout used by this project. Connection status is checked from OVS.</p></div><span class="status-pill ${state.status?.switch_connected?'good':'bad'}">${state.status?.switch_connected?'SWITCH CONNECTED':'SWITCH NOT CONNECTED'}</span></div><div class="topology-stage"><div class="topology-flow"><div class="topo-controller"><b>⬡ Ryu Security Controller</b><span>127.0.0.1:6653 · OpenFlow 1.3 · Control :6001</span></div><i class="topo-link"></i><div class="topo-switch"><b>⌘ s1 · Open vSwitch</b><span>Central switching point</span></div><i class="topo-link"></i><div class="topo-hosts">${state.hosts.map(h=>`<div class="topo-host ${h.id==='h3'?'server':h.id==='h4'?'logger':''}"><b>${esc(h.id)}</b><span>${esc(h.ip)}</span></div>`).join('')}</div></div><div class="topo-legend"><span><i class="legend-dot blue"></i>Controller</span><span><i class="legend-dot"></i>Client hosts</span><span><i class="legend-dot amber"></i>Service hosts h3 / h4</span></div></div></section><section class="panel"><div class="panel-head"><div><h3 class="panel-title">Host directory</h3><p class="panel-sub">Select a host to open its firewall controls.</p></div></div><div class="host-grid">${state.hosts.map(h=>`<div class="host-card"><div class="host-card-head"><span class="host-id">${esc(h.id)}</span><span class="status-pill ${h.id==='h3'||h.id==='h4'?'warn':'good'}">${h.id==='h3'?'SERVER':h.id==='h4'?'LOGGER':'CLIENT'}</span></div><div class="host-role">${esc(h.role)}</div><div class="host-ip">${esc(h.ip)}</div><div class="host-mac">${esc(h.mac)}</div><button class="btn btn-muted btn-sm" data-host="${esc(h.id)}">Manage host →</button></div>`).join('')}</div></section>`;
  }
  function firewall() {
    const host=state.hosts.find(h=>h.id===state.selectedHost)||state.hosts[1];
    const blocked=state.blockedHosts||[];
    return `<div class="firewall-layout"><section class="panel"><div class="panel-head"><div><h3 class="panel-title">Host access control</h3><p class="panel-sub">A rule is applied by the Ryu controller using the selected host’s MAC address.</p></div><span class="status-pill good">CONTROLLER MANAGED</span></div><label class="form-label" for="host-select">Select a host</label><select class="field" id="host-select">${state.hosts.map(h=>`<option value="${h.id}" ${h.id===state.selectedHost?'selected':''}>${h.id} · ${h.ip} · ${h.role}</option>`).join('')}</select><div class="inline-note" id="selected-host-info">Selected device MAC: <b>${esc(host?.mac||'')}</b><br>Only choose a client device for the blocking demonstration. Avoid blocking h3 (application server) or h4 (logger).</div><label class="form-label" for="block-seconds">Block duration</label><select class="field" id="block-seconds"><option value="10" ${state.seconds===10?'selected':''}>10 seconds</option><option value="30" ${state.seconds===30?'selected':''}>30 seconds</option><option value="60" ${state.seconds===60?'selected':''}>60 seconds</option><option value="120" ${state.seconds===120?'selected':''}>2 minutes</option><option value="300" ${state.seconds===300?'selected':''}>5 minutes</option></select><div class="field-help">The controller schedules an automatic unblock when the timer expires. The event timeline is used to confirm that recovery actually occurred.</div><div class="control-actions"><button class="btn btn-danger" id="block-btn">⊘ Block selected host</button><button class="btn btn-success" id="unblock-btn">↗ Unblock selected host</button></div><div class="inline-note">A timed block is not a countdown simulation: the dashboard shows the requested timer and waits for the controller’s UNBLOCK event before reporting recovery.</div></section><section class="panel"><div class="panel-head"><div><h3 class="panel-title">Currently blocked hosts</h3><p class="panel-sub">Derived from the latest BLOCK / UNBLOCK controller records.</p></div><button class="text-link" data-action="refresh">Refresh</button></div>${blocked.length?`<div class="blocked-list">${blocked.map(b=>`<div class="blocked-item"><div class="blocked-symbol">⊘</div><div style="flex:1"><b>${esc(b.id)} · ${esc(b.ip)}</b><span>${esc(b.mac)} · ${esc(b.seconds)}s configured duration</span></div><span class="status-pill bad">BLOCKED</span></div>`).join('')}</div>`:'<div class="empty-note">No currently active block is indicated by the latest controller records.</div>'}<div class="inline-note">If a timed block has expired, wait for the controller to write its automatic UNBLOCK record and refresh this panel.</div></section></div>`;
  }
  function testsPage() {
    return `<div class="test-toolbar"><p>Choose any test below. The result panel shows each check, its outcome and the evidence returned by the live test runner.</p><div class="test-toolbar-actions"><button class="btn btn-muted" data-action="clear-results">Clear results</button><button class="btn btn-primary" id="run-all-btn">▶ Run all 7 tests</button></div></div><div class="test-grid">${state.tests.map(t=>`<article class="test-card"><div class="test-card-top"><span class="test-number">${String(t.id).padStart(2,'0')}</span><span class="test-group">${esc(t.group)}</span></div><h3>${esc(t.name)}</h3><p>${esc(t.purpose)}</p><ul class="test-checks">${t.checks.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><div class="test-card-foot"><span class="duration">◷ ${esc(t.duration)}</span><button class="btn btn-muted btn-sm" data-run-test="${t.id}">Run this test →</button></div></article>`).join('')}</div><section class="panel test-results" id="test-results"><div class="panel-head"><div><h3 class="panel-title">Test results</h3><p class="panel-sub">Results appear here after you run a test. Nothing is marked PASS without returned evidence.</p></div><span class="status-pill warn">AWAITING TEST</span></div><div class="empty-note">Select a test above to begin. Test 5 takes approximately 40 seconds because it waits for the real automatic timer to expire.</div></section>`;
  }
  function resultHtml(result) {
    const status=(result.status||'ERROR').toUpperCase(); const cls=status==='PASS'?'pass':status==='INCONCLUSIVE'?'inconclusive':'fail';
    const symbol=status==='PASS'?'✓':status==='INCONCLUSIVE'?'!':'×';
    const steps=(result.steps||[]).map(s=>`<div class="step-row ${esc(s.state||'info')}"><i class="step-check">${s.state==='passed'?'✓':s.state==='failed'?'×':'·'}</i><div><b>${esc(s.label)}</b><span>${esc(s.detail)}</span></div></div>`).join('')||'<div class="empty-note">No step details were returned.</div>';
    const evidence=(result.evidence||[]).filter(Boolean).join('\n\n--- evidence source ---\n\n');
    return `<div class="result-banner ${cls}"><div class="result-symbol">${symbol}</div><div class="result-copy"><b>${esc(result.name||'Test result')}</b><span>${esc(result.summary||result.detail||'No summary returned.')}</span></div><span class="result-status">${esc(status)}</span></div><div class="step-list">${steps}</div>${evidence?`<details class="evidence"><summary>Show technical evidence / command output</summary><pre>${esc(evidence)}</pre></details>`:''}<div class="muted" style="margin-top:10px">${esc(result.timestamp||'Completed just now')}</div>`;
  }
  function eventsPage() {
    const search=state.search.toLowerCase(); const filtered=state.events.filter(e=>[e.action,e.mac,e.detail,e.source].join(' ').toLowerCase().includes(search));
    return `<section class="panel"><div class="panel-head"><div><h3 class="panel-title">Security event records</h3><p class="panel-sub">Controller CSV and network logger records. Historical records may also appear and are labelled by source.</p></div><button class="btn btn-muted btn-sm" data-action="refresh">↻ Refresh records</button></div><div class="timeline-tools"><input class="field" id="event-search" placeholder="Search action, MAC or details…" value="${esc(state.search)}"><span class="muted">${filtered.length} records</span></div><div class="event-table-wrap"><table class="event-table"><thead><tr><th>Action</th><th>Host / MAC</th><th>Details</th><th>Source</th><th>Time</th></tr></thead><tbody>${filtered.map(e=>`<tr><td><span class="event-kind ${esc((e.action||'').toLowerCase())}">${esc(e.action||'EVENT')}</span></td><td>${esc(e.mac||'—')}</td><td class="event-detail">${esc(e.detail||e.result||'—')}</td><td>${esc(e.source||'Project log')}</td><td>${esc(e.timestamp||'—')}</td></tr>`).join('')}</tbody></table></div>${filtered.length?'':'<div class="empty-note">No matching event records found.</div>'}</section>`;
  }
  function performancePage() {
    const rows=state.lastResults.filter(r=>r.metrics||r.test_id===6); const p=rows.find(r=>r.test_id===6); const multi=state.lastResults.find(r=>r.test_id===7);
    const loss=p?.metrics?.packet_loss_percent; const rtt=p?.metrics?.average_rtt_ms; const acks=multi?.metrics?.acknowledgements;
    return `<div class="metric-grid"><div class="metric-box"><span>Latest baseline packet loss</span><b>${loss===undefined||loss===null?'—':esc(loss)+'%'}</b><small>${p?'From the latest performance test':'Run test 6 to collect a live value'}</small></div><div class="metric-box"><span>Latest average RTT</span><b>${rtt===undefined||rtt===null?'—':esc(rtt)+' ms'}</b><small>${p?'Measured h1 → h3':'No measurement collected yet'}</small></div><div class="metric-box"><span>Concurrent ACK replies</span><b>${acks===undefined?'—':esc(acks)+'/10'}</b><small>${multi?'From the latest multi-client test':'Run test 7 to collect a live value'}</small></div></div><section class="panel" style="margin-top:16px"><div class="panel-head"><div><h3 class="panel-title">How to collect a useful comparison</h3><p class="panel-sub">Use fresh test runs for baseline, blocked and recovered phases.</p></div><button class="btn btn-primary btn-sm" data-go="tests">Open test centre →</button></div><div class="guide-grid"><div class="guide-card"><h3>1 · Baseline</h3><p>Run test 6 while the selected client is not blocked. Record packet loss and average RTT.</p></div><div class="guide-card"><h3>2 · During block</h3><p>Use firewall controls to block the test client. Run an equivalent ping measurement and record the result.</p></div><div class="guide-card"><h3>3 · Recovery</h3><p>Wait for the controller’s automatic UNBLOCK event or manually unblock the host, then repeat the same measurement.</p></div><div class="guide-card"><h3>4 · Report honestly</h3><p>Keep the test duration and packet count consistent. Do not confuse controller rule-submission time with end-to-end enforcement latency.</p></div></div></section>`;
  }
  function guidePage() {
    return `<div class="guide-grid"><section class="guide-card"><h3>Start the application</h3><ol><li>Open a terminal in the project folder.</li><li>Run <code>./RUN_APP.sh</code>.</li><li>Keep the terminal open while using the dashboard.</li><li>Press Ctrl+C in that terminal to stop the services.</li></ol></section><section class="guide-card"><h3>Understand the service checks</h3><ul><li><b>Mininet:</b> the six virtual hosts and OVS switch.</li><li><b>Ryu:</b> controller control socket and OpenFlow listener.</li><li><b>Application:</b> TCP server on h3:5000.</li><li><b>Logger:</b> event collector on h4:6000.</li></ul></section><section class="guide-card"><h3>Run tests safely</h3><p>Start with test 1 (TCP communication), then test 3 (firewall), test 4 (logger), and test 5 (automatic detection). Test 5 waits for the configured timer to expire and can take around 40 seconds.</p></section><section class="guide-card"><h3>Understand test outcomes</h3><ul><li><b>PASS:</b> all required checks returned expected evidence.</li><li><b>FAIL:</b> a check ran but did not meet its expected condition.</li><li><b>INCONCLUSIVE:</b> the test could not prove the behaviour.</li><li><b>ERROR:</b> the test could not complete because of an execution problem.</li></ul></section><section class="guide-card"><h3>Firewall controls</h3><p>Choose a client host and a duration. A timed block is removed by the Ryu controller. The dashboard checks the controller event log to confirm expiry. Avoid blocking h3 or h4 because they provide the application and logging services.</p></section><section class="guide-card"><h3>Where evidence is stored</h3><p>Controller actions: <code>logs/controller_events.csv</code><br>Network logger: <code>logs/runtime_logger/security_events.log</code><br>Service output: <code>logs/*.out</code></p></section></div>`;
  }
  function render() {
    const root=$('#page-content');
    if (state.page==='overview') root.innerHTML=overview();
    else if (state.page==='topology') root.innerHTML=topology();
    else if (state.page==='firewall') root.innerHTML=firewall();
    else if (state.page==='tests') root.innerHTML=testsPage();
    else if (state.page==='events') root.innerHTML=eventsPage();
    else if (state.page==='performance') root.innerHTML=performancePage();
    else root.innerHTML=guidePage();
    if (state.page==='tests' && state.lastResults.length) {
      const resultPanel=$('#test-results');
      if (resultPanel) resultPanel.innerHTML=`<div class="panel-head"><div><h3 class="panel-title">Latest test results</h3><p class="panel-sub">Actual results returned by the Mininet test runner.</p></div></div>${state.lastResults.map(resultHtml).join('<div style="height:12px"></div>')}`;
    }
    bindPageActions();
  }
  async function refresh(silent=false) {
    try {
      const [status,topology,events,blocked]=await Promise.all([api('/status'),api('/topology'),api('/events'),api('/firewall/state')]);
      state.status=status; state.hosts=topology.hosts||[]; state.events=events.events||[]; state.blockedHosts=blocked.blocked_hosts||[];
      $('#last-updated').textContent='Updated '+new Date().toLocaleTimeString();
      const health=$('#header-health'); const ok=[status.mininet,status.controller,status.app_server,status.logger].every(Boolean);
      health.className='system-indicator '+(ok?'ok':'bad'); health.innerHTML=`<i class="health-dot"></i><span>${ok?'All systems operational':`${[status.mininet,status.controller,status.app_server,status.logger].filter(Boolean).length}/4 services online`}</span>`;
      if (!silent) { setAlert(''); render(); }
    } catch (err) {
      $('#header-health').className='system-indicator bad'; $('#header-health').innerHTML='<i class="health-dot"></i><span>Dashboard API unavailable</span>';
      if (!silent) { setAlert('Could not refresh live project data: '+err.message); render(); }
    }
  }
  async function loadInitial() {
    try { const [t,hosts]=await Promise.all([api('/tests'),api('/hosts')]); state.tests=t.tests||[]; state.hosts=hosts.hosts||[]; }
    catch(err) { setAlert('Could not load dashboard configuration: '+err.message); }
    await refresh(true); render();
  }
  async function runTest(id) {
    if (state.busy) return;
    const test=state.tests.find(t=>t.id===id); state.busy=true;
    const panel=$('#test-results'); if(panel) panel.innerHTML=`<div class="panel-head"><div><h3 class="panel-title">${esc(test?.name||'Test')} running</h3><p class="panel-sub">The test is interacting with your live Mininet network. Please keep this page open.</p></div><span class="status-pill warn">RUNNING</span></div><div class="loading">◌ Running test and collecting evidence…</div>`;
    try { const result=await api('/tests/'+id,{method:'POST'}); result.name=result.name||test?.name; state.lastResults=[result,...state.lastResults.filter(r=>r.test_id!==id)];
      if (panel) panel.innerHTML=resultHtml(result); toast(`${result.name}: ${result.status}`); await refresh(true);
    } catch(err) { if(panel) panel.innerHTML=`<div class="result-banner fail"><div class="result-symbol">×</div><div class="result-copy"><b>Test could not complete</b><span>${esc(err.message)}</span></div><span class="result-status">ERROR</span></div>`; toast(err.message,true); }
    finally { state.busy=false; }
  }
  async function runAll() {
    if (state.busy) return; state.busy=true; state.lastResults=[];
    const panel=$('#test-results'); if(panel) panel.innerHTML='<div class="panel-head"><div><h3 class="panel-title">Running complete test suite</h3><p class="panel-sub">Seven tests are running in sequence. Automatic recovery waits for its real controller timer.</p></div><span class="status-pill warn">RUNNING</span></div><div class="loading">◌ This may take up to a minute. Keep the dashboard open.</div>';
    try { const data=await api('/tests/run-all',{method:'POST'}); state.lastResults=data.results||[]; if(panel) panel.innerHTML=`<div class="panel-head"><div><h3 class="panel-title">Complete test suite</h3><p class="panel-sub">Completed ${esc(data.completed_at||'')}</p></div><span class="status-pill ${state.lastResults.every(r=>r.status==='PASS')?'good':'warn'}">${state.lastResults.filter(r=>r.status==='PASS').length}/${state.lastResults.length} PASSED</span></div>${state.lastResults.map(resultHtml).join('<div style="height:12px"></div>')}`; toast('Complete test suite finished. Review each result below.'); await refresh(true);
    } catch(err) { if(panel) panel.innerHTML=`<div class="result-banner fail"><div class="result-symbol">×</div><div class="result-copy"><b>Test suite could not complete</b><span>${esc(err.message)}</span></div></div>`; toast(err.message,true); }
    finally { state.busy=false; }
  }
  async function firewallAction(action) {
    const host=state.hosts.find(h=>h.id===state.selectedHost); if(!host) return;
    if (['h3','h4'].includes(host.id) && action==='block') { toast('For safety, choose a client host instead of the application server or logger.',true); return; }
    const seconds=Number($('#block-seconds')?.value||state.seconds); state.seconds=seconds;
    const button=$('#'+action+'-btn'); if(button) button.disabled=true;
    try {
      const result=await api('/firewall/'+action,{method:'POST',body:JSON.stringify({mac:host.mac,seconds})});
      toast(result.response||`${action} request sent.`);
      state.lastAction=action==='block'?{mac:host.mac,expiresAt:result.expires_at}:null;
      await refresh(true); if(state.page==='firewall') render();
      if(action==='block' && result.expires_at) watchExpiry(host);
    } catch(err) { toast(err.message,true); }
    finally { if(button) button.disabled=false; }
  }
  function watchExpiry(host) {
    if(state.timer) clearInterval(state.timer);
    const expires=state.lastAction?.expiresAt; if(!expires) return;
    const started=Date.now();
    state.timer=setInterval(async()=>{
      await refresh(true);
      const stillBlocked=(state.blockedHosts||[]).some(h=>h.mac===host.mac);
      if(!stillBlocked) { clearInterval(state.timer); state.timer=null; toast(`${host.id} is unblocked. Controller recovery event detected.`); if(state.page==='firewall') render(); return; }
      if(Date.now()/1000>expires+5 && Date.now()-started>5000) { /* Keep waiting for controller evidence; do not fabricate an unblock. */ }
      if(state.page==='firewall') render();
    },2000);
  }
  function bindPageActions() {
    document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.go)));
    document.querySelectorAll('[data-page]').forEach(b=>{if(!b.classList.contains('nav-link')) b.addEventListener('click',()=>navigate(b.dataset.page));});
    document.querySelectorAll('[data-action="refresh"]').forEach(b=>b.addEventListener('click',()=>refresh()));
    document.querySelectorAll('[data-run-test]').forEach(b=>b.addEventListener('click',()=>runTest(Number(b.dataset.runTest))));
    document.querySelectorAll('[data-host]').forEach(b=>b.addEventListener('click',()=>{state.selectedHost=b.dataset.host;navigate('firewall');}));
    $('#run-all-btn')?.addEventListener('click',runAll);
    $('#block-btn')?.addEventListener('click',()=>firewallAction('block'));
    $('#unblock-btn')?.addEventListener('click',()=>firewallAction('unblock'));
    $('#host-select')?.addEventListener('change',e=>{state.selectedHost=e.target.value;render();});
    $('#block-seconds')?.addEventListener('change',e=>{state.seconds=Number(e.target.value);});
    $('#event-search')?.addEventListener('input',e=>{state.search=e.target.value;const pos=e.target.selectionStart;render();const input=$('#event-search');input.focus();input.setSelectionRange(pos,pos);});
    $('#page-content [data-action="clear-results"]')?.addEventListener('click',()=>{state.lastResults=[];render();});
  }
  $('#navigation').addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b)navigate(b.dataset.page);});
  $('#refresh-btn').addEventListener('click',()=>refresh());
  loadInitial(); setInterval(()=>refresh(true),5000);
})();
