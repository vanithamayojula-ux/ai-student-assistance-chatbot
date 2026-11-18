// Renders the report's diagrams and charts to report/figures/*.png.
// Needs Node, playwright-core and an installed Chrome:
//   npm i playwright-core   then   node report/make_figures.mjs
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const R = JSON.parse(fs.readFileSync(path.join(ROOT, 'data/eval/results.json'), 'utf8'));
const OUT = path.join(HERE, 'figures');
fs.mkdirSync(OUT, { recursive: true });

const C = { bm25: '#2a78d6', dense: '#eb6834', hybrid: '#1baf7a', rerank: '#eda100' };
const NAME = { bm25: 'BM25 (keywords)', dense: 'Dense (embeddings)', hybrid: 'Hybrid (fused)', rerank: 'Hybrid + reranker' };
const INK = '#0b0b0b', INK2 = '#52514e', GRID = '#e4e3df';
const pct = v => (v * 100).toFixed(1);

function legend(keys, x, y, names = NAME, cols = C) {
  let s = '', cx = x;
  for (const k of keys) {
    s += `<rect x="${cx}" y="${y - 10}" width="12" height="12" rx="3" fill="${cols[k]}"/>`;
    s += `<text x="${cx + 18}" y="${y}" font-size="13" fill="${INK2}">${names[k]}</text>`;
    cx += 34 + names[k].length * 7.4;
  }
  return s;
}

function groupedBars(id, title, groups, series, get, W = 760, H = 380) {
  const L = 52, T = 74, B = 44, PW = W - L - 20, PH = H - T - B;
  const y = v => T + PH * (1 - v);
  let s = `<svg id="${id}" xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" font-family="Segoe UI, Arial"><rect width="${W}" height="${H}" fill="#fff"/>`;
  s += `<text x="${L}" y="26" font-size="16" font-weight="600" fill="${INK}">${title}</text>` + legend(series, L, 50);
  for (const t of [0, .25, .5, .75, 1]) {
    s += `<line x1="${L}" x2="${W - 20}" y1="${y(t)}" y2="${y(t)}" stroke="${GRID}"/>`;
    s += `<text x="${L - 8}" y="${y(t) + 4}" font-size="12" text-anchor="end" fill="${INK2}">${t * 100}%</text>`;
  }
  const gw = PW / groups.length, bw = Math.min(46, Math.floor((gw - 28) / series.length) - 2);
  groups.forEach((g, gi) => {
    const x0 = L + gi * gw + (gw - series.length * (bw + 2)) / 2;
    series.forEach((k, si) => {
      const v = get(k, g.key), x = x0 + si * (bw + 2), yy = y(v);
      s += `<path d="M${x},${T + PH} V${yy + 4} q0,-4 4,-4 H${x + bw - 4} q4,0 4,4 V${T + PH} Z" fill="${C[k]}"/>`;
      s += `<text x="${x + bw / 2}" y="${yy - 6}" font-size="${bw < 40 ? 10 : 11.5}" text-anchor="middle" fill="${INK}">${bw < 40 ? Math.round(v * 100) : pct(v)}</text>`;
    });
    s += `<text x="${L + gi * gw + gw / 2}" y="${H - 18}" font-size="13" text-anchor="middle" fill="${INK}">${g.label}</text>`;
  });
  s += `<line x1="${L}" x2="${W - 20}" y1="${T + PH}" y2="${T + PH}" stroke="#8a8985"/></svg>`;
  return s;
}

const ret = R.retrieval, S = ['bm25', 'dense', 'hybrid', 'rerank'].filter((m) => ret[m]);
const STYLE = { direct: 'Direct', paraphrase: 'Paraphrase', colloquial: 'Colloquial', hinglish: 'Hindi-English' };
const answerable = ret.bm25.passage.n;
const chartA = groupedBars('chart-retrieval', `Labelled passage found in the top k results (${answerable} answerable questions)`,
  [{ key: 'hit@1', label: 'Hit@1' }, { key: 'hit@3', label: 'Hit@3' }, { key: 'hit@5', label: 'Hit@5' }],
  S, (k, g) => ret[k].passage[g]);
const chartB = groupedBars('chart-style', 'Hit@3 by how the question is worded',
  Object.keys(STYLE).filter((k) => ret.bm25.by_style[k]).map((k) => ({ key: k, label: `${STYLE[k]} (${ret.bm25.by_style[k].n})` })),
  S, (k, g) => ret[k].by_style[g]['hit@3']);

