from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Secretary AI Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
      :root {
        --bg: #f6f2e9;
        --panel: rgba(255, 255, 255, 0.88);
        --panel-solid: #ffffff;
        --ink: #1f2a23;
        --muted: #617068;
        --line: #d7cec0;
        --primary: #0f766e;
        --primary-2: #14b8a6;
        --accent: #c2410c;
        --accent-soft: #fed7aa;
        --ok: #15803d;
        --warn: #b45309;
        --err: #b91c1c;
        --console-bg: #101418;
        --console-ink: #c4f5ea;
        --shadow: 0 18px 48px -22px rgba(37, 56, 48, 0.35);
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Sora", sans-serif;
        color: var(--ink);
        background: var(--bg);
        background-image:
          radial-gradient(1000px 500px at 12% -10%, rgba(20, 184, 166, 0.18), transparent 60%),
          radial-gradient(900px 500px at 92% 8%, rgba(194, 65, 12, 0.18), transparent 60%),
          linear-gradient(180deg, #f8f4ec 0%, #f3efe6 100%);
        min-height: 100vh;
      }

      .header-area {
        max-width: 1320px;
        margin: 0 auto;
        padding: 34px 24px 20px;
        text-align: center;
      }
      .header-area h1 {
        margin: 0 0 10px;
        font-size: clamp(1.9rem, 2.8vw, 3rem);
        letter-spacing: -0.03em;
        font-weight: 800;
        background: linear-gradient(105deg, #0f766e, #115e59 45%, #1f2937 95%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
      }
      .hero-subtitle {
        margin: 0;
        color: #365147;
        font-size: 0.98rem;
      }
      .hero-meta {
        margin-top: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        flex-wrap: wrap;
      }
      .meta-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border: 1px solid #bfd8cc;
        background: rgba(255, 255, 255, 0.76);
        padding: 7px 10px;
        border-radius: 999px;
        font-size: 0.76rem;
        color: #365147;
        font-weight: 600;
      }
      .meta-chip .dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--primary-2);
        box-shadow: 0 0 10px rgba(20, 184, 166, 0.45);
      }

      .nav-container {
        margin: 0 24px 24px;
        padding: 8px;
        border: 1px solid var(--line);
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.72);
        backdrop-filter: blur(10px);
      }
      .nav-tabs {
        display: flex;
        gap: 8px;
        max-width: 1320px;
        margin: 0 auto;
      }
      .tab-btn {
        flex: 1;
        background: transparent;
        border: 1px solid transparent;
        color: var(--muted);
        font-family: "Sora", sans-serif;
        font-size: 0.96rem;
        font-weight: 600;
        padding: 12px 16px;
        cursor: pointer;
        transition: all 0.18s ease;
        border-radius: 999px;
        outline: none;
      }
      .tab-btn:hover { color: var(--ink); border-color: #d6e6de; }
      .tab-btn.active {
        color: #fff;
        border-color: transparent;
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        box-shadow: 0 8px 20px -10px rgba(15, 118, 110, 0.8);
      }

      .tab-content { display: none; }
      .tab-content.active { display: block; animation: fadeIn 0.35s ease-out; }
      @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

      .wrap { max-width: 1320px; margin: 0 auto; padding: 0 18px 36px; }

      .panel {
        background: var(--panel);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 18px;
        border: 1px solid var(--line);
        box-shadow: var(--shadow);
        padding: 22px;
        margin-bottom: 24px;
      }
      h2 { margin: 0 0 12px; font-weight: 700; font-size: 1.2rem; letter-spacing: -0.01em; }
      .subtitle { margin: 0 0 16px; color: var(--muted); font-size: 0.9rem; line-height: 1.45; }

      .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
      .stat-card {
        background: linear-gradient(165deg, rgba(255,255,255,0.9), rgba(242, 246, 243, 0.85));
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 16px;
        display: flex;
        flex-direction: column;
        gap: 8px;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
      }
      .stat-card:hover { transform: translateY(-2px); box-shadow: 0 12px 30px -20px rgba(24,44,37,0.45); }
      .stat-title { font-size: 0.79rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; font-weight: 600; }
      .stat-value { font-size: 1.25rem; font-weight: 700; color: #24382f; }
      .status-indicator { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; }
      .status-ok { background: var(--ok); box-shadow: 0 0 10px rgba(21, 128, 61, 0.6); }
      .status-warn { background: var(--warn); box-shadow: 0 0 10px rgba(180, 83, 9, 0.6); }
      .status-err { background: var(--err); box-shadow: 0 0 10px rgba(185, 28, 28, 0.6); }

      .table-wrapper { overflow-x: auto; }
      table { width: 100%; border-collapse: collapse; margin-top: 8px; }
      th { text-align: left; padding: 12px 14px; font-weight: 600; color: var(--muted); border-bottom: 1px solid var(--line); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
      td { padding: 13px 14px; border-bottom: 1px solid #ebe4d9; font-size: 0.93rem; }
      tr:last-child td { border-bottom: none; }
      tr:hover td { background: rgba(255,255,255,0.55); }
      .pill { padding: 4px 10px; border-radius: 999px; font-size: 0.71rem; font-weight: 700; text-transform: uppercase; display: inline-block; letter-spacing: 0.04em; }
      .pill-completed { background: rgba(21, 128, 61, 0.13); color: #166534; border: 1px solid rgba(21, 128, 61, 0.24); }
      .pill-routing { background: rgba(180, 83, 9, 0.13); color: #9a3412; border: 1px solid rgba(180, 83, 9, 0.23); }
      .pill-received { background: rgba(13, 148, 136, 0.13); color: #0f766e; border: 1px solid rgba(13, 148, 136, 0.24); }

      input, textarea {
        width: 100%;
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid var(--line);
        color: #1f2a23;
        padding: 12px 13px;
        border-radius: 11px;
        font-family: "Sora", sans-serif;
        margin-bottom: 12px;
        outline: none;
        transition: border-color 0.2s, box-shadow 0.2s;
        font-size: 0.92rem;
      }
      textarea {
        min-height: 95px;
        resize: vertical;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.83rem;
      }
      input:focus, textarea:focus {
        border-color: var(--primary);
        box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.15);
      }
      button {
        background: linear-gradient(135deg, var(--primary), var(--primary-2));
        border: 0;
        color: #fff;
        font-weight: 700;
        padding: 10px 16px;
        border-radius: 10px;
        cursor: pointer;
        transition: opacity 0.2s, transform 0.1s, box-shadow 0.2s;
        font-family: "Sora", sans-serif;
        font-size: 0.86rem;
        letter-spacing: 0.01em;
      }
      button:hover { opacity: 0.95; box-shadow: 0 12px 24px -14px rgba(15, 118, 110, 0.7); }
      button:active { transform: scale(0.98); }
      button.secondary { background: linear-gradient(135deg, #c2410c, #ea580c); }

      .layout { display: grid; gap: 24px; grid-template-columns: 1.2fr 0.8fr; }
      @media (max-width: 980px) { .layout { grid-template-columns: 1fr; } }
      .cards { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
      .card {
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 16px;
        background: linear-gradient(165deg, rgba(255,255,255,0.94), rgba(246,241,232,0.8));
        transition: transform 0.15s ease, box-shadow 0.15s ease;
      }
      .card:hover { transform: translateY(-2px); box-shadow: 0 14px 28px -22px rgba(24, 44, 37, 0.65); }
      .row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
      .method {
        font-size: 0.72rem;
        text-transform: uppercase;
        font-weight: 700;
        background: #0f766e;
        color: #fff;
        padding: 4px 10px;
        border-radius: 999px;
        letter-spacing: 0.06em;
      }
      .method.post { background: #c2410c; }
      code.path {
        background: #f2eee5;
        border: 1px solid #dfd7c8;
        color: #3e5048;
        border-radius: 8px;
        padding: 4px 8px;
        font-family: "JetBrains Mono", monospace;
        font-size: 0.8rem;
      }
      .hint { margin: 0 0 12px; color: var(--muted); font-size: 0.84rem; line-height: 1.45; }
      .output {
        min-height: 500px;
        padding: 16px;
        border-radius: 12px;
        background: var(--console-bg);
        color: var(--console-ink);
        font-family: "JetBrains Mono", monospace;
        font-size: 0.82rem;
        line-height: 1.4;
        white-space: pre-wrap;
        overflow-y: auto;
        border: 1px solid #203028;
      }

      .d-flex { display: flex; gap: 24px; }
      .flex-1 { flex: 1; min-width: 300px; }


      .loader {
        border: 2px solid rgba(15,118,110,0.2);
        border-top-color: var(--primary);
        border-radius: 50%;
        width: 16px;
        height: 16px;
        animation: spin 0.8s linear infinite;
        display: inline-block;
        vertical-align: middle;
        margin-right: 8px;
      }
      @keyframes spin { to { transform: rotate(360deg); } }

      .panel.right { border-style: dashed; }

      @media (max-width: 860px) {
        .header-area { padding-top: 26px; }
        .nav-container { margin: 0 14px 18px; }
        .d-flex { gap: 16px; }
        .panel { padding: 16px; }
      }
    </style>
  </head>
  <body>
    <!-- Header -->
    <div class="header-area">
      <h1>Secretary AI Control Center</h1>
      <p class="hero-subtitle">Telegram voice automation with live orchestration, diagnostics, and control.</p>
      <div class="hero-meta">
        <span class="meta-chip"><span class="dot"></span>Realtime Call Ops</span>
        <span class="meta-chip"><span class="dot"></span>Z.AI Reasoning</span>
        <span class="meta-chip"><span class="dot"></span>Hackathon Fast Mode</span>
      </div>
    </div>

    <!-- Top Nav -->
    <div class="nav-container">
      <div class="nav-tabs">
        <button class="tab-btn active" onclick="switchTab('overview', this)">Overview</button>
        <button class="tab-btn" onclick="switchTab('lab', this)">API Lab & Debug</button>
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
            <div style="margin-top: 14px; border: 1px solid var(--line); background: rgba(255,255,255,0.72); border-radius: 12px; padding: 12px;">
              <h3 style="margin: 0 0 8px; font-size: 0.9rem;">Voice Dialogue (No Call ID)</h3>
              <p style="margin: 0 0 10px; color: var(--muted); font-size: 0.84rem; line-height: 1.45;">
                Click Start, speak naturally, and the AI will answer with voice. No call setup needed.
              </p>
              <div class="row">
                <button onclick="voiceStartDialog()">Start Voice Dialogue</button>
                <button class="secondary" onclick="voiceStopDialog()">Stop</button>
                <button onclick="voiceClearDialog()">Clear</button>
              </div>
              <div id="voice-dialog-state" style="margin: 4px 0 8px; color: var(--muted); font-size: 0.84rem;">Idle</div>
              <div id="voice-dialog-log" style="max-height: 180px; overflow-y: auto; border: 1px solid var(--line); border-radius: 10px; padding: 10px; font-size: 0.84rem; line-height: 1.45; background: rgba(255,255,255,0.86); color: #26463d;">No conversation yet.</div>
            </div>
            <div style="margin-top: 14px; border: 1px solid var(--line); background: rgba(255,255,255,0.7); border-radius: 12px; padding: 12px;">
              <h3 style="margin: 0 0 8px; font-size: 0.9rem;">Voice Quickstart</h3>
              <ol style="margin: 0; padding-left: 18px; color: var(--muted); font-size: 0.84rem; line-height: 1.5;">
                <li>Open <b>API Lab & Debug</b> and run auth endpoints if Telegram is not authorized.</li>
                <li>Run <code>/api/v1/calls/outbound</code> or use <b>Trigger Outbound Call</b> to get a <code>call_id</code>.</li>
                <li>Use <code>/api/v1/ws/live/{call_id}</code> for manual transcript + live mic streaming, or use <code>/api/v1/calls/{call_id}/live/start</code> for full Telegram-native voice loop.</li>
                <li>Watch the Response Console and Call Audit Log to verify events and status.</li>
              </ol>
            </div>
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
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/agent/analyze</code></div>
                <p class="hint">Structured AI analysis: intent, confidence, handoff and action plan.</p>
                <textarea id="payload-analyze">{\n  "call_id": "tg-123456789",\n  "transcript": "Please move my appointment to next Tuesday at 3 PM.",\n  "context": {"customer_name":"Alex"}\n}</textarea>
                <button class="secondary" onclick="callPost('/api/v1/agent/analyze', 'payload-analyze')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/agent/live/respond</code></div>
                <p class="hint">Near realtime talk loop: transcript -> AI reply -> TTS -> push audio into active call.</p>
                <textarea id="payload-live">{\n  "call_id": "tg-123456789",\n  "transcript": "Hello, can we move my meeting to next Tuesday at 3 PM?",\n  "context": {"source":"dashboard"},\n  "speak_response": true\n}</textarea>
                <div class="row">
                  <button class="secondary" onclick="callPost('/api/v1/agent/live/respond', 'payload-live')">Run</button>
                  <button onclick="dictateIntoPayload('payload-live')">Dictate Transcript</button>
                </div>
              </article>
              <article class="card">
                <div class="row"><span class="method">GET</span><code class="path">/api/v1/calls/events</code></div>
                <p class="hint">Inspect inbound/outbound call state events.</p>
                <button onclick="callGet('/api/v1/calls/events?limit=100')">Run</button>
              </article>
              <article class="card">
                <div class="row"><span class="method">WS</span><code class="path">/api/v1/ws/live/{call_id}</code></div>
                <p class="hint">Realtime channel: send transcript chunks and receive instant AI + TTS call events.</p>
                <input type="text" id="ws-call-id" placeholder="Call ID, e.g. tg-123456789" />
                <textarea id="ws-transcript">Hello, can you please move my appointment to Tuesday at 3 PM?</textarea>
                <div class="row" style="justify-content: space-between;">
                  <label style="color: var(--muted); font-size: 0.85rem;">
                    <input type="checkbox" id="ws-speak-response" checked style="width: auto; margin: 0 6px 0 0;" />
                    Speak response into active call
                  </label>
                  <span id="ws-voice-state" style="color: var(--muted); font-size: 0.85rem;">Mic idle</span>
                </div>
                <div class="row">
                  <button onclick="wsConnect()">Connect</button>
                  <button class="secondary" onclick="wsSendTranscript()">Send Transcript</button>
                  <button onclick="wsStartLiveMic()">Start Live Mic</button>
                  <button onclick="wsStopLiveMic()">Stop Live Mic</button>
                  <button onclick="wsDisconnect()">Disconnect</button>
                </div>
              </article>
              <article class="card">
                <div class="row"><span class="method post">POST</span><code class="path">/api/v1/calls/{call_id}/live/start</code></div>
                <p class="hint">Telegram-native mode: call recording -> STT -> AI reply -> TTS into the same call.</p>
                <textarea id="payload-live-start">{\n  "context": {"source":"dashboard_live_telegram"},\n  "speak_response": true\n}</textarea>
                <div class="row">
                  <input type="text" id="live-call-id" placeholder="Call ID, e.g. tg-123456789" />
                </div>
                <div class="row">
                  <button class="secondary" onclick="startTelegramLive()">Start</button>
                  <button onclick="stopTelegramLive()">Stop</button>
                  <button onclick="statusTelegramLive()">Status</button>
                </div>
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
      function switchTab(tabId, buttonEl) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        if (buttonEl) buttonEl.classList.add('active');
      }


      // API Call Helpers for Lab
      let liveSocket = null;
      let wsRecognition = null;
      let wsVoiceEnabled = false;
      let wsSpeechSeq = 0;
      let voiceRecognition = null;
      let voiceDialogueOn = false;
      let voiceHistory = [];
      let voiceSpeaking = false;
      let voiceTurnInFlight = false;
      let voiceDialogSessionId = 0;
      let voiceBrowserChoice = null;

      async function fetchJson(path, init = {}, timeoutMs = 8000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
          const requestInit = {
            ...init,
            signal: controller.signal,
            cache: "no-store",
          };
          const res = await fetch(path, requestInit);
          const body = await res.json().catch(() => ({ raw: "Non-JSON response" }));
          return { ok: res.ok, status: res.status, body };
        } finally {
          clearTimeout(timer);
        }
      }

      function appendOutputLine(text) {
        const output = document.getElementById("output");
        output.textContent += `\\n\\n${text}`;
        output.scrollTop = output.scrollHeight;
      }

      function wsSupportsSpeechRecognition() {
        return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
      }

      function wsSetVoiceState(text, active = false) {
        const state = document.getElementById("ws-voice-state");
        if (!state) return;
        state.textContent = text;
        state.style.color = active ? "#34d399" : "var(--muted)";
      }

      function voiceSupportsDialog() {
        return Boolean((window.SpeechRecognition || window.webkitSpeechRecognition) && window.speechSynthesis);
      }

      function voiceSetDialogState(text, active = false) {
        const state = document.getElementById("voice-dialog-state");
        if (!state) return;
        state.textContent = text;
        state.style.color = active ? "#0f766e" : "var(--muted)";
      }

      function voiceAppendLog(role, text) {
        const log = document.getElementById("voice-dialog-log");
        if (!log) return;
        const stamp = new Date().toLocaleTimeString();
        if (log.textContent.includes("No conversation yet.")) {
          log.textContent = "";
        }
        const line = document.createElement("div");
        line.style.marginBottom = "8px";
        line.innerHTML = `<b>${stamp} ${role}:</b> ${text.replace(/</g, "&lt;").replace(/>/g, "&gt;")}`;
        log.appendChild(line);
        log.scrollTop = log.scrollHeight;
      }

      function voiceWaitForVoices(timeoutMs = 900) {
        return new Promise((resolve) => {
          if (!window.speechSynthesis) {
            resolve([]);
            return;
          }
          const initial = window.speechSynthesis.getVoices() || [];
          if (initial.length > 0) {
            resolve(initial);
            return;
          }
          const onChanged = () => {
            window.speechSynthesis.removeEventListener("voiceschanged", onChanged);
            resolve(window.speechSynthesis.getVoices() || []);
          };
          window.speechSynthesis.addEventListener("voiceschanged", onChanged);
          setTimeout(() => {
            window.speechSynthesis.removeEventListener("voiceschanged", onChanged);
            resolve(window.speechSynthesis.getVoices() || []);
          }, timeoutMs);
        });
      }

      function voicePickBrowserVoice(voices) {
        if (!Array.isArray(voices) || voices.length === 0) return null;
        const byName = (re) => voices.find(v => re.test(v.name || ""));
        const byLang = (re) => voices.find(v => re.test(v.lang || ""));
        const isMale = (name) => /ryan|guy|davis|daniel|thomas|steffan|david|mark|male/i.test(name || "");
        const firstNonMale = (re) => voices.find(v => re.test(v.lang || "") && !isMale(v.name || ""));

        return (
          byName(/joanna|jenny|sonia|aria|libby|sara|emma|olivia|zira|hazel|samantha|victoria|ava|alloy/i) ||
          firstNonMale(/^en-GB/i) ||
          firstNonMale(/^en-US/i) ||
          byLang(/^en-GB/i) ||
          byLang(/^en-US/i) ||
          voices[0]
        );
      }

      async function voiceSpeak(text) {
        if (!window.speechSynthesis) return;
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "en-GB";
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        try {
          if (!voiceBrowserChoice) {
            const voices = await voiceWaitForVoices();
            voiceBrowserChoice = voicePickBrowserVoice(voices);
          }
          if (voiceBrowserChoice) utterance.voice = voiceBrowserChoice;
        } catch (_) {}

        await new Promise((resolve) => {
          utterance.onend = () => resolve();
          utterance.onerror = () => resolve();
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utterance);
        });
      }

      async function voiceHandleTurn(userText) {
        if (!userText) return;
        if (voiceTurnInFlight) return;
        const sessionIdAtStart = voiceDialogSessionId;
        voiceTurnInFlight = true;
        voiceAppendLog("You", userText);
        voiceSetDialogState("Thinking...", true);
        try {
          const res = await fetch("/api/v1/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: userText, history: voiceHistory }),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            const detail = data.detail || `Server error ${res.status}`;
            if (!voiceDialogueOn || sessionIdAtStart !== voiceDialogSessionId) return;
            voiceAppendLog("AI", String(detail));
            voiceSetDialogState("Error from chat endpoint", false);
            return;
          }

          if (!voiceDialogueOn || sessionIdAtStart !== voiceDialogSessionId) return;
          const reply = data.reply || "(no reply)";
          voiceHistory = Array.isArray(data.history) ? data.history : voiceHistory;
          voiceAppendLog("AI", reply);

          voiceSpeaking = true;
          voiceSetDialogState("AI speaking...", true);
          if (voiceRecognition) {
            try { voiceRecognition.stop(); } catch (_) {}
          }
          await voiceSpeak(reply);
          voiceSpeaking = false;
          if (voiceDialogueOn && sessionIdAtStart === voiceDialogSessionId && voiceRecognition) {
            try {
              voiceRecognition.start();
              voiceSetDialogState("Listening...", true);
            } catch (_) {
              voiceSetDialogState("Listening restart delayed...", false);
            }
          } else {
            voiceSetDialogState("Idle", false);
          }
        } catch (err) {
          voiceSpeaking = false;
          if (!voiceDialogueOn || sessionIdAtStart !== voiceDialogSessionId) return;
          voiceAppendLog("AI", `Network error: ${String(err)}`);
          voiceSetDialogState("Network error", false);
        } finally {
          voiceTurnInFlight = false;
        }
      }

      async function voiceStartDialog() {
        if (voiceDialogueOn) {
          voiceSetDialogState("Already running", true);
          return;
        }
        if (!voiceSupportsDialog()) {
          alert("This browser does not support full voice dialogue. Try Chrome/Edge.");
          return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        voiceRecognition = new SpeechRecognition();
        voiceRecognition.lang = "en-GB";
        voiceRecognition.continuous = true;
        voiceRecognition.interimResults = false;
        voiceRecognition.maxAlternatives = 1;

        voiceDialogueOn = true;
        try {
          const voices = await voiceWaitForVoices();
          voiceBrowserChoice = voicePickBrowserVoice(voices);
        } catch (_) {}
        const chosen = voiceBrowserChoice ? ` (${voiceBrowserChoice.name})` : "";
        voiceSetDialogState(`Listening${chosen}...`, true);
        voiceAppendLog("System", "Voice dialogue started.");

        voiceRecognition.onresult = (event) => {
          if (!voiceDialogueOn || voiceSpeaking || voiceTurnInFlight) return;
          let latestFinal = "";
          for (let i = event.resultIndex; i < event.results.length; i += 1) {
            const result = event.results[i];
            if (!result.isFinal) continue;
            const text = (result[0]?.transcript || "").trim();
            if (text) latestFinal = text;
          }
          if (latestFinal) {
            voiceHandleTurn(latestFinal);
          }
        };

        voiceRecognition.onerror = (event) => {
          voiceSetDialogState(`Mic error: ${event.error}`, false);
        };

        voiceRecognition.onend = () => {
          if (!voiceDialogueOn || voiceSpeaking) return;
          try {
            voiceRecognition.start();
            voiceSetDialogState("Listening...", true);
          } catch (_) {
            voiceSetDialogState("Mic restart delayed...", false);
          }
        };

        voiceRecognition.start();
      }

      function voiceStopDialog() {
        voiceDialogueOn = false;
        voiceDialogSessionId += 1;
        voiceSpeaking = false;
        voiceTurnInFlight = false;
        if (voiceRecognition) {
          try { voiceRecognition.stop(); } catch (_) {}
          voiceRecognition = null;
        }
        if (window.speechSynthesis) {
          window.speechSynthesis.cancel();
        }
        voiceSetDialogState("Stopped", false);
        voiceAppendLog("System", "Voice dialogue stopped.");
      }

      function voiceClearDialog() {
        voiceHistory = [];
        const log = document.getElementById("voice-dialog-log");
        if (log) log.textContent = "No conversation yet.";
        voiceSetDialogState(voiceDialogueOn ? "Listening..." : "Idle", voiceDialogueOn);
      }

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
          const result = await fetchJson(path, { method: "GET" });
          printResult("GET", path, result.status, result.body);
        } catch (err) { printClientError("GET", path, err); }
      }
      async function callPost(path, textareaId) {
        try {
          const payload = JSON.parse(document.getElementById(textareaId).value);
          const result = await fetchJson(path, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          printResult("POST", path, result.status, result.body);
        } catch (err) { printClientError("POST", path, err); }
      }

      async function startTelegramLive() {
        const callId = document.getElementById("live-call-id").value.trim();
        if (!callId) { alert("Enter call_id first."); return; }
        await callPost(`/api/v1/calls/${encodeURIComponent(callId)}/live/start`, "payload-live-start");
      }

      async function stopTelegramLive() {
        const callId = document.getElementById("live-call-id").value.trim();
        if (!callId) { alert("Enter call_id first."); return; }
        try {
          const result = await fetchJson(`/api/v1/calls/${encodeURIComponent(callId)}/live/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          printResult("POST", `/api/v1/calls/${callId}/live/stop`, result.status, result.body);
        } catch (err) { printClientError("POST", `/api/v1/calls/${callId}/live/stop`, err); }
      }

      async function statusTelegramLive() {
        const callId = document.getElementById("live-call-id").value.trim();
        if (!callId) { alert("Enter call_id first."); return; }
        await callGet(`/api/v1/calls/${encodeURIComponent(callId)}/live/status`);
      }

      function wsEndpoint(callId) {
        const scheme = location.protocol === "https:" ? "wss" : "ws";
        return `${scheme}://${location.host}/api/v1/ws/live/${encodeURIComponent(callId)}`;
      }

      function wsConnect() {
        const callId = document.getElementById("ws-call-id").value.trim();
        if (!callId) {
          alert("Provide a call_id first.");
          return;
        }
        if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
          appendOutputLine(`[${new Date().toISOString()}] WS already connected for ${callId}`);
          return;
        }

        liveSocket = new WebSocket(wsEndpoint(callId));
        liveSocket.onopen = () => {
          appendOutputLine(`[${new Date().toISOString()}] WS connected: ${callId}`);
        };
        liveSocket.onmessage = (event) => {
          appendOutputLine(`[${new Date().toISOString()}] WS message\\n${event.data}`);
        };
        liveSocket.onerror = () => {
          appendOutputLine(`[${new Date().toISOString()}] WS error`);
        };
        liveSocket.onclose = () => {
          wsStopLiveMic();
          appendOutputLine(`[${new Date().toISOString()}] WS disconnected`);
          liveSocket = null;
        };
      }

      function wsSendTranscript() {
        if (!liveSocket || liveSocket.readyState !== WebSocket.OPEN) {
          alert("Connect the websocket first.");
          return;
        }
        const transcript = document.getElementById("ws-transcript").value.trim();
        if (!transcript) {
          alert("Transcript is empty.");
          return;
        }
        wsSendTranscriptChunk(transcript);
      }

      function wsSendTranscriptChunk(transcript) {
        if (!liveSocket || liveSocket.readyState !== WebSocket.OPEN) {
          appendOutputLine(`[${new Date().toISOString()}] WS not connected; transcript skipped`);
          return;
        }
        const speakResponse = document.getElementById("ws-speak-response")?.checked !== false;
        const payload = {
          type: "transcript",
          transcript,
          context: { source: "dashboard_ws", seq: wsSpeechSeq++ },
          speak_response: speakResponse
        };
        liveSocket.send(JSON.stringify(payload));
        appendOutputLine(`[${new Date().toISOString()}] WS transcript sent\\n${transcript}`);
      }

      function wsStartLiveMic() {
        if (!liveSocket || liveSocket.readyState !== WebSocket.OPEN) {
          alert("Connect the websocket first.");
          return;
        }
        if (!wsSupportsSpeechRecognition()) {
          alert("Speech recognition is not supported in this browser.");
          return;
        }
        if (wsVoiceEnabled) {
          appendOutputLine(`[${new Date().toISOString()}] Live mic already running`);
          return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        wsRecognition = new SpeechRecognition();
        wsRecognition.lang = "en-GB";
        wsRecognition.continuous = true;
        wsRecognition.interimResults = true;
        wsRecognition.maxAlternatives = 1;

        wsVoiceEnabled = true;
        wsSetVoiceState("Mic listening...", true);
        appendOutputLine(`[${new Date().toISOString()}] Live mic started`);

        wsRecognition.onresult = (event) => {
          let latestFinal = "";
          for (let i = event.resultIndex; i < event.results.length; i += 1) {
            const res = event.results[i];
            const text = (res[0]?.transcript || "").trim();
            if (!text) continue;
            if (res.isFinal) {
              latestFinal = text;
            }
          }
          if (latestFinal) {
            const textarea = document.getElementById("ws-transcript");
            if (textarea) textarea.value = latestFinal;
            wsSendTranscriptChunk(latestFinal);
          }
        };

        wsRecognition.onerror = (event) => {
          appendOutputLine(`[${new Date().toISOString()}] Live mic error: ${event.error}`);
          wsSetVoiceState(`Mic error: ${event.error}`, false);
        };

        wsRecognition.onend = () => {
          if (!wsVoiceEnabled) {
            wsSetVoiceState("Mic idle", false);
            return;
          }
          try {
            wsRecognition.start();
            wsSetVoiceState("Mic listening...", true);
          } catch (_) {
            wsSetVoiceState("Mic restart delayed...", false);
            setTimeout(() => {
              if (!wsVoiceEnabled || !wsRecognition) return;
              try {
                wsRecognition.start();
                wsSetVoiceState("Mic listening...", true);
              } catch (err) {
                appendOutputLine(`[${new Date().toISOString()}] Live mic restart failed: ${String(err)}`);
              }
            }, 400);
          }
        };

        wsRecognition.start();
      }

      function wsStopLiveMic() {
        wsVoiceEnabled = false;
        if (wsRecognition) {
          try { wsRecognition.stop(); } catch (_) {}
          wsRecognition = null;
        }
        wsSetVoiceState("Mic idle", false);
        appendOutputLine(`[${new Date().toISOString()}] Live mic stopped`);
      }

      function wsDisconnect() {
        wsStopLiveMic();
        if (liveSocket) {
          liveSocket.close(1000, "dashboard_disconnect");
          liveSocket = null;
        }
      }

      function dictateIntoPayload(textareaId) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
          alert("Speech recognition is not supported in this browser.");
          return;
        }
        const recognition = new SpeechRecognition();
        recognition.lang = "en-GB";
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onresult = (event) => {
          const spoken = event.results[0][0].transcript;
          const textarea = document.getElementById(textareaId);
          try {
            const payload = JSON.parse(textarea.value);
            payload.transcript = spoken;
            textarea.value = JSON.stringify(payload, null, 2);
          } catch (err) {
            alert("Payload JSON is invalid. Fix it and try again.");
          }
        };
        recognition.onerror = () => {
          alert("Could not capture speech. Try again.");
        };
        recognition.start();
      }

      // Overview Tab Refresh Loop
      async function refreshDashboard() {
        try {
          const [health, auth, calls] = await Promise.all([
            fetchJson('/api/v1/health', { method: 'GET' }, 6000),
            fetchJson('/api/v1/telegram/auth/status', { method: 'GET' }, 6000),
            fetchJson('/api/v1/calls', { method: 'GET' }, 6000),
          ]);

          const healthBody = health.body || {};
          if (health.ok) {
            const ind = healthBody.status === 'ok'
              ? '<span class="status-indicator status-ok"></span>'
              : '<span class="status-indicator status-err"></span>';
            document.getElementById('status-health').innerHTML = ind + (healthBody.status === 'ok' ? 'Online' : 'Error');
          } else {
            document.getElementById('status-health').innerHTML = '<span class="status-indicator status-err"></span>Offline';
          }

          const authBody = auth.body || {};
          if (auth.ok) {
            const state = authBody.authorized ? 'authorized' : (authBody.connected ? 'connected' : 'offline');
            let ind = '<span class="status-indicator status-warn"></span>';
            if (authBody.authorized) ind = '<span class="status-indicator status-ok"></span>';
            if (!authBody.connected) ind = '<span class="status-indicator status-err"></span>';
            document.getElementById('status-auth').innerHTML = ind + state;
          } else {
            document.getElementById('status-auth').innerHTML = '<span class="status-indicator status-err"></span>Error';
          }

          const tbody = document.getElementById('calls-body');
          const callsBody = Array.isArray(calls.body) ? calls.body : [];
          if (!calls.ok) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--muted); padding: 24px;">Failed to load calls.</td></tr>';
            return;
          }
          if (callsBody.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: var(--muted); padding: 24px;">No calls executed yet.</td></tr>';
            return;
          }
          tbody.innerHTML = '';
          const recent = callsBody.slice().reverse();
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
        } catch(e) { console.error('Dashboard refresh failed', e); }
      }

      // Quick Call
      async function startQuickCall() {
        const target = document.getElementById('quick-target').value;
        const purpose = document.getElementById('quick-purpose').value || "checking in";
        if (!target) return alert('Enter a target user!');
        try {
          const result = await fetchJson('/api/v1/calls/outbound', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_user: target, purpose: purpose, metadata: { quick_trigger: true } })
          });
          if(result.ok) alert('Call triggered! ID: ' + result.body.call_id);
          else alert('Error triggering call: ' + JSON.stringify(result.body));
          refreshDashboard();
        } catch(err) { alert('Error: ' + err.message); }
      }

      // Quick Model Check
      async function runModelCheck() {
        try {
          const result = await fetchJson('/api/v1/model/check', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt: 'ping' })
          });
          const body = result.body || {};
          const el = document.getElementById('status-model');
          if (result.ok && body.connected) {
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
    return RedirectResponse(
        url="/dashboard?v=20260418",
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
