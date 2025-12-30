# agents/views_embed.py
import json
import uuid

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from agents.models import Agent, Conversation, Message
from agents.services.chat_runtime import chat_answer


def _safe_json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return None


# -------------------------
# CORS helpers (for embed)
# -------------------------
def _corsify(resp: HttpResponse, request=None) -> HttpResponse:
    resp["Access-Control-Allow-Origin"] = "*"
    resp["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"

    # Respect browser preflight requested headers if present
    req_hdrs = ""
    if request is not None:
        req_hdrs = request.headers.get("Access-Control-Request-Headers", "") or ""

    resp["Access-Control-Allow-Headers"] = req_hdrs if req_hdrs else "Content-Type, Accept"
    resp["Access-Control-Max-Age"] = "86400"
    return resp


def _options_ok(request) -> HttpResponse:
    return _corsify(HttpResponse("", status=200), request=request)


# -------------------------
# Embed config
# -------------------------
@require_http_methods(["GET", "OPTIONS"])
def agent_embed_config(request, public_id):
    if request.method == "OPTIONS":
        return _options_ok(request)

    agent = get_object_or_404(Agent, public_id=public_id, is_active=True)

    icon_url = ""
    try:
        if agent.icon and getattr(agent.icon, "url", None):
            icon_url = request.build_absolute_uri(agent.icon.url)
    except Exception:
        icon_url = ""

    data = {
        "ok": True,
        "agent": {
            "name": agent.name,
            "description": agent.description,
            "greeting_message": agent.greeting_message or "Hi! How can I help?",
            "icon_url": icon_url,
        },
        "theme": {
            "title_bar_color": agent.title_bar_color,
            "window_bg_color": agent.window_bg_color,
            "bot_bubble_color": agent.bot_bubble_color,
            "user_bubble_color": agent.user_bubble_color,
            "text_color": agent.text_color,
        },
    }
    return _corsify(JsonResponse(data), request=request)


# -------------------------
# Embed chat endpoint (public, CSRF-exempt)
# -------------------------
@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def agent_embed_chat(request, public_id):
    if request.method == "OPTIONS":
        return _options_ok(request)

    payload = _safe_json(request)
    if payload is None:
        return _corsify(JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400), request=request)

    # ✅ IMPORTANT: use the exact same lookup rules as config
    agent = get_object_or_404(Agent, public_id=public_id, is_active=True)

    session_id = (payload.get("session_id") or payload.get("sessionId") or "").strip()[:80]
    message = (payload.get("message") or payload.get("text") or "").strip()
    pending_question = (payload.get("pending_question") or "").strip()

    if not session_id:
        session_id = str(uuid.uuid4())

    convo, _ = Conversation.objects.get_or_create(agent=agent, session_id=session_id)
    state = convo.state or {}

    # Mark channel + origin for analytics
    state.setdefault("channel", "embed")
    origin = request.headers.get("Origin") or ""
    referer = request.headers.get("Referer") or ""
    if origin:
        state["origin"] = origin
    if referer:
        state["referer"] = referer

    # Persist lead if supplied
    incoming_lead = payload.get("lead") or {}
    lead_name = (incoming_lead.get("name") or "").strip()
    lead_email = (incoming_lead.get("email") or "").strip()

    if lead_name and lead_email:
        state["lead"] = {"name": lead_name, "email": lead_email}
        state.pop("pending_question", None)
        state.pop("pending_reason", None)

    convo.state = state
    convo.save(update_fields=["state", "updated_at"])

    stored_lead = (convo.state or {}).get("lead") or {}

    # Continue flow (after lead submit)
    if message == "__continue__":
        message = pending_question or (state.get("pending_question") or "")
        message = (message or "").strip()

    if not message:
        return _corsify(JsonResponse({"ok": False, "error": "message is required"}, status=400), request=request)

    # Log user message
    Message.objects.create(
        conversation=convo,
        role="user",
        content=message,
        meta={"lead": stored_lead, "channel": "embed"},
    )

    # Run brain
    try:
        result = chat_answer(
            agent=agent,
            user_message=message,
            lead=stored_lead,
            max_intents=2,
        )
    except Exception as e:
        return _corsify(JsonResponse({"ok": False, "error": str(e)[:300]}, status=500), request=request)

    # If lead form required, store pending question
    actions = result.get("actions") or []
    lead_action = next((a for a in actions if a.get("type") == "lead_form"), None)
    if lead_action and not stored_lead:
        state = convo.state or {}
        state["pending_question"] = message
        state["pending_reason"] = lead_action.get("reason") or "lead_gen"
        convo.state = state
        convo.save(update_fields=["state", "updated_at"])

    resp = {"ok": True, "session_id": session_id, **result}

    # Log assistant
    Message.objects.create(
        conversation=convo,
        role="assistant",
        content=(resp.get("answer") or "")[:4000],
        meta={"debug": resp.get("debug", {}), "channel": "embed"},
    )

    return _corsify(JsonResponse(resp), request=request)


