from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Secretary AI</title>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg: #09090b;
        --panel: rgba(24, 24, 27, 0.7);
        --ink: #f0fdf4;
        --muted: #a1a1aa;
        --line: rgba(255, 255, 255, 0.1);
        --primary: #10b981;
        --primary-2: #3b82f6;
        --ok: #22c55e;
        --warn: #eab308;
        --err: #ef4444;
        --shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        --glass-border: rgba(255, 255, 255, 0.18);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Sora", sans-serif;
        color: var(--ink);
        background: var(--bg);
        min-height: 100vh;
      }

      .header-area {
        max-width: 1100px;
        margin: 0 auto;
        padding: 34px 24px 20px;
        text-align: center;
      }
      .header-area h1 {
        margin: 0 0 10px;
        font-size: clamp(1.9rem, 2.8vw, 2.6rem);
        letter-spacing: -0.03em;
        font-weight: 800;
        background: linear-gradient(105deg, var(--primary), var(--primary-2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .hero-subtitle { margin: 0; color: var(--muted); font-size: 0.95rem; }

      .nav-container {
        margin: 0 24px 24px;
        padding: 8px;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: rgba(24, 24, 27, 0.6);
        backdrop-filter: blur(10px);
      }
      .nav-tabs {
        display: flex; gap: 8px;
        max-width: 1100px; margin: 0 auto;
      }
      .tab-btn {
        flex: 1; background: transparent;
        border: 1px solid transparent;
        color: var(--muted);
        font-family: "Sora", sans-serif; font-size: 0.96rem; font-weight: 600;
        padding: 12px 16px; cursor: pointer;
        transition: all 0.18s ease; border-radius: 999px; outline: none;
      }
      .tab-btn:hover { color: var(--ink); border-color: var(--line); }
      .tab-btn.active {
        color: #fff; border-color: transparent;
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        box-shadow: 0 8px 20px -10px rgba(16, 185, 129, 0.7);
      }

      .tab-content { display: none; }
      .tab-content.active { display: block; animation: fadeIn 0.3s ease-out; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

      .wrap { max-width: 1100px; margin: 0 auto; padding: 0 18px 36px; }

      .panel {
        background: var(--panel);
        backdrop-filter: blur(16px);
        border-radius: 20px;
        border: 1px solid var(--glass-border);
        box-shadow: var(--shadow);
        padding: 24px;
        margin-bottom: 20px;
      }
      h2 { margin: 0 0 10px; font-weight: 700; font-size: 1.2rem; color: #fff; }
      .subtitle { margin: 0 0 14px; color: var(--muted); font-size: 0.88rem; line-height: 1.4; }

      .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 20px; }
      .stat-card {
        background: rgba(24, 24, 27, 0.5);
        border: 1px solid var(--glass-border);
        border-radius: 14px; padding: 16px;
        display: flex; flex-direction: column; gap: 6px;
      }
      .stat-title { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; }
      .stat-value { font-size: 1.15rem; font-weight: 700; color: var(--ink); }
      .status-indicator { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
      .status-ok { background: var(--ok); box-shadow: 0 0 8px rgba(34, 197, 94, 0.5); }
      .status-warn { background: var(--warn); box-shadow: 0 0 8px rgba(234, 179, 8, 0.5); }
      .status-err { background: var(--err); box-shadow: 0 0 8px rgba(239, 68, 68, 0.5); }

      .table-wrapper { overflow-x: auto; }
      table { width: 100%; border-collapse: collapse; margin-top: 6px; }
      th { text-align: left; padding: 10px 12px; font-weight: 600; color: var(--muted); border-bottom: 1px solid var(--line); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
      td { padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.9rem; }
      tr:last-child td { border-bottom: none; }
      .pill { padding: 3px 8px; border-radius: 999px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; display: inline-block; }
      .pill-active { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
      .pill-completed { background: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.3); }
      .pill-ended { background: rgba(161, 161, 170, 0.15); color: var(--muted); border: 1px solid rgba(161, 161, 170, 0.3); }

      .log-box {
        background: #000; color: #34d399;
        font-family: "JetBrains Mono", monospace; font-size: 0.82rem;
        padding: 14px; border-radius: 12px;
        max-height: 300px; overflow-y: auto; white-space: pre-wrap;
        border: 1px solid rgba(52, 211, 153, 0.15);
      }

      input, textarea {
        width: 100%; background: rgba(255,255,255,0.06);
        border: 1px solid var(--line); color: var(--ink);
        padding: 10px 12px; border-radius: 10px;
        font-family: "Sora", sans-serif; margin-bottom: 10px;
        outline: none; font-size: 0.88rem;
      }
      textarea {
        min-height: 80px; resize: vertical;
        font-family: "JetBrains Mono", monospace; font-size: 0.82rem;
      }
      input:focus, textarea:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15); }

      button {
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        border: 0; color: #fff; font-weight: 700;
        padding: 9px 14px; border-radius: 10px; cursor: pointer;
        font-family: "Sora", sans-serif; font-size: 0.84rem;
        transition: opacity 0.2s, transform 0.1s;
      }
      button:hover { opacity: 0.9; }
      button:active { transform: scale(0.97); }
      button.secondary { background: rgba(255,255,255,0.08); border: 1px solid var(--line); }
      button.secondary:hover { background: rgba(255,255,255,0.12); }

      .cards { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
      .card {
        border: 1px solid var(--line); border-radius: 14px;
        padding: 16px; background: rgba(24, 24, 27, 0.4);
      }
      .row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
      .method {
        font-size: 0.7rem; text-transform: uppercase; font-weight: 700;
        background: var(--primary); color: #fff;
        padding: 3px 8px; border-radius: 999px; letter-spacing: 0.05em;
      }
      .method.post { background: #c2410c; }
      code.path {
        background: rgba(255,255,255,0.06); border: 1px solid var(--line);
        color: var(--ink); border-radius: 6px; padding: 3px 8px;
        font-family: "JetBrains Mono", monospace; font-size: 0.82rem;
      }
      .hint { color: var(--muted); font-size: 0.82rem; margin: 0 0 10px; }

      .layout { display: grid; gap: 20px; grid-template-columns: 1.2fr 0.8fr; }
      @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }

      .loader {
        border: 2px solid rgba(16, 185, 129, 0.2);
        border-top-color: var(--primary);
        border-radius: 50%; width: 14px; height: 14px;
        animation: spin 0.8s linear infinite;
        display: inline-block; vertical-align: middle; margin-right: 6px;
      }
      @keyframes spin { to { transform: rotate(360deg); } }
    </style>
  </head>
  <body>
    <div class="header-area">
      <h1>Secretary AI</h1>
      <p class="hero-subtitle">Gemini Live voice automation for Telegram calls</p>
    </div>

    <div class="nav-container">
      <div class="nav-tabs">
        <button class="tab-btn active" onclick="switchTab('overview', this)">Status</button>
        <button class="tab-btn" onclick="switchTab('voice', this)">Voice</button>
        <button class="tab-btn" onclick="switchTab('bookings', this)">Bookings</button>
        <button class="tab-btn" onclick="switchTab('lab', this)">API Lab</button>
      </div>
    </div>

    <div class="wrap">

      <!-- STATUS TAB -->
      <div id="overview" class="tab-content active">
        <div class="stats-grid">
          <div class="stat-card">
            <span class="stat-title">Service</span>
            <span class="stat-value" id="status-health"><span class="loader"></span></span>
          </div>
          <div class="stat-card">
            <span class="stat-title">Telegram</span>
            <span class="stat-value" id="status-auth"><span class="loader"></span></span>
          </div>
          <div class="stat-card">
            <span class="stat-title">Gemini Live</span>
            <span class="stat-value" id="status-model"><span class="loader"></span></span>
          </div>
          <div class="stat-card">
            <span class="stat-title">Active Calls</span>
            <span class="stat-value" id="status-active-calls">0</span>
          </div>
          <div class="stat-card">
            <span class="stat-title">Voice TTS</span>
            <span class="stat-value" id="status-tts"><span class="loader"></span></span>
          </div>
          <div class="stat-card">
            <span class="stat-title">Calendar</span>
            <span class="stat-value" id="status-calendar"><span class="loader"></span></span>
          </div>
        </div>

        <div class="panel">
          <h2>Recent Calls</h2>
          <p class="subtitle">Inbound and outbound call history.</p>
          <div class="table-wrapper">
            <table>
              <thead>
                <tr><th>Call ID</th><th>User</th><th>Mode</th><th>Status</th></tr>
              </thead>
              <tbody id="calls-body">
                <tr><td colspan="4" style="text-align:center; color: var(--muted);"><span class="loader"></span> Loading...</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="panel">
          <h2>Quick Outbound Call</h2>
          <p class="subtitle">Start a Gemini Live call to a Telegram user.</p>
          <div class="row">
            <input type="text" id="quick-target" placeholder="@username or user ID" style="flex:1; margin:0;" />
            <input type="text" id="quick-purpose" placeholder="Purpose (optional)" style="flex:1; margin:0;" />
            <button onclick="startQuickCall()">Call</button>
          </div>
        </div>

        <div class="panel">
          <h2>Live Debug Log</h2>
          <p class="subtitle">Real-time debug events from Gemini Live sessions. Auto-streams via WebSocket.</p>
          <div class="row" style="margin-bottom: 8px; gap: 6px;">
            <span id="ws-status" style="font-size: 0.78rem; color: var(--muted);"><span class="status-indicator status-warn"></span>Connecting...</span>
            <div style="flex:1;"></div>
            <input type="text" id="debug-filter" placeholder="Filter by call_id or stage..." style="width: 260px; margin: 0; font-size: 0.78rem; padding: 6px 10px;" />
            <button class="secondary" onclick="clearDebugLog()" style="font-size: 0.78rem; padding: 6px 10px;">Clear</button>
          </div>
          <div class="log-box" id="debug-log" style="max-height: 400px;">Waiting for events...</div>
        </div>
      </div>

      <!-- VOICE TAB -->
      <div id="voice" class="tab-content">
        <div class="panel">
          <h2>Voice Provider</h2>
          <p class="subtitle">Current TTS engine and configuration.</p>
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-title">Provider</span>
              <span class="stat-value" id="voice-provider"><span class="loader"></span></span>
            </div>
            <div class="stat-card">
              <span class="stat-title">Voice / Speaker</span>
              <span class="stat-value" id="voice-speaker"><span class="loader"></span></span>
            </div>
            <div class="stat-card">
              <span class="stat-title">Sample Rate</span>
              <span class="stat-value" id="voice-sample-rate">-</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <h2>Silero TTS — Russian Native Voices</h2>
          <p class="subtitle">Open-source, local inference. No API key needed. 5 Russian speakers with auto-stress and homograph resolution.</p>
          <div id="silero-voices-grid" style="display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); margin-top: 12px;">
            <div class="loader"></div>
          </div>
        </div>

        <div class="panel">
          <h2>Edge TTS — Microsoft Neural Voices</h2>
          <p class="subtitle">Cloud-based voices. Russian: ru-RU-DmitryNeural (male), ru-RU-SvetlanaNeural (female).</p>
          <div style="display: grid; gap: 12px; grid-template-columns: 1fr 1fr; margin-top: 12px;">
            <article class="card">
              <strong>DmitryNeural</strong>
              <p style="color: var(--muted); font-size: 0.82rem; margin: 4px 0 0;">Male · ru-RU · Cloud</p>
            </article>
            <article class="card">
              <strong>SvetlanaNeural</strong>
              <p style="color: var(--muted); font-size: 0.82rem; margin: 4px 0 0;">Female · ru-RU · Cloud</p>
            </article>
          </div>
        </div>
      </div>

      <!-- BOOKINGS TAB -->
      <div id="bookings" class="tab-content">
        <div class="panel">
          <h2>Booking Search</h2>
          <p class="subtitle">Search for restaurants, hotels, events, and travel options.</p>
          <div style="display: grid; gap: 12px; grid-template-columns: 1fr 1fr; margin-bottom: 14px;">
            <div>
              <label style="font-size: 0.78rem; color: var(--muted); display: block; margin-bottom: 4px;">Search Type</label>
              <select id="booking-type" style="width:100%; background: rgba(255,255,255,0.06); border: 1px solid var(--line); color: var(--ink); padding: 10px 12px; border-radius: 10px; font-family: Sora, sans-serif; font-size: 0.88rem;">
                <option value="find_restaurant">Restaurants</option>
                <option value="find_hotel">Hotels</option>
                <option value="find_event">Events</option>
                <option value="find_travel">Travel</option>
                <option value="plan_evening">Plan Evening</option>
              </select>
            </div>
            <div>
              <label style="font-size: 0.78rem; color: var(--muted); display: block; margin-bottom: 4px;">Location</label>
              <input id="booking-location" placeholder="e.g. London, Paris..." />
            </div>
          </div>
          <div style="margin-bottom: 14px;">
            <label style="font-size: 0.78rem; color: var(--muted); display: block; margin-bottom: 4px;">Additional Details (optional)</label>
            <input id="booking-extra" placeholder="e.g. Italian cuisine, budget-friendly, tonight..." />
          </div>
          <button onclick="runBookingSearch()">Search</button>
          <div id="booking-voice" style="margin-top: 14px; padding: 12px; border-radius: 10px; background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.2); display: none;">
            <span style="font-size: 0.78rem; color: var(--primary); text-transform: uppercase; font-weight: 700;">Voice Summary</span>
            <p id="booking-voice-text" style="margin: 6px 0 0; font-size: 0.92rem;"></p>
          </div>
        </div>

        <div class="panel" id="booking-results-panel" style="display: none;">
          <h2>Results</h2>
          <div id="booking-results-grid" class="cards"></div>
        </div>

        <div class="panel">
          <h2>Wake Word Actions</h2>
          <p class="subtitle">Voice trigger phrases that route to specific actions during calls.</p>
          <div id="wake-word-list" style="margin-top: 10px;"></div>
        </div>
      </div>

      <!-- API LAB TAB -->
      <div id="lab" class="tab-content">
        <section class="layout">
          <div>
            <h2 style="margin-bottom: 14px;">Endpoints</h2>
            <div class="cards">
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/health</code></div>
                <p class="hint">Service health and mode.</p>
                <button onclick="callGet('/api/v1/health')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/telegram/auth/status</code></div>
                <p class="hint">Telegram MTProto client status.</p>
                <button onclick="callGet('/api/v1/telegram/auth/status')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/telegram/auth/send-code</code></div>
                <p class="hint">Send login code to your Telegram.</p>
                <textarea id="payload-send-code">{
  "phone_number": "+441234567890"
}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/telegram/auth/send-code', 'payload-send-code')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/telegram/auth/sign-in</code></div>
                <p class="hint">Complete sign-in with code and password.</p>
                <textarea id="payload-signin">{
  "phone_number": "+441234567890",
  "code": "12345",
  "phone_code_hash": "from_send_code",
  "password": null
}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/telegram/auth/sign-in', 'payload-signin')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/calls/outbound</code></div>
                <p class="hint">Start outbound Telegram call with Gemini Live.</p>
                <textarea id="payload-outbound">{
  "target_user": "@username",
  "purpose": "reminder",
  "initial_audio_path": null,
  "metadata": {}
}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/calls/outbound', 'payload-outbound')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/chat</code></div>
                <p class="hint">Text chat via OpenAI.</p>
                <textarea id="payload-chat">{
  "message": "Hello, what can you do?"
}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/chat', 'payload-chat')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/calls/{call_id}/live/start</code></div>
                <p class="hint">Start Gemini Live agent on an active call.</p>
                <textarea id="payload-live-start">{
  "context": {"source": "dashboard"},
  "speak_response": true
}</textarea>
                <input type="text" id="live-call-id" placeholder="Call ID, e.g. tg-123456789" />
                <div class="row">
                  <button class="secondary" onclick="startTelegramLive()">Start</button>
                  <button class="secondary" onclick="stopTelegramLive()">Stop</button>
                  <button class="secondary" onclick="statusTelegramLive()">Status</button>
                </div>
              </article>
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/calls/events</code></div>
                <p class="hint">Call state events log.</p>
                <button onclick="callGet('/api/v1/calls/events?limit=50')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/calendar/cache</code></div>
                <p class="hint">Cached calendar events.</p>
                <button onclick="callGet('/api/v1/calendar/cache')">Run</button>
              </article>
            </div>
          </div>
          <div class="panel" style="align-self: start; position: sticky; top: 24px;">
            <h2>Response</h2>
            <div class="log-box" id="output">Ready. Run any endpoint.</div>
          </div>
        </section>
      </div>
    </div>

    <script>
      function switchTab(tabId, btn) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        if (btn) btn.classList.add('active');
      }

      function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
      function safeHref(u) { return /^https?:\/\//i.test(u) ? esc(u) : '#'; }

      async function fetchJson(path, init = {}, timeoutMs = 8000) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeoutMs);
        try {
          const res = await fetch(path, { ...init, signal: ctrl.signal, cache: "no-store" });
          const body = await res.json().catch(() => ({ raw: "Non-JSON response" }));
          return { ok: res.ok, status: res.status, body };
        } finally { clearTimeout(timer); }
      }

      function printResult(method, path, status, body) {
        const el = document.getElementById("output");
        const ok = status >= 200 && status < 300;
        el.textContent = `[${new Date().toISOString()}] ${method} ${path}\\nStatus: ${status} (${ok ? "OK" : "ERROR"})\\n\\n${JSON.stringify(body, null, 2)}`;
      }

      async function callGet(path) {
        try {
          const r = await fetchJson(path, { method: "GET" });
          printResult("GET", path, r.status, r.body);
        } catch (e) { document.getElementById("output").textContent = `Error: ${e}`; }
      }

      async function callPost(path, textareaId) {
        try {
          const payload = JSON.parse(document.getElementById(textareaId).value);
          const r = await fetchJson(path, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          printResult("POST", path, r.status, r.body);
        } catch (e) { document.getElementById("output").textContent = `Error: ${e}`; }
      }

      async function startTelegramLive() {
        const id = document.getElementById("live-call-id").value.trim();
        if (!id) return alert("Enter a call ID.");
        await callPost(`/api/v1/calls/${encodeURIComponent(id)}/live/start`, "payload-live-start");
      }

      async function stopTelegramLive() {
        const id = document.getElementById("live-call-id").value.trim();
        if (!id) return alert("Enter a call ID.");
        try {
          const r = await fetchJson(`/api/v1/calls/${encodeURIComponent(id)}/live/stop`, {
            method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
          });
          printResult("POST", `/api/v1/calls/${id}/live/stop`, r.status, r.body);
        } catch (e) { document.getElementById("output").textContent = `Error: ${e}`; }
      }

      async function statusTelegramLive() {
        const id = document.getElementById("live-call-id").value.trim();
        if (!id) return alert("Enter a call ID.");
        await callGet(`/api/v1/calls/${encodeURIComponent(id)}/live/status`);
      }

      async function startQuickCall() {
        const target = document.getElementById("quick-target").value.trim();
        const purpose = document.getElementById("quick-purpose").value.trim() || "call";
        if (!target) return alert("Enter a target user.");
        try {
          const r = await fetchJson("/api/v1/calls/outbound", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_user: target, purpose, metadata: {} }),
          });
          if (r.ok) alert("Call started: " + (r.body.call_id || "ok"));
          else alert("Error: " + JSON.stringify(r.body));
          refreshDashboard();
        } catch (e) { alert("Error: " + e); }
      }

      function connectCalendar() {
        window.open("/api/v1/calendar/oauth/authorize", "_blank");
      }

      async function refreshDashboard() {
        try {
          const [health, auth, calls, cal] = await Promise.all([
            fetchJson("/api/v1/health", { method: "GET" }, 5000),
            fetchJson("/api/v1/telegram/auth/status", { method: "GET" }, 5000),
            fetchJson("/api/v1/calls", { method: "GET" }, 5000),
            fetchJson("/api/v1/calendar/oauth/status", { method: "GET" }, 5000),
          ]);

          const hEl = document.getElementById("status-health");
          if (health.ok && health.body?.status === "ok") {
            hEl.innerHTML = '<span class="status-indicator status-ok"></span>Online';
          } else {
            hEl.innerHTML = '<span class="status-indicator status-err"></span>Offline';
          }
          updateGeminiStatus(health.body);
          updateCalendarStatus(cal.body);

          const aEl = document.getElementById("status-auth");
          const ab = auth.body || {};
          if (auth.ok && ab.authorized) {
            aEl.innerHTML = '<span class="status-indicator status-ok"></span>Authorized';
          } else if (auth.ok && ab.connected) {
            aEl.innerHTML = '<span class="status-indicator status-warn"></span>Connected';
          } else {
            aEl.innerHTML = '<span class="status-indicator status-err"></span>Offline';
          }

          const tbody = document.getElementById("calls-body");
          const callList = Array.isArray(calls.body) ? calls.body : [];
          let activeCount = 0;

          if (!calls.ok || callList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--muted); padding: 20px;">No calls yet.</td></tr>';
          } else {
            tbody.innerHTML = "";
            const recent = callList.slice().reverse();
            recent.forEach(c => {
              const st = (c.status || "unknown").toLowerCase();
              if (st === "active") activeCount++;
              let cls = "pill-ended";
              if (st === "active") cls = "pill-active";
              else if (st === "completed") cls = "pill-completed";
              const mode = c.live_agent?.running ? "Gemini Live" : (st === "active" ? "Waiting" : "-");
              const tr = document.createElement("tr");
              tr.innerHTML = `
                <td style="font-family: 'JetBrains Mono', monospace; color: var(--primary-2); font-size: 0.82rem;">${c.call_id || "-"}</td>
                <td>${c.target_user || c.source_user || "-"}</td>
                <td style="color: var(--muted); font-size: 0.85rem;">${mode}</td>
                <td><span class="pill ${cls}">${st}</span></td>
              `;
              tbody.appendChild(tr);
            });
          }
          document.getElementById("status-active-calls").textContent = String(activeCount);
        } catch (e) { console.error("Dashboard refresh failed", e); }
      }

      function updateGeminiStatus(healthBody) {
        const el = document.getElementById("status-model");
        const gl = healthBody?.gemini_live;
        if (gl?.enabled) {
          el.innerHTML = '<span class="status-indicator status-ok"></span>' + (gl.model || "Enabled");
        } else {
          el.innerHTML = '<span class="status-indicator status-warn"></span>Disabled';
        }
      }

      function updateCalendarStatus(calBody) {
        const el = document.getElementById("status-calendar");
        if (calBody?.connected) {
          el.innerHTML = '<span class="status-indicator status-ok"></span>Connected';
        } else {
          el.innerHTML = '<span class="status-indicator status-warn"></span>Not connected ' +
            '<button onclick="connectCalendar()" style="font-size:0.72rem;padding:4px 10px;margin-left:6px;">Connect</button>';
        }
      }

      // --- Booking Search ---
      async function runBookingSearch() {
        const type = document.getElementById("booking-type").value;
        const location = document.getElementById("booking-location").value.trim() || "London";
        const extra = document.getElementById("booking-extra").value.trim();
        const voiceBox = document.getElementById("booking-voice");
        const voiceText = document.getElementById("booking-voice-text");
        const resultsPanel = document.getElementById("booking-results-panel");
        const resultsGrid = document.getElementById("booking-results-grid");

        voiceBox.style.display = "none";
        resultsPanel.style.display = "none";
        resultsGrid.innerHTML = '<div class="loader"></div> Searching...';
        resultsPanel.style.display = "block";

        try {
          const r = await fetchJson("/api/v1/booking/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              call_id: "dashboard-" + Date.now(),
              booking_type: type,
              location: location,
              query_params: extra ? { preferences: extra } : {},
            }),
          }, 20000);

          if (r.ok && r.body) {
            if (r.body.voice_summary) {
              voiceText.textContent = r.body.voice_summary;
              voiceBox.style.display = "block";
            }
            const results = r.body.results || [];
            if (results.length === 0) {
              resultsGrid.innerHTML = '<p style="color: var(--muted);">No results found.</p>';
            } else {
              resultsGrid.innerHTML = results.map(r => {
                const title = esc(r.title || "Untitled");
                const url = safeHref(r.url || "");
                const content = esc((r.content || "").slice(0, 200));
                const score = r.score ? `<span class="pill pill-active">${(r.score * 100).toFixed(0)}%</span>` : "";
                return `<article class="card">
                  <div class="row"><strong>${title}</strong> ${score}</div>
                  <p style="color: var(--muted); font-size: 0.82rem; margin: 0 0 8px;">${content}${content.length >= 200 ? "..." : ""}</p>
                  <a href="${url}" target="_blank" style="color: var(--primary); font-size: 0.82rem; text-decoration: none;">${url}</a>
                </article>`;
              }).join("");
            }
          } else {
            resultsGrid.innerHTML = `<p style="color: var(--err);">Error: ${JSON.stringify(r.body)}</p>`;
          }
        } catch (e) {
          resultsGrid.innerHTML = `<p style="color: var(--err);">Request failed: ${e}</p>`;
        }
      }

      // --- Wake Word Actions ---
      async function loadWakeWordActions() {
        try {
          const r = await fetchJson("/api/v1/wake-word/actions", { method: "GET" }, 5000);
          const container = document.getElementById("wake-word-list");
          if (r.ok && Array.isArray(r.body) && r.body.length > 0) {
            container.innerHTML = r.body.map(a => {
              const phrases = (a.phrases || []).map(p => `<span class="pill pill-completed" style="margin: 2px;">${esc(p)}</span>`).join(" ");
              return `<div style="margin-bottom: 12px; padding: 12px; border: 1px solid var(--line); border-radius: 10px;">
                <div style="font-weight: 600; margin-bottom: 6px;">
                  <span class="pill pill-active">${esc(a.action)}</span>
                  <span style="color: var(--muted); font-size: 0.82rem; margin-left: 8px;">${esc(a.description || "")}</span>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 4px;">${phrases}</div>
              </div>`;
            }).join("");
          } else {
            container.innerHTML = '<p style="color: var(--muted);">No wake-word actions configured.</p>';
          }
        } catch (e) {
          document.getElementById("wake-word-list").innerHTML = `<p style="color: var(--err);">Failed to load: ${e}</p>`;
        }
      }

      // --- Voice Provider ---
      async function loadVoiceConfig() {
        try {
          const r = await fetchJson("/api/v1/voice/providers", { method: "GET" }, 5000);
          if (!r.ok) return;
          const d = r.body;

          // Status card
          const ttsEl = document.getElementById("status-tts");
          const provider = d.current_provider || "unknown";
          if (provider === "silero") {
            ttsEl.innerHTML = '<span class="status-indicator status-ok"></span>Silero';
          } else if (provider === "edge_tts") {
            ttsEl.innerHTML = '<span class="status-indicator status-ok"></span>Edge TTS';
          } else {
            ttsEl.innerHTML = '<span class="status-indicator status-warn"></span>' + esc(provider);
          }

          // Voice tab details
          document.getElementById("voice-provider").textContent = provider === "silero" ? "Silero (Russian Native)" : provider === "edge_tts" ? "Edge TTS (Microsoft)" : provider;
          if (provider === "silero" && d.silero) {
            document.getElementById("voice-speaker").textContent = d.silero.speaker || "-";
            document.getElementById("voice-sample-rate").textContent = (d.silero.sample_rate || "-") + " Hz";
          } else if (d.edge_tts) {
            document.getElementById("voice-speaker").textContent = d.edge_tts.voice || "-";
            document.getElementById("voice-sample-rate").textContent = "-";
          }

          // Silero voices grid
          const sileroGrid = document.getElementById("silero-voices-grid");
          const ruVoices = d.silero?.available_voices?.ru || [];
          if (ruVoices.length > 0) {
            const activeSpeaker = d.silero?.speaker || "";
            sileroGrid.innerHTML = ruVoices.map(v => {
              const isActive = v.id === activeSpeaker;
              const border = isActive ? "border-color: var(--primary);" : "";
              const badge = isActive ? '<span class="pill pill-active" style="font-size: 0.7rem;">Active</span>' : "";
              return `<article class="card" style="${border}">
                <div class="row"><strong>${esc(v.name)}</strong> ${badge}</div>
                <p style="color: var(--muted); font-size: 0.82rem; margin: 4px 0 0;">${esc(v.gender)} · Local · No API key</p>
              </article>`;
            }).join("");
          } else {
            sileroGrid.innerHTML = '<p style="color: var(--muted);">Install silero + torch to enable Russian native voices.</p>';
          }
        } catch (e) {
          console.error("Failed to load voice config", e);
        }
      }

      const MAX_LOG_LINES = 200;
      let debugLogLines = [];

      function clearDebugLog() {
        debugLogLines = [];
        document.getElementById("debug-log").textContent = "Cleared.";
      }

      function renderDebugLog() {
        const el = document.getElementById("debug-log");
        const filter = (document.getElementById("debug-filter")?.value || "").toLowerCase().trim();
        const filtered = filter
          ? debugLogLines.filter(l => l.toLowerCase().includes(filter))
          : debugLogLines;
        el.textContent = filtered.length ? filtered.join("\\n") : "No matching events.";
        el.scrollTop = el.scrollHeight;
      }

      function addDebugEntry(entry) {
        const ts = (entry.ts || "").substring(11, 19);
        const line = `[${ts}] ${entry.call_id || "-"} | ${entry.stage || "?"} | ${JSON.stringify(entry.data || {})}`;
        debugLogLines.push(line);
        if (debugLogLines.length > MAX_LOG_LINES) debugLogLines.shift();
        renderDebugLog();
      }

      async function loadInitialDebugLog() {
        try {
          const r = await fetchJson("/api/v1/debug/logs?lines=50", { method: "GET" }, 5000);
          if (r.ok && Array.isArray(r.body)) {
            r.body.forEach(entry => addDebugEntry(entry));
          }
        } catch (e) {
          document.getElementById("debug-log").textContent = "Failed to load initial log.";
        }
      }

      function connectDebugWs() {
        const wsEl = document.getElementById("ws-status");
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${proto}//${location.host}/api/v1/debug/ws`);
        ws.onopen = () => {
          wsEl.innerHTML = '<span class="status-indicator status-ok"></span>Live';
        };
        ws.onmessage = (evt) => {
          try { addDebugEntry(JSON.parse(evt.data)); } catch (e) {}
        };
        ws.onclose = () => {
          wsEl.innerHTML = '<span class="status-indicator status-err"></span>Disconnected';
          setTimeout(connectDebugWs, 3000);
        };
        ws.onerror = () => ws.close();
      }

      document.getElementById("debug-filter")?.addEventListener("input", renderDebugLog);

      refreshDashboard();
      loadInitialDebugLog();
      connectDebugWs();
      loadWakeWordActions();
      loadVoiceConfig();
      setInterval(refreshDashboard, 5000);
    </script>
  </body>
</html>
"""

@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(
        url="/dashboard",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(
        content=DASHBOARD_HTML,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
