# agents/views_embed.py
import json
import uuid

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from agents.models import Agent, Conversation, Message
from agents.services.chat_runtime import chat_answer


def _cors(request, resp):
    origin = request.headers.get("Origin")
    resp["Access-Control-Allow-Origin"] = origin or "*"
    resp["Vary"] = "Origin"
    resp["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@require_GET
def agent_embed_js(request, public_id):
    """
    Public widget loader JS.
    URL: /agents/embed/<uuid>.js
    """
    public_id_str = str(public_id)

    agent = Agent.objects.filter(public_id=public_id, is_active=True).first()
    active_guard = "" if agent else "return;"

    js = r"""
(function() {
  var SCRIPT = document.currentScript || (function() {
    var ss = document.getElementsByTagName('script');
    return ss[ss.length-1];
  })();

  var src = SCRIPT && SCRIPT.src ? SCRIPT.src : "";
  var u = new URL(src, window.location.href);
  var origin = u.origin;
  var publicId = "__PUBLIC_ID__";
  var base = origin + "/agents/embed/" + publicId;
  var cfgUrl = base + "/config/";
  var chatUrl = base + "/chat/";
  var SESSION_KEY = "mira_embed_session_" + publicId;

  function uuidFallback() {
    return "sess_" + Math.random().toString(16).slice(2) + "_" + Date.now();
  }
  function getSessionId() {
    var sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = (crypto && crypto.randomUUID) ? crypto.randomUUID() : uuidFallback();
      localStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  }

  function el(tag, attrs) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function(k) {
        if (k === "text") n.textContent = attrs[k];
        else if (k === "html") n.innerHTML = attrs[k];
        else n.setAttribute(k, attrs[k]);
      });
    }
    return n;
  }

  function initWidget(config) {
    var cfg = config || {};
    var theme = cfg.theme || {};

    var host = el("div", {"id":"mira-widget-host"});
    host.style.position = "fixed";
    host.style.right = "18px";
    host.style.bottom = "18px";
    host.style.zIndex = "2147483647";
    host.style.fontFamily = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial";
    document.body.appendChild(host);

    var shadow = host.attachShadow ? host.attachShadow({mode:"open"}) : host;

    var style = el("style");
    style.textContent = `
      .mira-btn {
        width: 52px; height: 52px; border-radius: 16px;
        border: 1px solid rgba(255,255,255,.14);
        background: ${theme.bot_bubble_color || "#0EA5A4"};
        color: white; cursor: pointer;
        display:flex; align-items:center; justify-content:center;
        box-shadow: 0 10px 28px rgba(0,0,0,.35);
      }
      .mira-panel {
        position: absolute;
        right: 0;
        bottom: 62px;
        width: 360px;
        max-width: calc(100vw - 36px);
        height: 520px;
        max-height: calc(100vh - 120px);
        border-radius: 18px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,.12);
        background: ${theme.window_bg_color || "#020617"};
        box-shadow: 0 12px 40px rgba(0,0,0,.45);
        display: none;
      }
      .mira-title {
        padding: 12px 14px;
        background: ${theme.title_bar_color || "#0F172A"};
        color: ${theme.text_color || "#E2E8F0"};
        display:flex; align-items:center; gap:10px;
      }
      .mira-title .name { font-weight: 700; font-size: 14px; }
      .mira-body {
        padding: 12px;
        height: calc(100% - 110px);
        overflow: auto;
        color: ${theme.text_color || "#E2E8F0"};
      }
      .mira-input {
        padding: 12px;
        border-top: 1px solid rgba(255,255,255,.10);
        display:flex; gap:8px;
        background: ${theme.window_bg_color || "#020617"};
      }
      .mira-input input {
        flex: 1;
        border-radius: 12px;
        padding: 10px 12px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.22);
        color: ${theme.text_color || "#E2E8F0"};
        outline: none;
      }
      .mira-input button {
        border-radius: 12px;
        padding: 10px 14px;
        border: 0;
        cursor: pointer;
        background: ${theme.bot_bubble_color || "#0EA5A4"};
        color: white;
        font-weight: 600;
      }
      .row { display:flex; margin: 10px 0; }
      .row.user { justify-content:flex-end; }
      .bubble {
        max-width: 80%;
        border-radius: 16px;
        padding: 10px 12px;
        border: 1px solid rgba(255,255,255,.10);
        white-space: pre-line;
        font-size: 13px;
      }
      .bubble.user { background: ${theme.user_bubble_color || "#334155"}; }
      .bubble.bot { background: color-mix(in oklab, ${theme.bot_bubble_color || "#0EA5A4"} 18%, transparent); }

      .cards {
        display:grid;
        grid-template-columns: 1fr;
        gap: 8px;
        margin: 10px 0 0 0;
      }
      .card {
        display:block;
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(255,255,255,.06);
        padding: 10px 12px;
        text-decoration: none;
        color: ${theme.text_color || "#E2E8F0"};
      }
      .card:hover { background: rgba(255,255,255,.10); }
      .card .t { font-weight: 700; font-size: 13px; color: white; }
      .card .s { font-size: 12px; opacity: .85; margin-top: 4px; }
      .card .u { font-size: 11px; color: #5eead4; margin-top: 6px; word-break: break-all; }

      .lead {
        margin-top: 10px;
        border-radius: 16px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.22);
        padding: 12px;
      }
      .lead h4 { margin:0; font-size: 13px; color: white; }
      .lead p { margin:6px 0 0 0; font-size: 12px; opacity: .85; }
      .lead input {
        width: 100%;
        margin-top: 10px;
        border-radius: 12px;
        padding: 10px 12px;
        border: 1px solid rgba(255,255,255,.12);
        background: rgba(0,0,0,.25);
        color: ${theme.text_color || "#E2E8F0"};
        outline: none;
      }
      .lead button {
        margin-top: 10px;
        width: 100%;
        border-radius: 12px;
        padding: 10px 12px;
        border: 0;
        cursor: pointer;
        background: ${theme.bot_bubble_color || "#0EA5A4"};
        color: white;
        font-weight: 700;
      }
    `;
    shadow.appendChild(style);

    var btn = el("button");
    btn.className = "mira-btn";
    btn.setAttribute("aria-label", "Open chat");
    btn.textContent = "💬";

    var panel = el("div");
    panel.className = "mira-panel";

    var title = el("div");
    title.className = "mira-title";

    var iconWrap = el("div");
    iconWrap.style.width = "28px";
    iconWrap.style.height = "28px";
    iconWrap.style.borderRadius = "999px";
    iconWrap.style.overflow = "hidden";
    iconWrap.style.border = "1px solid rgba(255,255,255,.18)";
    iconWrap.style.background = "rgba(255,255,255,.08)";
    if (cfg.icon_url) {
      var img = el("img");
      img.src = cfg.icon_url;
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = "cover";
      iconWrap.appendChild(img);
    }
    title.appendChild(iconWrap);

    var name = el("div");
    name.className = "name";
    name.textContent = cfg.name || "Chat";
    title.appendChild(name);

    panel.appendChild(title);

    var body = el("div");
    body.className = "mira-body";
    panel.appendChild(body);

    var inputWrap = el("div");
    inputWrap.className = "mira-input";

    var input = el("input");
    input.placeholder = "Type a message…";

    var send = el("button", {text:"Send"});
    inputWrap.appendChild(input);
    inputWrap.appendChild(send);

    panel.appendChild(inputWrap);

    shadow.appendChild(panel);
    shadow.appendChild(btn);

    function addBubble(who, text) {
      var row = el("div");
      row.className = "row " + (who === "user" ? "user" : "bot");

      var b = el("div");
      b.className = "bubble " + (who === "user" ? "user" : "bot");
      b.textContent = text || "";
      row.appendChild(b);
      body.appendChild(row);
      body.scrollTop = body.scrollHeight;
    }

    function addCards(cards) {
      if (!cards || !cards.length) return;
      var wrap = el("div");
      wrap.className = "cards";
      cards.forEach(function(c) {
        if (!c || !c.url) return;
        var a = el("a");
        a.className = "card";
        a.href = c.url;
        a.target = "_blank";
        a.rel = "noopener";
        var t = el("div"); t.className = "t"; t.textContent = c.title || "Relevant page";
        var s = el("div"); s.className = "s"; s.textContent = c.subtitle || "";
        var u = el("div"); u.className = "u"; u.textContent = c.url;
        a.appendChild(t); a.appendChild(s); a.appendChild(u);
        wrap.appendChild(a);
      });
      body.appendChild(wrap);
      body.scrollTop = body.scrollHeight;
    }

    function addLeadForm(action) {
      if (!action || action.type !== "lead_form") return;
      var wrap = el("div");
      wrap.className = "lead";

      var h = el("h4"); h.textContent = "Share your details";
      var p = el("p"); p.textContent = "Enter name + email to continue.";
      var nameI = el("input"); nameI.placeholder = "Name";
      var emailI = el("input"); emailI.placeholder = "Email"; emailI.type = "email";
      var b = el("button", {text: action.cta || "Continue"});

      b.addEventListener("click", function() {
        var n = (nameI.value || "").trim();
        var e = (emailI.value || "").trim();
        if (!n || !e) {
          addBubble("bot", "Please enter both name and email.");
          return;
        }
        b.disabled = true;
        b.textContent = "Submitting…";
        postMessage("__continue__", {name:n, email:e});
      });

      wrap.appendChild(h);
      wrap.appendChild(p);
      wrap.appendChild(nameI);
      wrap.appendChild(emailI);
      wrap.appendChild(b);

      body.appendChild(wrap);
      body.scrollTop = body.scrollHeight;
    }

    async function postMessage(text, lead) {
      try {
        var payload = {
          session_id: getSessionId(),
          message: text
        };
        if (lead) payload.lead = lead;

        var r = await fetch(chatUrl, {
          method: "POST",
          headers: { "Content-Type":"application/json" },
          body: JSON.stringify(payload)
        });
        var data = await r.json();
        if (!r.ok || !data.ok) {
          addBubble("bot", (data && data.error) ? data.error : "Something went wrong.");
          return;
        }

        if (data.session_id) localStorage.setItem(SESSION_KEY, data.session_id);

        if (data.messages && data.messages.length) {
          data.messages.forEach(function(m) {
            if (m.type === "text" && m.text) addBubble("bot", m.text);
          });
        } else if (data.answer) {
          addBubble("bot", data.answer);
        }

        // Persist widgets in chat history (do NOT clear previous cards/forms)
        addCards(data.cards || []);
        var actions = data.actions || [];
        var leadAction = actions.find(function(a){ return a.type === "lead_form"; });
        if (leadAction) addLeadForm(leadAction);

      } catch (e) {
        addBubble("bot", "Network error.");
      }
    }

    function sendNow() {
      var t = (input.value || "").trim();
      if (!t) return;
      input.value = "";
      addBubble("user", t);
      postMessage(t);
    }

    send.addEventListener("click", sendNow);
    input.addEventListener("keydown", function(e) {
      if (e.key === "Enter") sendNow();
    });

    btn.addEventListener("click", function() {
      panel.style.display = (panel.style.display === "none" || !panel.style.display) ? "block" : "none";
      if (panel.style.display === "block" && !body.dataset.greeted) {
        body.dataset.greeted = "1";
        addBubble("bot", cfg.greeting || "Hi! How can I help?");
      }
    });
  }

  async function boot() {
    __ACTIVE_GUARD__
    try {
      var r = await fetch(cfgUrl, { method:"GET" });
      var data = await r.json();
      if (!r.ok || !data.ok) return;
      initWidget(data.agent);
    } catch (e) {
      // silent fail
    }
  }

  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(boot);
})();
""".replace("__PUBLIC_ID__", public_id_str).replace("__ACTIVE_GUARD__", active_guard)

    return HttpResponse(js, content_type="application/javascript")


@require_GET
def agent_embed_config(request, public_id):
    agent = get_object_or_404(Agent, public_id=public_id, is_active=True)

    icon_url = ""
    if getattr(agent, "icon", None):
        icon_url = request.build_absolute_uri(agent.icon.url)

    data = {
        "ok": True,
        "agent": {
            "public_id": str(agent.public_id),
            "name": agent.name,
            "description": agent.description or "",
            "greeting": agent.greeting_message or "Hi! How can I help?",
            "icon_url": icon_url,
            "theme": {
                "title_bar_color": agent.title_bar_color,
                "window_bg_color": agent.window_bg_color,
                "bot_bubble_color": agent.bot_bubble_color,
                "user_bubble_color": agent.user_bubble_color,
                "text_color": agent.text_color,
            },
        }
    }
    resp = JsonResponse(data)
    return _cors(request, resp)


@csrf_exempt
@require_POST
def agent_embed_chat(request, public_id):
    agent = get_object_or_404(Agent, public_id=public_id, is_active=True)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        resp = JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        return _cors(request, resp)

    session_id = (payload.get("session_id") or payload.get("sessionId") or "").strip()[:80]
    message = (payload.get("message") or payload.get("text") or "").strip()
    pending_question = (payload.get("pending_question") or "").strip()

    if not session_id:
        session_id = str(uuid.uuid4())

    convo, _ = Conversation.objects.get_or_create(agent=agent, session_id=session_id)
    state = convo.state or {}

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

    if message == "__continue__":
        message = pending_question or (state.get("pending_question") or "")
        message = (message or "").strip()

    if not message:
        resp = JsonResponse({"ok": False, "error": "message is required"}, status=400)
        return _cors(request, resp)

    Message.objects.create(conversation=convo, role="user", content=message, meta={"lead": stored_lead})

    try:
        result = chat_answer(agent=agent, user_message=message, lead=stored_lead, max_intents=2)

        actions = result.get("actions") or []
        lead_action = next((a for a in actions if a.get("type") == "lead_form"), None)

        if lead_action and not stored_lead:
            state = convo.state or {}
            state["pending_question"] = message
            state["pending_reason"] = lead_action.get("reason") or "lead_gen"
            convo.state = state
            convo.save(update_fields=["state", "updated_at"])

        out = {
            "ok": True,
            "session_id": session_id,
            "answer": result.get("answer") or "",
            "messages": result.get("messages") or [],
            "cards": result.get("cards") or [],
            "actions": result.get("actions") or [],
        }

        Message.objects.create(conversation=convo, role="assistant", content=(out["answer"] or "")[:4000])

        resp = JsonResponse(out)
        return _cors(request, resp)

    except Exception as e:
        resp = JsonResponse({"ok": False, "error": str(e)[:300]}, status=500)
        return _cors(request, resp)