function curve() {
  const W = 760, H = 400, L = 52, T = 74, B = 50, PW = W - L - 150, PH = H - T - B;
  const cv = R.abstention.curve, th = R.abstention.threshold;
  const x0 = cv[0].threshold, x1 = cv[cv.length - 1].threshold;
  const X = v => L + PW * (v - x0) / (x1 - x0), Y = v => T + PH * (1 - v);
  const cols = { a: '#2a78d6', d: '#eb6834' };
  let s = `<svg id="chart-threshold" xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" font-family="Segoe UI, Arial"><rect width="${W}" height="${H}" fill="#fff"/>`;
  s += `<text x="${L}" y="26" font-size="16" font-weight="600" fill="${INK}">Effect of the confidence threshold (all ${R.questions.total} questions)</text>`;
  s += legend(['a', 'd'], L, 50, { a: 'Answerable questions answered', d: 'Out-of-scope questions declined' }, cols);
  for (const t of [0, .25, .5, .75, 1]) {
    s += `<line x1="${L}" x2="${L + PW}" y1="${Y(t)}" y2="${Y(t)}" stroke="${GRID}"/>`;
    s += `<text x="${L - 8}" y="${Y(t) + 4}" font-size="12" text-anchor="end" fill="${INK2}">${t * 100}%</text>`;
  }
  for (const p of cv) {
    if (Math.round(p.threshold * 100) % 10 === 0) {
      s += `<text x="${X(p.threshold)}" y="${T + PH + 18}" font-size="12" text-anchor="middle" fill="${INK2}">${p.threshold.toFixed(1)}</text>`;
    }
  }
  s += `<text x="${L + PW / 2}" y="${H - 8}" font-size="13" text-anchor="middle" fill="${INK2}">Confidence threshold</text>`;
  s += `<line x1="${X(th)}" x2="${X(th)}" y1="${T - 6}" y2="${T + PH}" stroke="${INK}" stroke-dasharray="4 4"/>`;
  s += `<text x="${X(th) + 6}" y="${T + 4}" font-size="12" fill="${INK}">chosen: ${th}</text>`;
  const line = (key, col) => `<polyline fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" points="${cv.map(p => X(p.threshold) + ',' + Y(p[key])).join(' ')}"/>`;
  s += line('answered_when_answerable', cols.a) + line('declined_when_unanswerable', cols.d);
  const last = cv[cv.length - 1];
  s += `<text x="${L + PW + 8}" y="${Y(last.answered_when_answerable) + 4}" font-size="12.5" fill="${INK}">Answered ${pct(last.answered_when_answerable)}%</text>`;
  s += `<text x="${L + PW + 8}" y="${Y(last.declined_when_unanswerable) + 4}" font-size="12.5" fill="${INK}">Declined ${pct(last.declined_when_unanswerable)}%</text>`;
  s += `<line x1="${L}" x2="${L + PW}" y1="${T + PH}" y2="${T + PH}" stroke="#8a8985"/></svg>`;
  return s;
}

