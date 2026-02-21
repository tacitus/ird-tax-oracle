/* NZ Tax RAG — Frontend with Conversation Support */

const $ = (sel) => document.querySelector(sel);
const textarea = $("#question");
const form = $("#ask-form");
const askBtn = $(".ask-btn");
const sections = {
  examples: $(".examples-section"),
  error: $(".error-section"),
  conversation: $(".conversation-container"),
  disclaimer: $(".disclaimer"),
};
const newConvBtn = $(".new-conversation-btn");

const MAX_HISTORY = 5;
let conversationHistory = []; // {question, answer} pairs
let lastQuestion = "";
let currentQueryId = null;
let currentAnswerEl = null; // the active .conv-answer element being streamed into
let typingIndicatorEl = null; // the active typing indicator element

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

/* Inline typing indicator */
function showTypingIndicator() {
  const el = document.createElement("div");
  el.className = "conv-typing-indicator";
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.innerHTML = `
    <div class="loading-dots" aria-hidden="true"><span></span><span></span><span></span></div>
    <div class="typing-status">Searching IRD guidance...</div>
  `;
  sections.conversation.appendChild(el);
  typingIndicatorEl = el;
  scrollToBottom();
}

function removeTypingIndicator() {
  if (typingIndicatorEl) {
    typingIndicatorEl.remove();
    typingIndicatorEl = null;
  }
}

/* State management */
function showLanding() {
  sections.examples.hidden = false;
  sections.error.hidden = true;
  sections.conversation.hidden = true;
  sections.disclaimer.hidden = false;
  newConvBtn.hidden = true;
  askBtn.disabled = false;
  removeTypingIndicator();
}

function showConversation() {
  sections.examples.hidden = true;
  sections.error.hidden = true;
  sections.conversation.hidden = false;
  newConvBtn.hidden = false;
  askBtn.disabled = false;
}

function showError(msg) {
  removeTypingIndicator();
  sections.error.hidden = false;
  $(".error-section p").textContent = msg;
  sections.error.focus();
  askBtn.disabled = false;
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
  textarea.value = "";
  textarea.style.height = "auto";
  await submitQuestion(question);
});

/* Add a user question bubble to the conversation */
function addQuestionBubble(question) {
  const bubble = document.createElement("div");
  bubble.className = "conv-question";
  bubble.textContent = question;
  sections.conversation.appendChild(bubble);
}

/* Create an answer block and append to conversation. Returns the element. */
function createAnswerBlock() {
  const block = document.createElement("div");
  block.className = "conv-answer";
  block.tabIndex = -1;
  block.innerHTML = `
    <div class="tools-used" hidden aria-label="Tools used"></div>
    <div class="answer-content"></div>
    <div class="sources" hidden>
      <h2 class="sources-label">Sources</h2>
      <ul class="sources-list"></ul>
    </div>
    <div class="answer-footer">
      <div class="model-attr"></div>
      <div class="feedback-bar" hidden>
        <span class="feedback-label">Was this helpful?</span>
        <button class="feedback-btn" data-feedback="positive" aria-label="Thumbs up">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8.5 1.5l-1 3.5H3a1 1 0 00-1 1v6a1 1 0 001 1h2l1.5 1.5h5a1 1 0 001-.8l1-5a1 1 0 00-1-1.2H9.5l.7-2.5a1.5 1.5 0 00-1.7-1.5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
        </button>
        <button class="feedback-btn" data-feedback="negative" aria-label="Thumbs down">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M7.5 14.5l1-3.5H13a1 1 0 001-1V4a1 1 0 00-1-1h-2L9.5 1.5h-5a1 1 0 00-1 .8l-1 5a1 1 0 001 1.2H6.5l-.7 2.5a1.5 1.5 0 001.7 1.5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
        </button>
        <span class="feedback-thanks" hidden>Thanks for your feedback!</span>
      </div>
    </div>
  `;
  sections.conversation.appendChild(block);

  // Wire up feedback buttons for this answer block
  block.querySelectorAll(".feedback-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleFeedback(btn, block));
  });

  return block;
}

/* Scroll to the bottom of the conversation */
function scrollToBottom() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

