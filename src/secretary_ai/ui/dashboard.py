from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(include_in_schema=False)


DASHBOARD_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Secretary AI Dashboard</title>
    <style>
      :root {
        --bg: #eef3f5;
        --panel: #ffffff;
        --panel-soft: #f8fbfc;
        --ink: #11324a;
        --muted: #4a6377;
        --brand: #12748a;
        --brand-2: #0ea5a8;
        --accent: #d97706;
        --accent-2: #f59e0b;
        --ok: #059669;
        --err: #dc2626;
        --line: #dbe7ee;
        --shadow: 0 16px 36px rgba(17, 50, 74, 0.1);
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
        font-family: "Space Grotesk", "Avenir Next", "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at -5% -30%, rgba(14, 165, 168, 0.28), transparent 42%),
          radial-gradient(circle at 110% -15%, rgba(245, 158, 11, 0.22), transparent 36%),
          var(--bg);
        min-height: 100vh;
      }
      .wrap {
        max-width: 1300px;
        margin: 0 auto;
        padding: 28px 20px 34px;
      }
      .hero {
        background: linear-gradient(120deg, #0e4c61 0%, #12748a 50%, #0ea5a8 100%);
        color: #f0fdfd;
        border-radius: 22px;
        box-shadow: var(--shadow);
        padding: 24px;
        margin-bottom: 14px;
        position: relative;
        overflow: hidden;
      }
      .hero::after {
        content: "";
        position: absolute;
        width: 220px;
        height: 220px;
        right: -40px;
        top: -80px;
        border-radius: 999px;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.38), rgba(255, 255, 255, 0));
      }
      .hero h1 {
        margin: 0 0 6px;
        font-size: clamp(1.45rem, 2.5vw, 2.1rem);
        letter-spacing: 0.25px;
      }
      .hero p {
        margin: 0;
        opacity: 0.94;
      }
      .links {
        margin-top: 12px;
        font-size: 0.95rem;
      }
      .links a {
        color: #ecfeff;
        text-decoration: underline;
        margin-right: 14px;
      }
      .layout {
        display: grid;
        gap: 14px;
        grid-template-columns: 1.2fr 0.8fr;
      }
      .panel {
        background: var(--panel);
        border-radius: 18px;
        box-shadow: var(--shadow);
        border: 1px solid rgba(17, 50, 74, 0.04);
      }
      .left {
        padding: 14px;
      }
      .left h2,
      .right h2 {
        margin: 0;
        font-size: 1.06rem;
        letter-spacing: 0.2px;
      }
      .subtitle {
        color: var(--muted);
        font-size: 0.9rem;
        margin: 6px 0 12px;
      }
      .cards {
        display: grid;
        gap: 10px;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      }
      .card {
        background: var(--panel-soft);
        border-radius: 14px;
        border: 1px solid var(--line);
        padding: 14px;
        animation: rise 0.45s ease both;
      }
      @keyframes rise {
        from {
          opacity: 0;
          transform: translateY(8px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
      .row {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        align-items: center;
        margin: 8px 0;
      }
      .method {
        font-size: 0.72rem;
        letter-spacing: 0.35px;
        text-transform: uppercase;
        font-weight: 700;
        padding: 4px 9px;
        border-radius: 999px;
        color: white;
        background: var(--brand);
      }
      .method.post {
        background: var(--accent);
      }
      code.path {
        padding: 3px 8px;
        border-radius: 8px;
        background: #e3edf3;
        color: #243b53;
        font-size: 0.9rem;
      }
      .hint {
        margin: 2px 0 8px;
        color: var(--muted);
        font-size: 0.8rem;
      }
      textarea,
      input {
        width: 100%;
        border: 1px solid #cad9e4;
        border-radius: 10px;
        padding: 10px;
        font-family: "Cascadia Code", "Consolas", monospace;
        font-size: 0.81rem;
        background: #fbfdff;
        color: #1f3a4f;
      }
      textarea {
        min-height: 118px;
        resize: vertical;
      }
      button {
        border: 0;
        border-radius: 10px;
        font-weight: 700;
        letter-spacing: 0.25px;
        padding: 9px 13px;
        color: #f0fdfa;
        background: linear-gradient(120deg, var(--brand), var(--brand-2));
        cursor: pointer;
        transition: transform 0.16s ease, filter 0.16s ease;
      }
      button.secondary {
        background: linear-gradient(120deg, var(--accent), var(--accent-2));
      }
      button:hover {
        transform: translateY(-1px);
        filter: brightness(1.04);
      }
      .right {
        padding: 14px;
        display: flex;
        flex-direction: column;
        position: sticky;
        top: 12px;
        height: fit-content;
      }
      .meta {
        margin-bottom: 10px;
        color: var(--muted);
        font-size: 0.86rem;
      }
      .output {
        margin-top: 8px;
        background: #0f1d2b;
        color: #d5e7f7;
        border-radius: 14px;
        padding: 14px;
        min-height: 520px;
        font-family: "Cascadia Code", "Consolas", monospace;
        font-size: 0.81rem;
        overflow: auto;
        white-space: pre-wrap;
      }
      .bar {
        margin-top: 10px;
        padding: 10px;
        border-radius: 10px;
        background: #ecfdf5;
        color: #065f46;
        font-size: 0.84rem;
      }
      @media (max-width: 980px) {
        .layout {
          grid-template-columns: 1fr;
        }
        .right {
          position: static;
        }
        .output {
          min-height: 300px;
        }
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <section class="hero">
        <h1>Secretary AI Dashboard</h1>
        <p>Fast local tester for API endpoints while you build the hackathon flows.</p>
        <div class="links">
          <a href="/docs" target="_blank" rel="noreferrer">Swagger Docs</a>
          <a href="/api/v1/health" target="_blank" rel="noreferrer">Health Endpoint</a>
        </div>
      </section>

      <section class="layout">
        <div class="panel left">
          <h2>Endpoint Runner</h2>
          <p class="subtitle">Run test requests quickly with editable payloads.</p>

          <div class="cards">
            <article class="card">
              <div class="row">
                <span class="method">GET</span>
                <code class="path">/api/v1/health</code>
              </div>
              <p class="hint">Service status and mode.</p>
              <button onclick="callGet('/api/v1/health')">Run</button>
            </article>

            <article class="card">
              <div class="row">
                <span class="method">GET</span>
                <code class="path">/api/v1/architecture</code>
              </div>
              <p class="hint">Current architecture map and status notes.</p>
              <button onclick="callGet('/api/v1/architecture')">Run</button>
            </article>

            <article class="card">
              <div class="row">
                <span class="method post">POST</span>
                <code class="path">/api/v1/model/check</code>
              </div>
              <p class="hint">Checks live Z.AI GLM connectivity.</p>
              <textarea id="payload-model">{
  "prompt": "Reply with connection_ok only"
}</textarea>
              <div class="row">
                <button class="secondary" onclick="callPost('/api/v1/model/check', 'payload-model')">Run</button>
              </div>
            </article>

            <article class="card">
              <div class="row">
                <span class="method post">POST</span>
                <code class="path">/api/v1/calls/inbound</code>
              </div>
              <p class="hint">Placeholder route, currently returns 501.</p>
              <textarea id="payload-inbound">{
  "call_id": "call-001",
  "from_number": "+441111111111",
  "to_number": "+442222222222",
  "transcript": "Hello",
  "metadata": {}
}</textarea>
              <div class="row">
                <button class="secondary" onclick="callPost('/api/v1/calls/inbound', 'payload-inbound')">Run</button>
              </div>
            </article>

            <article class="card">
              <div class="row">
                <span class="method post">POST</span>
                <code class="path">/api/v1/calls/outbound</code>
              </div>
              <p class="hint">Placeholder route, currently returns 501.</p>
              <textarea id="payload-outbound">{
  "to_number": "+441111111111",
  "message": "Reminder call",
  "purpose": "reminder",
  "metadata": {}
}</textarea>
              <div class="row">
                <button class="secondary" onclick="callPost('/api/v1/calls/outbound', 'payload-outbound')">Run</button>
              </div>
            </article>

            <article class="card">
              <div class="row">
                <span class="method post">POST</span>
                <code class="path">/api/v1/calls/post-call</code>
              </div>
              <p class="hint">Placeholder route, currently returns 501.</p>
              <textarea id="payload-postcall">{
  "call_id": "call-001",
  "transcript": "Call summary text",
  "metadata": {}
}</textarea>
              <div class="row">
                <button class="secondary" onclick="callPost('/api/v1/calls/post-call', 'payload-postcall')">Run</button>
              </div>
            </article>

            <article class="card">
              <div class="row">
                <span class="method">GET</span>
                <code class="path">/api/v1/calls/{call_id}</code>
              </div>
              <p class="hint">Fetch specific call by ID (planned storage).</p>
              <input id="call-id" value="call-001" />
              <div class="row">
                <button onclick="callGet('/api/v1/calls/' + encodeURIComponent(document.getElementById('call-id').value))">Run</button>
              </div>
            </article>
          </div>
        </div>

        <aside class="panel right">
          <h2>Response Console</h2>
          <p class="meta">Latest response is shown below.</p>
          <div class="bar">Current model route target: <strong>/api/v1/model/check</strong></div>
          <section class="output" id="output">Ready. Use the buttons on the left to test endpoints.</section>
        </aside>
      </section>
    </div>

    <script>
      function printResult(method, path, status, body) {
        const output = document.getElementById("output");
        const stamp = new Date().toISOString();
        const ok = status >= 200 && status < 300;
        const marker = ok ? "OK" : "ERROR";
        output.textContent =
          `[${stamp}] ${method} ${path}\\n` +
          `Status: ${status} (${marker})\\n\\n` +
          `${JSON.stringify(body, null, 2)}`;
      }

      function printClientError(method, path, err) {
        const output = document.getElementById("output");
        const stamp = new Date().toISOString();
        output.textContent =
          `[${stamp}] ${method} ${path}\\n` +
          `Status: CLIENT_ERROR\\n\\n${String(err)}`;
      }

      async function callGet(path) {
        try {
          const response = await fetch(path, { method: "GET" });
          const body = await response.json().catch(() => ({ raw: "Non-JSON response" }));
          printResult("GET", path, response.status, body);
        } catch (err) {
          printClientError("GET", path, err);
        }
      }

      async function callPost(path, textareaId) {
        let payload;
        try {
          payload = JSON.parse(document.getElementById(textareaId).value);
        } catch (err) {
          printClientError("POST", path, `Invalid JSON payload: ${err}`);
          return;
        }

        try {
          const response = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const body = await response.json().catch(() => ({ raw: "Non-JSON response" }));
          printResult("POST", path, response.status, body);
        } catch (err) {
          printClientError("POST", path, err);
        }
      }
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