function flow() {
  const W = 820, H = 960;
  const box = (x, y, w, h, lines, o = {}) => {
    let t = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${o.rx ?? 8}" fill="${o.fill || '#fff'}" stroke="${o.stroke || '#2B3990'}" stroke-width="1.5"/>`;
    const y0 = y + h / 2 - (lines.length - 1) * 9 + 5;
    lines.forEach((l, i) => {
      t += `<text x="${x + w / 2}" y="${y0 + i * 18}" font-size="${i === 0 ? 14 : 12.5}" font-weight="${i === 0 ? 600 : 400}" fill="${i === 0 ? (o.ink || INK) : INK2}" text-anchor="middle">${l}</text>`;
    });
    return t;
  };
  const dia = (cx, cy, w, h, lines) => {
    let t = `<polygon points="${cx},${cy - h / 2} ${cx + w / 2},${cy} ${cx},${cy + h / 2} ${cx - w / 2},${cy}" fill="#FFF6C2" stroke="#8a6d00" stroke-width="1.5"/>`;
    lines.forEach((l, i) => {
      t += `<text x="${cx}" y="${cy - (lines.length - 1) * 9 + 5 + i * 18}" font-size="13.5" font-weight="600" fill="${INK}" text-anchor="middle">${l}</text>`;
    });
    return t;
  };
  const arr = (pts, label, lx, ly) =>
    `<polyline points="${pts}" fill="none" stroke="#3a3a3a" stroke-width="1.5" marker-end="url(#ah)"/>` +
    (label ? `<text x="${lx}" y="${ly}" font-size="12.5" font-weight="600" fill="${INK}">${label}</text>` : '');
  const MX = 530, BW = 340, BX = MX - BW / 2;
  let s = `<svg id="flowchart" xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" font-family="Segoe UI, Arial"><rect width="${W}" height="${H}" fill="#fff"/>`;
  s += `<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 Z" fill="#3a3a3a"/></marker></defs>`;
  s += `<text x="130" y="28" font-size="12.5" font-weight="700" fill="${INK2}" text-anchor="middle">INGEST (once, and after uploads)</text>`;
  s += `<text x="${MX}" y="28" font-size="12.5" font-weight="700" fill="${INK2}" text-anchor="middle">ANSWER (every question)</text>`;
  s += `<line x1="276" x2="276" y1="14" y2="${H - 14}" stroke="${GRID}" stroke-dasharray="5 5"/>`;
  s += box(20, 48, 220, 60, ['Documents', '.md  .txt  .pdf  .docx'], { fill: '#EEF0FA' });
  s += arr('130,108 130,140');
  s += box(20, 142, 220, 60, ['Split into passages', 'at section headings']);
  s += arr('130,202 130,234');
  s += box(20, 236, 220, 60, ['BM25 keyword index', 'term statistics per passage']);
  s += arr('130,296 130,328');
  s += box(20, 330, 220, 60, ['Sentence embeddings', 'bge-small-en-v1.5, cached']);
  s += arr(`240,360 300,360 300,250 ${BX - 2},250`);
  s += box(BX, 48, BW, 46, ['Student question'], { rx: 23, fill: '#1D2768', ink: '#fff', stroke: '#1D2768' });
  s += arr(`${MX},94 ${MX},120`);
  s += box(BX, 122, BW, 60, ['Prepare the question', 'follow-up: add previous question; Hindi-English: rewrite']);
  s += arr(`${MX},182 ${MX},208`);
  s += box(BX, 210, BW, 78, ['Hybrid retrieval', 'rank by BM25 and by embedding similarity,', 'merge with reciprocal rank fusion, keep top 4']);
  s += arr(`${MX},288 ${MX},314`);
  s += box(BX, 316, BW, 60, ['Confidence score (0 to 1)', 'question-term coverage + best similarity']);
  s += arr(`${MX},376 ${MX},402`);
  s += dia(MX, 452, 300, 96, ['Confidence at or', 'above threshold?']);
  s += arr(`${MX},500 ${MX},540`, 'Yes', MX + 8, 524);
  s += box(BX, 542, BW, 78, ['Generate the answer', 'quote-only, Gemini or Claude,', 'using only the 4 passages, with [n] citations']);
  s += arr(`${MX},620 ${MX},646`);
  s += dia(MX, 696, 300, 96, ['Model replied', 'NO_ANSWER?']);
  s += arr(`${MX},744 ${MX},784`, 'No', MX + 8, 768);
  s += box(BX, 786, BW, 60, ['Mark supporting sentences', 'in each cited passage']);
  s += arr(`${MX},846 ${MX},872`);
  s += box(BX, 874, BW, 60, ['Answer and sources shown', 'streamed to the browser'], { rx: 30, fill: '#E8F6EF', stroke: '#1b7a55' });
  s += box(30, 664, 210, 64, ['Decline', '"not in the documents"'], { fill: '#FDECEA', stroke: '#b3392f' });
  s += arr(`${MX - 150},452 135,452 135,662`, 'No', 330, 444);
  s += arr(`${MX - 150},696 242,696`, 'Yes', 330, 688);
  s += `<text x="135" y="750" font-size="12" fill="${INK2}" text-anchor="middle">and point the student to</text>`;
  s += `<text x="135" y="766" font-size="12" fill="${INK2}" text-anchor="middle">the right university office</text>`;
  return s + '</svg>';
}