/* Main submit — try streaming, fall back to non-streaming */
async function submitQuestion(question) {
  setQueryParam(question);

  // Switch to conversation mode
  sections.examples.hidden = true;
  sections.conversation.hidden = false;
  sections.error.hidden = true;
  newConvBtn.hidden = false;

  // Add question bubble + inline typing indicator
  addQuestionBubble(question);
  askBtn.disabled = true;
  showTypingIndicator();

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);

  try {
    /* Try streaming endpoint first */
    const resp = await fetch("/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: conversationHistory.slice(-MAX_HISTORY),
      }),
      signal: controller.signal,
    });

    /* If streaming endpoint doesn't exist, fall back */
    if (resp.status === 404) {
      clearTimeout(timeout);
      await submitQuestionFallback(question);
      return;
    }

    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.detail || `Server error (${resp.status})`);
    }

    let fullText = "";
    let sources = [];
    let model = "";
    let answerStarted = false;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6);
        if (!jsonStr) continue;

        let event;
        try {
          event = JSON.parse(jsonStr);
        } catch {
          continue;
        }

        if (event.type === "status") {
          if (typingIndicatorEl) {
            const statusEl = typingIndicatorEl.querySelector(".typing-status");
            if (statusEl) statusEl.textContent = event.message;
          }
        } else if (event.type === "tool_use") {
          // Create answer block on first tool_use if not yet created
          if (!answerStarted) {
            removeTypingIndicator();
            currentAnswerEl = createAnswerBlock();
            answerStarted = true;
          }
          addToolPillTo(currentAnswerEl, event.label || event.tool, event.tool);
          scrollToBottom();
        } else if (event.type === "chunk") {
          // Create answer block on first chunk if not yet created
          if (!answerStarted) {
            removeTypingIndicator();
            currentAnswerEl = createAnswerBlock();
            answerStarted = true;
          }
          fullText += event.delta;
          const html = DOMPurify.sanitize(marked.parse(fullText), {
            ADD_ATTR: ["target"],
          });
          currentAnswerEl.querySelector(".answer-content").innerHTML = html;
          scrollToBottom();
        } else if (event.type === "sources") {
          sources = event.sources || [];
        } else if (event.type === "done") {
          model = event.model || "";
          currentQueryId = event.query_id || null;
        } else if (event.type === "error") {
          throw new Error(event.message || "Stream error");
        }
      }
    }

    clearTimeout(timeout);

    // Ensure indicator is removed even if no chunks arrived
    removeTypingIndicator();

    // If no answer block was created (edge case), create one now
    if (!currentAnswerEl) {
      currentAnswerEl = createAnswerBlock();
    }

    /* Render sources, model, and feedback */
    renderSourcesIn(currentAnswerEl, sources);
    if (model) {
      currentAnswerEl.querySelector(".model-attr").textContent = `Answered by ${model}`;
    }
    if (currentQueryId) {
      currentAnswerEl.querySelector(".feedback-bar").hidden = false;
      // Store query_id on the element for feedback
      currentAnswerEl.dataset.queryId = currentQueryId;
    }

    // Push to conversation history
    conversationHistory.push({ question, answer: fullText });
    // Cap history
    if (conversationHistory.length > MAX_HISTORY) {
      conversationHistory = conversationHistory.slice(-MAX_HISTORY);
    }

    showConversation();
    textarea.focus();
    scrollToBottom();
  } catch (err) {
    clearTimeout(timeout);
    removeTypingIndicator();
    const msg =
      err.name === "AbortError"
        ? "Request timed out. The server may be busy \u2014 please try again."
        : err.message || "Something went wrong.";
    showError(msg);
  }
}

