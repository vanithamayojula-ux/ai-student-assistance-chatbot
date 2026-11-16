/* Student Help Desk: the website's logic (home page, Ask, Library, Evaluation). No framework, no build step.
   All text from the server is inserted with textContent, never innerHTML. */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const STORE = "shd.conversations.v1";

  const STARTERS = [
    { cat: "regulations", q: "What is the fee for re-evaluation of an answer script?" },
    { cat: "notices", q: "When is the last date to pay the semester fee without a late fine?" },
    { cat: "syllabus", q: "How are the marks divided in Data Structures?" },
    { cat: "policies", q: "How much similarity is allowed in an assignment before it counts as plagiarism?" },
    { cat: "faqs", q: "When does the hostel gate close at night?" },
  ];
  // Shown in the running strip on the home page. Each is answered by the sample corpus.
  const TICKER = [
    { cat: "regulations", q: "What is the minimum attendance required?" },
    { cat: "notices", q: "How much is the fine for late fee payment?" },
    { cat: "regulations", q: "What is the passing grade in a course?" },
    { cat: "syllabus", q: "How many credits is the Data Structures course?" },
    { cat: "faqs", q: "How do I apply for a duplicate ID card?" },
    ...STARTERS,
  ];
  const METHOD = { bm25: "BM25 (keywords)", dense: "Dense (embeddings)", hybrid: "Hybrid (BM25 + dense)" };
  const GENERATOR = { extractive: "Quoted from the documents", gemini: "Written by Gemini from the documents",
                      claude: "Written by Claude from the documents" };
  const GEN_SHORT = { extractive: "Quote the documents", gemini: "Gemini", claude: "Claude" };

  const state = {
    health: null,
    conversations: load(),
    currentId: null,
    busy: false,
    shown: null,          // the bot message whose sources are in the evidence panel
    docs: [],
    openDoc: null,
    evalData: null,
    evalGen: null,
    evalWrongOnly: false,
  };

  /* ---------- tiny DOM helper ---------- */
  function el(tag, props, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === false || value == null) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "style") node.setAttribute("style", value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child == null || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function toast(message, isError = false) {
    const node = $("#toast");
    node.textContent = message;
    node.className = "toast show" + (isError ? " error" : "");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.className = "toast"; }, isError ? 6000 : 3000);
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let detail = `Request failed (${response.status}).`;
      try { detail = (await response.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(typeof detail === "string" ? detail : "The request was not valid.");
    }
    return response.json();
  }

  function load() {
    try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; }
  }
  function save() {
    try { localStorage.setItem(STORE, JSON.stringify(state.conversations.slice(0, 30))); } catch { /* storage full */ }
  }
  const current = () => state.conversations.find((c) => c.id === state.currentId) || null;
  const categoryLabel = (id) => (state.health?.categories.find((c) => c.id === id)?.label) || id;

  function formatDate(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso
      : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  }

  /* ---------- rendering document text ---------- */
  function inline(text, parent) {
    // **bold** is the only inline markdown the corpus uses
    text.split(/(\*\*[^*]+\*\*)/g).forEach((part) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length > 4) parent.append(el("strong", { text: part.slice(2, -2) }));
      else if (part) parent.append(part);
    });
    return parent;
  }
  const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

  function renderBlocks(blocks) {
    const root = el("div", { class: "doc-text" });
    for (const block of blocks) {
      if (block.kind === "table") {
        const [head, ...rows] = block.units;
        const table = el("table", {},
          el("thead", {}, el("tr", {}, cells(head.text).map((c) => inline(c, el("th", { scope: "col" }))))),
          el("tbody", {}, rows.map((row) =>
            el("tr", { class: row.hit ? "hit" : null }, cells(row.text).map((c) => inline(c, el("td")))))));
        root.append(el("div", { class: "table-wrap" }, table));
      } else if (block.kind === "list") {
        root.append(el("ul", {}, block.units.map((unit) => {
          const body = unit.text.replace(/^(?:[-+*]|\d+[.)])\s+/, "");
          const li = el("li");
          inline(body, unit.hit ? li.appendChild(el("mark")) : li);
          return li;
        })));
      } else {
        const p = el("p");
        block.units.forEach((unit, i) => {
          if (i) p.append(" ");
          inline(unit.text, unit.hit ? p.appendChild(el("mark")) : p);
        });
        root.append(p);
      }
    }
    return root;
  }

  /* ---------- rendering an answer ---------- */
  function renderAnswer(text, message) {
    const frag = document.createDocumentFragment();
    let list = null;
    const fill = (line, parent) => {
      line.split(/(\[\d+\]|\*\*[^*]+\*\*)/g).forEach((part) => {
        const cite = /^\[(\d+)\]$/.exec(part);
        if (cite && message?.sources?.some((s) => s.n === Number(cite[1]))) {
          parent.append(el("button", {
            class: "cite", type: "button", text: cite[1], "data-n": cite[1],
            "aria-label": `Show source ${cite[1]}`,
            onclick: () => showEvidence(message, Number(cite[1]), true),
          }));
        } else if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          parent.append(el("strong", { text: part.slice(2, -2) }));
        } else if (part) parent.append(part);
      });
      return parent;
    };
    for (const raw of text.split(/\n+/)) {
      const line = raw.trim();
      if (!line) continue;
      const item = /^(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
      if (item) {
        if (!list) { list = el("ul"); frag.append(list); }
        list.append(fill(item[1], el("li")));
      } else {
        list = null;
        frag.append(fill(line.replace(/^#+\s*/, ""), el("p")));
      }
    }
    return frag;
  }

  function botNode(message) {
    const answer = el("div", { class: "answer" + (message.abstained ? " declined" : "") });
    if (message.pending && !message.content) {
      answer.append(el("span", { class: "thinking" }, el("i"), el("i"), el("i"),
        message.sources?.length ? "Writing the answer from the passages" : "Searching the documents"));
    } else {
      answer.append(renderAnswer(message.content, message));
    }
    if (message.note) answer.append(el("p", { class: "note", text: message.note }));

    const node = el("div", { class: "msg-bot" }, answer);
    if (!message.pending && message.generator !== "none") {
      const cited = (message.sources || []).filter((s) => s.cited).length;
      const meta = el("div", { class: "msg-meta" });
      if (message.abstained) meta.append(el("span", { text: "No matching passage" }));
      else meta.append(el("span", { text: GENERATOR[message.generator] || "" }),
        el("span", { text: `${cited} ${cited === 1 ? "passage" : "passages"} cited` }));
      if (message.latency_ms != null) meta.append(el("span", { text: `${(message.latency_ms / 1000).toFixed(1)} s` }));
      if ((message.sources || []).length) {
        meta.append(el("button", { class: "btn-quiet view-sources", type: "button", text: "View sources",
          onclick: () => showEvidence(message, null, true) }));
      }
      meta.append(el("span", { class: "spacer" }));
      const vote = (helpful) => async (event) => {
        message.helpful = helpful; save();
        event.target.parentElement.querySelectorAll("[data-vote]").forEach((b) =>
          b.setAttribute("aria-pressed", String(b.dataset.vote === String(helpful))));
        try {
          await api("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: message.question || "", answer: message.content, helpful, generator: message.generator || "" }) });
          toast("Feedback saved");
        } catch (error) { toast(error.message, true); }
      };
      meta.append(
        el("button", { class: "btn-quiet", type: "button", "data-vote": "true", text: "Helpful",
          "aria-pressed": String(message.helpful === true), onclick: vote(true) }),
        el("button", { class: "btn-quiet", type: "button", "data-vote": "false", text: "Not helpful",
          "aria-pressed": String(message.helpful === false), onclick: vote(false) }));
      node.append(meta);
    }
    return node;
  }

  function renderThread(keepScroll = false, animateLast = false) {
    const thread = $("#thread");
    const conversation = current();
    thread.replaceChildren();
    if (!conversation || !conversation.messages.length) {
      const name = state.health?.university || "the university";
      thread.append(el("div", { class: "welcome" },
        el("h1", { text: "What do you need to know?" }),
        el("p", { text: `Answers come from ${name}'s syllabus, regulations, notices, FAQs and academic policies. ` +
          "Each one is shown beside the passage it was taken from." }),
        el("div", { class: "starters" }, STARTERS.map((s) =>
          el("button", { type: "button", onclick: () => ask(s.q) },
            el("span", { class: "tag", "data-cat": s.cat, text: categoryLabel(s.cat) }),
            el("span", { class: "q", text: s.q }))))));
      return;
    }
    const inner = el("div", { class: "thread-inner" });
    const messages = conversation.messages;
    messages.forEach((message, i) => {
      const isNew = animateLast && i === messages.length - 2;       // the question just asked
      inner.append(message.role === "user"
        ? el("div", { class: "msg-user" + (isNew ? " new" : ""), text: message.content })
        : botNode(message));
    });
    thread.append(inner);
    if (!keepScroll) thread.scrollTop = thread.scrollHeight;
  }

  function renderChats() {
    const list = $("#chat-list");
    list.replaceChildren();
    if (!state.conversations.length) {
      list.append(el("li", { class: "none", text: "Your questions will appear here." }));
      return;
    }
    for (const conversation of state.conversations) {
      list.append(el("li", { class: conversation.id === state.currentId ? "active" : null },
        el("button", { class: "open", type: "button", text: conversation.title, title: conversation.title,
          onclick: () => { openConversation(conversation.id); location.hash = "#/ask"; } }),
        el("button", { class: "remove", type: "button", text: "Delete", "aria-label": `Delete conversation: ${conversation.title}`,
          onclick: () => {
            state.conversations = state.conversations.filter((c) => c.id !== conversation.id);
            if (state.currentId === conversation.id) { state.currentId = null; state.shown = null; renderThread(); showEvidence(null); }
            save(); renderChats();
          } })));
    }
  }

  function openConversation(id) {
    state.currentId = id;
    const conversation = current();
    const lastBot = conversation ? [...conversation.messages].reverse().find((m) => m.role === "bot" && m.sources?.length) : null;
    renderChats(); renderThread(); showEvidence(lastBot || null);
  }

  /* ---------- evidence panel ---------- */
  function showEvidence(message, focusN = null, openSheet = false) {
    state.shown = message;
    const body = $("#evidence-body");
    body.replaceChildren();
    document.querySelectorAll(".cite[aria-pressed]").forEach((c) => c.removeAttribute("aria-pressed"));

    if (!message || !(message.sources || []).length) {
      body.append(el("div", { class: "evidence-empty" },
        el("p", { text: "When you ask a question, the passages the answer was taken from appear here." }),
        el("div", { class: "source cited sweep demo-card" },
          el("div", { class: "source-body" }, el("div", { class: "doc-text" },
            el("p", {}, "The assistant only answers from the university's documents. ",
              el("mark", { text: "The sentence that supports the answer is marked like this," }),
              " so you can check it yourself."))))));
      return;
    }

    const cited = message.sources.filter((s) => s.cited);
    const others = message.sources.filter((s) => !s.cited);
    const card = (source) => {
      const node = el("article", { class: "source" + (source.cited ? " cited" : ""), id: `source-${source.n}`, "data-n": source.n },
        el("div", { class: "source-head" },
          el("div", { class: "source-top" },
            el("span", { class: "source-n", text: source.n }),
            el("span", { class: "tag", "data-cat": source.category, text: categoryLabel(source.category) }),
            source.updated ? el("span", { class: "when", text: `Updated ${formatDate(source.updated)}` }) : null),
          el("div", { class: "source-title", text: source.title }),
          el("div", { class: "source-section", text: source.section })),
        el("div", { class: "source-body" }, renderBlocks(source.blocks)));
      if (!source.cited) {
        const toggle = el("button", { class: "btn-quiet source-toggle", type: "button", text: "Read passage", "aria-expanded": "false",
          onclick: () => {
            const open = node.classList.toggle("open");
            toggle.textContent = open ? "Hide passage" : "Read passage";
            toggle.setAttribute("aria-expanded", String(open));
          } });
        node.append(toggle);
      }
      return node;
    };
    cited.forEach((s) => body.append(card(s)));
    if (others.length) {
      body.append(el("p", { class: "evidence-label",
        text: message.pending ? "Passages found. The answer is being written from these."
          : message.abstained ? "Closest passages found. None of them answers the question."
          : "Also retrieved, not used in the answer" }));
      others.forEach((s) => body.append(card(s)));
    }

    const target = focusN ? $(`#source-${focusN}`, body) : $(".source.cited", body);
    if (target) {
      if (focusN) {
        target.classList.add("focus");
        document.querySelectorAll(`.cite[data-n="${focusN}"]`).forEach((c) => c.setAttribute("aria-pressed", "true"));
      }
      target.classList.add("sweep");                      // the highlighter stroke draws itself in
      target.scrollIntoView({ block: "nearest" });
      if (!focusN) body.scrollTop = 0;
    }
    if (openSheet) $("#evidence").classList.add("open");
  }

  /* ---------- asking ---------- */
  async function ask(question) {
    question = question.trim();
    if (!question || state.busy) return;
    let conversation = current();
    if (!conversation) {
      conversation = { id: String(Date.now()), title: question.slice(0, 60), messages: [] };
      state.conversations.unshift(conversation);
      state.currentId = conversation.id;
    }
    const history = conversation.messages.slice(-6).map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.content.slice(0, 3900) }));
    const message = { role: "bot", content: "", pending: true, question, sources: [] };
    conversation.messages.push({ role: "user", content: question }, message);
    state.busy = true; $("#send").disabled = true;
    $("#question").value = ""; autosize();
    renderChats(); renderThread(false, true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history, generator: $("#generator").value || "extractive", category: $("#category").value || null }),
      });
      if (!response.ok || !response.body) throw new Error(`The server could not answer (${response.status}).`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const handle = (event) => {
        if (event.type === "meta") {
          // passages are known before the answer is written: show them while the model works
          message.sources = event.sources;
          if (event.sources.length) { showEvidence(message); updateLast(message); }
        }
        else if (event.type === "token") { message.content += event.text; updateLast(message); }
        else if (event.type === "reset") { message.content = ""; updateLast(message); }
        else if (event.type === "error") throw new Error(event.message);
        else if (event.type === "done") {
          Object.assign(message, { content: event.answer, sources: event.sources, abstained: event.abstained,
            generator: event.generator, note: event.note, latency_ms: event.latency_ms, confidence: event.confidence, pending: false });
        }
      };
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let newline;
        while ((newline = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, newline).trim();
          buffer = buffer.slice(newline + 1);
          if (line) handle(JSON.parse(line));
        }
      }
      if (buffer.trim()) handle(JSON.parse(buffer));
      if (message.pending) throw new Error("The answer stopped before it finished. Ask again.");
    } catch (error) {
      Object.assign(message, { pending: false, abstained: true, generator: "none", sources: [],
        content: `Something went wrong: ${error.message}` });
    } finally {
      state.busy = false; $("#send").disabled = false;
      save(); renderThread(); showEvidence(message.sources.length ? message : null);
      $("#question").focus({ preventScroll: true });
    }
  }

  function updateLast(message) {
    const nodes = document.querySelectorAll(".msg-bot");
    const last = nodes[nodes.length - 1];
    if (!last) return;
    last.replaceWith(botNode(message));
    const thread = $("#thread");
    thread.scrollTop = thread.scrollHeight;
  }

  function autosize() {
    const box = $("#question");
    box.style.height = "auto";
    // while the Ask page is hidden the box has no height to measure: leave it to the stylesheet
    box.style.height = box.scrollHeight ? Math.min(box.scrollHeight, 160) + "px" : "";
  }

  /* ---------- library ---------- */
  async function loadLibrary() {
    try {
      state.docs = (await api("/api/documents")).documents;
    } catch (error) { toast(error.message, true); return; }
    const list = $("#doc-list");
    list.replaceChildren();
    const passages = state.docs.reduce((sum, d) => sum + d.passages, 0);
    $("#library-sub").textContent = `${state.docs.length} documents, split into ${passages} searchable passages. ` +
      "Add your university's own files to make the assistant answer from them.";
    const notice = $("#library-notice");
    notice.hidden = !state.docs.some((d) => d.origin === "sample");
    notice.textContent = "The documents marked Sample are illustrative data for a fictional university, written for this project. " +
      "Replace them with official documents before relying on any answer.";

    for (const category of state.health.categories) {
      const docs = state.docs.filter((d) => d.category === category.id);
      if (!docs.length) continue;
      list.append(el("section", { class: "doc-group" },
        el("h2", {}, el("span", { class: "tag", "data-cat": category.id, text: category.label }),
          el("small", { text: `${docs.length} ${docs.length === 1 ? "document" : "documents"}` })),
        el("ul", {}, docs.map((d) => el("li", {},
          el("button", { class: "doc-item", type: "button", "data-doc": d.doc_id, style: `--cat: var(--cat-${d.category})`,
            "aria-current": String(state.openDoc === d.doc_id), onclick: () => openDoc(d.doc_id) },
            el("strong", { text: d.title }),
            el("span", { text: `${d.doc_id}, ${d.sections} sections, ${d.origin === "sample" ? "Sample" : "Added by you"}` })))))));
    }
    if (!state.docs.length) list.append(el("p", { class: "empty", text: "No documents yet. Add one above to start." }));
  }

  async function openDoc(docId) {
    state.openDoc = docId;
    document.querySelectorAll(".doc-item").forEach((b) => b.setAttribute("aria-current", String(b.dataset.doc === docId)));
    const reader = $("#reader");
    try {
      const doc = await api(`/api/documents/${encodeURIComponent(docId)}`);
      const meta = el("div", { class: "reader-meta" },
        el("span", { class: "tag", "data-cat": doc.category, text: categoryLabel(doc.category) }),
        el("span", { text: doc.doc_id }),
        doc.updated ? el("span", { text: `Updated ${formatDate(doc.updated)}` }) : null,
        el("span", { text: doc.file }));
      if (doc.origin === "upload") {
        meta.append(el("button", { class: "btn-quiet danger", type: "button", text: "Remove document",
          onclick: async () => {
            if (!confirm(`Remove "${doc.title}" from the library?`)) return;
            try {
              await api(`/api/documents/${encodeURIComponent(doc.doc_id)}`, { method: "DELETE" });
              state.openDoc = null;
              reader.replaceChildren(el("p", { class: "empty", text: "Choose a document to read it section by section." }));
              await refreshHealth(); await loadLibrary(); toast("Document removed");
            } catch (error) { toast(error.message, true); }
          } }));
      }
      reader.replaceChildren(
        el("header", { class: "reader-head" }, el("h2", { text: doc.title }), meta),
        ...doc.sections.map((s) => el("section", {}, el("h3", { text: s.heading }), renderBlocks(s.blocks))));
      reader.scrollTop = 0;
      if (window.matchMedia("(max-width: 940px)").matches) reader.scrollIntoView({ block: "start" });
    } catch (error) { toast(error.message, true); }
  }

  async function upload(event) {
    event.preventDefault();
    const file = $("#upload-file").files[0];
    if (!file) return;
    const button = $("#upload-btn");
    button.disabled = true; button.textContent = "Adding...";
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("category", $("#upload-category").value);
      const result = await api("/api/documents", { method: "POST", body: form });
      $("#upload-form").reset(); $("#upload-name").textContent = "Choose a PDF, DOCX, MD or TXT file";
      await refreshHealth(); await loadLibrary(); await openDoc(result.doc_id);
      toast(result.replaced ? "Document replaced" : "Document added");
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.textContent = "Add document"; }
  }

  /* ---------- evaluation ---------- */
  const pct = (value) => `${(value * 100).toFixed(1)}%`;
  const bar = (value) => el("div", { class: "bar" }, el("span", { text: pct(value) }), el("i", { style: `--v:${(value * 100).toFixed(1)}%` }));
  const panel = (title, sub, ...body) => el("section", { class: "panel" },
    el("div", { class: "panel-head" }, el("h2", { text: title }), sub ? el("p", { text: sub }) : null),
    el("div", { class: "panel-body" }, ...body));
  const table = (head, rows) => el("div", { class: "table-scroll" }, el("table", { class: "data" },
    el("thead", {}, el("tr", {}, head.map((h) => el("th", { scope: "col", text: h })))), el("tbody", {}, rows)));

  async function loadEval() {
    try { state.evalData = await api("/api/eval/results"); }
    catch (error) { toast(error.message, true); return; }
    state.evalFresh = true;
    renderEval();
  }

  function renderEval() {
    const data = state.evalData;
    const body = $("#eval-body");
    body.replaceChildren();
    body.classList.toggle("fresh", Boolean(state.evalFresh));     // bars grow only on arrival, not on every filter click
    state.evalFresh = false;
    if (!data?.available) {
      body.append(el("p", { class: "empty", text: "No results yet. Run the evaluation to score the assistant on the labelled questions." }));
      return;
    }
    const methods = Object.keys(data.retrieval);
    const best = methods.reduce((a, b) => (data.retrieval[b].passage.mrr > data.retrieval[a].passage.mrr ? b : a));
    const generators = Object.keys(data.answers);
    if (!generators.includes(state.evalGen)) state.evalGen = generators[0];
    const firstGen = data.answers[generators[0]].summary;

    body.append(el("dl", { class: "facts" },
      el("div", {}, el("dt", { text: "Labelled questions" }), el("dd", {}, String(data.questions.total), " ",
        el("small", { text: `${data.questions.answerable} answerable, ${data.questions.unanswerable} out of scope` }))),
      el("div", {}, el("dt", { text: "Corpus" }), el("dd", {}, String(data.corpus.documents), " ",
        el("small", { text: `documents, ${data.corpus.passages} passages` }))),
      el("div", {}, el("dt", { text: `Right passage in top 3, ${best}` }), el("dd", { text: pct(data.retrieval[best].passage["hit@3"]) })),
      el("div", {}, el("dt", { text: `Answers correct, ${GEN_SHORT[generators[0]].toLowerCase()}` }), el("dd", { text: pct(firstGen.accuracy) }))));

    body.append(panel("Retrieval",
      "Share of answerable questions where the passage labelled as correct is among the top results. Hit@1 means it was ranked first. MRR averages 1/rank, so it rewards ranking the right passage higher.",
      table(["Retriever", "Hit@1", "Hit@3", "Hit@5", "MRR", "Time per query"], methods.map((m) => {
        const p = data.retrieval[m].passage;
        return el("tr", { class: m === best && methods.length > 1 ? "best" : null }, el("th", { scope: "row", text: METHOD[m] || m }),
          el("td", {}, bar(p["hit@1"])), el("td", {}, bar(p["hit@3"])), el("td", {}, bar(p["hit@5"])),
          el("td", { text: p.mrr.toFixed(3) }), el("td", { text: `${data.retrieval[m].ms_per_query} ms` }));
      }))));

    const breakdown = (title, sub, key, label) => {
      const values = Object.keys(data.retrieval[methods[0]][key]);
      const short = { bm25: "BM25", dense: "Dense", hybrid: "Hybrid" };
      return panel(title, sub, table([label, "Questions", ...methods.map((m) => short[m] || m)], values.map((v) =>
        el("tr", {}, el("th", { scope: "row", text: key === "by_category" ? categoryLabel(v) : v[0].toUpperCase() + v.slice(1) }),
          el("td", { text: data.retrieval[methods[0]][key][v].n }),
          methods.map((m) => el("td", { text: pct(data.retrieval[m][key][v]["hit@3"]) }))))));
    };
    body.append(el("div", { class: "split" },
      breakdown("By how the question is worded", "Right passage in the top 3. Direct questions reuse the document's words. Paraphrased and colloquial ones do not, which is where keyword search struggles.", "by_style", "Wording"),
      breakdown("By document category", "Right passage in the top 3, by where that passage lives.", "by_category", "Category")));

    const ab = data.abstention;
    const abRow = (name, r) => el("tr", {}, el("th", { scope: "row", text: name }),
      el("td", { text: `${r.n_answerable} + ${r.n_unanswerable}` }), el("td", {}, bar(r.answered_when_answerable)),
      el("td", {}, bar(r.declined_when_unanswerable)), el("td", { text: pct(r.balanced_accuracy) }));
    body.append(panel("Knowing when not to answer",
      `The assistant declines when its retrieval confidence is below ${ab.threshold}. That threshold was chosen on the dev half of the questions and is scored here on the held-out test half.`,
      table(["Split", "Answerable + out of scope", "Answered when answerable", "Declined when out of scope", "Balanced accuracy"],
        [abRow("Dev (used to choose)", ab.dev), abRow("Test (held out)", ab.test)]),
      el("p", { class: "explain", text: `With only ${data.questions.unanswerable} out-of-scope questions, each one moves the declined rate by several points. Treat it as an indication, not a precise figure.` })));

    body.append(panel("Answer quality",
      "An answerable question counts as correct when the assistant answered and the answer contains every labelled key fact. An out-of-scope question counts as correct when the assistant declined.",
      table(["Answer by", "Questions", "Correct overall", "Answerable correct", "Key facts found", "Cited the right document", "Out of scope declined", "Median time"],
        generators.map((g) => {
          const s = data.answers[g].summary;
          return el("tr", {}, el("th", { scope: "row", text: GEN_SHORT[g] || g }), el("td", { text: s.n }),
            el("td", {}, bar(s.accuracy)), el("td", { text: pct(s.answerable_correct) }), el("td", { text: pct(s.fact_coverage) }),
            el("td", { text: pct(s.cited_gold_document) }), el("td", { text: pct(s.unanswerable_declined) }),
            el("td", { text: s.latency_ms.median >= 1000 ? `${(s.latency_ms.median / 1000).toFixed(1)} s` : `${s.latency_ms.median} ms` }));
        }))));

    const rows = data.answers[state.evalGen].rows.filter((r) => !state.evalWrongOnly || !r.correct);
    const wrong = data.answers[state.evalGen].rows.filter((r) => !r.correct).length;
    body.append(panel("Question by question", null,
      el("div", { class: "filters" },
        generators.length > 1 ? el("label", { class: "pick" }, el("span", { text: "Answer by" }),
          el("select", { onchange: (e) => { state.evalGen = e.target.value; renderEval(); } },
            generators.map((g) => el("option", { value: g, selected: g === state.evalGen, text: GEN_SHORT[g] || g })))) : null,
        el("button", { class: "btn-quiet", type: "button", "aria-pressed": String(!state.evalWrongOnly), text: `All ${data.answers[state.evalGen].rows.length}`,
          onclick: () => { state.evalWrongOnly = false; renderEval(); } }),
        el("button", { class: "btn-quiet", type: "button", "aria-pressed": String(state.evalWrongOnly), text: `Incorrect ${wrong}`,
          onclick: () => { state.evalWrongOnly = true; renderEval(); } })),
      rows.length ? table(["Id", "Question", "Wording", "Result", "Answer given"], rows.map((r) =>
        el("tr", {}, el("td", { text: r.id }), el("td", { class: "q", text: r.question }),
          el("td", { text: r.type === "unanswerable" ? "Out of scope" : r.style }),
          el("td", {}, el("span", { class: `verdict ${r.correct ? "yes" : "no"}`,
            text: r.correct ? "Correct" : (r.type === "unanswerable" ? "Should have declined" : r.abstained ? "Declined" : `${r.facts_found}/${r.facts_total} facts`) })),
          el("td", { class: "a", text: r.abstained ? "Declined to answer" : r.answer.length > 190 ? r.answer.slice(0, 190) + "..." : r.answer }))))
        : el("p", { class: "empty", text: "Nothing to show for this filter." })));

    $("#eval-sub").textContent = `How the assistant scores on the labelled student-question set. Last run ${formatDate(data.generated_at)}, ` +
      `${new Date(data.generated_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}.`;
  }

  async function runEval() {
    const button = $("#eval-run");
    button.disabled = true; button.textContent = "Running...";
    try {
      state.evalData = await api("/api/eval/run", { method: "POST" });
      state.evalFresh = true;
      renderEval(); await refreshHealth(); toast("Evaluation finished");
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; button.textContent = "Run evaluation"; }
  }

  /* ---------- motion helpers ---------- */
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Run a callback the first time an element scrolls into view.
  function whenSeen(node, callback, threshold = 0.25) {
    if (!node) return;
    if (reducedMotion || !("IntersectionObserver" in window)) { callback(); return; }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { observer.disconnect(); callback(); }
    }, { threshold });
    observer.observe(node);
  }

  // Count a figure such as "94.1%" or "180 ms" up from zero.
  function countUp(node) {
    const match = /^([\d.]+)(.*)$/.exec(node.textContent.trim());
    if (!match || reducedMotion) return;
    const target = Number(match[1]);
    const decimals = (match[1].split(".")[1] || "").length;
    const started = performance.now();
    const frame = (now) => {
      const t = Math.min(1, (now - started) / 1100);
      const eased = 1 - Math.pow(1 - t, 3);
      node.textContent = (target * eased).toFixed(decimals) + match[2];
      if (t < 1) requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  // Type text into a node at a pace that takes about a second and a half whatever its length.
  function typeInto(node, text, done) {
    if (reducedMotion) { node.textContent = text; done(); return; }
    node.textContent = "";
    node.classList.add("typing");
    const step = Math.max(1, Math.ceil(text.length / 75));
    let shown = 0;
    const timer = setInterval(() => {
      shown = Math.min(text.length, shown + step);
      node.textContent = text.slice(0, shown);
      if (shown >= text.length) { clearInterval(timer); node.classList.remove("typing"); done(); }
    }, 20);
  }

  // Wrap each word of the hero headline so the words can rise in one after another.
  function splitHeadline() {
    const title = $("#hero-title");
    const text = title.textContent.trim();
    title.setAttribute("aria-label", text);
    title.replaceChildren();
    text.split(/\s+/).forEach((word, i) => {
      title.append(el("span", { class: "w", "aria-hidden": "true" }, el("span", { style: `--i:${i}`, text: word })), " ");
    });
  }

  /* ---------- home ---------- */
  // Ask from anywhere on the site: start a fresh conversation on the Ask page.
  function goAsk(question) {
    state.currentId = null;
    if (location.hash !== "#/ask") location.hash = "#/ask";
    renderChats(); renderThread(); showEvidence(null);
    ask(question);
  }

  // One quoted answer, without touching the conversation (used for the home page example).
  async function quickAnswer(question) {
    const response = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: [], generator: "extractive", category: null }),
    });
    if (!response.ok) throw new Error(`The server could not answer (${response.status}).`);
    const events = (await response.text()).split("\n").filter((line) => line.trim()).map((line) => JSON.parse(line));
    return events.find((event) => event.type === "done") || null;
  }

  async function renderHome() {
    if (state.homeReady) return;
    state.homeReady = true;
    const h = state.health;

    $("#hero-sub").textContent = `Ask about attendance, exams, fees, hostel or syllabus. The help desk answers only from ` +
      `${h.university}'s own documents, shows you the passage, and tells you when the documents don't cover it.`;
    $("#hero-try").replaceChildren(...STARTERS.slice(2, 5).map((s) =>
      el("button", { type: "button", text: s.q, onclick: () => goAsk(s.q) })));

    // a running strip of questions; each one can be asked with a click
    const tickerTrack = (copy) => el("div", { class: "ticker-track", "aria-hidden": copy ? "true" : null },
      TICKER.map((item) => el("button", { type: "button", "data-cat": item.cat, tabindex: copy ? "-1" : null,
        text: item.q, onclick: () => goAsk(item.q) })));
    $("#ticker").replaceChildren(tickerTrack(false), tickerTrack(true));

    const steps = [...document.querySelectorAll(".steps li")];
    steps.forEach((li, i) => li.style.setProperty("--i", i));
    whenSeen($(".steps"), () => steps.forEach((li) => li.classList.add("on")), 0.35);

    // the example exchange in the hero is a real answer from the running assistant
    const example = STARTERS[1].q;
    $("#demo-q").textContent = example;
    quickAnswer(example).then((result) => {
      if (!result) return;
      const firstCite = /\[(\d+)\]/.exec(result.answer);
      const source = firstCite ? result.sources.find((s) => s.n === Number(firstCite[1])) : null;
      const answerText = (firstCite ? result.answer.slice(0, firstCite.index) : result.answer).trim();
      if (source) {
        const chip = $("#demo-src");
        chip.hidden = false;
        chip.replaceChildren("From ", el("b", { text: source.title }), `, section ${source.section}`);
        chip.addEventListener("click", () => goAsk(example));

        const proof = $("#home-passage");
        proof.hidden = false;
        proof.replaceChildren(
          el("article", { class: "source cited" },
            el("div", { class: "source-head" },
              el("div", { class: "source-top" },
                el("span", { class: "source-n", text: source.n }),
                el("span", { class: "tag", "data-cat": source.category, text: categoryLabel(source.category) }),
                source.updated ? el("span", { class: "when", text: `Updated ${formatDate(source.updated)}` }) : null),
              el("div", { class: "source-title", text: source.title }),
              el("div", { class: "source-section", text: source.section })),
            el("div", { class: "source-body" }, renderBlocks(source.blocks))),
          el("p", { class: "how-proof-note", text: "The passage behind the example answer at the top of this page. The marked sentences are the ones the help desk found relevant." }));
      }
      // asked, then answered as if typed, then the source is inked in
      const demo = $("#demo");
      setTimeout(() => {
        demo.classList.add("in");
        setTimeout(() => {
          demo.classList.add("answering");
          typeInto($("#demo-a"), answerText, () => demo.classList.add("sourced"));
        }, reducedMotion ? 0 : 750);
      }, reducedMotion ? 0 : 900);
    }).catch(() => { $("#demo").hidden = true; });

    // what the corpus holds, by category
    api("/api/documents").then(({ documents }) => {
      const passages = documents.reduce((sum, d) => sum + d.passages, 0);
      $("#cats-sub").textContent = `${documents.length} documents, split into ${passages} searchable passages. ` +
        "Read any of them in the Library, or add your own.";
      $("#home-cats").replaceChildren(...h.categories.map((category, i) => {
        const docs = documents.filter((d) => d.category === category.id);
        const starter = STARTERS.find((s) => s.cat === category.id);
        const askable = starter && docs.length;
        return el("div", { class: "cat", "data-cat": category.id, style: `--i:${i}`,
          onclick: (event) => { if (askable && !event.target.closest("button")) goAsk(starter.q); } },
          el("div", { class: "cat-name" }, category.label,
            el("small", { text: `${docs.length} ${docs.length === 1 ? "document" : "documents"}` })),
          el("p", { class: "cat-docs", text: docs.length ? docs.slice(0, 3).map((d) => d.title).join(", ") + (docs.length > 3 ? ` and ${docs.length - 3} more` : "") : "No documents yet." }),
          askable ? el("button", { class: "cat-ask", type: "button", text: starter.q, onclick: () => goAsk(starter.q) }) : null);
      }));
      whenSeen($("#home-cats"), () => $("#home-cats").classList.add("on"), 0.12);
    }).catch(() => {});

    // measured results, straight from the last evaluation
    api("/api/eval/results").then((data) => {
      if (!data.available) return;
      const methods = Object.keys(data.retrieval);
      const best = methods.reduce((a, b) => (data.retrieval[b].passage.mrr > data.retrieval[a].passage.mrr ? b : a));
      const summary = data.answers[Object.keys(data.answers)[0]].summary;
      const score = (label, detail, value, text) => el("div", {},
        el("dt", {}, label, el("small", { text: detail })), el("dd", { text: text || pct(value) }),
        value == null ? null : el("div", { class: "meter" }, el("i", { style: `--v:${(value * 100).toFixed(1)}%` })));
      const ms = summary.latency_ms.median;
      $("#home-scores").replaceChildren(
        score("Right passage found", `in the top three results, ${data.questions.answerable} answerable questions`, data.retrieval[best].passage["hit@3"]),
        score("Answers correct", `all ${data.questions.total} questions, every key fact present`, summary.accuracy),
        score("Out-of-scope questions declined", `${data.questions.unanswerable} questions the documents do not cover`, summary.unanswerable_declined),
        score("Time to answer", "median, quoting the documents", null, ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`));
      $("#measured-title").textContent = `Tested on ${data.questions.total} student questions, including ones it should refuse`;
      $("#measured-sub").textContent = `Informal and Hindi-English questions are the weak spot: ${pct(summary.by_style.colloquial)} of those are answered correctly, ` +
        `against ${pct(summary.by_style.direct)} for questions that use the documents' own words.`;
      $("#home-measured").hidden = false;
      whenSeen($("#home-scores"), () => {
        $("#home-scores").classList.add("on");
        document.querySelectorAll("#home-scores dd").forEach(countUp);
      }, 0.3);
    }).catch(() => {});
  }

  /* ---------- shell ---------- */
  async function refreshHealth() {
    state.health = await api("/api/health");
    const h = state.health;
    $("#university").textContent = h.university;
    $("#topbar").hidden = !h.sample_corpus;
    $("#corpus-stat").textContent = `${h.university}. ${h.documents} documents, ${h.passages} passages. ` +
      (h.retrievers.includes("hybrid") ? "Keyword and meaning search." : "Keyword search only.");
    document.title = `Student Help Desk, ${h.university}`;
  }

  function fillSelects() {
    const h = state.health;
    for (const id of ["category", "upload-category"]) {
      const select = $("#" + id);
      h.categories.forEach((c) => select.append(el("option", { value: c.id, text: c.label })));
    }
    const generator = $("#generator");
    const saved = localStorage.getItem("shd.generator");
    h.generators.forEach((g) => generator.append(el("option", { value: g.id, disabled: !g.ready, title: g.detail,
      text: GEN_SHORT[g.id] + (g.ready ? "" : " (not set up)") })));
    if (saved && h.generators.some((g) => g.id === saved && g.ready)) generator.value = saved;
    generator.addEventListener("change", () => localStorage.setItem("shd.generator", generator.value));
  }

  function route() {
    const view = (location.hash.replace(/^#\/?/, "") || "home").split("/")[0];
    const name = ["home", "ask", "library", "evaluation"].includes(view) ? view : "home";
    const changed = $("#app").dataset.view !== name;
    $("#app").dataset.view = name;
    document.querySelectorAll("[data-nav]").forEach((a) =>
      a.dataset.nav === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    document.querySelectorAll("main.view").forEach((main) =>
      main.dataset.for === name ? main.setAttribute("id", "main") : main.removeAttribute("id"));
    $("#evidence").classList.remove("open");
    if (changed) window.scrollTo(0, 0);
    if (name === "home") renderHome();
    if (name === "ask") autosize();
    if (name === "library") loadLibrary();
    if (name === "evaluation") loadEval();
  }

  async function start() {
    splitHeadline();
    try { await refreshHealth(); }
    catch (error) {
      $("#app").dataset.view = "ask";
      $("#thread").append(el("div", { class: "welcome" }, el("h1", { text: "The help desk is not running" }),
        el("p", { text: `Start the server and reload this page. (${error.message})` })));
      return;
    }
    fillSelects();
    renderChats(); renderThread(); showEvidence(null);

    $("#composer").addEventListener("submit", (event) => { event.preventDefault(); ask($("#question").value); });
    $("#question").addEventListener("input", autosize);
    $("#question").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); ask($("#question").value); }
    });
    $("#new-chat").addEventListener("click", () => {
      state.currentId = null; location.hash = "#/ask";
      renderChats(); renderThread(); showEvidence(null); $("#question").focus();
    });
    $("#evidence-close").addEventListener("click", () => $("#evidence").classList.remove("open"));
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") $("#evidence").classList.remove("open"); });
    $("#upload-form").addEventListener("submit", upload);
    $("#upload-file").addEventListener("change", (event) => {
      $("#upload-name").textContent = event.target.files[0]?.name || "Choose a PDF, DOCX, MD or TXT file";
    });
    $("#eval-run").addEventListener("click", runEval);
    $("#hero-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const question = $("#hero-q").value.trim();
      if (!question) { $("#hero-q").focus(); return; }
      $("#hero-q").value = "";
      goAsk(question);
    });
    window.addEventListener("hashchange", route);

    // A link such as /?q=What+is+the+minimum+attendance asks that question on arrival.
    const linked = new URLSearchParams(location.search).get("q");
    if (linked) history.replaceState(null, "", location.pathname + "#/ask");
    route();
    if (linked) goAsk(linked.slice(0, 1000));
  }

  start();
})();
