/* NZ Tax RAG — Frontend */

const $ = (sel) => document.querySelector(sel);
const textarea = $("#question");
const form = $("#ask-form");
const askBtn = $(".ask-btn");
const sections = {
  ask: $(".ask-card"),
  examples: $(".examples-section"),
  loading: $(".loading-section"),
  answer: $(".answer-section"),
  error: $(".error-section"),
};

let lastQuestion = "";

/* URL permalink helpers */
function setQueryParam(question) {
  if (question.length > 1800) return;
  const url = new URL(window.location);
  url.searchParams.set("q", question);
  history.replaceState(null, "", url);
}

function clearQueryParam() {
  const url = new URL(window.location);
  url.searchParams.delete("q");
  history.replaceState(null, "", url.pathname);
}

function getQueryParam() {
  return new URLSearchParams(window.location.search).get("q");
}

function showState(state) {
  sections.loading.hidden = state !== "loading";
  sections.answer.hidden = state !== "answer";
  sections.error.hidden = state !== "error";
  sections.examples.hidden = state === "loading" || state === "answer";
  sections.ask.hidden = state === "loading";
  askBtn.disabled = state === "loading";
}

/* Auto-resize textarea */
textarea.addEventListener("input", () => {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 160) + "px";
});

/* Enter submits, Shift+Enter inserts newline */
textarea.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

/* Form submit */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = textarea.value.trim();
  if (!question) return;
  lastQuestion = question;
  await submitQuestion(question);
});

async function submitQuestion(question) {
  setQueryParam(question);
  showState("loading");

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.detail || `Server error (${resp.status})`);
    }

    const data = await resp.json();
    renderAnswer(data);
    showState("answer");
    sections.answer.focus();
  } catch (err) {
    clearTimeout(timeout);
    const msg =
      err.name === "AbortError"
        ? "Request timed out. The server may be busy — please try again."
        : err.message || "Something went wrong.";
    $(".error-section p").textContent = msg;
    showState("error");
    sections.error.focus();
  }
}

/* Open markdown-rendered links in new tabs */
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.getAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

function renderAnswer(data) {
  /* Markdown → sanitised HTML */
  const html = DOMPurify.sanitize(marked.parse(data.answer), {
    ADD_ATTR: ["target"],
  });
  $(".answer-content").innerHTML = html;

  /* Sources */
  const list = $(".sources-list");
  list.innerHTML = "";
  if (data.sources && data.sources.length) {
    data.sources.forEach((s) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      const label = s.title || s.url;
      a.textContent = label;
      const srHint = document.createElement("span");
      srHint.className = "visually-hidden";
      srHint.textContent = " (opens in new tab)";
      a.appendChild(srHint);
      li.appendChild(a);
      if (s.section_title) {
        const span = document.createElement("span");
        span.className = "source-section";
        span.textContent = ` — ${s.section_title}`;
        li.appendChild(span);
      }
      list.appendChild(li);
    });
    $(".sources").hidden = false;
  } else {
    $(".sources").hidden = true;
  }

  /* Model attribution */
  $(".model-attr").textContent = `Answered by ${data.model}`;
}

/* Example cards */
document.querySelectorAll(".example-card").forEach((card) => {
  card.addEventListener("click", () => {
    const q = card.dataset.question;
    textarea.value = q;
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + "px";
    submitQuestion(q);
  });
});

/* Ask another */
$(".ask-another-btn").addEventListener("click", () => {
  clearQueryParam();
  textarea.value = "";
  textarea.style.height = "auto";
  showState("empty");
  textarea.focus();
});

/* Copy link */
$(".copy-link-btn").addEventListener("click", () => {
  const btn = $(".copy-link-btn");
  const url = window.location.href;

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url).then(() => showCopied(btn));
  } else {
    /* Fallback for insecure contexts */
    const ta = document.createElement("textarea");
    ta.value = url;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    showCopied(btn);
  }
});

function showCopied(btn) {
  btn.textContent = "Copied!";
  btn.classList.add("copied");
  setTimeout(() => {
    btn.textContent = "Copy link";
    btn.classList.remove("copied");
  }, 2000);
}

/* Retry */
$(".retry-btn").addEventListener("click", () => {
  if (lastQuestion) submitQuestion(lastQuestion);
});

/* Initial state — auto-submit if ?q= is present */
const initialQuery = getQueryParam();
if (initialQuery) {
  textarea.value = initialQuery;
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 160) + "px";
  lastQuestion = initialQuery;
  submitQuestion(initialQuery);
} else {
  showState("empty");
}
