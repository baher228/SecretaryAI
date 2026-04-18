from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Secretary AI Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg: #0f172a;
        --panel: rgba(30, 41, 59, 0.7);
        --panel-solid: #1e293b;
        --ink: #f8fafc;
        --muted: #94a3b8;
        --line: rgba(255, 255, 255, 0.1);
        --primary: #0ea5e9;
        --primary-2: #38bdf8;
        --accent: #f59e0b;
        --shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Outfit", sans-serif;
        color: var(--ink);
        background: var(--bg);
        background-image: 
          radial-gradient(circle at 15% 50%, rgba(14, 165, 233, 0.15), transparent 25%),
          radial-gradient(circle at 85% 30%, rgba(245, 158, 11, 0.15), transparent 25%);
        min-height: 100vh;
      }
      
      /* Headers & Navigation */
      .header-area {
        padding: 32px 24px;
        text-align: center;
      }
      .header-area h1 {
        margin: 0;
        font-size: 2.2rem;
        background: linear-gradient(to right, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .nav-container { border-bottom: 1px solid var(--line); margin-bottom: 24px; padding: 0 24px; }
      .nav-tabs { display: flex; gap: 32px; max-width: 1320px; margin: 0 auto; }
      .tab-btn {
        background: none; border: none; color: var(--muted); font-family: 'Outfit'; font-size: 1.05rem;
        font-weight: 500; padding: 16px 0; cursor: pointer; transition: 0.2s;
        border-bottom: 2px solid transparent; outline: none;
      }
      .tab-btn:hover { color: var(--ink); }
      .tab-btn.active { color: var(--primary-2); border-bottom-color: var(--primary-2); }
      
      .tab-content { display: none; }
      .tab-content.active { display: block; animation: fadeIn 0.4s ease-out; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

      .wrap { max-width: 1320px; margin: 0 auto; padding: 0 18px 28px; }
      
      /* Panels & Cards */
      .panel {
        background: var(--panel);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 16px;
        border: 1px solid var(--line);
        box-shadow: var(--shadow);
        padding: 24px;
        margin-bottom: 24px;
      }
      h2 { margin: 0 0 16px; font-weight: 600; font-size: 1.3rem; }
      .subtitle { margin: 0 0 16px; color: var(--muted); font-size: 0.95rem; }
      
      /* Overview Stats */
      .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
      .stat-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 16px;
        display: flex; flex-direction: column; gap: 8px;
        transition: transform 0.2s;
      }
      .stat-card:hover { transform: translateY(-2px); border-color: rgba(255, 255, 255, 0.2); }
      .stat-title { font-size: 0.85rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 500; }
      .stat-value { font-size: 1.4rem; font-weight: 600; color: #fff; }
      .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
      .status-ok { background: #10b981; box-shadow: 0 0 8px #10b981; }
      .status-warn { background: #f59e0b; box-shadow: 0 0 8px #f59e0b; }
      .status-err { background: #ef4444; box-shadow: 0 0 8px #ef4444; }

      /* Recent Calls Table */
      .table-wrapper { overflow-x: auto; }
      table { width: 100%; border-collapse: collapse; margin-top: 8px; }
      th { text-align: left; padding: 12px 16px; font-weight: 500; color: var(--muted); border-bottom: 1px solid var(--line); font-size: 0.9rem; }
      td { padding: 14px 16px; border-bottom: 1px solid var(--line); font-size: 0.95rem; }
      tr:last-child td { border-bottom: none; }
      tr:hover td { background: rgba(255,255,255,0.02); }
      .pill { padding: 4px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; display: inline-block; }
      .pill-completed { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
      .pill-routing { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
      .pill-received { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }

      /* Form inputs */
      input, textarea {
        width: 100%; background: rgba(0,0,0,0.25); border: 1px solid var(--line);
        color: #fff; padding: 14px; border-radius: 10px; font-family: "Outfit", "Cascadia Code", sans-serif;
        margin-bottom: 14px; outline: none; transition: border-color 0.2s; font-size: 0.95rem;
      }
      input:focus, textarea:focus { border-color: var(--primary); }
      button {
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        border: none; color: #fff; font-weight: 600; padding: 12px 24px; border-radius: 10px;
        cursor: pointer; transition: opacity 0.2s, transform 0.1s; font-family: "Outfit"; font-size: 0.95rem;
      }
      button:hover { opacity: 0.9; }
      button:active { transform: scale(0.98); }
      button.secondary { background: linear-gradient(135deg, #f59e0b, #ea580c); }
      
      /* Reused old layout classes for Lab */
      .layout { display: grid; gap: 24px; grid-template-columns: 1.2fr 0.8fr; }
      @media (max-width: 980px) { .layout { grid-template-columns: 1fr; } }
      .cards { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
      .card { border: 1px solid var(--line); border-radius: 12px; padding: 16px; background: rgba(0,0,0,0.15); }
      .row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
      .method { font-size: 0.75rem; text-transform: uppercase; font-weight: 700; background: var(--primary); padding: 4px 10px; border-radius: 99px; }
      .method.post { background: var(--accent); }
      code.path { background: rgba(255,255,255,0.1); border-radius: 6px; padding: 4px 8px; font-family: "Cascadia Code", monospace; font-size: 0.85rem; }
      .hint { margin: 0 0 12px; color: var(--muted); font-size: 0.88rem; }
      .output {
        min-height: 500px; padding: 16px; border-radius: 12px;
        background: #000; color: #a5b4fc; font-family: "Cascadia Code", monospace; font-size: 0.85rem;
        white-space: pre-wrap; overflow-y: auto; border: 1px solid var(--line);
      }
      
      .d-flex { display: flex; gap: 24px; }
      .flex-1 { flex: 1; min-width: 300px; }
      
      .loader {
        border: 2px solid rgba(255,255,255,0.1); border-top-color: var(--primary);
        border-radius: 50%; width: 18px; height: 18px; animation: spin 1s linear infinite;
        display: inline-block; vertical-align: middle; margin-right: 8px;
      }
      @keyframes spin { to { transform: rotate(360deg); } }
    </style>
  </head>
  <body>
    <!-- Header -->
    <div class="header-area">
      <h1>Secretary AI Control Center</h1>
    </div>

    <!-- Top Nav -->
    <div class="nav-container">
      <div class="nav-tabs">
        <button class="tab-btn active" onclick="switchTab('overview')">Overview</button>
        <button class="tab-btn" onclick="switchTab('lab')">API Lab & Debug</button>
      </div>
    </div>

    <!-- MAIN CONTENT -->
    <div class="wrap">
      
      <!-- OVERVIEW TAB -->
      <div id="overview" class="tab-content active">
        <div class="panel">
          <h2>System Intelligence Status</h2>
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-title">Core Service Tracker</span>
              <span class="stat-value" id="status-health">
                <span class="loader"></span> Loading...
              </span>
            </div>
            <div class="stat-card">
              <span class="stat-title">Telegram Session</span>
              <span class="stat-value" id="status-auth">
                <span class="loader"></span> Loading...
              </span>
            </div>
            <div class="stat-card">
              <span class="stat-title">Z.AI Logic Brain</span>
              <span class="stat-value" id="status-model">
                <span class="loader"></span> Interrogating...
              </span>
            </div>
          </div>
        </div>

        <div class="d-flex" style="flex-wrap: wrap;">
          <div class="panel flex-1" style="flex-grow: 1;">
            <h2>Quick Call Dispatch</h2>
            <p class="subtitle">Deploy the AI agent to a user via Telegram handle.</p>
            <input type="text" id="quick-target" placeholder="Target e.g., @telegram_username" />
            <input type="text" id="quick-purpose" placeholder="Purpose (e.g. reschedule meeting)" />
            <button onclick="startQuickCall()" style="width: 100%; margin-top: 4px;">Trigger Outbound Call</button>
          </div>
          
          <div class="panel flex-1" style="flex-grow: 2; height: 420px; overflow-y: auto;">
            <h2>Call Audit Log</h2>
            <p class="subtitle">Recent interactions handled by Secretary AI.</p>
            <div class="table-wrapper">
              <table id="calls-table">
                <thead>
                  <tr>
                    <th>Call ID</th>
                    <th>Target / Source</th>
                    <th>Purpose</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="calls-body">
                  <tr><td colspan="4" style="text-align:center; color: var(--muted);"><span class="loader"></span> Fetching records...</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- API LAB TAB -->
      <div id="lab" class="tab-content">
        <section class="layout">
          <div class="panel left">
            <h2>Endpoint Runner</h2>
            <p class="subtitle">Use these quick payloads to run the Telegram flow end to end.</p>
            <div class="cards">
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/health</code></div>
                <p class="hint">Service mode and status.</p>
                <button onclick="callGet('/api/v1/health')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/telegram/auth/status</code></div>
                <p class="hint">Check Telegram MTProto client readiness.</p>
                <button onclick="callGet('/api/v1/telegram/auth/status')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/telegram/auth/send-code</code></div>
                <p class="hint">Send login code to your Telegram.</p>
                <textarea id="payload-send-code">{\n  "phone_number": "+441234567890"\n}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/telegram/auth/send-code', 'payload-send-code')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/telegram/auth/sign-in</code></div>
                <p class="hint">Complete sign-in with code and password.</p>
                <textarea id="payload-signin">{\n  "phone_number": "+441234567890",\n  "code": "12345",\n  "phone_code_hash": "from_send_code",\n  "password": null\n}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/telegram/auth/sign-in', 'payload-signin')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/calls/outbound</code></div>
                <p class="hint">Start outbound private Telegram call.</p>
                <textarea id="payload-outbound">{\n  "target_user": "@target_username",\n  "purpose": "reminder",\n  "initial_audio_path": null,\n  "metadata": {}\n}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/calls/outbound', 'payload-outbound')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/agent/reply</code></div>
                <p class="hint">Generate AI response from transcript.</p>
                <textarea id="payload-agent">{\n  "call_id": "tg-123456789",\n  "transcript": "Caller wants to reschedule to tomorrow.",\n  "context": {}\n}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/agent/reply', 'payload-agent')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/calls/events</code></div>
                <p class="hint">Inspect inbound/outbound call state events.</p>
                <button onclick="callGet('/api/v1/calls/events?limit=100')">Run</button>
              </article>
            </div>
          </div>
          <div class="panel right" style="align-self: start; position: sticky; top: 24px;">
            <h2>Response Console</h2>
            <p class="subtitle">Latest request output is shown below.</p>
            <div class="output" id="output">Ready. Run any endpoint from the left panel.</div>
          </div>
        </section>
      </div>
    </div>

    <script>
      // Tab Switching
      function switchTab(tabId) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        event.currentTarget.classList.add('active');
      }

      // API Call Helpers for Lab
      function printResult(method, path, status, body) {
        const output = document.getElementById("output");
        const stamp = new Date().toISOString();
        const ok = status >= 200 && status < 300;
        output.textContent = `[${stamp}] ${method} ${path}\\nStatus: ${status} (${ok ? "OK" : "ERROR"})\\n\\n${JSON.stringify(body, null, 2)}`;
      }
      function printClientError(method, path, err) {
        document.getElementById("output").textContent = `[${new Date().toISOString()}] ${method} ${path}\\nStatus: CLIENT_ERROR\\n\\n${String(err)}`;
      }
      async function callGet(path) {
        try {
          const res = await fetch(path, { method: "GET" });
          const body = await res.json().catch(() => ({ raw: "Non-JSON response" }));
          printResult("GET", path, res.status, body);
        } catch (err) { printClientError("GET", path, err); }
      }
      async function callPost(path, textareaId) {
        try {
          const payload = JSON.parse(document.getElementById(textareaId).value);
          const res = await fetch(path, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const body = await res.json().catch(() => ({ raw: "Non-JSON response" }));
          printResult("POST", path, res.status, body);
        } catch (err) { printClientError("POST", path, err); }
      }

      // Overview Tab Refresh Loop
      async function refreshDashboard() {
        try {
          // Health
          fetch('/api/v1/health').then(r => r.json()).then(d => {
            const ind = d.status === 'ok' ? '<span class="status-indicator status-ok"></span>' : '<span class="status-indicator status-err"></span>';
            document.getElementById('status-health').innerHTML = ind + (d.status === 'ok' ? 'Online' : 'Error');
          }).catch(() => document.getElementById('status-health').innerHTML = '<span class="status-indicator status-err"></span>Offline');

          // Auth
          fetch('/api/v1/telegram/auth/status').then(r => r.json()).then(d => {
            const state = d.state || 'unknown';
            let ind = '<span class="status-indicator status-warn"></span>';
            if (state === 'authorized') ind = '<span class="status-indicator status-ok"></span>';
            document.getElementById('status-auth').innerHTML = ind + state;
          }).catch(() => document.getElementById('status-auth').innerHTML = '<span class="status-indicator status-err"></span>Error');

          // List Calls
          fetch('/api/v1/calls').then(r => r.json()).then(calls => {
            const tbody = document.getElementById('calls-body');
            if (!calls || calls.length === 0) {
              tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--muted); padding: 24px;">No calls executed yet.</td></tr>';
              return;
            }
            tbody.innerHTML = '';
            // Make a clone and reverse it to show newest calls top
            const recent = calls.slice().reverse();
            recent.forEach(c => {
              const tr = document.createElement('tr');
              let statusCls = 'pill-routing';
              if (c.status === 'completed') statusCls = 'pill-completed';
              else if (c.status === 'received') statusCls = 'pill-received';
              tr.innerHTML = `
                <td style="font-family: 'Cascadia Code', monospace; color: var(--primary-2)">${c.call_id || 'unknown'}</td>
                <td>${c.target_user || c.source_user || 'N/A'}</td>
                <td>${c.metadata?.purpose || c.purpose || 'N/A'}</td>
                <td><span class="pill ${statusCls}">${c.status || 'unknown'}</span></td>
              `;
              tbody.appendChild(tr);
            });
          }).catch(e => console.error(e));
        } catch(e) { console.error('Dashboard refresh failed', e); }
      }

      // Quick Call
      async function startQuickCall() {
        const target = document.getElementById('quick-target').value;
        const purpose = document.getElementById('quick-purpose').value || "checking in";
        if (!target) return alert('Enter a target user!');
        try {
          const res = await fetch('/api/v1/calls/outbound', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_user: target, purpose: purpose, metadata: { quick_trigger: true } })
          });
          const body = await res.json();
          if(res.ok) alert('Call triggered! ID: ' + body.call_id);
          else alert('Error triggering call: ' + JSON.stringify(body));
          refreshDashboard();
        } catch(err) { alert('Error: ' + err.message); }
      }

      // Quick Model Check
      async function runModelCheck() {
        try {
          const res = await fetch('/api/v1/model/check', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt: 'ping' })
          });
          const body = await res.json();
          const el = document.getElementById('status-model');
          if (res.ok && body.connected) {
             el.innerHTML = '<span class="status-indicator status-ok"></span>Connected';
          } else {
             el.innerHTML = '<span class="status-indicator status-err"></span>' + (body.detail || 'Offline');
          }
        } catch(err) {
          document.getElementById('status-model').innerHTML = '<span class="status-indicator status-err"></span>Error';
        }
      }

      // Initial loaders
      refreshDashboard();
      runModelCheck();
      setInterval(refreshDashboard, 5000);
    </script>
  </body>
</html>
"""

@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")

@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(content=DASHBOARD_HTML)
