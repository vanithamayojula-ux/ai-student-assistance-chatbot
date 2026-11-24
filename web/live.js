/* Connects the Stitch pages to the FastAPI backend (/api/*).
   Each page keeps its Stitch markup; this script swaps the sample content for live data.
   Text from the server is inserted with textContent, never innerHTML. */
(() => {
  "use strict";

  const STORE = "shd.conversations.v1";          // shared with classic.html
  const GEN_KEY = "shd.generator";
  const PAGE = (location.pathname.split("/").pop() || "index.html").replace(/\.html$/, "") || "index";
  const params = new URLSearchParams(location.search);

  const STARTERS = [
    { cat: "regulations", q: "What is the minimum attendance required?" },
    { cat: "regulations", q: "What is the fee for re-evaluation of an answer script?" },
    { cat: "notices", q: "When is the last date to pay the semester fee without a late fine?" },
    { cat: "syllabus", q: "How are the marks divided in Data Structures?" },
    { cat: "policies", q: "How much similarity is allowed in an assignment before it counts as plagiarism?" },
    { cat: "faqs", q: "When does the hostel gate close at night?" },
    { cat: "faqs", q: "How do I apply for a duplicate ID card?" },
  ];
  const CAT_STYLE = {
    syllabus: { icon: "menu_book", tag: "SYL", color: "bg-blue-50 text-blue-800" },
    regulations: { icon: "gavel", tag: "REG", color: "bg-red-50 text-red-700" },
    notices: { icon: "campaign", tag: "NOTICE", color: "bg-amber-50 text-amber-800" },
    faqs: { icon: "help", tag: "FAQ", color: "bg-purple-50 text-purple-800" },
    policies: { icon: "policy", tag: "POL", color: "bg-emerald-50 text-emerald-800" },
  };
  const METHOD = { bm25: "BM25 keywords", dense: "Dense embeddings", hybrid: "Hybrid retrieval", rerank: "Hybrid + reranker" };
  const GEN_BADGE = { extractive: "Quoted from documents", gemini: "Written by Gemini", claude: "Written by Claude", none: "Help desk" };

  /* ---------- small helpers ---------- */
  // Shortcuts: $ finds the first element matching a CSS selector, $$ finds all of them.
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // Build an HTML element in one call: tag name, attributes/events, then child nodes.
  // Text is set with textContent, so text coming from the server can never run as code (prevents XSS).
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === false || value == null) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child == null || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }
  // A Material Symbols icon, by its name.
  const icon = (name, cls = "") => el("span", { class: `material-symbols-outlined ${cls}`, text: name });

  // Replace the text node whose trimmed value matches `from` (string or RegExp). Returns its parent element.
  function swapText(root, from, to) {
    if (!root) return null;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n; (n = walker.nextNode());) {
      const value = n.nodeValue.trim();
      if (from instanceof RegExp ? from.test(value) : value === from) {
        n.nodeValue = String(to);
        return n.parentElement;
      }
    }
    return null;
  }
  // Find the first element matching `sel` whose text contains `text`.
  const byText = (sel, text, root = document) => $$(sel, root).find((n) => n.textContent.trim().includes(text));
  // Hide an element.
  const hide = (node) => node && node.classList.add("hidden");
  // Drop the listeners Stitch's own inline script attached, keeping the element in place.
  function fresh(node) { if (!node) return node; const copy = node.cloneNode(true); node.replaceWith(copy); return copy; }

  // Formatting helpers: pct(0.875) -> "87.5%"; plural(2, "document") -> "2 documents";
  // stripCites removes the [1] markers and ** from an answer.
  const pct = (x, digits = 1) => (x == null ? "—" : `${(x * 100).toFixed(digits).replace(/\.0$/, "")}%`);
  const plural = (n, word, many = word + "s") => `${n} ${n === 1 ? word : many}`;
  const stripCites = (text) => (text || "").replace(/\s*\[\d+\]/g, "").replace(/\*\*/g, "").trim();

  // Show a date in a readable form, e.g. "5 Dec 2026".
  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  // A friendly time: "Today, 3:10 PM", "Yesterday" or "Dec 5".
  function fmtWhen(ms, withTime = false) {
    const d = new Date(ms), now = new Date();
    const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (d.toDateString() === now.toDateString()) return withTime ? `Today, ${time}` : time;
    const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return withTime ? `Yesterday, ${time}` : "Yesterday";
    const date = d.toLocaleDateString([], { month: "short", day: "numeric" });
    return withTime ? `${date}, ${time}` : date;
  }

  /* ---------- toast ---------- */
  let toastTimer;
  // Show a small pop-up message at the bottom of the screen for a few seconds (red when it is an error).
  function toast(message, bad = false) {
    let node = $("#live-toast");
    if (!node) {
      node = el("div", { id: "live-toast", role: "status", "aria-live": "polite" });
      document.body.append(node);
    }
    node.className = `fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] max-w-[90vw] px-4 py-2.5 rounded-xl shadow-lg font-label-md text-label-md transition-opacity duration-300 ${bad ? "bg-error text-on-error" : "bg-inverse-surface text-inverse-on-surface"}`;
    node.textContent = message;
    node.style.opacity = "1";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { node.style.opacity = "0"; }, 3800);
  }

  /* ---------- API ---------- */
  // Call the backend and return its JSON reply; a failed request becomes a readable error message.
  async function api(path, init = {}) {
    let response;
    try { response = await fetch(path, init); }
    catch { throw new Error("Can't reach the server. Start it with: python -m uvicorn app.main:app --port 8000"); }
    let body = null;
    try { body = await response.json(); } catch { /* not JSON */ }
    if (!response.ok) {
      const detail = typeof body?.detail === "string" ? body.detail : `The server answered ${response.status}.`;
      throw new Error(detail);
    }
    return body;
  }
  let healthCache = null;
  // The system status (GET /api/health) and the document list (GET /api/documents) are fetched once
  // and then reused (cached). refreshCorpus() clears both after an upload or a delete.
  const health = () => (healthCache ||= api("/api/health"));
  let docsCache = null;
  const loadDocs = () => (docsCache ||= api("/api/documents").then((r) => r.documents));
  const refreshCorpus = () => { healthCache = null; docsCache = null; };
  // Display name of a category id, e.g. "faqs" -> "FAQs".
  const catLabel = (h, id) => h?.categories?.find((c) => c.id === id)?.label || (id ? id[0].toUpperCase() + id.slice(1) : "All documents");

  // Send a question to POST /api/chat and read the reply as a STREAM.
  // The server sends one JSON event per line; onEvent is called for each one as it arrives,
  // so the answer can appear on screen while it is still being written.
  async function streamChat(body, onEvent) {
    let response;
    try {
      response = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } catch { throw new Error("Can't reach the server. Start it with: python -m uvicorn app.main:app --port 8000"); }
    if (!response.ok || !response.body) {
      let detail = "";
      try { detail = (await response.json()).detail; } catch { /* not JSON */ }
      throw new Error(typeof detail === "string" && detail ? detail : `The server could not answer (${response.status}).`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer));
  }

  /* ---------- uploads ---------- */
  // Open the browser's file picker and return the chosen file (or null).
  function chooseFile() {
    return new Promise((resolve) => {
      const input = el("input", { type: "file", accept: ".pdf,.docx,.md,.txt", class: "hidden" });
      input.addEventListener("change", () => { resolve(input.files[0] || null); input.remove(); });
      document.body.append(input);
      input.click();
    });
  }
  // Send a file and its category to the backend (POST /api/documents). The server re-indexes at once.
  async function uploadFile(file, category) {
    const form = new FormData();
    form.append("file", file);
    form.append("category", category);
    toast(`Reading ${file.name}…`);
    const result = await api("/api/documents", { method: "POST", body: form });
    refreshCorpus();
    toast(`${result.replaced ? "Replaced" : "Added"} “${result.title}” (${plural(result.sections, "section")}).`);
    return result;
  }
  // A small menu of the five categories, opened under `anchor`.
  async function pickCategory(anchor) {
    const h = await health();
    $("#live-menu")?.remove();
    return new Promise((resolve) => {
      const box = anchor.getBoundingClientRect();
      const menu = el("div", {
        id: "live-menu", role: "menu",
        class: "fixed z-[90] w-56 bg-surface-container-lowest rounded-lg shadow-xl py-1 flex flex-col font-label-md text-label-md text-on-surface",
        style: `top:${Math.min(box.bottom + 6, innerHeight - 260)}px;left:${Math.max(8, Math.min(box.left, innerWidth - 232))}px`,
      }, el("span", { class: "px-3 pt-1.5 pb-1 font-label-sm text-label-sm text-outline uppercase tracking-wider", text: "Add to category" }));
      for (const c of h.categories) {
        menu.append(el("button", { type: "button", role: "menuitem", class: "px-3 py-2 text-left hover:bg-surface-container-low", text: c.label,
          onclick: () => { menu.remove(); resolve(c.id); } }));
      }
      const close = (event) => {
        if (menu.contains(event.target)) return;
        menu.remove(); document.removeEventListener("pointerdown", close, true); resolve(null);
      };
      setTimeout(() => document.addEventListener("pointerdown", close, true));
      document.body.append(menu);
      menu.querySelector("button")?.focus();
    });
  }
  // The whole upload flow: pick a category, pick a file, upload it.
  async function pickAndUpload(anchor, fixedCategory) {
    try {
      const category = fixedCategory || (await pickCategory(anchor));
      if (!category) return null;
      const file = await chooseFile();
      if (!file) return null;
      return await uploadFile(file, category);
    } catch (error) { toast(error.message, true); return null; }
  }

  /* ---------- conversations (browser storage) ---------- */
  // Conversations are kept in the browser's localStorage (on this device, not on the server):
  // loadConvs reads them, saveConvs writes the 30 most recent.
  function loadConvs() { try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; } }
  function saveConvs(list) { try { localStorage.setItem(STORE, JSON.stringify(list.slice(0, 30))); } catch { /* storage full */ } }
  // Small helpers over one conversation: when it was last used, its questions, its finished answers.
  const when = (c) => Number(c.at || c.id) || Date.now();
  const questionsOf = (c) => c.messages.filter((m) => m.role === "user");
  const answersOf = (c) => c.messages.filter((m) => m.role !== "user" && !m.pending);
  // The documents cited across a conversation, with how many times each was cited.
  function citedDocs(c) {
    const seen = new Map();
    for (const m of answersOf(c)) for (const s of m.sources || []) {
      if (!s.cited) continue;
      const key = s.doc_id;
      if (!seen.has(key)) seen.set(key, { ...s, count: 0 });
      seen.get(key).count++;
    }
    return [...seen.values()];
  }
  // The document category cited most in a conversation (used as its topic label).
  function convCategory(c) {
    const counts = {};
    for (const m of answersOf(c)) for (const s of m.sources || []) if (s.cited) counts[s.category] = (counts[s.category] || 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
  }
  // The conversation as markdown text (questions, answers and cited sources), for copy and download.
  function transcript(c) {
    const lines = [`# ${c.title}`, ""];
    for (const m of c.messages) {
      if (m.role === "user") lines.push(`**Question:** ${m.content}`, "");
      else {
        lines.push(`**Answer:** ${m.content}`, "");
        const cited = (m.sources || []).filter((s) => s.cited);
        for (const s of cited) lines.push(`- [${s.n}] ${s.title} — ${s.section}`);
        if (cited.length) lines.push("");
      }
    }
    return lines.join("\n");
  }
  // Make the browser download some text as a file.
  function download(name, text, type = "text/markdown") {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = el("a", { href: url, download: name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  // A safe file name made from a conversation title.
  const fileName = (title) => (title || "conversation").replace(/[^\w-]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) + ".md";

  /* ---------- rendering passage text ---------- */
  // Add text to an element, turning **bold** markdown into real bold text.
  function inline(text, parent) {
    text.split(/(\*\*[^*]+\*\*)/g).forEach((part) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) parent.append(el("strong", { class: "font-semibold", text: part.slice(2, -2) }));
      else if (part) parent.append(part);
    });
    return parent;
  }
  const MARK = "bg-primary/15 text-on-surface rounded px-0.5";
  // Split a markdown table row "| a | b |" into its cells.
  const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  // Draw a passage (paragraphs, lists, tables). Sentences marked "hit" are the evidence
  // for the answer, so they are wrapped in <mark> and appear highlighted.
  function renderBlocks(blocks, textClass = "") {
    const root = el("div", { class: `flex flex-col gap-3 ${textClass}` });
    for (const block of blocks) {
      if (block.kind === "table") {
        const [head, ...rows] = block.units;
        root.append(el("div", { class: "overflow-x-auto" }, el("table", { class: "w-full text-left border-collapse text-[0.95em]" },
          el("thead", {}, el("tr", { class: "bg-surface-container-low" }, cells(head.text).map((c) => inline(c, el("th", { class: "py-1.5 px-2 font-semibold", scope: "col" }))))),
          el("tbody", {}, rows.map((row) => el("tr", { class: row.hit ? "bg-primary/10" : "" },
            cells(row.text).map((c) => inline(c, el("td", { class: "py-1.5 px-2 align-top" })))))))));
      } else if (block.kind === "list") {
        root.append(el("ul", { class: "list-disc pl-5 space-y-1" }, block.units.map((unit) => {
          const li = el("li");
          inline(unit.text.replace(/^(?:[-+*]|\d+[.)])\s+/, ""), unit.hit ? li.appendChild(el("mark", { class: MARK })) : li);
          return li;
        })));
      } else {
        const p = el("p", { class: "leading-relaxed" });
        block.units.forEach((unit, i) => {
          if (i) p.append(" ");
          inline(unit.text, unit.hit ? p.appendChild(el("mark", { class: MARK })) : p);
        });
        root.append(p);
      }
    }
    return root;
  }

  /* ---------- shared chrome: sidebar status, search box ---------- */
  // Runs on every page: the header search box opens the document explorer, and the sample status
  // text is replaced by the real number of documents and passages from the server.
  async function decorate() {
    const status = $$("span").filter((s) => /^Spring 2025 . (KB Connected|Active Node)$/.test(s.textContent.trim()));
    const searchBoxes = $$("header div").filter((d) => /^search\s*Search (knowledge base|campus papers)/.test(d.textContent.trim().replace(/\s+/g, " ")));
    for (const box of searchBoxes) {
      box.style.cursor = "pointer";
      box.setAttribute("role", "link");
      box.setAttribute("tabindex", "0");
      box.title = "Search the documents";
      // Open the document explorer with its search box focused.
      const go = () => { location.href = "documents.html?focus=search"; };
      box.addEventListener("click", go);
      box.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    }
    if (PAGE !== "chat" && PAGE !== "documents") {
      document.addEventListener("keydown", (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); location.href = "documents.html?focus=search"; }
      });
    }
    try {
      const h = await health();
      status.forEach((s) => { s.textContent = `${plural(h.documents, "document")} • ${h.passages} passages`; });
      $$("span").filter((s) => s.textContent.trim() === "Campus Research Engine").forEach((s) => { s.textContent = h.university; s.title = h.university; });
    } catch {
      status.forEach((s) => {
        s.textContent = "Server offline";
        s.previousElementSibling?.classList.replace("bg-primary", "bg-error");
      });
    }
  }

  /* =====================================================================
     Chat
     ===================================================================== */
  // CHAT PAGE (chat.html). Sets up the conversation list, the message thread, the question box and
  // all buttons. The functions inside it share one `state` object (conversations, current chat, busy flag).
  function initChat() {
    const aside = $("main aside");
    const [newBtn, searchWrap, listBox, kbCard] = aside.firstElementChild.children;
    const search = $("input", searchWrap);
    const center = $("main main");
    const [head, thread, composer] = center.children;
    const title = $("h1", head);
    const pill = title.nextElementSibling;
    const subtitle = title.parentElement.nextElementSibling;
    const modelPill = $$("div", head).find((d) => d.className.includes("lg:flex"));
    const [shareBtn, downloadBtn] = $$(":scope > div:last-child > button", head);
    const textarea = $("textarea", composer);
    const [uploadBtn, corpusBtn, micBtn, sendBtn] = $$("button", composer);
    const hint = byText("span", "⌘ + Enter", composer);

    const state = { convs: loadConvs(), currentId: null, busy: false, category: null, health: null };
    // The conversation that is open right now (or null).
    const current = () => state.convs.find((c) => c.id === state.currentId) || null;
    // The confidence threshold the server uses to decide whether to answer or decline.
    const threshold = () => state.health?.threshold ?? 0.58;

    textarea.id = "question";
    textarea.setAttribute("aria-label", "Your question");
    textarea.maxLength = 1000;
    sendBtn.setAttribute("aria-label", "Send");
    if (hint) hint.textContent = "Enter to send";
    newBtn.querySelector("kbd")?.replaceChildren("Ctrl K");
    thread.setAttribute("aria-live", "polite");

    /* generator picker inside the model pill */
    const genSelect = el("select", { class: "bg-transparent font-label-md text-label-md text-on-surface focus:outline-none cursor-pointer max-w-[12rem]", "aria-label": "Answer with" },
      el("option", { value: "extractive", text: "Quote the documents" }));
    modelPill.children[1].replaceWith(genSelect);
    const methodTag = modelPill.children[2];
    genSelect.addEventListener("change", () => { try { localStorage.setItem(GEN_KEY, genSelect.value); } catch { /* ignore */ } });

    // Limit the search to one document category (or all documents) and show the choice.
    function setCategory(id) {
      state.category = id || null;
      const label = catLabel(state.health, state.category);
      pill.textContent = label;
      corpusBtn.children[1].textContent = state.category ? label : "All documents";
    }

    /* conversation list */
    // One row of the conversation list in the sidebar.
    function listItem(c) {
      const active = c.id === state.currentId;
      return el("a", {
        href: `chat.html?c=${encodeURIComponent(c.id)}`,
        class: active
          ? "group relative flex items-center justify-between p-2.5 rounded-lg bg-surface-container-lowest shadow-sm hover:bg-surface-container transition-colors"
          : "group flex items-center justify-between p-2.5 rounded-lg hover:bg-surface-container text-on-surface-variant transition-colors",
        "aria-current": active ? "page" : null,
        onclick: (e) => { e.preventDefault(); openConv(c.id); },
      },
      el("div", { class: "flex items-center gap-space-xs min-w-0 pr-2" },
        icon(active ? "forum" : "chat_bubble_outline", `${active ? "text-primary" : "text-secondary"} text-lg flex-shrink-0`),
        el("span", { class: `font-body-md text-body-md truncate ${active ? "text-on-surface font-medium" : ""}`, text: c.title })),
      active ? el("span", { class: "w-2 h-2 rounded-full bg-primary flex-shrink-0" })
        : el("span", { class: "font-label-sm text-label-sm text-outline whitespace-nowrap", text: fmtWhen(when(c)) }));
    }
    // Redraw the sidebar: saved conversations, filtered by the search box, grouped into Today / Earlier.
    function renderList() {
      const q = search.value.trim().toLowerCase();
      const items = state.convs.filter((c) => !q || c.title.toLowerCase().includes(q) || c.messages.some((m) => m.content.toLowerCase().includes(q)));
      const today = new Date().toDateString();
      listBox.replaceChildren();
      const groups = [["Today", items.filter((c) => new Date(when(c)).toDateString() === today)],
                      ["Earlier", items.filter((c) => new Date(when(c)).toDateString() !== today)]];
      for (const [label, list] of groups) {
        if (!list.length) continue;
        listBox.append(el("div", { class: "flex flex-col gap-1" },
          el("div", { class: "flex items-center justify-between px-space-xs py-1" },
            el("span", { class: "font-label-sm text-label-sm text-outline uppercase tracking-wider", text: label }),
            el("span", { class: "font-label-sm text-label-sm text-primary font-bold", text: String(list.length) })),
          list.map(listItem)));
      }
      if (!items.length) {
        listBox.append(el("p", { class: "px-space-xs py-2 font-body-sm text-body-sm text-outline",
          text: q ? "No conversations match." : "Your conversations will appear here." }));
      }
    }

    /* messages */
    // The bubble for a question the student asked.
    function userNode(m) {
      return el("div", { class: "flex items-start gap-space-md max-w-4xl" },
        el("div", { class: "w-10 h-10 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center flex-shrink-0 shadow-sm mt-0.5" }, icon("person", "text-2xl")),
        el("div", { class: "flex flex-col gap-1.5 min-w-0" },
          el("div", { class: "flex items-center gap-space-xs" },
            el("span", { class: "font-label-md text-label-md text-on-surface font-semibold", text: "You" }),
            m.at ? el("span", { class: "font-label-sm text-label-sm text-outline", text: fmtWhen(m.at, true) }) : null),
          el("div", { class: "bg-surface-container-lowest p-space-md rounded-2xl rounded-tl-sm shadow-sm text-on-surface font-body-lg text-body-lg whitespace-pre-wrap break-words", text: m.content })));
    }

    // Draw the answer text. Every citation like [1] becomes a button that jumps to that source card.
    function renderAnswer(text, m, key) {
      const frag = document.createDocumentFragment();
      let list = null;
      const fill = (line, parent) => {
        line.split(/(\[\d+\]|\*\*[^*]+\*\*)/g).forEach((part) => {
          const cite = /^\[(\d+)\]$/.exec(part);
          if (cite && m.sources?.some((s) => s.n === Number(cite[1]))) {
            parent.append(el("button", {
              type: "button", text: cite[1], "aria-label": `Show source ${cite[1]}`,
              class: "inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 mx-0.5 rounded bg-primary/10 text-primary text-[11px] font-bold align-middle hover:bg-primary hover:text-on-primary transition-colors",
              onclick: () => focusSource(key, cite[1]),
            }));
          } else if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
            parent.append(el("strong", { class: "font-semibold text-on-surface", text: part.slice(2, -2) }));
          } else if (part) parent.append(part);
        });
        return parent;
      };
      for (const raw of text.split(/\n+/)) {
        const line = raw.trim();
        if (!line) continue;
        const item = /^(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
        if (item) {
          if (!list) { list = el("ul", { class: "list-disc pl-6 space-y-1" }); frag.append(list); }
          list.append(fill(item[1], el("li")));
        } else {
          list = null;
          frag.append(fill(line.replace(/^#+\s*/, ""), el("p", { class: "leading-relaxed" })));
        }
      }
      return frag;
    }
    // Scroll to a source card and flash a ring around it.
    function focusSource(key, n) {
      const card = document.getElementById(`src-${key}-${n}`);
      if (!card) return;
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      card.classList.add("ring-2", "ring-primary");
      setTimeout(() => card.classList.remove("ring-2", "ring-primary"), 1600);
    }
    // A short preview of a source: the highlighted (evidence) sentences. Click to read the whole passage.
    function snippet(s) {
      const units = s.blocks.flatMap((b) => b.units);
      const hits = units.filter((u) => u.hit);
      const box = el("div", { class: "mt-2 text-body-sm font-body-sm text-on-surface-variant line-clamp-3 bg-surface-container-lowest p-2 rounded-lg cursor-pointer", title: "Show the whole passage" });
      const pick = hits.length ? hits : units.slice(0, 3);
      pick.forEach((u, i) => {
        if (i) box.append(" … ");
        const text = u.text.replace(/^(?:[-+*]|\d+[.)])\s+/, "").replace(/\*\*/g, "");
        box.append(u.hit ? el("mark", { class: MARK, text }) : text);
      });
      box.addEventListener("click", () => {
        if (box.dataset.full) return;
        box.dataset.full = "1";
        box.classList.remove("line-clamp-3", "cursor-pointer");
        box.replaceChildren(renderBlocks(s.blocks));
      });
      return box;
    }
    // The source cards under an answer: the cited passages, the retrieval confidence
    // (High / Medium / Low) and a link that opens the document in the explorer.
    function sourcesNode(m, key) {
      const cited = m.sources.filter((s) => s.cited);
      const shown = cited.length ? cited : m.sources;
      const conf = m.confidence;
      const level = conf == null ? "" : conf >= 0.75 ? "High" : conf >= threshold() ? "Medium" : "Low";
      return el("div", { class: "pt-2 space-y-space-sm" },
        el("div", { class: "flex items-center justify-between gap-2 flex-wrap" },
          el("span", { class: "font-label-sm text-label-sm text-outline uppercase tracking-wider flex items-center gap-1" },
            icon("verified_user", "text-sm text-primary"),
            ` ${cited.length ? "Cited passages" : m.pending ? "Passages found" : "Closest passages"} (${shown.length})`),
          conf != null ? el("span", { class: "font-label-sm text-label-sm text-secondary", text: `Retrieval confidence: ${level} (${pct(conf, 0)})` }) : null),
        el("div", { class: "grid grid-cols-1 md:grid-cols-2 gap-space-sm" }, shown.map((s) => {
          const style = CAT_STYLE[s.category] || CAT_STYLE.faqs;
          const inspect = `documents.html?doc=${encodeURIComponent(s.doc_id)}&section=${encodeURIComponent(s.section || "")}`;
          return el("div", { id: `src-${key}-${s.n}`, class: "p-space-sm bg-surface-container-low rounded-xl shadow-[0_1px_4px_rgba(0,0,0,0.02)] flex flex-col justify-between hover:bg-surface-container transition-all group" },
            el("div", {},
              el("div", { class: "flex items-start justify-between gap-space-xs" },
                el("div", { class: "flex items-center gap-2 min-w-0" },
                  icon(style.icon, "text-primary text-lg"),
                  el("div", { class: "flex flex-col min-w-0" },
                    el("span", { class: "font-label-md text-label-md text-on-surface font-semibold line-clamp-1", text: s.title }),
                    el("span", { class: "font-body-sm text-body-sm text-outline line-clamp-1", text: [catLabel(state.health, s.category), s.section].filter(Boolean).join(" • ") }))),
                el("span", { class: `px-1.5 py-0.5 rounded font-label-sm text-label-sm font-bold flex-shrink-0 ${s.cited ? "bg-primary/10 text-primary" : "bg-surface-container-high text-on-surface-variant"}`, text: `[${s.n}] ${s.cited ? "Cited" : "Found"}` })),
              snippet(s)),
            el("div", { class: "mt-2.5 pt-2 flex items-center justify-between" },
              el("a", { href: inspect, class: "text-primary hover:underline font-label-sm text-label-sm flex items-center gap-1 font-semibold" },
                el("span", { text: "Inspect in Explorer" }), icon("arrow_outward", "text-xs")),
              el("span", { class: "font-label-sm text-label-sm text-outline", text: s.updated ? `Updated ${fmtDate(s.updated)}` : (s.origin === "upload" ? "Uploaded" : "") })));
        })));
    }
    // An information box inside an answer, e.g. "Not covered by the documents".
    function callout(name, heading, body) {
      return el("div", { class: "flex items-start gap-space-sm p-space-md bg-secondary-container/40 rounded-xl text-on-secondary-fixed" },
        icon(name, "text-xl text-primary flex-shrink-0 mt-0.5"),
        el("div", { class: "flex flex-col gap-0.5" },
          el("span", { class: "font-label-md text-label-md font-bold", text: heading }),
          el("p", { class: "font-body-sm text-body-sm text-on-surface-variant leading-relaxed", text: body })));
    }
    // A small icon + label button (Copy, Regenerate).
    const toolBtn = (name, label, onclick, extra = "") => el("button", {
      type: "button", onclick,
      class: `flex items-center gap-1 px-2.5 py-1 rounded-lg hover:bg-surface-container hover:text-on-surface font-label-sm text-label-sm transition-colors ${extra}`,
    }, icon(name, "text-base"), el("span", { text: label }));

    // Send a thumbs-up/down to the backend (POST /api/feedback) and remember it.
    async function vote(m, helpful, button) {
      if (m.vote === helpful) return;
      try {
        await api("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: (m.question || "").slice(0, 1000), answer: m.content.slice(0, 6000), helpful, generator: m.generator || "" }) });
        m.vote = helpful; saveConvs(state.convs);
        toast(helpful ? "Thanks. Marked as accurate." : "Thanks. Reported so the answer can be checked.");
        button.closest("[data-msg]")?.replaceWith(botNode(m, current(), true));
      } catch (error) { toast(error.message, true); }
    }

    // Build one assistant message: the answer text, notes, source cards and the action row
    // (copy, regenerate, thumbs up/down, report).
    function botNode(m, c, isLast) {
      const key = c.messages.indexOf(m);
      const card = el("div", { class: "bg-surface-container-lowest p-space-lg rounded-2xl rounded-tl-sm shadow-sm text-on-surface space-y-space-md" });
      if (m.pending && !m.content) {
        card.append(el("div", { class: "flex items-center gap-2 font-body-md text-body-md text-on-surface-variant" },
          el("span", { class: "flex gap-1" }, [0, 150, 300].map((d) => el("span", { class: "w-1.5 h-1.5 rounded-full bg-primary animate-bounce", style: `animation-delay:${d}ms` }))),
          m.sources?.length ? "Writing the answer from the passages" : "Searching the documents"));
      } else {
        card.append(el("div", { class: "space-y-space-sm font-body-lg text-body-lg" }, renderAnswer(m.content, m, key)));
      }
      if (m.abstained && !m.pending && m.generator !== "none" && !m.error) {
        card.append(callout("gavel", "Not covered by the documents",
          "The help desk answers only from the university's documents, and the passages it found don't settle this. Try rephrasing, or ask the office concerned."));
      }
      if (m.note) card.append(callout("info", "Note", m.note));
      if (m.sources?.length) card.append(sourcesNode(m, key));

      const meta = m.pending ? "Working…" : m.latency_ms != null ? `Answered in ${(m.latency_ms / 1000).toFixed(1)} s` : (m.at ? fmtWhen(m.at, true) : "");
      const node = el("div", { class: "flex items-start gap-space-md max-w-4xl", "data-msg": String(key) },
        el("div", { class: "w-10 h-10 rounded-xl bg-primary text-on-primary flex items-center justify-center flex-shrink-0 shadow-sm mt-0.5" }, icon("school", "text-2xl")),
        el("div", { class: "flex-1 flex flex-col gap-space-md min-w-0" },
          el("div", { class: "flex items-center justify-between" },
            el("div", { class: "flex items-center gap-space-xs" },
              el("span", { class: "font-label-md text-label-md text-primary font-bold", text: "STUDY BUDDY" }),
              el("span", { class: "px-2 py-0.5 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm font-semibold", text: GEN_BADGE[m.generator] || "Official Policy Corpus" })),
            el("span", { class: "font-label-sm text-label-sm text-outline", text: meta })),
          card));
      const column = node.lastElementChild;

      if (!m.pending && !m.error) {
        const up = el("button", { type: "button", title: "Mark as accurate", "aria-pressed": String(m.vote === true),
          class: `p-1.5 rounded-lg hover:bg-surface-container hover:text-primary transition-colors ${m.vote === true ? "text-primary" : ""}` },
          icon("thumb_up", "text-base"));
        const down = el("button", { type: "button", title: "Report a wrong answer", "aria-pressed": String(m.vote === false),
          class: `p-1.5 rounded-lg hover:bg-surface-container hover:text-error transition-colors ${m.vote === false ? "text-error" : ""}` },
          icon("thumb_down", "text-base"));
        if (m.vote === true) up.firstChild.style.fontVariationSettings = "'FILL' 1";
        if (m.vote === false) down.firstChild.style.fontVariationSettings = "'FILL' 1";
        up.addEventListener("click", () => vote(m, true, up));
        down.addEventListener("click", () => vote(m, false, down));
        const report = el("button", { type: "button", class: "font-label-sm text-label-sm text-outline hover:text-error flex items-center gap-1 transition-colors", onclick: () => vote(m, false, report) },
          icon("flag", "text-sm"), el("span", { text: "Report Discrepancy" }));
        column.append(el("div", { class: "flex items-center justify-between px-space-xs" },
          el("div", { class: "flex items-center gap-space-xs text-secondary" },
            toolBtn("content_copy", "Copy", () => navigator.clipboard?.writeText(stripCites(m.content)).then(() => toast("Answer copied."), () => toast("Couldn't copy.", true))),
            isLast ? toolBtn("refresh", "Regenerate", regenerate) : null,
            el("div", { class: "h-3 w-px bg-surface-container-highest mx-1" }),
            up, down),
          report));
      }
      if (isLast && !m.pending) column.append(followUps(c));
      return node;
    }

    // A row of clickable suggested questions.
    function chips(list) {
      return el("div", { class: "flex flex-wrap gap-2" }, list.map((s) => el("button", {
        type: "button", text: `→ ${s.q}`,
        class: "px-3 py-1.5 rounded-full bg-surface-container-lowest shadow-sm hover:bg-primary/10 hover:text-primary text-on-surface font-label-md text-label-md transition-all text-left",
        onclick: () => ask(s.q),
      })));
    }
    // Suggest up to three questions not asked yet, preferring the topic of this conversation.
    function followUps(c) {
      const asked = new Set(questionsOf(c).map((m) => m.content.toLowerCase()));
      const cat = convCategory(c);
      const pool = STARTERS.filter((s) => !asked.has(s.q.toLowerCase()));
      const list = [...pool.filter((s) => s.cat === cat), ...pool.filter((s) => s.cat !== cat)].slice(0, 3);
      if (!list.length) return null;
      return el("div", { class: "flex flex-col gap-2 pt-1" },
        el("span", { class: "font-label-sm text-label-sm text-outline", text: "Other questions students ask:" }), chips(list));
    }
    // The welcome message and starter questions shown before the first question.
    function emptyState() {
      const uni = state.health?.university || "the university";
      return el("div", { class: "flex items-start gap-space-md max-w-4xl" },
        el("div", { class: "w-10 h-10 rounded-xl bg-primary text-on-primary flex items-center justify-center flex-shrink-0 shadow-sm mt-0.5" }, icon("school", "text-2xl")),
        el("div", { class: "flex-1 flex flex-col gap-space-md min-w-0" },
          el("div", { class: "flex items-center gap-space-xs" },
            el("span", { class: "font-label-md text-label-md text-primary font-bold", text: "STUDY BUDDY" }),
            el("span", { class: "px-2 py-0.5 rounded-full bg-primary/10 text-primary font-label-sm text-label-sm font-semibold", text: "Official Policy Corpus" })),
          el("div", { class: "bg-surface-container-lowest p-space-lg rounded-2xl rounded-tl-sm shadow-sm text-on-surface space-y-space-sm" },
            el("p", { class: "font-body-lg text-body-lg leading-relaxed", text: `Ask about attendance, exams, fees, hostel or syllabus. Every answer is taken from ${uni}'s own documents and shows the passage it came from. If the documents don't cover a question, you'll be told so.` })),
          el("div", { class: "flex flex-col gap-2 pt-1" },
            el("span", { class: "font-label-sm text-label-sm text-outline", text: "Try asking:" }), chips(STARTERS.slice(0, 5)))));
    }

    // Redraw the whole conversation.
    function renderThread() {
      const c = current();
      title.textContent = c ? c.title : "New conversation";
      document.title = c ? `${c.title} · AI Chatbot` : "AI Chatbot";
      thread.replaceChildren();
      if (!c || !c.messages.length) { thread.append(emptyState()); return; }
      const last = c.messages.length - 1;
      c.messages.forEach((m, i) => thread.append(m.role === "user" ? userNode(m) : botNode(m, c, i === last)));
      thread.scrollTop = thread.scrollHeight;
    }
    // Redraw only the answer that is being written (called for every streamed piece).
    function updateLast(m) {
      const c = current();
      const node = thread.querySelector(`[data-msg="${c.messages.indexOf(m)}"]`);
      if (node) node.replaceWith(botNode(m, c, true));
      thread.scrollTop = thread.scrollHeight;
    }
    // Open a saved conversation and put its id in the page address.
    function openConv(id) {
      state.currentId = id;
      history.replaceState(null, "", id ? `chat.html?c=${encodeURIComponent(id)}` : "chat.html");
      renderList(); renderThread();
    }
    // Start a new, empty conversation.
    function newConv() {
      if (state.busy) return;
      openConv(null);
      textarea.focus();
    }

    // MAIN FLOW of the chat page. Adds the question to the conversation, calls the backend through
    // streamChat and updates the answer as events arrive:
    //   "meta"  = the passages were found (shown at once, before the answer is written)
    //   "token" = one more piece of the answer text
    //   "done"  = the final answer with its sources, confidence and time taken
    // Any error becomes a visible message. The conversation is saved at the end.
    async function ask(question) {
      question = question.trim();
      if (!question || state.busy) return;
      let c = current();
      if (!c) {
        c = { id: String(Date.now()), at: Date.now(), title: question.slice(0, 60), messages: [] };
        state.convs.unshift(c);
        state.currentId = c.id;
        history.replaceState(null, "", `chat.html?c=${encodeURIComponent(c.id)}`);
      }
      const historyTurns = c.messages.filter((m) => !m.error).slice(-6)
        .map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content.slice(0, 3900) }));
      const m = { role: "bot", content: "", pending: true, question, sources: [], at: Date.now() };
      c.messages.push({ role: "user", content: question, at: Date.now() }, m);
      state.busy = true; sendBtn.disabled = true;
      textarea.value = ""; autosize();
      renderList(); renderThread();
      try {
        await streamChat({ question, history: historyTurns, generator: genSelect.value || "extractive", category: state.category }, (event) => {
          if (event.type === "meta") { m.sources = event.sources; m.confidence = event.confidence; updateLast(m); }
          else if (event.type === "token") { m.content += event.text; updateLast(m); }
          else if (event.type === "reset") { m.content = ""; updateLast(m); }
          else if (event.type === "error") throw new Error(event.message);
          else if (event.type === "done") {
            Object.assign(m, { content: event.answer, sources: event.sources, abstained: event.abstained, generator: event.generator,
              note: event.note, latency_ms: event.latency_ms, confidence: event.confidence, pending: false });
          }
        });
        if (m.pending) throw new Error("The answer stopped before it finished. Ask again.");
      } catch (error) {
        Object.assign(m, { pending: false, error: true, abstained: true, generator: "none", sources: [], content: `Something went wrong: ${error.message}` });
      } finally {
        state.busy = false; sendBtn.disabled = false;
        c.at = Date.now();
        state.convs = [c, ...state.convs.filter((x) => x !== c)];
        saveConvs(state.convs);
        renderList(); renderThread();
        textarea.focus({ preventScroll: true });
      }
    }
    // Ask the last question again (the old answer is dropped first).
    function regenerate() {
      const c = current();
      if (!c || state.busy) return;
      const lastUser = [...c.messages].reverse().find((m) => m.role === "user");
      if (!lastUser) return;
      c.messages.splice(c.messages.lastIndexOf(lastUser));
      ask(lastUser.content);
    }

    /* composer */
    // Grow the question box as the student types, up to a maximum height.
    function autosize() {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
    textarea.addEventListener("input", autosize);
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(textarea.value); }
    });
    sendBtn.addEventListener("click", () => ask(textarea.value));
    newBtn.addEventListener("click", newConv);
    search.addEventListener("input", renderList);
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); newConv(); }
    });

    uploadBtn.title = "Add a syllabus document to the library";
    uploadBtn.addEventListener("click", async () => {
      const result = await pickAndUpload(uploadBtn, "syllabus");
      if (result) { state.health = await health().catch(() => state.health); renderKb(); }
    });
    corpusBtn.setAttribute("aria-haspopup", "menu");
    corpusBtn.addEventListener("click", async () => {
      const h = await health().catch(() => null);
      if (!h) return toast("Can't reach the server.", true);
      $("#live-menu")?.remove();
      const box = corpusBtn.getBoundingClientRect();
      const menu = el("div", { id: "live-menu", role: "menu",
        class: "fixed z-[90] w-52 bg-surface-container-lowest rounded-lg shadow-xl py-1 flex flex-col font-label-md text-label-md text-on-surface",
        style: `bottom:${innerHeight - box.top + 6}px;left:${box.left}px` });
      for (const c of [{ id: null, label: "All documents" }, ...h.categories]) {
        const on = (state.category || null) === c.id;
        menu.append(el("button", { type: "button", role: "menuitemradio", "aria-checked": String(on),
          class: `px-3 py-2 text-left hover:bg-surface-container-low flex items-center justify-between ${on ? "text-primary font-semibold" : ""}`,
          onclick: () => { menu.remove(); setCategory(c.id); textarea.focus(); } },
          c.label, on ? icon("check", "text-sm") : null));
      }
      const close = (event) => { if (!menu.contains(event.target)) { menu.remove(); document.removeEventListener("pointerdown", close, true); } };
      setTimeout(() => document.addEventListener("pointerdown", close, true));
      document.body.append(menu);
    });

    const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Speech) hide(micBtn);
    else {
      let rec = null;
      micBtn.addEventListener("click", () => {
        if (rec) { rec.stop(); return; }
        rec = new Speech();
        rec.lang = "en-IN";
        rec.interimResults = true;
        const before = textarea.value;
        micBtn.classList.add("text-error");
        rec.onresult = (e) => { textarea.value = `${before} ${[...e.results].map((r) => r[0].transcript).join("")}`.trim(); autosize(); };
        rec.onend = () => { rec = null; micBtn.classList.remove("text-error"); textarea.focus(); };
        rec.onerror = () => toast("Voice input isn't available here.", true);
        rec.start();
      });
    }

    shareBtn.title = "Copy this conversation";
    shareBtn.addEventListener("click", () => {
      const c = current();
      if (!c) return toast("Ask a question first.");
      navigator.clipboard?.writeText(transcript(c)).then(() => toast("Conversation copied."), () => toast("Couldn't copy.", true));
    });
    downloadBtn.title = "Download this conversation";
    downloadBtn.addEventListener("click", () => {
      const c = current();
      if (!c) return toast("Ask a question first.");
      download(fileName(c.title), transcript(c));
    });

    // Fill the knowledge-base card: search method in use, number of documents and passages.
    function renderKb() {
      const h = state.health;
      if (!h) return;
      const [row, text, bar] = kbCard.children;
      row.lastElementChild.textContent = METHOD[h.answers_with] || h.answers_with;
      text.textContent = `${plural(h.documents, "university document")} split into ${h.passages} searchable passages.`;
      bar.firstElementChild.className = "bg-primary h-full rounded-full w-full";
      methodTag.textContent = METHOD[h.answers_with]?.split(" ")[0] || h.answers_with;
      subtitle.lastChild.nodeValue = ` Answers only from ${h.university} documents`;
    }

    /* start */
    if (params.get("c") && state.convs.some((c) => c.id === params.get("c"))) state.currentId = params.get("c");
    setCategory(params.get("cat"));
    renderList(); renderThread(); autosize();
    health().then((h) => {
      state.health = h;
      genSelect.replaceChildren(...h.generators.map((g) => el("option", { value: g.id, disabled: !g.ready, title: g.detail, text: g.ready ? g.label : `${g.label} (not set up)` })));
      let saved = null;
      try { saved = localStorage.getItem(GEN_KEY); } catch { /* ignore */ }
      if (saved && h.generators.some((g) => g.id === saved && g.ready)) genSelect.value = saved;
      else genSelect.value = ["local", "gemini"].find((id) => h.generators.some((g) => g.id === id && g.ready)) || genSelect.value;
      setCategory(state.category);
      renderKb();
      if (!current()) renderThread();
    }).catch((error) => toast(error.message, true));

    const q = params.get("q");
    if (q) { state.currentId = null; history.replaceState(null, "", "chat.html"); ask(q); }
    else textarea.focus({ preventScroll: true });
  }

  /* =====================================================================
     Document explorer
     ===================================================================== */
  // DOCUMENT EXPLORER PAGE (documents.html): the list of documents with search, filter and sort,
  // and a reader that shows one document section by section.
  async function initDocuments() {
    const grid = $("#documentGridArea");
    const readerCol = grid.nextElementSibling;
    const cards = [...grid.children];
    const selectedTpl = cards[0].cloneNode(true);
    const normalTpl = cards[1].cloneNode(true);
    const search = $('input[placeholder^="Search full text"]');
    const [catSelect, sortSelect] = $$("select");
    const uploadBtn = byText("button", "Upload Academic Record");
    const showing = $$("span").find((s) => s.textContent.trim().startsWith("Showing"));
    const resetBtn = byText("button", "Reset Filters");
    hide(byText("span", "Quick Filters:")?.parentElement);
    search.placeholder = "Search titles, sections and file names";

    const reader = readerCol.firstElementChild;
    const [rHead, rNav, rPageWrap, rMeta, rActions] = reader.children;
    const rTitle = $(".font-headline-sm", rHead);
    const rSub = rTitle.nextElementSibling;
    $$("button", rHead).forEach(hide);
    const navButtons = $$("button", rNav);
    const [firstBtn, prevBtn, nextBtn, lastBtn, zoomOut, zoomIn, findBtn] = navButtons;
    const pageLabel = byText("span", "Page 38", rNav);
    const ofLabel = byText("span", "of 124", rNav);
    const zoomLabel = byText("span", "115%", rNav);
    hide(findBtn); hide(findBtn.previousElementSibling);
    const page = rPageWrap.firstElementChild;
    const metaValues = $$(".grid > div > span:last-child", rMeta);
    const actionButtons = rActions ? $$("button", rActions) : $$("button", rMeta).slice(-4);
    const queryBtn = actionButtons.find((b) => b.textContent.includes("Query This Document"));
    const suggestBtns = actionButtons.filter((b) => b.textContent.trim().startsWith("\""));
    hide(actionButtons.find((b) => b.textContent.trim() === "Compare"));

    const state = { docs: [], details: new Map(), selected: null, section: 0, zoom: 100, compact: false, h: null };

    try {
      [state.h, state.docs] = await Promise.all([health(), loadDocs()]);
    } catch (error) {
      grid.replaceChildren(el("p", { class: "p-space-md font-body-md text-body-md text-error", text: error.message }));
      toast(error.message, true);
      return;
    }
    const h = state.h;
    swapText(document.body, "1,420 Certified Documents Indexed", `${plural(h.documents, "document")} indexed`);
    swapText(document.body, "v4.8.2 Vector Store", METHOD[h.answers_with] || h.answers_with);
    swapText(document.body, "pgvector · cosine-0.89", h.embedding_model || "BM25 keyword index");
    catSelect.replaceChildren(el("option", { value: "", text: "All Categories" }), ...h.categories.map((c) => el("option", { value: c.id, text: c.label })));
    sortSelect.replaceChildren(...[["updated", "Sort: Recently Updated"], ["title", "Sort: Title A–Z"], ["passages", "Sort: Most Passages"], ["category", "Sort: Category"]]
      .map(([v, t]) => el("option", { value: v, text: t })));
    if (params.get("cat")) catSelect.value = params.get("cat");

    // Section headings make the search useful; fetch them once in the background.
    Promise.all(state.docs.map((d) => api(`/api/documents/${encodeURIComponent(d.doc_id)}`).then((full) => state.details.set(d.doc_id, full)).catch(() => {})))
      .then(() => render());

    // The documents that match the search box and category, in the chosen sort order.
    function filtered() {
      const q = search.value.trim().toLowerCase();
      const cat = catSelect.value;
      const list = state.docs.filter((d) => {
        if (cat && d.category !== cat) return false;
        if (!q) return true;
        const headings = state.details.get(d.doc_id)?.sections.map((s) => s.heading).join(" ") || "";
        return `${d.title} ${d.file} ${catLabel(h, d.category)} ${headings}`.toLowerCase().includes(q);
      });
      const by = sortSelect.value;
      list.sort((a, b) => by === "title" ? a.title.localeCompare(b.title)
        : by === "passages" ? b.passages - a.passages
        : by === "category" ? a.category.localeCompare(b.category) || a.title.localeCompare(b.title)
        : String(b.updated || "").localeCompare(String(a.updated || "")));
      return list;
    }
    // Fill one document card (copied from the page's template) with a document's details.
    function fillCard(d, selected) {
      const node = (selected ? selectedTpl : normalTpl).cloneNode(true);
      const style = CAT_STYLE[d.category] || CAT_STYLE.faqs;
      const box = $(".w-12.h-12", node);
      box.className = box.className.split(/\s+/).filter((c) => !/^(bg|text)-(red|emerald|blue|amber|purple)-/.test(c)).join(" ") + " " + style.color;
      box.children[0].textContent = style.icon;
      box.children[1].textContent = style.tag;
      const tags = $(".mb-1", node).children;
      tags[0].textContent = catLabel(h, d.category);
      tags[1].textContent = d.updated ? `Updated ${fmtDate(d.updated)}` : (d.origin === "upload" ? "Uploaded" : "Sample");
      tags[2].textContent = d.file;
      $("h2", node).textContent = d.title;
      const headings = state.details.get(d.doc_id)?.sections.map((s) => s.heading).filter(Boolean) || [];
      const desc = $("p", node);
      desc.textContent = headings.length ? `Sections: ${headings.join(" · ")}` : `${plural(d.sections, "section")} from ${d.file}.`;
      const foot = desc.nextElementSibling;
      const facts = foot.firstElementChild.children;
      facts[0].lastChild.nodeValue = ` ${d.file.split(".").pop().toUpperCase()} · ${plural(d.sections, "section")}`;
      facts[1].lastChild.nodeValue = ` ${d.updated ? fmtDate(d.updated) : "No date"}`;
      facts[2].lastChild.nodeValue = ` ${d.passages} passages indexed`;
      const [readBtn, askBtn] = $$("button", foot);
      readBtn.textContent = "Read";
      readBtn.addEventListener("click", (e) => { e.stopPropagation(); select(d.doc_id); });
      askBtn.addEventListener("click", (e) => { e.stopPropagation(); location.href = `chat.html?cat=${d.category}`; });
      askBtn.title = `Ask about ${catLabel(h, d.category).toLowerCase()} documents`;
      if (state.compact) { hide(desc); hide(foot); }
      node.style.cursor = "pointer";
      node.tabIndex = 0;
      node.setAttribute("role", "button");
      node.setAttribute("aria-pressed", String(selected));
      node.addEventListener("click", () => select(d.doc_id));
      node.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(d.doc_id); } });
      return node;
    }
    // Redraw the document cards and the "Showing X of Y" line.
    function render() {
      const list = filtered();
      grid.replaceChildren(...list.map((d) => fillCard(d, d.doc_id === state.selected)));
      if (!list.length) grid.append(el("div", { class: "bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant", text: "No documents match. Try another search or category." }));
      showing.replaceChildren("Showing ", el("strong", { class: "text-on-surface font-semibold", text: String(list.length) }), ` of ${state.docs.length} documents`);
    }
    // Select a document, load its text if needed and show it in the reader.
    async function select(docId, sectionName) {
      state.selected = docId;
      render();
      let full = state.details.get(docId);
      if (!full) {
        try { full = await api(`/api/documents/${encodeURIComponent(docId)}`); state.details.set(docId, full); }
        catch (error) { toast(error.message, true); return; }
      }
      const idx = sectionName ? full.sections.findIndex((s) => s.heading === sectionName) : 0;
      state.section = Math.max(0, idx);
      renderReader();
      history.replaceState(null, "", `documents.html?doc=${encodeURIComponent(docId)}`);
    }
    // Show the current section of the selected document, its details and suggested questions.
    function renderReader() {
      const full = state.details.get(state.selected);
      if (!full) return;
      const total = full.sections.length;
      const s = full.sections[state.section] || { heading: "", blocks: [] };
      rTitle.textContent = full.title;
      rTitle.title = full.file;
      rSub.textContent = s.heading ? `Section ${state.section + 1}: ${s.heading}` : `Section ${state.section + 1}`;
      pageLabel.textContent = `Section ${state.section + 1}`;
      ofLabel.textContent = `of ${total}`;
      zoomLabel.textContent = `${state.zoom}%`;
      [firstBtn, prevBtn].forEach((b) => { b.disabled = state.section === 0; b.classList.toggle("opacity-40", b.disabled); });
      [nextBtn, lastBtn].forEach((b) => { b.disabled = state.section >= total - 1; b.classList.toggle("opacity-40", b.disabled); });
      page.classList.remove("select-none");
      page.style.fontSize = `${state.zoom}%`;
      page.replaceChildren(
        el("div", { class: "flex justify-between items-center pb-2 text-[10px] text-outline font-code-snippet gap-2" },
          el("span", { class: "uppercase", text: catLabel(h, full.category) }), el("span", { class: "truncate", text: full.file })),
        s.heading ? el("div", { class: "font-semibold text-primary flex items-center gap-1 text-xs" }, icon("bookmark", "text-sm"), s.heading) : null,
        renderBlocks(s.blocks, "text-on-surface leading-relaxed"),
        el("div", { class: "flex items-center justify-between pt-4 text-[9px] text-outline uppercase" },
          el("span", { text: h.university }), el("span", { text: `Section ${state.section + 1} of ${total}` })));
      const meta = [full.updated ? fmtDate(full.updated) : "Not dated", `Indexed (${state.docs.find((d) => d.doc_id === full.doc_id)?.passages ?? "?"} passages)`,
        full.origin === "upload" ? "Uploaded through the library" : "Sample corpus", catLabel(h, full.category)];
      metaValues.slice(0, 4).forEach((span, i) => { span.textContent = meta[i]; span.title = meta[i]; });
      ["Corpus ingestion", "Index status", "Source", "Category"].forEach((label, i) => {
        const span = metaValues[i]?.previousElementSibling;
        if (span) span.textContent = label.toUpperCase();
      });
      const starters = STARTERS.filter((x) => x.cat === full.category);
      suggestBtns.forEach((b, i) => {
        const starter = starters[i];
        if (!starter) { hide(b); return; }
        b.classList.remove("hidden");
        b.textContent = `"${starter.q}"`;
        b.onclick = () => { location.href = `chat.html?q=${encodeURIComponent(starter.q)}&cat=${full.category}`; };
      });
      if (queryBtn) queryBtn.onclick = () => { location.href = `chat.html?cat=${full.category}`; };
    }
    // Jump to section number i of the open document.
    const go = (i) => { const full = state.details.get(state.selected); if (!full) return; state.section = Math.max(0, Math.min(full.sections.length - 1, i)); renderReader(); };
    firstBtn.addEventListener("click", () => go(0));
    prevBtn.addEventListener("click", () => go(state.section - 1));
    nextBtn.addEventListener("click", () => go(state.section + 1));
    lastBtn.addEventListener("click", () => go(Infinity));
    zoomOut.addEventListener("click", () => { state.zoom = Math.max(80, state.zoom - 10); renderReader(); });
    zoomIn.addEventListener("click", () => { state.zoom = Math.min(150, state.zoom + 10); renderReader(); });
    search.addEventListener("input", render);
    catSelect.addEventListener("change", render);
    sortSelect.addEventListener("change", render);
    resetBtn?.addEventListener("click", () => { search.value = ""; catSelect.value = ""; sortSelect.value = "updated"; render(); });
    $("#viewGridBtn")?.addEventListener("click", () => { state.compact = false; render(); });
    $("#viewTableBtn")?.addEventListener("click", () => { state.compact = true; render(); });
    uploadBtn?.addEventListener("click", async () => {
      const result = await pickAndUpload(uploadBtn, catSelect.value || null);
      if (!result) return;
      state.docs = await loadDocs();
      state.details.delete(result.doc_id);
      select(result.doc_id);
    });
    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); search.focus(); }
    });

    const list = filtered();
    const wanted = params.get("doc");
    render();
    if (wanted && state.docs.some((d) => d.doc_id === wanted)) select(wanted, params.get("section"));
    else if (list.length) select(list[0].doc_id);
    if (params.get("focus") === "search") search.focus();
  }

  /* =====================================================================
     Chat history
     ===================================================================== */
  // CHAT HISTORY PAGE (history.html): saved conversations with search, filters, star, rename,
  // export and delete. The conversations live in the browser's localStorage.
  function initHistory() {
    const firstSection = $$("section").find((s) => s.className.includes("flex flex-col gap-space-sm"));
    const column = firstSection.parentElement;
    const sectionHeadTpl = firstSection.firstElementChild.cloneNode(true);
    const articleTpl = $("article", firstSection).cloneNode(true);
    const pager = [...column.children].find((c) => c.tagName === "DIV" && c.textContent.includes("Showing"));
    const right = column.nextElementSibling;
    const search = $('input[placeholder^="Search queries"]');
    const indexedBadge = byText("span", "Indexed", search.parentElement);
    const starBtn = fresh($("#starredFilterBtn"));
    const selectAll = fresh($("#selectAllCheckbox"));
    const toolbar = $("#bulkActionsToolbar");
    const countText = $("#selectedCountText");
    const selectAllLabel = selectAll.parentElement;
    const [exportPdf, exportMd, deleteSel] = ["Export PDF", "Export Markdown", "Delete Selected"].map((t) => byText("button", t, toolbar));
    const timeBtns = ["All Time", "This Semester", "Past 7 Days"].map((t) => $$("button").find((b) => b.textContent.trim() === t));
    const allDomains = $$("button").find((b) => b.textContent.trim().startsWith("All Domains"));
    const chipBox = allDomains.parentElement;
    const activeChipClass = allDomains.className;
    const idleChipClass = allDomains.nextElementSibling?.className || allDomains.className;
    const idleChipCount = allDomains.nextElementSibling?.querySelector("span")?.className || "font-label-sm text-label-sm opacity-70";
    const activeTime = timeBtns[0].className, idleTime = timeBtns[1].className;
    swapText(document.body, "This Semester", "Past 30 Days");
    $("#toggleSelectionModeBtn")?.addEventListener("click", () => toolbar.classList.toggle("hidden"));

    const state = { convs: loadConvs(), time: 0, starred: false, domain: null, h: null, selected: new Set() };

    // The conversations that match the search box, time range, star filter and topic.
    function filtered() {
      const q = search.value.trim().toLowerCase();
      const limit = [Infinity, 30, 7][state.time] * 864e5;
      return state.convs.filter((c) => {
        if (Date.now() - when(c) > limit) return false;
        if (state.starred && !c.starred) return false;
        if (state.domain && convCategory(c) !== state.domain) return false;
        return !q || c.title.toLowerCase().includes(q) || c.messages.some((m) => m.content.toLowerCase().includes(q));
      }).sort((a, b) => when(b) - when(a));
    }
    // Write the conversations back to browser storage.
    function save() { saveConvs(state.convs); }
    // Delete the given conversations.
    function remove(ids) {
      state.convs = state.convs.filter((c) => !ids.has(c.id));
      ids.forEach((id) => state.selected.delete(id));
      save(); render();
    }
    // Build the card for one conversation: title, topic, citations, last answer and its buttons.
    function articleFor(c) {
      const node = articleTpl.cloneNode(true);
      const last = answersOf(c).at(-1);
      const cat = convCategory(c);
      const box = $(".session-checkbox", node);
      box.checked = state.selected.has(c.id);
      box.setAttribute("aria-label", `Select “${c.title}”`);
      box.addEventListener("change", () => { box.checked ? state.selected.add(c.id) : state.selected.delete(c.id); updateCount(); });
      const metaRow = $("h3", node).previousElementSibling;
      const [chip, time, timer] = metaRow.children;
      chip.textContent = cat ? catLabel(state.h, cat) : "General";
      time.textContent = `• ${fmtWhen(when(c), true)}`;
      timer.replaceChildren(icon("forum", "text-xs"), ` ${plural(questionsOf(c).length, "question")}`);
      $("h3", node).textContent = c.title;
      const [star, resume, menuWrap] = $("h3", node).closest(".flex.items-start.justify-between").lastElementChild.children;
      star.firstElementChild.style.fontVariationSettings = c.starred ? "'FILL' 1" : "'FILL' 0";
      star.classList.toggle("text-primary", !!c.starred);
      star.classList.toggle("text-outline", !c.starred);
      star.title = c.starred ? "Unstar" : "Star";
      star.setAttribute("aria-pressed", String(!!c.starred));
      star.addEventListener("click", () => { c.starred = !c.starred; save(); render(); });
      resume.onclick = () => { location.href = `chat.html?c=${encodeURIComponent(c.id)}`; };
      const menuId = `menu-${c.id}`;
      const [menuBtn, menu] = menuWrap.children;
      menu.id = menuId;
      // A listener rather than an onclick attribute, so a stored id can never be read as code.
      menuBtn.removeAttribute("onclick");
      menuBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        $$('[id^="menu-"]').forEach((m) => { if (m !== menu) m.classList.add("hidden"); });
        menu.classList.toggle("hidden");
      });
      const [renameBtn, exportBtn, delBtn] = $$("button", menu);
      renameBtn.addEventListener("click", () => {
        const name = prompt("Rename conversation", c.title);
        if (name && name.trim()) { c.title = name.trim().slice(0, 80); save(); render(); }
      });
      exportBtn.addEventListener("click", () => download(fileName(c.title), transcript(c)));
      delBtn.addEventListener("click", () => { if (confirm(`Delete “${c.title}”?`)) remove(new Set([c.id])); });

      const cites = citedDocs(c);
      const citeRow = $("h3", node).closest(".flex.items-start.justify-between").nextElementSibling;
      const [label] = citeRow.children;
      label.replaceChildren(icon("verified", "text-xs"), ` ${plural(cites.length, "Citation")}${cites.length ? ":" : ""}`);
      const pillTpl = citeRow.querySelector("a");
      citeRow.replaceChildren(label, ...cites.slice(0, 3).map((s) => {
        const pill = pillTpl.cloneNode(true);
        pill.href = `documents.html?doc=${encodeURIComponent(s.doc_id)}&section=${encodeURIComponent(s.section || "")}`;
        pill.children[0].textContent = (CAT_STYLE[s.category] || CAT_STYLE.faqs).icon;
        pill.children[1].textContent = s.section ? `${s.title} · ${s.section}` : s.title;
        return pill;
      }));

      const panel = citeRow.nextElementSibling;
      const conf = byText("span", "Confidence", panel);
      if (conf) conf.textContent = last?.confidence != null ? `Confidence ${pct(last.confidence)}` : "";
      const takeaway = $("p", panel);
      takeaway.textContent = last ? (stripCites(last.content).slice(0, 320) + (stripCites(last.content).length > 320 ? "…" : "")) : "No answer yet.";
      const footer = panel.lastElementChild;
      footer.firstElementChild.textContent = last?.abstained ? "The documents did not cover the last question." : `Answered from ${state.h?.university || "the university"} documents`;
      const rounds = footer.lastElementChild;
      rounds.firstElementChild.textContent = `Open all ${plural(questionsOf(c).length, "question")}`;
      rounds.onclick = () => { location.href = `chat.html?c=${encodeURIComponent(c.id)}`; };
      return node;
    }
    // The date group a conversation belongs to: Today, Earlier this week, or its month.
    function groupOf(c) {
      const d = new Date(when(c)), now = new Date();
      if (d.toDateString() === now.toDateString()) return "Today";
      if (Date.now() - d < 7 * 864e5) return "Earlier this week";
      return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    }
    // Redraw the history list grouped by date, then the filter chips, counters and statistics.
    function render() {
      const list = filtered();
      const groups = new Map();
      for (const c of list) { const g = groupOf(c); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(c); }
      const sections = [...groups].map(([name, items]) => {
        const head = sectionHeadTpl.cloneNode(true);
        $("h2", head).textContent = name;
        $("h2", head).nextElementSibling.textContent = `• ${plural(items.length, "Inquiry", "Inquiries")}`;
        const dates = items.map(when);
        const a = fmtDate(new Date(Math.min(...dates))), b = fmtDate(new Date(Math.max(...dates)));
        head.lastElementChild.textContent = a === b ? a : `${a} – ${b}`;
        return el("section", { class: "flex flex-col gap-space-sm" }, head, items.map(articleFor));
      });
      if (!list.length) {
        sections.push(el("div", { class: "bg-surface-container-lowest rounded-xl shadow-sm p-space-lg flex flex-col items-start gap-space-sm" },
          el("p", { class: "font-body-md text-body-md text-on-surface-variant", text: state.convs.length ? "No conversations match these filters." : "No conversations yet. Questions you ask in the chatbot are saved here, in this browser." }),
          el("a", { href: "chat.html", class: "px-3 py-1.5 rounded-lg bg-primary text-on-primary font-label-md text-label-md", text: "Ask a question" })));
      }
      column.replaceChildren(...sections, pager);
      pager.firstElementChild.replaceChildren("Showing ", el("strong", { class: "text-on-surface", text: String(list.length) }), ` of ${plural(state.convs.length, "conversation")}`);
      [...pager.children].slice(1).forEach(hide);
      const allLabel = $$("*", selectAllLabel).find((n) => !n.children.length && n.textContent.includes("Select All Visible"));
      if (allLabel) allLabel.textContent = `Select All Visible (${list.length})`;
      selectAll.checked = list.length > 0 && list.every((c) => state.selected.has(c.id));
      if (indexedBadge) indexedBadge.textContent = `${state.convs.length} Saved`;
      starBtn.lastElementChild.textContent = String(state.convs.filter((c) => c.starred).length);
      starBtn.className = state.starred ? starBtn.className.replace("bg-surface-container-low", "bg-primary").replace("text-on-surface-variant", "text-on-primary")
        : starBtn.className.replace(/\bbg-primary\b/, "bg-surface-container-low").replace("text-on-primary", "text-on-surface-variant");
      timeBtns.forEach((b, i) => { b.className = i === state.time ? activeTime : idleTime; });
      renderChips();
      updateCount();
      renderStats();
    }
    // Draw the topic filter chips, with the number of conversations in each category.
    function renderChips() {
      const counts = {};
      state.convs.forEach((c) => { const k = convCategory(c); if (k) counts[k] = (counts[k] || 0) + 1; });
      const chip = (id, label, n) => {
        const on = state.domain === id;
        const b = el("button", { type: "button", class: on ? activeChipClass : idleChipClass, "aria-pressed": String(on),
          onclick: () => { state.domain = on && id ? null : id; render(); } }, label);
        if (id === null && on) b.append(" ", icon("close", "text-xs"));
        else if (n != null) b.append(" ", el("span", { class: idleChipCount, text: String(n) }));
        return b;
      };
      chipBox.replaceChildren(chipBox.firstChild?.nodeType === 3 ? chipBox.firstChild : "",
        ...[...chipBox.children].filter((c) => c.tagName === "SPAN").slice(0, 1),
        chip(null, "All Domains"),
        ...(state.h?.categories || []).filter((c) => counts[c.id]).map((c) => chip(c.id, c.label, counts[c.id])));
    }
    // Show how many conversations are ticked.
    function updateCount() {
      countText.textContent = String(state.selected.size);
    }
    // Fill the statistics panel: questions asked, share answered from the documents, most-cited documents.
    function renderStats() {
      if (!right) return;
      const questions = state.convs.reduce((n, c) => n + questionsOf(c).length, 0);
      const answers = state.convs.flatMap(answersOf);
      const answered = answers.filter((m) => !m.abstained).length;
      const card = byText("span", "Total Queries Logged", right)?.parentElement || byText("span", "TOTAL QUERIES LOGGED", right)?.parentElement;
      if (card) {
        swapText(card, "47", String(questions));
        swapText(card, /compared to Fall 2024/, `in ${plural(state.convs.length, "conversation")}`);
      }
      swapText(right, "Spring 2025", "This browser");
      swapText(right, "Avg Consultation", "Questions per chat");
      swapText(right, "6.4 min", state.convs.length ? (questions / state.convs.length).toFixed(1) : "0");
      const focused = swapText(right, "Focused", "average");
      if (focused) focused.querySelector(".material-symbols-outlined")?.remove();
      swapText(right, "Source Accuracy", "Answered from docs");
      swapText(right, "99.1%", answers.length ? pct(answered / answers.length, 0) : "—");
      swapText(right, "Verified", `${answered} of ${answers.length}`);

      const tally = new Map();
      state.convs.forEach((c) => citedDocs(c).forEach((s) => {
        const t = tally.get(s.doc_id) || { ...s, count: 0 };
        t.count += s.count; tally.set(s.doc_id, t);
      }));
      const top = [...tally.values()].sort((a, b) => b.count - a.count);
      const total = top.reduce((n, s) => n + s.count, 0);
      const topTitle = swapText(right, "Registrar Academic Calendar 2024-25", top[0]?.title || "Nothing cited yet");
      swapText(right, /^Office of the University Registrar/, top[0] ? `${catLabel(state.h, top[0].category)} • ${top[0].section || ""}` : "Ask a question to see which documents answer it");
      swapText(right, "19 Citations in Sessions", top[0] ? `${plural(top[0].count, "Citation")} in Sessions` : "");
      swapText(right, "40.4% share", top[0] ? `${pct(top[0].count / total, 0)} share` : "");
      const inspect = byText("a", "Inspect in Document Explorer", right) || byText("button", "Inspect in Document Explorer", right);
      if (inspect) inspect.onclick = (e) => { e.preventDefault(); location.href = top[0] ? `documents.html?doc=${encodeURIComponent(top[0].doc_id)}` : "documents.html"; };
      [["Undergraduate Academic Code Ch. 8", "12 refs"], ["FAFSA Priority Filing Statutes 2025", "8 refs"], ["Math Placement & Prerequisite Rules", "6 refs"]]
        .forEach(([name, refs], i) => {
          const s = top[i + 1];
          const nameEl = swapText(right, name, s ? s.title : "");
          swapText(right, refs, s ? plural(s.count, "ref") : "");
          if (!s && nameEl) hide(nameEl.closest("li, a, div"));
        });
      if (topTitle && !top[0]) topTitle.classList.add("text-outline");
    }

    search.addEventListener("input", render);
    timeBtns.forEach((b, i) => b.addEventListener("click", () => { state.time = i; render(); }));
    starBtn.addEventListener("click", () => { state.starred = !state.starred; render(); });
    selectAll.addEventListener("change", () => {
      filtered().forEach((c) => (selectAll.checked ? state.selected.add(c.id) : state.selected.delete(c.id)));
      render();
    });
    // The conversations that are ticked right now.
    const chosen = () => state.convs.filter((c) => state.selected.has(c.id));
    exportMd?.addEventListener("click", () => {
      const list = chosen();
      if (!list.length) return toast("Select at least one conversation.");
      download(list.length === 1 ? fileName(list[0].title) : "conversations.md", list.map(transcript).join("\n\n---\n\n"));
    });
    exportPdf?.addEventListener("click", () => {
      const list = chosen();
      if (!list.length) return toast("Select at least one conversation.");
      const win = window.open("", "_blank");
      if (!win) return toast("Allow pop-ups to print.", true);
      win.document.title = "Conversations";
      const body = win.document.body;
      body.style.font = "14px/1.6 Inter, system-ui, sans-serif";
      body.style.margin = "2rem";
      list.forEach((c) => {
        body.append(Object.assign(win.document.createElement("h1"), { textContent: c.title }));
        c.messages.forEach((m) => {
          const p = win.document.createElement("p");
          p.style.whiteSpace = "pre-wrap";
          p.textContent = `${m.role === "user" ? "Question" : "Answer"}: ${m.content}`;
          body.append(p);
        });
      });
      win.print();
    });
    deleteSel?.addEventListener("click", () => {
      const list = chosen();
      if (!list.length) return toast("Select at least one conversation.");
      if (confirm(`Delete ${plural(list.length, "conversation")}? This can't be undone.`)) remove(new Set(list.map((c) => c.id)));
    });

    render();
    health().then((h) => { state.h = h; render(); }).catch(() => {});
  }

  /* =====================================================================
     Admin
     ===================================================================== */
  // ADMIN PAGE (admin.html): corpus statistics, uploading a document, the newest documents,
  // and the registry table with delete and CSV export.
  async function initAdmin() {
    const sections = $$("main section");
    const stats = sections.find((s) => s.className.includes("xl:grid-cols-4"));
    const dropZone = $("#dropZone");
    const uploadCard = dropZone.parentElement;
    const [catSelect, audienceSelect, registrySelect] = $$("select");
    hide(audienceSelect.closest(".flex.flex-col"));
    swapText(dropZone, "Max 150MB", "Max 10 MB");
    swapText(dropZone, "CAMPUS API / URL", "TXT");
    swapText(dropZone, /^Automatic optical character recognition/, "PDF, Word, Markdown or plain text. The document is split into passages and added to the search index straight away.");
    const dropTitle = $("p", dropZone);
    const commitBtn = byText("button", "Commit & Ingest", uploadCard);
    const discardBtn = byText("button", "Discard Draft", uploadCard);
    const table = $("table");
    const tbody = $("tbody", table);
    const rowTpl = $("tr", tbody).cloneNode(true);
    const registry = table.closest("section");
    const pagerBar = registry.lastElementChild.previousElementSibling?.textContent.includes("Showing") ? registry.lastElementChild.previousElementSibling
      : $$("div", registry).find((d) => d.children.length >= 2 && d.firstElementChild?.textContent.trim().startsWith("Showing"));
    const exportBtn = byText("button", "Export CSV", registry);

    let h, docs, evalData = null;
    try {
      [h, docs] = await Promise.all([health(), loadDocs()]);
      evalData = await api("/api/eval/results").catch(() => null);
    } catch (error) {
      toast(error.message, true);
      swapText(document.body, "RAG Pipeline: Healthy", "RAG Pipeline: Offline");
      return;
    }

    /* header + stat cards */
    swapText(document.body, /^Latency: .*Sync/, `${METHOD[h.answers_with] || h.answers_with} • ${h.passages} passages`);
    swapText(document.body, "Cluster: US-East-Academic-01", h.university);
    // Fill the stat cards: documents, evaluation questions, answer accuracy and retrieval Hit@3.
    function renderStats() {
      const uploads = docs.filter((d) => d.origin === "upload").length;
      const answers = evalData?.available ? evalData.answers?.extractive?.summary : null;
      const best = evalData?.available ? evalData.retrieval?.[h.answers_with] || Object.values(evalData.retrieval || {})[0] : null;
      const q = evalData?.questions;
      const set = (from, to) => swapText(stats, from, to);
      set("1,420", String(docs.length));
      set("+12 this wk", `${uploads} uploaded`);
      set("Syllabi, Catalogues, Addenda", `${h.categories.length} categories`);
      set("98.2% indexed", `${h.passages} passages`);
      set("Active Student Users", "Evaluation Questions");
      set("8,940", q ? String(q.total) : "—");
      set("+14% MoM", "labelled");
      set("Undergrad, Grad, Faculty", q ? `${q.answerable} answerable` : "Run python -m app.evaluate");
      set("68% daily MAU", q ? `${q.unanswerable} unanswerable` : "");
      set("Total AI Queries Resolved", "Answer Accuracy");
      set("42,650", answers ? pct(answers.accuracy) : "—");
      set("99.4% CSAT", answers ? `${pct(answers.cited_gold_document, 0)} cited` : "");
      set(/^Avg token count/, "Median latency:");
      set(/^<0\.4s/, answers ? `${answers.latency_ms.median} ms` : "—");
      set("Citation Verification Rate", "Retrieval Hit@3");
      set("99.8%", best ? pct(best.passage["hit@3"]) : "—");
      set("0 Flags", best ? `MRR ${best.passage.mrr.toFixed(2)}` : "");
      set(/^Zero hallucination/, METHOD[h.answers_with] || h.answers_with);
      set("Institutional Grade", evalData?.generated_at ? `Run ${fmtDate(evalData.generated_at)}` : "");
    }
    renderStats();

    /* upload */
    catSelect.replaceChildren(...h.categories.map((c) => el("option", { value: c.id, text: c.label })));
    let draft = null;
    const defaultTitle = dropTitle.textContent;
    // Remember the file that is waiting to be uploaded and show its name.
    function setDraft(file) {
      draft = file;
      dropTitle.textContent = file ? `${file.name} (${(file.size / 1024).toFixed(0)} KB) ready to add` : defaultTitle;
      commitBtn.disabled = !file;
      commitBtn.classList.toggle("opacity-50", !file);
    }
    setDraft(null);
    dropZone.setAttribute("role", "button");
    dropZone.tabIndex = 0;
    dropZone.addEventListener("click", async () => { const f = await chooseFile(); if (f) setDraft(f); });
    dropZone.addEventListener("keydown", async (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); const f = await chooseFile(); if (f) setDraft(f); } });
    dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("ring-2", "ring-primary"); });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("ring-2", "ring-primary"));
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault(); dropZone.classList.remove("ring-2", "ring-primary");
      const f = e.dataTransfer.files[0];
      if (f) setDraft(f);
    });
    discardBtn?.addEventListener("click", () => setDraft(null));
    commitBtn?.addEventListener("click", async () => {
      if (!draft) return;
      commitBtn.disabled = true;
      try {
        await uploadFile(draft, catSelect.value);
        setDraft(null);
        [h, docs] = await Promise.all([health(), loadDocs()]);
        renderAll();
      } catch (error) { toast(error.message, true); commitBtn.disabled = false; }
    });

    /* ingestion monitor: newest documents */
    const monitorHead = byText("h2", "Ingestion Pipeline Monitor") || byText("h3", "Ingestion Pipeline Monitor");
    const monitor = monitorHead?.closest(".rounded-2xl");
    const firstJob = monitor && $$("div", monitor).find((d) => d.textContent.includes("100% Vectorized") && d.className.includes("rounded-xl"));
    const jobList = firstJob?.parentElement;
    const jobTpl = firstJob?.cloneNode(true);
    // Show the three most recently added documents.
    function renderMonitor() {
      if (!jobTpl) return;
      swapText(monitor, "3 Active Jobs", `${docs.length} indexed`);
      if (h.embedding_model) swapText(monitor, "text-embedding-3-large", h.embedding_model);
      const recent = [...docs].sort((a, b) => (b.origin === "upload") - (a.origin === "upload") || String(b.updated || "").localeCompare(String(a.updated || ""))).slice(0, 3);
      const jobs = recent.map((d) => {
        const node = jobTpl.cloneNode(true);
        const titleEl = $$("span, p, h3, h4", node).find((n) => n.textContent.trim().startsWith("Spring 2025 Final Exa"));
        if (titleEl) { titleEl.textContent = d.title; titleEl.title = d.title; }
        swapText(node, /^Registrar/, `${catLabel(h, d.category)} • ${plural(d.sections, "section")} • ${d.passages} passages`);
        swapText(node, /\d+ pages/, "");
        swapText(node, /vectors$/, "");
        swapText(node, "100% Vectorized", d.origin === "upload" ? "Uploaded" : "Indexed");
        return node;
      });
      [...jobList.children].filter((c) => c.className.includes("rounded-xl")).forEach((c) => c.remove());
      const anchor = [...jobList.children].find((c) => !c.className.includes("rounded-xl"));
      jobs.forEach((j) => jobList.insertBefore(j, anchor || null));
    }

    /* registry table */
    const PAGE_SIZE = 5;
    let pageNo = 0;
    registrySelect.replaceChildren(el("option", { value: "", text: "All Categories" }), ...h.categories.map((c) => el("option", { value: c.id, text: c.label })));
    // The documents shown in the registry table (category filter applied, sorted by title).
    const regList = () => docs.filter((d) => !registrySelect.value || d.category === registrySelect.value).sort((a, b) => a.title.localeCompare(b.title));
    // Delete an uploaded document (DELETE /api/documents/{id}) after the user confirms.
    async function removeDoc(d) {
      if (!confirm(`Remove “${d.title}” from the library?`)) return;
      try {
        await api(`/api/documents/${encodeURIComponent(d.doc_id)}`, { method: "DELETE" });
        refreshCorpus();
        [h, docs] = await Promise.all([health(), loadDocs()]);
        toast(`Removed “${d.title}”.`);
        renderAll();
      } catch (error) { toast(error.message, true); }
    }
    // Build one table row for a document, with read / ask / delete buttons.
    function rowFor(d) {
      const tr = rowTpl.cloneNode(true);
      const style = CAT_STYLE[d.category] || CAT_STYLE.faqs;
      const tds = tr.children;
      tds[0].querySelector(".material-symbols-outlined").textContent = style.icon;
      const [name, sub] = $(".flex.flex-col", tds[0]).children;
      name.textContent = d.title;
      sub.textContent = `${d.file} • ${plural(d.sections, "section")}`;
      $("span", tds[1]).textContent = catLabel(h, d.category);
      const [date, officer] = $(".flex.flex-col", tds[2]).children;
      date.textContent = d.updated ? fmtDate(d.updated) : "Not dated";
      officer.textContent = d.origin === "upload" ? "Uploaded" : "Sample corpus";
      $$("span", tds[3])[1].textContent = "Indexed";
      const [hits, note] = $$("span", tds[4]);
      hits.textContent = String(d.passages);
      note.textContent = "passages";
      const actions = $("div", tds[5]);
      const btn = (name, title, onclick, extra = "") => el("button", { type: "button", title, "aria-label": title, onclick,
        class: `p-1.5 hover:bg-surface-container rounded-lg transition-colors ${extra}` }, icon(name, "text-base"));
      const canDelete = d.origin === "upload";
      actions.replaceChildren(
        btn("visibility", "Read in the explorer", () => { location.href = `documents.html?doc=${encodeURIComponent(d.doc_id)}`; }),
        btn("chat_bubble", "Ask about this category", () => { location.href = `chat.html?cat=${d.category}`; }, "text-primary"),
        btn("delete", canDelete ? "Remove" : "Sample documents are removed from data/corpus by hand", () => canDelete && removeDoc(d),
          canDelete ? "hover:text-error" : "text-outline opacity-40 cursor-not-allowed"));
      return tr;
    }
    // Draw the current page of the registry table and its page buttons (5 rows per page).
    function renderRegistry() {
      const list = regList();
      const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
      pageNo = Math.min(pageNo, pages - 1);
      tbody.replaceChildren(...list.slice(pageNo * PAGE_SIZE, pageNo * PAGE_SIZE + PAGE_SIZE).map(rowFor));
      swapText(registry, /Active Documents$/, `${docs.length} Active Documents`);
      if (!pagerBar) return;
      const [info, buttons] = pagerBar.children;
      const from = list.length ? pageNo * PAGE_SIZE + 1 : 0, to = Math.min(list.length, (pageNo + 1) * PAGE_SIZE);
      info.replaceChildren("Showing ", el("strong", { class: "text-on-surface font-semibold", text: `${from} to ${to}` }), " of ",
        el("strong", { class: "text-on-surface font-semibold", text: String(list.length) }), " documents");
      if (!buttons) return;
      const all = $$("button", buttons);
      const active = all.find((b) => b.textContent.trim() === "1")?.className || "";
      const idle = all.find((b) => b.textContent.trim() === "2")?.className || "";
      const edge = all[0].className;
      const mk = (label, target, cls, disabled) => el("button", { type: "button", class: cls + (disabled ? " opacity-50 cursor-not-allowed" : ""), disabled,
        onclick: () => { pageNo = target; renderRegistry(); } }, label);
      buttons.replaceChildren(mk("Previous", pageNo - 1, edge, pageNo === 0),
        ...Array.from({ length: pages }, (_, i) => mk(String(i + 1), i, i === pageNo ? active : idle, false)),
        mk("Next", pageNo + 1, edge, pageNo >= pages - 1));
    }
    registrySelect.addEventListener("change", () => { pageNo = 0; renderRegistry(); });
    exportBtn?.addEventListener("click", () => {
      const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const rows = [["doc_id", "title", "category", "file", "updated", "origin", "sections", "passages"],
        ...regList().map((d) => [d.doc_id, d.title, d.category, d.file, d.updated, d.origin, d.sections, d.passages])];
      download("corpus.csv", rows.map((r) => r.map(esc).join(",")).join("\n"), "text/csv");
    });

    // Redraw every part of the admin page.
    function renderAll() { renderStats(); renderMonitor(); renderRegistry(); }
    renderAll();
  }

  /* =====================================================================
     Dashboard
     ===================================================================== */
  // DASHBOARD PAGE (dashboard.html): a question box, quick prompts, counts of questions and
  // citations, and the three most recent conversations.
  function initDashboard() {
    // fresh() drops the hash-navigation listeners Stitch's inline script attached.
    const input = fresh($("#dashboardQueryInput"));
    const submit = fresh($("#submitQueryBtn"));
    // Take the typed question to the chat page.
    const go = () => {
      const q = input.value.trim();
      if (!q) { input.focus(); return; }
      location.href = `chat.html?q=${encodeURIComponent(q)}`;
    };
    submit.addEventListener("click", go);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    input.placeholder = "e.g., What is the minimum attendance required?";
    const tags = $$(".quick-prompt-tag");
    tags.forEach((tag, i) => {
      const starter = STARTERS[i];
      const t = fresh(tag);
      if (!starter) { hide(t); return; }
      t.textContent = `"${starter.q}"`;
      t.addEventListener("click", () => { location.href = `chat.html?q=${encodeURIComponent(starter.q)}`; });
    });

    const convs = loadConvs();
    const questions = convs.reduce((n, c) => n + questionsOf(c).length, 0);
    const week = convs.reduce((n, c) => n + questionsOf(c).filter((m) => Date.now() - (m.at || when(c)) < 7 * 864e5).length, 0);
    const cites = convs.flatMap(citedDocs);
    const byCat = {};
    cites.forEach((s) => { byCat[s.category] = (byCat[s.category] || 0) + 1; });
    const queriesCard = byText("span", "AI Queries Solved")?.closest(".rounded-xl, .rounded-2xl");
    swapText(queriesCard, "47", String(questions));
    swapText(queriesCard, "+8 this week", `${week} this week`);
    const citesCard = byText("span", "Saved Citations")?.closest(".rounded-xl, .rounded-2xl");
    swapText(citesCard, "12", String(cites.length));
    swapText(citesCard, "3 syllabus, 9 handbooks", Object.entries(byCat).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([k, n]) => `${n} ${k}`).join(", ") || "from your answers");

    const recentHead = byText("h2", "Recent AI Consultations");
    const recent = recentHead?.closest(".lg\\:col-span-7");
    if (recent) {
      const [headRow, list, footer] = recent.children;
      const clear = byText("button", "Clear History", headRow);
      // Draw the three most recent conversations.
      const render = () => {
        const all = loadConvs();
        const items = all.slice().sort((a, b) => when(b) - when(a)).slice(0, 3);
        list.replaceChildren(...items.map((c) => {
          const last = answersOf(c).at(-1);
          const docsCited = citedDocs(c);
          return el("div", { class: "bg-surface-container-lowest rounded-xl p-space-md shadow-sm hover:shadow-md transition-shadow" },
            el("div", { class: "flex items-start justify-between gap-space-sm" },
              el("div", { class: "flex-1 min-w-0" },
                el("div", { class: "flex items-center gap-space-xs mb-1" },
                  el("span", { class: "font-label-sm text-label-sm text-outline", text: fmtWhen(when(c), true) }),
                  el("span", { class: "text-outline-variant", text: "•" }),
                  el("span", { class: "font-label-sm text-label-sm text-primary font-medium bg-surface-container px-2 py-0.5 rounded", text: plural(docsCited.length, "Cited Document") })),
                el("h3", { class: "font-headline-sm text-headline-sm text-on-surface", text: c.title }),
                last ? el("p", { class: "font-body-sm text-body-sm text-on-surface-variant line-clamp-2 mt-1", text: stripCites(last.content) }) : null),
              el("a", { href: `chat.html?c=${encodeURIComponent(c.id)}`, class: "px-space-sm py-1.5 rounded-lg bg-surface-container hover:bg-primary hover:text-on-primary text-on-surface text-label-sm font-label-sm font-medium transition-colors whitespace-nowrap flex items-center gap-1" },
                el("span", { text: "Resume" }), icon("arrow_forward", "text-xs"))),
            docsCited.length ? el("div", { class: "mt-space-sm pt-space-xs flex flex-wrap items-center gap-space-xs" },
              el("span", { class: "font-label-sm text-label-sm text-outline", text: "Citations:" }),
              docsCited.slice(0, 3).map((s) => el("a", { href: `documents.html?doc=${encodeURIComponent(s.doc_id)}`, class: "font-label-sm text-label-sm text-primary bg-primary-fixed/20 px-2 py-0.5 rounded-full hover:underline", text: s.title }))) : null);
        }));
        if (!items.length) {
          list.append(el("div", { class: "bg-surface-container-lowest rounded-xl p-space-md shadow-sm font-body-md text-body-md text-on-surface-variant" },
            "No questions yet. ", el("a", { href: "chat.html", class: "text-primary font-semibold hover:underline", text: "Ask the chatbot" }), " and your conversations will show up here."));
        }
        const more = footer && ($("a", footer) || $("button", footer));
        if (more) {
          more.firstChild.nodeValue = all.length ? `View all ${plural(all.length, "conversation")} ` : "Open chat history ";
          more.onclick = (e) => { e.preventDefault(); location.href = "history.html"; };
        }
      };
      clear?.addEventListener("click", () => {
        if (!loadConvs().length) return;
        if (confirm("Delete all saved conversations from this browser?")) { saveConvs([]); render(); toast("History cleared."); }
      });
      render();
    }
  }

  /* =====================================================================
     Landing page
     ===================================================================== */
  // LANDING PAGE (index.html): turn the demo box into a real question box that opens the chat.
  function initIndex() {
    const demo = $("#interactive-preview");
    const input = demo && $("input[readonly]", demo);
    if (input) {
      input.removeAttribute("readonly");
      input.value = "";
      input.placeholder = "Ask anything about attendance, exams, fees, hostel or syllabus…";
      input.classList.remove("cursor-pointer");
      input.setAttribute("aria-label", "Ask a question");
      // Take the typed question to the chat page.
      const go = () => {
        const q = input.value.trim();
        location.href = q ? `chat.html?q=${encodeURIComponent(q)}` : "chat.html";
      };
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
      const send = input.parentElement.querySelector("button") || input.parentElement.parentElement.querySelector("button");
      send?.addEventListener("click", go);
    }
  }

  /* ---------- start ---------- */
  // Pick the setup function for the page that is open, and run it once the page has loaded.
  const init = { chat: initChat, documents: initDocuments, history: initHistory, admin: initAdmin, dashboard: initDashboard, index: initIndex }[PAGE];
  const start = () => {
    decorate();
    try { const result = init?.(); if (result?.catch) result.catch((e) => { console.error(e); toast(e.message, true); }); }
    catch (e) { console.error(e); toast(`This page could not connect: ${e.message}`, true); }
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
