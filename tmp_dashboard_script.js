
      // Tab Switching
      function switchTab(tabId, buttonEl) {
        document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        if (buttonEl) buttonEl.classList.add('active');
      }

      function openChatTab() {
        const btn = document.getElementById("tab-chat-btn");
        switchTab("chat", btn);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }

      // API Call Helpers for Lab
      let liveSocket = null;
      let wsRecognition = null;
      let wsVoiceEnabled = false;
      let wsSpeechSeq = 0;

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

      // ── Chat Tab ──
      let chatHistory = [];

      function chatRenderMessage(role, text) {
        const messages = document.getElementById('chat-messages');
        const empty = document.getElementById('chat-empty');
        if (empty) empty.remove();

        const wrap = document.createElement('div');
        wrap.style.display = 'flex';
        wrap.style.flexDirection = 'column';
        wrap.style.alignItems = role === 'user' ? 'flex-end' : 'flex-start';

        const label = document.createElement('div');
        label.className = 'bubble-label';
        label.textContent = role === 'user' ? 'You' : 'Secretary AI';
        label.style.textAlign = role === 'user' ? 'right' : 'left';
        if (role !== 'user') label.style.color = 'var(--primary)';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble ' + (role === 'user' ? 'bubble-user' : 'bubble-ai');
        // basic markdown-lite: **bold**, *italic*, newlines
        bubble.innerHTML = text
          .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
          .replace(/\\*\\*(.+?)\\*\\*/g,'<b>$1</b>')
          .replace(/\\*(.+?)\\*/g,'<i>$1</i>')
          .replace(/`(.+?)`/g,'<code>$1</code>')
          .replace(/\n/g,'<br>');

        wrap.appendChild(label);
        wrap.appendChild(bubble);
        messages.appendChild(wrap);
        messages.scrollTop = messages.scrollHeight;
      }

      function chatShowTyping() {
        const messages = document.getElementById('chat-messages');
        const el = document.createElement('div');
        el.id = 'chat-typing';
        el.className = 'typing-indicator';
        el.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
        messages.appendChild(el);
        messages.scrollTop = messages.scrollHeight;
      }

      function chatHideTyping() {
        const el = document.getElementById('chat-typing');
        if (el) el.remove();
      }

      async function chatSend() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        if (!message) return;
        input.value = '';
        input.style.height = 'auto';

        chatRenderMessage('user', message);
        chatShowTyping();

        try {
          const res = await fetch('/api/v1/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history: chatHistory }),
          });
          const data = await res.json();
          chatHideTyping();
          if (res.ok) {
            chatHistory = data.history || [];
            chatRenderMessage('assistant', data.reply || '(no reply)');
            const tag = document.getElementById('chat-model-tag');
            if (tag && data.model) tag.textContent = 'Model: ' + data.model;
          } else {
            chatRenderMessage('assistant', '⚠️ Server error ' + res.status + ': ' + (data.detail || JSON.stringify(data)));
          }
        } catch (err) {
          chatHideTyping();
          chatRenderMessage('assistant', '⚠️ Network error: ' + String(err));
        }
      }

      function chatClear() {
        chatHistory = [];
        const messages = document.getElementById('chat-messages');
        messages.innerHTML = '';
        const empty = document.createElement('div');
        empty.id = 'chat-empty';
        empty.className = 'chat-empty';
        empty.innerHTML = '<span class="chat-empty-icon">🤖</span><span>Say hello — I\'m your AI Secretary.</span><span style="font-size:0.78rem;opacity:0.65;">Powered by Z.AI GLM</span>';
        messages.appendChild(empty);
        document.getElementById('chat-model-tag').textContent = 'Model: —';
      }

      // Enter to send, Shift+Enter for newline
      document.getElementById('chat-input').addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          chatSend();
        }
      });
      // Auto-grow textarea
      document.getElementById('chat-input').addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 140) + 'px';
      });

      // Initial loaders
      refreshDashboard();
      runModelCheck();
      setInterval(refreshDashboard, 5000);
    