/* Non-streaming fallback */
async function submitQuestionFallback(question) {
  // Typing indicator is already showing from submitQuestion;
  // if called directly, ensure it's visible
  if (!typingIndicatorEl) {
    askBtn.disabled = true;
    showTypingIndicator();
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  try {
    const resp = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: conversationHistory.slice(-MAX_HISTORY),
      }),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!resp.ok) {
      const body = await resp.json().catch(() => null);
      throw new Error(body?.detail || `Server error (${resp.status})`);
    }

    const data = await resp.json();

    removeTypingIndicator();
    currentAnswerEl = createAnswerBlock();

    // Render tools
    if (data.tools_used && data.tools_used.length) {
      data.tools_used.forEach((t) =>
        addToolPillTo(currentAnswerEl, t.label, t.name)
      );
    }

    // Render answer
    const html = DOMPurify.sanitize(marked.parse(data.answer), {
      ADD_ATTR: ["target"],
    });
    currentAnswerEl.querySelector(".answer-content").innerHTML = html;

    // Render sources
    renderSourcesIn(currentAnswerEl, data.sources);

    // Model attribution
    currentAnswerEl.querySelector(".model-attr").textContent =
      `Answered by ${data.model}`;

    // Feedback
    currentQueryId = data.query_id || null;
    if (currentQueryId) {
      currentAnswerEl.querySelector(".feedback-bar").hidden = false;
      currentAnswerEl.dataset.queryId = currentQueryId;
    }

    // Push to history
    conversationHistory.push({ question, answer: data.answer });
    if (conversationHistory.length > MAX_HISTORY) {
      conversationHistory = conversationHistory.slice(-MAX_HISTORY);
    }

    showConversation();
    textarea.focus();
    scrollToBottom();
  } catch (err) {
    clearTimeout(timeout);
    removeTypingIndicator();
    const msg =
      err.name === "AbortError"
        ? "Request timed out. The server may be busy \u2014 please try again."
        : err.message || "Something went wrong.";
    showError(msg);
  }
}

/* Open markdown-rendered links in new tabs */
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.getAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

const TOOL_ICONS = {
  calculate_income_tax: "\u{1F9EE}",
  calculate_paye: "\u{1F9EE}",
  calculate_student_loan_repayment: "\u{1F9EE}",
  calculate_acc_levy: "\u{1F9EE}",
  search_tax_documents: "\u{1F50D}",
};

function addToolPillTo(answerEl, label, toolName) {
  const container = answerEl.querySelector(".tools-used");
  const pill = document.createElement("span");
  pill.className = "tool-pill";
  const icon = document.createElement("span");
  icon.className = "tool-pill-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = TOOL_ICONS[toolName] || "\u{1F9EE}";
  pill.appendChild(icon);
  pill.appendChild(document.createTextNode(label));
  container.appendChild(pill);
  container.hidden = false;
}

function renderSourcesIn(answerEl, sources) {
  const sourcesEl = answerEl.querySelector(".sources");
  const list = answerEl.querySelector(".sources-list");
  list.innerHTML = "";
  if (sources && sources.length) {
    sources.forEach((s) => {
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
        const clean = s.section_title.replace(/\*{1,2}|_{1,2}/g, "");
        const span = document.createElement("span");
        span.className = "source-section";
        span.textContent = ` > ${clean}`;
        li.appendChild(span);
      }
      list.appendChild(li);
    });
    sourcesEl.hidden = false;
  } else {
    sourcesEl.hidden = true;
  }
}

/* Example cards */
document.querySelectorAll(".example-card").forEach((card) => {
  card.addEventListener("click", () => {
    const q = card.dataset.question;
    submitQuestion(q);
  });
});

/* New conversation */
newConvBtn.addEventListener("click", () => {
  clearQueryParam();
  conversationHistory = [];
  sections.conversation.innerHTML = "";
  currentQueryId = null;
  currentAnswerEl = null;
  typingIndicatorEl = null;
  textarea.value = "";
  textarea.style.height = "auto";
  showLanding();
  textarea.focus();
});

/* Feedback handler (per answer block) */
async function handleFeedback(btn, answerEl) {
  const queryId = answerEl.dataset.queryId;
  if (!queryId) return;
  const feedback = btn.dataset.feedback;

  /* Optimistic UI update */
  answerEl.querySelectorAll(".feedback-btn").forEach((b) => {
    b.disabled = true;
    b.classList.remove("selected");
  });
  btn.classList.add("selected");

  try {
    const resp = await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query_id: queryId, feedback }),
    });
    if (resp.ok) {
      answerEl.querySelector(".feedback-label").hidden = true;
      answerEl.querySelectorAll(".feedback-btn").forEach((b) => {
        if (b !== btn) b.hidden = true;
      });
      answerEl.querySelector(".feedback-thanks").hidden = false;
    }
  } catch {
    /* Silently fail — feedback is non-critical */
    answerEl.querySelectorAll(".feedback-btn").forEach((b) => {
      b.disabled = false;
    });
  }
}

/* Retry */
$(".retry-btn").addEventListener("click", () => {
  if (lastQuestion) submitQuestion(lastQuestion);
});

/* Initial state — auto-submit if ?q= is present */
const initialQuery = getQueryParam();
if (initialQuery) {
  lastQuestion = initialQuery;
  submitQuestion(initialQuery);
} else {
  showLanding();
}