# -------------------------
# Embed JS
# -------------------------
@require_http_methods(["GET"])
def agent_embed_js(request, public_id):
    base = f"{request.scheme}://{request.get_host()}"
    public_id_str = str(public_id)

    js = f"""
(function() {{
  const PUBLIC_ID = "{public_id_str}";
  const scriptEl = document.currentScript || (function() {{
    const s = document.getElementsByTagName('script');
    return s[s.length - 1];
  }})();
  const scriptSrc = scriptEl && scriptEl.src ? scriptEl.src : "{base}/agents/embed/{public_id_str}.js";
  const serverOrigin = (new URL(scriptSrc)).origin;

  const CONFIG_URL = serverOrigin + "/agents/embed/" + PUBLIC_ID + "/config/";
  const CHAT_URL   = serverOrigin + "/agents/embed/" + PUBLIC_ID + "/chat/";

  const SESSION_KEY = "mira_embed_session_" + PUBLIC_ID;

  function uuidFallback() {{
    return "sess_" + Math.random().toString(16).slice(2) + "_" + Date.now();
  }}
  function getSessionId() {{
    let sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {{
      sid = (crypto && crypto.randomUUID) ? crypto.randomUUID() : uuidFallback();
      localStorage.setItem(SESSION_KEY, sid);
    }}
    return sid;
  }}

  const style = document.createElement("style");
  style.textContent = `
    .mira-root, .mira-root * {{ box-sizing: border-box; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; }}
    .mira-launcher {{
      position: fixed; right: 20px; bottom: 20px;
      width: 52px; height: 52px; border-radius: 16px;
      border: 1px solid rgba(255,255,255,.12);
      background: rgba(15,23,42,.92);
      display: flex; align-items: center; justify-content: center;
      cursor: pointer; z-index: 2147483647;
      box-shadow: 0 18px 40px rgba(0,0,0,.35);
    }}
    .mira-launcher img {{ width: 28px; height: 28px; border-radius: 999px; object-fit: cover; }}
    .mira-panel {{
      position: fixed; right: 20px; bottom: 84px;
      width: 360px; max-width: calc(100vw - 40px);
      height: 560px; max-height: calc(100vh - 120px);
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,.12);
      box-shadow: 0 22px 60px rgba(0,0,0,.45);
      display: none;
      z-index: 2147483647;
    }}
    .mira-header {{
      padding: 12px 14px;
      display: flex; align-items: center; gap: 10px;
      border-bottom: 1px solid rgba(255,255,255,.10);
    }}
    .mira-header img {{ width: 28px; height: 28px; border-radius: 999px; object-fit: cover; }}
    .mira-title {{ color: #fff; font-weight: 700; font-size: 14px; }}
    .mira-body {{
      padding: 12px;
      height: calc(100% - 54px - 62px);
      overflow: auto;
    }}
    .mira-row {{ display: flex; margin-bottom: 10px; }}
    .mira-row.user {{ justify-content: flex-end; }}
    .mira-bubble {{
      max-width: 82%;
      padding: 10px 12px;
      border-radius: 16px;
      border: 1px solid rgba(255,255,255,.10);
      white-space: pre-wrap;
      line-height: 1.35;
      font-size: 13px;
    }}
    .mira-inputbar {{
      height: 62px;
      padding: 10px;
      display: flex; gap: 8px;
      border-top: 1px solid rgba(255,255,255,.10);
      align-items: center;
    }}
    .mira-input {{
      flex: 1;
      height: 42px;
      border-radius: 14px;
      padding: 0 12px;
      border: 1px solid rgba(255,255,255,.14);
      background: rgba(0,0,0,.22);
      outline: none;
      color: inherit;
      font-size: 13px;
      min-width: 0;
    }}
    .mira-send {{
      height: 42px;
      padding: 0 14px;
      border-radius: 14px;
      border: 0;
      cursor: pointer;
      color: #fff;
      font-weight: 600;
      min-width: 78px;
    }}
    .mira-cards {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin: 10px 0 14px;
    }}
    .mira-card {{
      display: block;
      text-decoration: none;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,.10);
      background: rgba(255,255,255,.06);
    }}
    .mira-card-title {{ color: #fff; font-weight: 700; font-size: 12.5px; }}
    .mira-card-sub {{ color: rgba(226,232,240,.9); font-size: 11.5px; margin-top: 6px; }}
    .mira-card-url {{ color: rgba(94,234,212,.95); font-size: 11px; margin-top: 8px; word-break: break-all; }}
    .mira-form {{
      border: 1px solid rgba(255,255,255,.10);
      background: rgba(0,0,0,.22);
      border-radius: 14px;
      padding: 12px;
      margin: 10px 0 14px;
    }}
    .mira-form h4 {{ margin: 0; color: #fff; font-size: 13px; }}
    .mira-form p {{ margin: 6px 0 10px; color: rgba(226,232,240,.85); font-size: 11.5px; }}
    .mira-form input {{
      width: 100%;
      height: 40px;
      border-radius: 12px;
      padding: 0 12px;
      border: 1px solid rgba(255,255,255,.14);
      background: rgba(0,0,0,.22);
      color: #fff;
      outline: none;
      margin-top: 8px;
    }}
    .mira-form button {{
      margin-top: 10px;
      height: 40px;
      padding: 0 14px;
      border-radius: 12px;
      border: 0;
      cursor: pointer;
      color: #fff;
      font-weight: 700;
    }}
  `;
  document.head.appendChild(style);

  const root = document.createElement("div");
  root.className = "mira-root";
  document.body.appendChild(root);

  const launcher = document.createElement("div");
  launcher.className = "mira-launcher";
  root.appendChild(launcher);

  const panel = document.createElement("div");
  panel.className = "mira-panel";
  root.appendChild(panel);

  const header = document.createElement("div");
  header.className = "mira-header";
  panel.appendChild(header);

  const headerIcon = document.createElement("img");
  headerIcon.style.display = "none";
  header.appendChild(headerIcon);

  const headerTitle = document.createElement("div");
  headerTitle.className = "mira-title";
  header.appendChild(headerTitle);

  const body = document.createElement("div");
  body.className = "mira-body";
  panel.appendChild(body);

  const inputBar = document.createElement("div");
  inputBar.className = "mira-inputbar";
  panel.appendChild(inputBar);

  const input = document.createElement("input");
  input.className = "mira-input";
  input.placeholder = "Type a message…";
  inputBar.appendChild(input);

  const send = document.createElement("button");
  send.className = "mira-send";
  send.textContent = "Send";
  inputBar.appendChild(send);

  function addBubble(who, text) {{
    const row = document.createElement("div");
    row.className = "mira-row " + (who === "user" ? "user" : "bot");

    const bub = document.createElement("div");
    bub.className = "mira-bubble";
    bub.textContent = text || "";
    row.appendChild(bub);

    bub.dataset.kind = (who === "user") ? "user" : "bot";

    body.appendChild(row);
    body.scrollTop = body.scrollHeight;
  }}

  function renderCards(cards) {{
    if (!cards || !cards.length) return;
    const wrap = document.createElement("div");
    wrap.className = "mira-cards";

    cards.forEach(c => {{
      const a = document.createElement("a");
      a.className = "mira-card";
      a.href = c.url || "#";
      a.target = "_blank";
      a.rel = "noopener";

      const t = document.createElement("div");
      t.className = "mira-card-title";
      t.textContent = c.title || "Relevant page";

      const s = document.createElement("div");
      s.className = "mira-card-sub";
      s.textContent = c.subtitle || "";

      const u = document.createElement("div");
      u.className = "mira-card-url";
      u.textContent = c.url || "";

      a.appendChild(t); a.appendChild(s); a.appendChild(u);
      wrap.appendChild(a);
    }});

    body.appendChild(wrap);
    body.scrollTop = body.scrollHeight;
  }}

  function renderLeadForm(action) {{
    if (!action || action.type !== "lead_form") return;

    const wrap = document.createElement("div");
    wrap.className = "mira-form";

    const h = document.createElement("h4");
    h.textContent = "Share your details";
    wrap.appendChild(h);

    const p = document.createElement("p");
    p.textContent = "Enter name + email to continue.";
    wrap.appendChild(p);

    const name = document.createElement("input");
    name.placeholder = "Name";
    wrap.appendChild(name);

    const email = document.createElement("input");
    email.placeholder = "Email";
    email.type = "email";
    wrap.appendChild(email);

    const btn = document.createElement("button");
    btn.textContent = action.cta || "Continue";
    wrap.appendChild(btn);

    btn.addEventListener("click", async () => {{
      const n = (name.value || "").trim();
      const e = (email.value || "").trim();
      if (!n || !e) {{
        addBubble("bot", "Please enter both name and email.");
        return;
      }}
      btn.disabled = true;
      btn.textContent = "Submitted";

      await postToChat({{
        session_id: getSessionId(),
        message: "__continue__",
        lead: {{ name: n, email: e }}
      }});
    }});

    body.appendChild(wrap);
    body.scrollTop = body.scrollHeight;
  }}

  let THEME = {{
    title_bar_color: "#0F172A",
    window_bg_color: "#020617",
    bot_bubble_color: "#0EA5A4",
    user_bubble_color: "#334155",
    text_color: "#E2E8F0",
  }};

  function applyTheme() {{
    panel.style.background = THEME.window_bg_color;
    body.style.background = THEME.window_bg_color;
    body.style.color = THEME.text_color;
    inputBar.style.background = THEME.window_bg_color;
    header.style.background = THEME.title_bar_color;
    send.style.background = THEME.bot_bubble_color;

    body.querySelectorAll(".mira-bubble").forEach(b => {{
      const kind = b.dataset.kind;
      b.style.background = (kind === "user")
        ? THEME.user_bubble_color
        : ("color-mix(in oklab, " + THEME.bot_bubble_color + " 18%, transparent)");
      b.style.color = THEME.text_color;
    }});
  }}

  async function loadConfig() {{
    try {{
      const r = await fetch(CONFIG_URL, {{ method: "GET", mode: "cors" }});
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || "config error");

      THEME = Object.assign(THEME, data.theme || {{}});
      applyTheme();

      const agent = data.agent || {{}};
      headerTitle.textContent = agent.name || "Chat";
      const iconUrl = agent.icon_url || "";

      launcher.innerHTML = "";
      if (iconUrl) {{
        const img = document.createElement("img");
        img.src = iconUrl;
        img.alt = "chat";
        launcher.appendChild(img);

        headerIcon.src = iconUrl;
        headerIcon.style.display = "block";
      }} else {{
        launcher.textContent = "💬";
      }}

      addBubble("bot", agent.greeting_message || "Hi! How can I help?");
      applyTheme();
    }} catch (e) {{
      launcher.textContent = "💬";
      headerTitle.textContent = "Chat";
      applyTheme();
      addBubble("bot", "Chat is not available right now.");
    }}
  }}

  async function postToChat(bodyObj) {{
    try {{
      const r = await fetch(CHAT_URL, {{
        method: "POST",
        mode: "cors",
        credentials: "omit",
        headers: {{
          "Content-Type": "application/json",
          "Accept": "application/json"
        }},
        body: JSON.stringify(bodyObj)
      }});

      const data = await r.json();

      if (!r.ok || !data.ok) {{
        addBubble("bot", data.error || "Network error.");
        applyTheme();
        return;
      }}

      const msgs = data.messages || [];
      if (msgs.length) {{
        msgs.forEach(m => {{
          if (m.type === "text" && m.text) addBubble("bot", m.text);
        }});
      }} else if (data.answer) {{
        addBubble("bot", data.answer);
      }}

      renderCards(data.cards || []);
      const leadAction = (data.actions || []).find(a => a.type === "lead_form");
      if (leadAction) renderLeadForm(leadAction);

      applyTheme();
    }} catch (e) {{
      addBubble("bot", "Network error.");
      applyTheme();
    }}
  }}

  function sendMessage() {{
    const txt = (input.value || "").trim();
    if (!txt) return;

    addBubble("user", txt);
    applyTheme();
    input.value = "";

    postToChat({{
      session_id: getSessionId(),
      message: txt
    }});
  }}

  send.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (e) => {{
    if (e.key === "Enter") sendMessage();
  }});

  launcher.addEventListener("click", () => {{
    panel.style.display = (panel.style.display === "block") ? "none" : "block";
  }});

  loadConfig();
}})();
"""
    resp = HttpResponse(js, content_type="application/javascript; charset=utf-8")
    # Helps during development so you don’t fight caching
    resp["Cache-Control"] = "no-store"
    return resp