const logical = `<div id="logical" style="width:820px;background:#fff;padding:18px;font-family:Segoe UI,Arial;color:${INK};box-sizing:border-box">
<style>
#logical .layer{border:1.5px solid #2B3990;border-radius:10px;padding:12px 14px 14px;margin-bottom:8px}
#logical .lt{font-size:12px;font-weight:700;letter-spacing:.06em;color:#2B3990;margin-bottom:9px}
#logical .row{display:flex;gap:10px}
#logical .b{flex:1;border:1px solid #b9bfdc;border-radius:7px;padding:8px 10px;background:#F6F7FC}
#logical .b b{display:block;font-size:13.5px;margin-bottom:2px}
#logical .b span{font-size:12px;color:${INK2};line-height:1.35;display:block}
#logical .arrow{text-align:center;font-size:12px;color:${INK2};margin:0 0 8px}
#logical .y{background:#FFF6C2;border-color:#d8c25a}
#logical .g{background:#EEF6F1;border-color:#a9cdbb}
</style>
<div class="layer"><div class="lt">PRESENTATION &nbsp;·&nbsp; web/ (HTML, CSS, JavaScript in the browser)</div><div class="row">
<div class="b"><b>Home</b><span>what the assistant does, with a live example answer</span></div>
<div class="b"><b>Ask</b><span>conversation, streamed answer, evidence panel with highlighted source sentences</span></div>
<div class="b"><b>Library</b><span>browse and read documents, upload or remove files</span></div>
<div class="b"><b>Evaluation</b><span>retrieval, abstention and answer scores, per-question table</span></div>
<div class="b"><b>Local storage</b><span>past conversations kept in the browser</span></div></div></div>
<div class="arrow">▲▼ &nbsp; HTTP and JSON; answers streamed as newline-delimited JSON events</div>
<div class="layer"><div class="lt">API &nbsp;·&nbsp; app/main.py (FastAPI)</div><div class="row">
<div class="b"><b>/api/chat</b><span>question in, event stream out</span></div>
<div class="b"><b>/api/documents</b><span>list, read, upload, delete</span></div>
<div class="b"><b>/api/eval</b><span>results, re-run</span></div>
<div class="b"><b>/api/feedback</b><span>helpful or not helpful</span></div>
<div class="b"><b>/api/health</b><span>corpus and model status</span></div></div></div>
<div class="arrow">▲▼</div>
<div class="layer"><div class="lt">RAG CORE &nbsp;·&nbsp; app/pipeline.py (Engine: retrieve, gate, generate, cite)</div><div class="row">
<div class="b"><b>ingest.py</b><span>read files, split at headings into passages</span></div>
<div class="b"><b>retrieval.py</b><span>BM25, dense encoder, rank fusion, confidence score</span></div>
<div class="b y"><b>generate.py</b><span>quote-only, Gemini and Claude generators; sentence highlighting</span></div>
<div class="b"><b>textutil.py</b><span>tokenizer, sentence and table-row splitting</span></div>
<div class="b"><b>evaluate.py</b><span>metrics on the labelled question set, threshold tuning</span></div></div></div>
<div class="arrow">▲▼</div>
<div class="row" style="gap:8px">
<div class="layer" style="flex:1.7;margin:0"><div class="lt">DATA &nbsp;·&nbsp; data/</div><div class="row">
<div class="b g"><b>corpus/, uploads/</b><span>documents in five categories</span></div>
<div class="b g"><b>index/</b><span>embedding model and cached vectors</span></div>
<div class="b g"><b>eval/</b><span>questions.jsonl, results.json, threshold.json</span></div></div></div>
<div class="layer" style="flex:1;margin:0;border-style:dashed"><div class="lt">OPTIONAL LANGUAGE MODELS</div><div class="row">
<div class="b"><b>Gemini API</b><span>needs an API key</span></div>
<div class="b"><b>Claude API</b><span>needs an API key</span></div></div></div>
</div></div>`;

const html = path.join(OUT, '_figs.html');
fs.writeFileSync(html, `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#fff">${flow()}${logical}${chartA}${chartB}${curve()}</body>`);
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 900, height: 1000 }, deviceScaleFactor: 2 });
await page.goto('file:///' + html.replace(/\\/g, '/'));
for (const id of ['flowchart', 'logical', 'chart-retrieval', 'chart-style', 'chart-threshold']) {
  await page.locator('#' + id).screenshot({ path: path.join(OUT, id + '.png') });
}
await browser.close();
fs.unlinkSync(html);
console.log('figures written to', OUT);
