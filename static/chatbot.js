(function () {
  const toggle = document.getElementById("chatToggle");
  const panel = document.getElementById("chatPanel");
  const closeBtn = document.getElementById("chatClose");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const messagesEl = document.getElementById("chatMessages");

  if (!toggle || !panel || !form || !input || !messagesEl) return;

  /** @type {{ role: string, content: string }[]} */
  let history = [];

  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      input.focus();
    }
  }

  function appendBubble(text, kind) {
    const div = document.createElement("div");
    div.className = "chat-bubble chat-bubble--" + kind;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  toggle.addEventListener("click", function () {
    setOpen(panel.hidden);
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !panel.hidden) {
      setOpen(false);
    }
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    appendBubble(text, "user");
    history.push({ role: "user", content: text });

    const sendBtn = form.querySelector(".chat-send");
    if (sendBtn) sendBtn.disabled = true;
    input.disabled = true;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });
      const data = await res.json().catch(function () {
        return {};
      });

      if (!res.ok) {
        const detail =
          typeof data.detail === "string"
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail.map(function (d) {
                  return d.msg || d;
                }).join(" ")
              : "Error al contactar el asistente.";
        appendBubble(detail, "error");
        history.pop();
        return;
      }

      const reply = data.reply || "Sin respuesta.";
      history.push({ role: "assistant", content: reply });
      appendBubble(reply, "bot");
      if (data.note) {
        appendBubble(String(data.note), "note");
      }
    } catch (err) {
      appendBubble("No se pudo conectar con el servidor. ¿Está uvicorn en marcha?", "error");
      history.pop();
    } finally {
      input.disabled = false;
      if (sendBtn) sendBtn.disabled = false;
      input.focus();
    }
  });
})();
