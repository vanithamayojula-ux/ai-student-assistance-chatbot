"""Builds the project report from the university template and the latest evaluation.

    .venv\\Scripts\\python report\\build_report.py

Reads report/template.docx, data/eval/results.json and report/figures/*.png and writes
report/AI_Student_Assistance_Chatbot_Report.docx. Every number in the report is read
from results.json, so re-running after a new evaluation keeps the text in step.
Open the result in Word and press Ctrl+A then F9 to refresh the contents lists
(report/finalize.ps1 does this automatically and also saves a PDF).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from docx.text.paragraph import Paragraph

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FIG = HERE / "figures"
OUT = HERE / "AI_Student_Assistance_Chatbot_Report.docx"

# ---- details only the student knows: fill these in, then rebuild ---------------------
TITLE = "AI Student Assistance Chatbot"
STUDENT = "Mayojula Aravind"
MONTH_YEAR = "November 2026"
# Left as the template's [placeholders] on purpose: registration number, roll number,
# section, program, course code and title, faculty name, designation, department, date.

R = json.loads((ROOT / "data/eval/results.json").read_text(encoding="utf-8"))
RET, ABS, ANS = R["retrieval"], R["abstention"], R["answers"]
EX = ANS["extractive"]["summary"]
LLM = ANS.get("gemini", {}).get("summary")
QUESTIONS = [json.loads(line) for line in (ROOT / "data/eval/questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def pc(v: float, d: int = 1) -> str:
    return f"{v * 100:.{d}f}%"


def f3(v: float) -> str:
    return f"{v:.3f}"


# ---- document helpers ----------------------------------------------------------------
doc = Document(str(HERE / "template.docx"))
P = list(doc.paragraphs)          # template paragraphs, by their original index
BODY_PROTO = P[38]                # a "[Text]" paragraph: justified body text
REF_PROTO = P[93]                 # a numbered reference entry


def ensure_style(name: str, size: float, bold: bool = False, italic: bool = False):
    if name in [s.name for s in doc.styles]:
        return doc.styles[name]
    style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = doc.styles["Normal"]
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.italic = italic
    style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    style.paragraph_format.space_before = Pt(6)
    style.paragraph_format.space_after = Pt(10)
    return style


ensure_style("Figure Caption", 10.5)
ensure_style("Table Caption", 10.5)


def set_text(par: Paragraph, text: str) -> None:
    """Replace a paragraph's text, keeping the formatting of its first run."""
    runs = par.runs
    if not runs:
        par.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run._r.getparent().remove(run._r)
    # the template's placeholders are grey italic; real text must not be
    props = runs[0]._r.rPr
    if props is not None:
        for tag in ("w:i", "w:iCs", "w:color"):
            for el in props.findall(qn(tag)):
                props.remove(el)


def replace_in(par: Paragraph, mapping: dict[str, str]) -> None:
    for run in par.runs:
        for old, new in mapping.items():
            if old in run.text:
                run.text = run.text.replace(old, new)


def new_par(after, proto: Paragraph = BODY_PROTO, text: str = "") -> Paragraph:
    element = copy.deepcopy(proto._p)
    for child in list(element):
        if child.tag != qn("w:pPr"):
            element.remove(child)
    after.addnext(element)
    par = Paragraph(element, proto._parent)
    if text:
        par.add_run(text)
    return par


class Cursor:
    """Inserts blocks one after another, starting after a given paragraph."""

    def __init__(self, par: Paragraph):
        self.at = par._p

    def p(self, text: str, bold_lead: str = "") -> Paragraph:
        par = new_par(self.at)
        par.paragraph_format.space_before = Pt(6)
        if bold_lead:
            par.add_run(bold_lead).bold = True
        par.add_run(text)
        self.at = par._p
        return par

    def bullets(self, items: list[str], numbered: bool = False) -> None:
        for i, item in enumerate(items, start=1):
            par = new_par(self.at)
            fmt = par.paragraph_format
            fmt.left_indent = Inches(0.45)
            fmt.first_line_indent = Inches(-0.25)
            fmt.space_after = Pt(3)
            lead, _, rest = item.partition("||")
            mark = f"{i}.\t" if numbered else "•\t"
            par.add_run(mark)
            if rest:
                par.add_run(lead).bold = True
                par.add_run(rest)
            else:
                par.add_run(lead)
            fmt.tab_stops.add_tab_stop(Inches(0.45))
            self.at = par._p

    def h3(self, text: str) -> None:
        par = new_par(self.at)
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT
        par.paragraph_format.space_before = Pt(8)
        par.paragraph_format.keep_with_next = True
        par.add_run(text).bold = True
        self.at = par._p

    def figure(self, file: str, caption: str, width: float = 6.0) -> None:
        par = new_par(self.at)
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.keep_with_next = True
        par.paragraph_format.space_before = Pt(8)
        par.add_run().add_picture(str(FIG / file), width=Inches(width))
        self.at = par._p
        cap = new_par(self.at)
        cap.style = doc.styles["Figure Caption"]
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.add_run(caption)
        self.at = cap._p

    def table(self, caption: str, header: list[str], rows: list[list[str]],
              widths: list[float] | None = None, bold_rows: tuple[int, ...] = ()) -> None:
        cap = new_par(self.at)
        cap.style = doc.styles["Table Caption"]
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.keep_with_next = True
        cap.add_run(caption)
        self.at = cap._p

        table = doc.add_table(rows=len(rows) + 1, cols=len(header))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl_pr = table._tbl.tblPr
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}")
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "808080")
            borders.append(el)
        tbl_pr.append(borders)
        for r, values in enumerate([header] + rows):
            for c, value in enumerate(values):
                cell = table.cell(r, c)
                if widths:
                    cell.width = Inches(widths[c])
                par = cell.paragraphs[0]
                par.paragraph_format.space_after = Pt(2)
                par.paragraph_format.space_before = Pt(2)
                par.paragraph_format.keep_with_next = r < len(rows)   # keep the table on one page
                par.alignment = WD_ALIGN_PARAGRAPH.LEFT if c == 0 else WD_ALIGN_PARAGRAPH.CENTER
                run = par.add_run(str(value))
                run.font.size = Pt(10)
                run.bold = r == 0 or (r - 1) in bold_rows
                if r == 0:
                    shade = OxmlElement("w:shd")
                    shade.set(qn("w:val"), "clear")
                    shade.set(qn("w:fill"), "E7E9F4")
                    cell._tc.get_or_add_tcPr().append(shade)
        if widths and len(header) > 0:
            for row in table.rows:
                row.cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
        self.at.addnext(table._tbl)
        self.at = table._tbl
        spacer = new_par(self.at)
        spacer.paragraph_format.space_after = Pt(4)
        self.at = spacer._p

    def code(self, text: str) -> None:
        for line in text.strip("\n").split("\n"):
            par = new_par(self.at)
            par.alignment = WD_ALIGN_PARAGRAPH.LEFT
            fmt = par.paragraph_format
            fmt.space_after = Pt(0)
            fmt.space_before = Pt(0)
            fmt.left_indent = Inches(0.3)
            fmt.line_spacing = 1.0
            run = par.add_run(line if line else " ")
            run.font.name = "Courier New"
            run._r.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Courier New")
            run.font.size = Pt(9)
            self.at = par._p
        gap = new_par(self.at)
        gap.paragraph_format.space_after = Pt(2)
        self.at = gap._p


def fill(index: int, first: str) -> Cursor:
    """Put `first` into template paragraph `index`; return a cursor placed after it."""
    set_text(P[index], first)
    return Cursor(P[index])


# ---- numbers used in the text --------------------------------------------------------
n_docs, n_pass = R["corpus"]["documents"], R["corpus"]["passages"]
n_q = len(QUESTIONS)
n_ans = sum(q["type"] == "answerable" for q in QUESTIONS)
n_oos = n_q - n_ans
STYLES = [s for s in ("direct", "paraphrase", "colloquial", "hinglish")
          if any(q["style"] == s and q["type"] == "answerable" for q in QUESTIONS)]
STYLE_NAME = {"direct": "Direct", "paraphrase": "Paraphrase", "colloquial": "Colloquial", "hinglish": "Hindi-English"}
by_style_n = {s: sum(q["style"] == s and q["type"] == "answerable" for q in QUESTIONS) for s in STYLES}
METHODS = [m for m in ("bm25", "dense", "hybrid", "rerank") if m in RET]
SHORT = {"bm25": "BM25", "dense": "Dense", "hybrid": "Hybrid", "rerank": "Reranked"}
H = {m: RET[m]["passage"] for m in METHODS}
HAS_RR = "rerank" in RET
DESIGN = R.get("design_choices", {})
TH, LOOSE = ABS["threshold"], ABS["loose_threshold"]
DEV, TEST = ABS["dev"], ABS["test"]
RETR_NAME = {"bm25": "BM25 (keywords)", "dense": "Dense (embeddings)", "hybrid": "Hybrid (rank fusion)",
             "rerank": "Hybrid + reranker"}


def ms(value: float) -> str:
    return f"{value:.0f} ms" if value >= 10 else f"{value:.1f} ms"


def join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

# ---- cover, certificate, declaration ---------------------------------------------------
NAMES = {"[Your Specific Project Title]": TITLE, "[Student Name]": STUDENT, "[Month, Year]": MONTH_YEAR}
for par in P[:24]:
    replace_in(par, NAMES)
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            for par in cell.paragraphs:
                replace_in(par, NAMES)

# ---- acknowledgement, abstract -----------------------------------------------------------
set_text(P[25], (
    "I would like to thank my project supervisor, [Faculty Name], for the guidance and feedback "
    "given throughout this work, and the School of [Department], Lovely Professional University, "
    "for the opportunity to carry out this project as part of the course. I am grateful to my "
    "classmates, whose everyday questions about attendance, examinations and fees shaped the "
    "evaluation questions used in this report, and to my family for their constant support. "
    "This project builds on openly available tools, and I thank the people who maintain FastAPI, "
    "FastEmbed and the BGE embedding models."))

llm_abstract = ""
if LLM:
    llm_abstract = (f" When Gemini writes the answer instead, "
                    f"{pc(LLM['accuracy'])} of the answers are correct, at a median of "
                    f"{LLM['latency_ms']['median'] / 1000:.1f} seconds per answer.")
set_text(P[27], (
    "Students regularly need answers to questions about attendance, examinations, fees, syllabus and "
    "university policies, and the answers are spread over many long documents. This project builds a "
    "retrieval-augmented generation (RAG) chatbot that answers such questions from a university "
    "knowledge corpus and shows the passage each answer came from. Documents are split into passages "
    "at their section headings. For each question, a BM25 keyword ranking and a sentence-embedding "
    "ranking are merged with reciprocal rank fusion, a confidence score decides whether the documents "
    "cover the question, and an answer is then written only from the retrieved passages, with "
    f"citations. The system was evaluated on a sample corpus of {n_docs} documents ({n_pass} passages) "
    f"in five categories and a labelled set of {n_q} student questions, {n_oos} of which are out of "
    f"scope. Hybrid retrieval places the correct passage in the top three results for "
    f"{pc(H['hybrid']['hit@3'])} of answerable questions (BM25 alone: {pc(H['bm25']['hit@3'])}). "
    f"With answers quoted directly from the documents, {pc(EX['accuracy'])} of all answers are correct "
    f"and {pc(EX['unanswerable_declined'])} of out-of-scope questions are declined, at a median "
    f"response time of {EX['latency_ms']['median']} ms.{llm_abstract} Informal and Hindi-English "
    "questions remain the weakest case. The work shows that a grounded, source-citing assistant can "
    "be built from small open components that run on an ordinary laptop."))
set_text(P[28], "Keywords: retrieval-augmented generation, question answering, BM25, sentence embeddings, "
                "reciprocal rank fusion, chatbot, abstention")

# The two contents lists are fields; finalize.ps1 (or F9 in Word) fills them in.
def toc_field(par: Paragraph, instruction: str, placeholder: str) -> None:
    for child in list(par._p):
        if child.tag != qn("w:pPr"):
            par._p.remove(child)
    par.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for kind, text in (("begin", None), (None, instruction), ("separate", None), ("text", placeholder), ("end", None)):
        run = par.add_run()
        if kind in ("begin", "separate", "end"):
            char = OxmlElement("w:fldChar")
            char.set(qn("w:fldCharType"), kind)
            if kind == "begin":
                char.set(qn("w:dirty"), "true")
            run._r.append(char)
        elif kind == "text":
            run.text = text
        else:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = text
            run._r.append(instr)


toc_field(P[31], ' TOC \\h \\z \\t "Figure Caption,1" ', "Press F9 to build the list of figures.")
toc_field(P[33], ' TOC \\h \\z \\t "Table Caption,1" ', "Press F9 to build the list of tables.")

# ---- 1. Introduction -------------------------------------------------------------------
fill(36, (
    "This report describes the design, implementation and evaluation of an AI Student Assistance "
    "Chatbot: a question-answering assistant that replies to students' academic and institutional "
    "questions using only the university's own documents, and shows the source of every answer. The "
    "project follows problem statement SIH1631 of Smart India Hackathon 2024, \"AI-Powered Student "
    "Assistance Chatbot\" [1]."))
c = fill(38, (
    "A university communicates its rules through many documents: syllabus files, academic "
    "regulations, examination and fee notices, frequently asked questions and policy documents. A "
    "student who wants to know one fact, such as the minimum attendance needed to sit an "
    "examination or the last date to pay a fee without a fine, has to know which document holds it, "
    "find the right section and read it correctly. In practice students ask seniors, class groups or "
    "the department office, and the answers they receive are not always correct or current."))
c.p("Early chatbots such as ELIZA [2] matched patterns in the user's text and replied from fixed "
    "scripts. Large language models, built on the transformer architecture [3], can now write fluent "
    "answers to almost any question, but they answer from what they absorbed during training. They "
    "know nothing about one particular university's attendance rule, and when they do not know they "
    "tend to produce a plausible but invented answer, a failure known as hallucination [4]. For "
    "institutional questions this is serious: a wrong date or amount can cost a student money or an "
    "examination attempt.")
c.p("Retrieval-augmented generation (RAG) [5] addresses this. The system first searches a document "
    "collection for passages relevant to the question, and the answer is then written from those "
    "passages rather than from the model's memory. The documents can be updated without retraining "
    "anything, and the retrieved passages can be shown to the user as evidence.")
c = fill(40, (
    "The motivation for this project is reliability. A student assistant is useful only if its "
    "answers can be trusted, and trust needs three things that a general chatbot does not provide. "
    "First, every answer must come from the university's documents. Second, the student must be able "
    "to check the answer against the source in a few seconds. Third, when the documents do not "
    "cover a question, the assistant must say so instead of guessing."))
c.p("A second motivation is practicality. Many RAG systems depend on paid cloud services and a "
    "graphics processor. A college department is more likely to adopt a tool that runs on an "
    "ordinary computer, can work without an internet connection, and can keep student questions on the "
    "premises. This project therefore uses small open components and treats a hosted language model "
    "as optional.")

# ---- 2. Review of literature ------------------------------------------------------------
fill(42, (
    "This chapter reviews the methods on which the project is built: keyword and dense retrieval, "
    "the fusion of ranked lists, retrieval-augmented generation, the handling of unanswerable "
    "questions, and the evaluation of such systems."))
c = Cursor(P[43])
P[44]._p.getparent().remove(P[44]._p)
c.p("Classical retrieval ranks documents by the words they share with the query. BM25, "
    "which grew out of the probabilistic relevance framework [6], weights each shared word by how "
    "rare it is in the collection and how often it occurs in the document, with a correction for "
    "document length. It needs no training, is fast, and remains a strong baseline, particularly "
    "for exact terms such as course codes and names [7]. Its weakness is vocabulary mismatch: a "
    "question that says \"bunk limit\" does not match a regulation that says \"minimum attendance "
    "requirement\".", "Keyword retrieval. ")
c.p("Dense retrievers encode the query and each passage as vectors and rank passages by "
    "vector similarity. Sentence-BERT [8] showed how to train transformer encoders that give "
    "meaningful sentence vectors, and Dense Passage Retrieval [9] showed that such encoders can "
    "outperform BM25 for open-domain question answering. General-purpose embedding models such as "
    "the BGE family [10] are now available in small sizes that run on a CPU. Dense retrieval handles "
    "paraphrase well but can miss exact identifiers and rare terms.", "Dense retrieval. ")
c.p("Because the two approaches fail on different questions, combining them is "
    "common. Reciprocal rank fusion (RRF) [11] merges ranked lists using only the rank positions, "
    "giving each passage a score equal to the sum of 1/(k + rank) over the lists. It needs no score "
    "normalisation and no training, and it often outperforms each individual ranker.", "Hybrid retrieval. ")
c.p("Lewis et al. [5] introduced RAG as the combination of a "
    "retriever with a sequence-to-sequence generator, so that generated text is conditioned on "
    "retrieved passages. With instruction-following language models the usual form today is to "
    "place the retrieved passages in the prompt and instruct the model to answer only from them; "
    "Gao et al. [12] survey the many variants.", "Retrieval-augmented generation. ")
c.p("SQuAD 2.0 [13] added questions that look answerable but are not, and "
    "showed that systems which always answer do poorly on them. A reliable assistant must detect "
    "these cases and abstain. In RAG systems this is done by thresholding a retrieval confidence "
    "score, by instructing the generator to refuse, or by both.", "Unanswerable questions. ")
c.p("Retrieval is evaluated with rank metrics such as Hit@k and mean reciprocal rank "
    "(MRR) against labelled relevant passages [7]. Generated answers are harder to score; "
    "frameworks such as RAGAS [14] estimate faithfulness and relevance with a second language "
    "model, while simpler evaluations check for labelled key facts in the answer.", "Evaluation. ")
c = fill(46, (
    "The published work leaves three gaps for the present problem. First, most results are reported "
    "on large public benchmarks of encyclopaedic questions; there is no standard labelled set of "
    "student questions over university documents, and little evidence on the informal and "
    "mixed-language way in which students actually write. Second, many student-chatbot "
    "implementations are demonstrated without a quantitative evaluation, and in particular without "
    "measuring how often the system answers a question it should have declined. Third, most RAG "
    "systems assume a hosted language model, so their behaviour when no such model is available is "
    "not reported."))
c.p("This project addresses these gaps on a small scale. It builds a labelled evaluation set with "
    "several styles of wording and a set of out-of-scope questions, reports retrieval, abstention and "
    "answer quality separately, and includes a generator that uses no language model at all, so the "
    "system can be measured and used without one.")

# ---- 3. Rationale and scope -------------------------------------------------------------
fill(48, (
    "This chapter states why the topic was chosen, the problem to be solved, and the boundaries of "
    "the work."))
c = fill(50, (
    "The topic was chosen for three reasons. The problem is real and close at hand: every student "
    "has needed an answer from a regulation or a notice and has struggled to find it. The problem "
    "is a recognised one, set as problem statement SIH1631 in Smart India Hackathon 2024 [1]. And it "
    "exercises a complete, current technique: a RAG system involves text processing, information "
    "retrieval, neural embeddings, language-model prompting, a web application and, most "
    "importantly, measurement."))
c = fill(52, (
    "Students need reliable answers to academic and institutional queries. The task is to build a "
    "RAG chatbot over a university knowledge corpus consisting of syllabus documents, regulations, "
    "notices, FAQs and academic policies, and to evaluate it on a labelled set of student "
    "questions."))
c.p("In operational terms: given a student's question in natural language, the system must (a) find "
    "the passages of the corpus that answer it, (b) write a short answer using only those passages "
    "and cite them, and (c) decline when the corpus does not contain the answer.")
c = fill(54, "The scope of the work is as follows.")
c.bullets([
    "Corpus||: text documents in five categories (syllabus, regulations, notices, FAQs, academic "
    "policies) in Markdown, plain text, PDF or Word format. New documents can be added through the "
    "interface.",
    "Questions||: single questions and simple follow-up questions in English, including informal "
    "wording. Hindi-English mixed questions are included in the evaluation set to measure "
    "performance, but no special processing is done for them.",
    "Answers||: short factual answers with citations. The system does not give advice, opinions or "
    "answers that need information about an individual student.",
    "Interface||: a website with a home page, a conversation view, a document library and an evaluation "
    "page.",
])
c.p("The constraints are these.")
c.bullets([
    "The corpus used in this report is sample data written for the project for a fictional "
    "institution, \"Sutlej Valley University\". It is not the rulebook of any real university, and "
    "the reported numbers describe the system on this corpus only.",
    "The system must run on an ordinary laptop without a graphics processor, and must work "
    "without an internet connection after the first start.",
    "Scanned documents are not supported, because no optical character recognition is performed.",
    "There are no user accounts; the system does not access student records, results or the "
    "university portal.",
])

# ---- 4. Objectives and hypothesis -------------------------------------------------------
fill(56, "This chapter lists what the project set out to achieve and the outcomes that were predicted.")
c = fill(58, "The objectives of the study are:")
c.bullets([
    "To prepare a university knowledge corpus covering syllabus, regulations, notices, FAQs and "
    "academic policies, and a labelled set of student questions for evaluation.",
    "To implement a document pipeline that splits documents into topic-sized passages and indexes "
    "them for keyword and for meaning-based search.",
    "To implement hybrid retrieval and compare it with keyword-only and embedding-only retrieval.",
    "To implement answer generation that uses only the retrieved passages and cites them, with a "
    "version that needs no language model.",
    "To make the assistant decline questions that the corpus does not answer, and to measure how "
    "well it does so.",
    "To build a professional web interface in which a student can check each answer against its "
    "source.",
    "To evaluate retrieval, abstention and answer quality on the labelled question set.",
], numbered=True)
c = fill(60, "Three hypotheses were tested.")
c.bullets([
    "H1||. Hybrid retrieval, which fuses the BM25 and embedding rankings, finds the correct passage "
    "at least as often as either retriever alone, and the gain is largest for questions that do not "
    "reuse the document's wording.",
    "H2||. A confidence score computed from the retrieved passages can separate answerable from "
    "out-of-scope questions well enough to decline at least 80% of out-of-scope questions while "
    "still answering at least 80% of answerable ones.",
    "H3||. Answers quoted directly from the retrieved passages, with no language model, are correct "
    "for at least 70% of questions and are returned in under one second.",
])

# ---- 5. Methodology ----------------------------------------------------------------------
fill(62, (
    "The system is a retrieval-augmented generation pipeline with two phases. Ingestion runs once, "
    "and again whenever a document is added. Answering runs for every question. This chapter gives "
    "the system flowchart, the logical structure of the software and the algorithms used."))
c = fill(64, (
    "Figure 5.1 shows the flow of control. During ingestion, documents are split into passages and "
    "two indexes are built. For each question the system retrieves passages, computes a confidence "
    "score, and either declines or generates a cited answer. There are two points at which the "
    "assistant can decline: the confidence check, and the generator's own reply when a language "
    "model is used."))
c.figure("flowchart.png", "Figure 5.1: System flowchart of the ingestion and answering phases", 4.5)
c = fill(66, (
    "Figure 5.2 shows the logical structure. The browser interface talks to a FastAPI server over "
    "HTTP. The server passes each question to the RAG core, which uses the ingestion, retrieval and "
    "generation modules. Documents, the cached index and the evaluation files are stored as "
    "ordinary files, so no database is required. The language models are optional."))
c.figure("logical.png", "Figure 5.2: Logical diagram of the software components", 6.0)
c = fill(68, "The algorithms are described in the order in which a question passes through them.")
c.h3("5.3.1 Splitting documents into passages")
c.p("Each document is cut at its section headings, so that one passage deals with one topic, for "
    "example \"Condonation of shortage\". A section longer than 220 words is divided into windows "
    "of 160 words that overlap by 40 words, so that a sentence at a boundary is not lost. The "
    "document title and section heading are indexed together with the passage text, because a "
    "question often names the topic rather than repeating the sentence that answers it.")
c.h3("5.3.2 BM25 keyword ranking")
c.p("Text is lower-cased, common function words are removed and a light stemmer strips plural and "
    "verb endings. For a query q and passage d, BM25 [6] gives the score")
c.code("score(q, d) = SUM over terms t in q of\n"
       "    IDF(t) * f(t, d) * (k1 + 1) / ( f(t, d) + k1 * (1 - b + b * |d| / avgdl) )")
c.p("where f(t, d) is the number of times t occurs in d, |d| is the passage length, avgdl is the "
    "average passage length, and IDF(t) is larger for rarer terms. The usual values k1 = 1.5 and "
    "b = 0.75 are used. The implementation was written for this project with NumPy.")
c.h3("5.3.3 Dense ranking with sentence embeddings")
c.p("Each passage is encoded once as a 384-dimensional vector by the model BAAI/bge-small-en-v1.5 "
    "[10], run on the CPU through the FastEmbed library [15]; the vectors are cached on disk. A "
    "question is encoded in the same way, and passages are ranked by cosine similarity between the "
    "question vector and the passage vectors.")
c.h3("5.3.4 Reciprocal rank fusion")
c.p("The top 20 passages from each ranking are merged by reciprocal rank fusion [11]:")
c.code("RRF(d) = 1 / (k + rank_BM25(d)) + 1 / (k + rank_dense(d)),   k = 60")
c.p("A passage missing from a list contributes nothing for that list. The four passages with the "
    "highest fused score are passed on. Only rank positions are used, so the BM25 scores and cosine "
    "similarities, which are on different scales, never have to be compared.")
c.h3("5.3.5 Rewriting Hindi-English questions")
c.p("Students often type Hindi in Latin letters, for example \"fees ki last date kab hai\". The "
    "documents are in English, so neither the keyword index nor the English embedding model can "
    "match \"kab\" to \"when\". Before searching, a question that contains Hindi function words "
    "is rewritten with a word list: common question words, time words and campus vocabulary are "
    "replaced by English words, and grammatical particles are dropped. For example, \"medical "
    "certificate kitne din me submit karna hai\" becomes \"medical certificate how many days "
    "submit\". It is a word list and not a translator; words it does not know are kept as typed. "
    "The rewritten text is used only for searching. A language model that writes the answer still "
    "receives the student's own words.")
c.h3("5.3.6 Reranking with a cross-encoder")
c.p("BM25 and the embedding model each look at the question and the passage separately. A "
    "cross-encoder [18] reads the two together, which is slower but more precise. The model "
    "ms-marco-MiniLM-L-6-v2 scores the ten best fused passages against the question, and they are "
    "reordered by that score. It is evaluated as a fourth retriever. Whether the assistant should "
    "use it when answering was decided by measurement, reported in Chapter 8.")
c.h3("5.3.7 Confidence score and the decision to answer")
c.p("A confidence value between 0 and 1 is computed from the retrieved passages:")
c.code("coverage   = IDF-weighted share of the question's content words found in the passages\n"
       "similarity = clip( (best cosine similarity - 0.45) / 0.40, 0, 1 )\n"
       "confidence = 0.5 * coverage + 0.5 * similarity")
c.p(f"If the confidence is below a threshold, the assistant declines. The threshold was chosen on "
    f"the development half of the question set as the value that maximises balanced accuracy (the "
    f"mean of the rate of answering answerable questions and the rate of declining out-of-scope "
    f"ones), giving {TH}. When a language model writes the answer, a looser threshold of {LOOSE} is "
    f"used and the model is instructed to reply NO_ANSWER when the passages do not contain the "
    f"answer, which acts as a second check.")
c.h3("5.3.8 Answer generation")
c.p("Three interchangeable generators are provided.")
c.bullets([
    "Quote the documents||. No language model is used. The four passages are split into sentences, "
    "list items and table rows. Each unit is scored as 0.25 times its IDF-weighted word overlap "
    "with the question plus 0.75 times its embedding similarity to the question. The best unit, and "
    "up to two more that score at least 72% of the best, are quoted with citations. These three "
    "values were chosen on the development half of the question set. For FAQ "
    "documents the score of a question line is passed on to the answer that follows it. This "
    "generator cannot state anything that is not in the documents.",
    "Gemini||. The question and the four numbered passages are sent to the Gemini API [16] (model "
    "gemini-3.8-flash). The instructions tell the model to use only the passages, to cite each "
    "claim as [1], [2], to copy numbers, dates and amounts exactly, and to reply NO_ANSWER if the "
    "passages do not answer the question. The reply is streamed to the browser as it is written.",
    "Claude||. The same prompt is sent to the Claude API.",
])
c.h3("5.3.9 Follow-up questions and evidence highlighting")
c.p("A question with two or fewer content words, or one that uses a pronoun such as \"it\" or "
    "\"that\", is treated as a follow-up, and the previous question is added to it before "
    "retrieval. After an answer is produced, the sentence in each cited passage that best matches "
    "the answer is marked, and the interface shows it highlighted.")
c.h3("5.3.10 Evaluation method")
c.p("Retrieval is scored with Hit@k (the share of questions whose labelled passage is among the top "
    "k results) for k = 1, 3, 5 and with mean reciprocal rank. Abstention is scored on the "
    "development and test halves of the question set, which were split alternately within each "
    "question type. An answer to an answerable question is counted correct if the assistant "
    "answered and the answer contains every labelled key fact; an out-of-scope question is counted "
    "correct if the assistant declined.")

# ---- 6. Expected outcomes ----------------------------------------------------------------
c = fill(70, "The study was expected to produce the following.")
c.bullets([
    "A working web application in which a student types a question and receives a short answer "
    "with numbered citations, alongside the cited passages with the supporting sentence highlighted.",
    "A clear refusal, with the nearest passages shown, when the documents do not cover the question.",
    "A document library in which the corpus can be read and new documents can be added without "
    "any programming.",
    "An evaluation page and a results file reporting retrieval accuracy for each retriever, "
    "the behaviour of the confidence threshold, and answer accuracy by question style and category.",
    "Evidence for or against the three hypotheses of Chapter 4, in particular that hybrid "
    "retrieval is at least as good as either single retriever.",
    "Source code with automated tests, so that the results can be reproduced.",
])

# ---- 7. Experimental work ----------------------------------------------------------------
fill(72, (
    "This chapter describes the dataset that was prepared, the implementation, and the experiments "
    "that were run."))
set_text(P[74], (
    f"Two datasets were prepared: a knowledge corpus and a labelled question set. The corpus has "
    f"{n_docs} documents in the five categories named in the problem statement, {n_pass} passages "
    f"in all after splitting. It was written for this project for a fictional institution, Sutlej "
    f"Valley University, so that the work does not depend on, or misstate, the rules of any real "
    f"university. The documents imitate the structure of real ones: numbered sections, tables of "
    f"marks and dates, and cross-references between a notice and the regulation it applies. "
    f"Table 7.1 lists them."))
c = Cursor(P[74])
import sys
sys.path.insert(0, str(ROOT))
from app.pipeline import get_engine  # noqa: E402

engine = get_engine()
LABEL = {"syllabus": "Syllabus", "regulations": "Regulations", "notices": "Notices", "faqs": "FAQs", "policies": "Academic policies"}
order = {"syllabus": 0, "regulations": 1, "notices": 2, "faqs": 3, "policies": 4}
docs = sorted(engine.documents, key=lambda d: (order[d.category], d.doc_id))
c.table("Table 7.1: Documents in the knowledge corpus",
        ["ID", "Category", "Title", "Sections", "Words"],
        [[d.doc_id, LABEL[d.category], d.title, str(len(d.sections)),
          str(sum(len(body.split()) for _, body in d.sections))] for d in docs],
        widths=[0.7, 1.2, 3.3, 0.7, 0.6])
c.p(f"The question set has {n_q} questions. {n_ans} are answerable from the corpus and {n_oos} are "
    f"out of scope. Each answerable question is labelled with the document and section that contain "
    f"the answer, a reference answer, and the key facts (dates, amounts, percentages) that a correct "
    f"answer must contain. To test robustness to wording, the answerable questions come in "
    f"{len(STYLES)} styles (Table 7.2). The out-of-scope questions are mostly near misses: they ask "
    f"about a topic the corpus covers, but for a fact it does not state, such as the hostel fee for "
    f"a room type that is not listed. These are the hardest to decline.")
c.p("The set was built in two rounds. The first 80 questions were written together with the "
    "corpus. A further 50 were added later, because two groups were too small to measure reliably: "
    "out-of-scope questions (12 at first) and Hindi-English questions (4 at first). The added "
    "questions were written from the documents alone, without running the system on them, and the "
    "choices described below had not seen them.")
DESCRIBE = {"direct": "Uses the document's own words", "paraphrase": "Same meaning, different words",
            "colloquial": "Informal English, as students type", "hinglish": "Hindi and English mixed, in Latin letters"}
examples = {}
for style in STYLES:
    found = [q for q in QUESTIONS if q["style"] == style and q["type"] == "answerable"]
    examples[style] = found[min(2, len(found) - 1)]["question"]
oos_example = [q["question"] for q in QUESTIONS if q["type"] == "unanswerable"][-20]
c.table("Table 7.2: Composition of the labelled question set",
        ["Type", "Questions", "Description", "Example"],
        [[STYLE_NAME[s], str(by_style_n[s]), DESCRIBE[s], examples[s]] for s in STYLES] +
        [["Out of scope", str(n_oos), "Not answered by the corpus", oos_example]],
        widths=[1.1, 0.8, 1.9, 2.7])
c.p("The questions were divided into a development half and a test half, alternating within each "
    "type so that both halves have the same mix. Thresholds were chosen on the development half "
    "only.")

set_text(P[76], (
    "The system was implemented in Python 3 with the FastAPI web framework [17]. The interface is "
    "written in plain HTML, CSS and JavaScript and needs no build step. The work was carried out in "
    "the following steps."))
c = Cursor(P[76])
c.bullets([
    "Ingestion (app/ingest.py)||. Readers for Markdown, text, PDF and Word files; splitting at "
    "headings; windowing of long sections.",
    "Retrieval (app/retrieval.py)||. The BM25 index, the embedding encoder with a disk cache, rank "
    "fusion and the confidence score. If the embedding model cannot be loaded, the system falls "
    "back to BM25 alone and reports this.",
    "Generation (app/generate.py)||. The quote-only generator, the prompt and streaming clients for "
    "the Gemini and Claude APIs, and the highlighting of supporting sentences.",
    "Pipeline (app/pipeline.py)||. The Engine class, which joins the steps, handles follow-up "
    "questions, applies the thresholds, and falls back to the quote-only generator if a language "
    "model fails.",
    "Server (app/main.py)||. Endpoints for chat, documents, evaluation and feedback. Answers are "
    "streamed to the browser as newline-delimited JSON events so that text appears as it is "
    "written. Uploads are checked for type, size and file name.",
    "Interface (web/)||. A website with four pages: a home page, Ask, Library and Evaluation. The "
    "home page explains the assistant and shows a live example answer taken from the running "
    "system. The design is black and white throughout, like a printed rulebook: the five document "
    "types are told apart by shape instead of colour, and the supporting sentence is shown in "
    "reverse, white on black. Short animations show what the system is doing, for example the "
    "example answer is typed out and the scores count up when reached, and they are switched off "
    "for users who ask their device for reduced motion. The site adapts to phone-sized screens.",
    "Evaluation (app/evaluate.py)||. Computes all metrics in this report and writes them to "
    "data/eval/results.json, which the Evaluation page displays.",
    "Testing (tests/)||. Eighteen automated tests cover the tokenizer, retrieval, grounded "
    "answering, declining, follow-up questions, the chat stream, document upload (including "
    "rejection of unsafe file names) and the Gemini generator against a simulated API.",
], numbered=True)
c.p("Listing 7.1 shows the fusion step, and Listing 7.2 the confidence score, as implemented.")
c.code('''# Listing 7.1  Reciprocal rank fusion (app/retrieval.py, simplified)
fused = defaultdict(float)
for scores in (bm25_scores, dense_scores):
    order = np.argsort(-scores)[:CANDIDATES]      # top 20 of each
    for rank, idx in enumerate(order, start=1):
        fused[idx] += 1.0 / (RRF_K + rank)         # RRF_K = 60
top = sorted(fused, key=fused.get, reverse=True)[:TOP_K]  # 4''')
c.code('''# Listing 7.2  Confidence score (app/retrieval.py, simplified)
terms = set(tokenize(query))
found = {t for t in terms if any(t in passage_terms[h] for h in hits)}
coverage = sum(idf[t] for t in found) / sum(idf[t] for t in terms)
best = max(cosine(query_vec, passage_vec[h]) for h in hits)
similarity = np.clip((best - 0.45) / 0.40, 0.0, 1.0)
confidence = 0.5 * coverage + 0.5 * similarity
abstain = confidence < threshold''')
c.p("Four experiments were run with the command \"python -m app.evaluate --design-choices\".")
c.bullets([
    f"Experiment 1, retrieval||. Each of the {len(METHODS)} retrievers ranked the passages for the "
    f"{n_ans} answerable questions, and Hit@1, Hit@3, Hit@5 and MRR were computed against the "
    "labelled passages.",
    "Experiment 2, abstention||. The confidence score was computed for all questions, the threshold "
    "was chosen on the development half, and the answer and decline rates were measured on the test "
    "half.",
    "Experiment 3, answers||. The complete pipeline answered all questions with the quote-only "
    "generator" + (" and with Gemini" if LLM else "") + ", and each answer was "
    "scored against the labelled key facts.",
    "Experiment 4, design choices||. Two choices were measured so that they rest on numbers: "
    "hybrid retrieval with and without the Hindi-English rewriting, and quote-only answers built "
    "from reranked passages against answers built from plain hybrid passages.",
])
c.p("Two further questions were explored with separate scripts, kept in the experiments folder: "
    "how sentences should be selected for quote-only answers, and whether a better signal for "
    "declining could be found. In each case the choice was made on the development half and then "
    "checked on the test half.")
c.p("The experiments were run on a Windows 11 laptop using the CPU only.")

# ---- 8. Results --------------------------------------------------------------------------
fill(78, (
    "This chapter shows the working application, reports the measurements from the three "
    "experiments, and discusses them against the hypotheses."))
set_text(P[80], (
    "Figures 8.1 to 8.6 show the application. As this is a text system, the outputs are screens of "
    "the interface rather than processed images; the \"before\" is the student's question and the "
    "\"after\" is the cited answer."))
c = Cursor(P[80])
c.figure("ui-home.png", "Figure 8.1: Home page of the website, with an example answer produced live by the assistant", 6.0)
c.figure("ui-answer.png", "Figure 8.2: A cited answer (centre) and the source passages with the supporting sentence highlighted (right)", 6.0)
c.figure("ui-declined.png", "Figure 8.3: An out-of-scope question is declined, and the nearest passages are offered", 6.0)
c.figure("ui-library.png", "Figure 8.4: Library view, where documents are read, uploaded and removed", 6.0)
c.figure("ui-evaluation.png", "Figure 8.5: Evaluation view showing the results of the labelled question set", 6.0)
c.figure("ui-mobile.png", "Figure 8.6: The conversation view on a phone-sized screen", 2.3)

set_text(P[82], (
    f"Retrieval. Table 8.1 and Figure 8.7 give the retrieval results on the {n_ans} answerable "
    f"questions."))
c = Cursor(P[82])
best_m = max(H, key=lambda m: H[m]["mrr"])
c.table("Table 8.1: Retrieval performance (labelled passage within the top k results)",
        ["Retriever", "Hit@1", "Hit@3", "Hit@5", "MRR", "Time per query"],
        [[RETR_NAME[m], pc(H[m]["hit@1"]), pc(H[m]["hit@3"]), pc(H[m]["hit@5"]), f3(H[m]["mrr"]),
          ms(RET[m]["ms_per_query"])] for m in METHODS],
        widths=[1.9, 0.8, 0.8, 0.8, 0.8, 1.2], bold_rows=(METHODS.index(best_m),))
c.figure("chart-retrieval.png", f"Figure 8.7: Retrieval performance of the {len(METHODS)} retrievers", 5.6)
c.p("Table 8.2 and Figure 8.8 break the Hit@3 result down by the wording of the question.")
col_w = [1.6, 1.0] + [0.95] * len(METHODS)
c.table("Table 8.2: Hit@3 by question wording",
        ["Wording", "Questions"] + [SHORT[m] for m in METHODS],
        [[STYLE_NAME[s], str(RET["bm25"]["by_style"][s]["n"])] +
         [pc(RET[m]["by_style"][s]["hit@3"]) for m in METHODS] for s in STYLES],
        widths=col_w)
c.figure("chart-style.png", "Figure 8.8: Hit@3 by question wording", 5.6)
cats = ("syllabus", "regulations", "notices", "faqs", "policies")
c.table("Table 8.3: Hit@3 by document category",
        ["Category", "Questions"] + [SHORT[m] for m in METHODS],
        [[LABEL[k], str(RET["bm25"]["by_category"][k]["n"])] +
         [pc(RET[m]["by_category"][k]["hit@3"]) for m in METHODS] for k in cats],
        widths=col_w)
c.p(f"Table 8.4 gives the behaviour of the confidence threshold of {TH}, and Figure 8.9 shows "
    f"how the two rates change as the threshold moves.", "Abstention. ")
c.table("Table 8.4: Answering and declining at the chosen confidence threshold",
        ["Split", "Answerable / out of scope", "Answered when answerable", "Declined when out of scope", "Balanced accuracy"],
        [["Development", f"{DEV['n_answerable']} / {DEV['n_unanswerable']}", pc(DEV["answered_when_answerable"]),
          pc(DEV["declined_when_unanswerable"]), pc(DEV["balanced_accuracy"])],
         ["Test", f"{TEST['n_answerable']} / {TEST['n_unanswerable']}", pc(TEST["answered_when_answerable"]),
          pc(TEST["declined_when_unanswerable"]), pc(TEST["balanced_accuracy"])]],
        widths=[1.1, 1.3, 1.4, 1.4, 1.1])
c.figure("chart-threshold.png", "Figure 8.9: Effect of the confidence threshold on answering and declining", 5.6)

gens = [("Quote the documents", EX)] + ([("Gemini", LLM)] if LLM else [])


def latency(s: dict) -> str:
    value = s["latency_ms"]["median"]
    return f"{value} ms" if value < 2000 else f"{value / 1000:.1f} s"


metric_rows = [
    ["Correct, all questions"] + [pc(s["accuracy"]) for _, s in gens],
    ["Correct, test half only"] + [pc(s["accuracy_test_split"]) for _, s in gens],
    ["Answerable questions answered correctly"] + [pc(s["answerable_correct"]) for _, s in gens],
    ["Answerable questions wrongly declined"] + [pc(s["answerable_declined"]) for _, s in gens],
    ["Key facts present in the answers given"] + [pc(s["fact_coverage"]) for _, s in gens],
    ["Answers citing the labelled document"] + [pc(s["cited_gold_document"]) for _, s in gens],
    ["Out-of-scope questions declined"] + [pc(s["unanswerable_declined"]) for _, s in gens],
] + [[f"Correct: {STYLE_NAME[st].lower()} wording"] + [pc(s["by_style"][st]) for _, s in gens] for st in STYLES] + [
    ["Median response time"] + [latency(s) for _, s in gens],
]
c.p(f"Table 8.5 gives the quality of the final answers on all {n_q} questions.", "Answers. ")
c.table("Table 8.5: Answer quality of the complete pipeline",
        ["Metric"] + [name for name, _ in gens], metric_rows,
        widths=[3.0] + [1.7] * len(gens))
c.table("Table 8.6: Correct answers by document category",
        ["Category"] + [name for name, _ in gens],
        [[LABEL[k]] + [pc(s["by_category"][k]) for _, s in gens] for k in cats],
        widths=[3.0] + [1.7] * len(gens))

if DESIGN:
    rw, rr = DESIGN["rewriting"], DESIGN["reranking"]
    c.p("Table 8.7 gives the two design choices that were measured.", "Design choices. ")
    rows = [["Hybrid retrieval, Hindi-English questions: Hit@1 / Hit@3",
             f"{pc(rw['without_rewrite']['hinglish']['hit@1'])} / {pc(rw['without_rewrite']['hinglish']['hit@3'])}",
             f"{pc(rw['with_rewrite']['hinglish']['hit@1'])} / {pc(rw['with_rewrite']['hinglish']['hit@3'])}"],
            ["Hybrid retrieval, all questions: Hit@1 / Hit@3",
             f"{pc(rw['without_rewrite']['all']['hit@1'])} / {pc(rw['without_rewrite']['all']['hit@3'])}",
             f"{pc(rw['with_rewrite']['all']['hit@1'])} / {pc(rw['with_rewrite']['all']['hit@3'])}"]]
    c.table("Table 8.7: Effect of rewriting Hindi-English questions before searching",
            ["Measure", "Without rewriting", "With rewriting"], rows, widths=[3.4, 1.5, 1.5])
    if "rerank" in rr:
        c.table("Table 8.8: Quote-only answers built from hybrid passages and from reranked passages",
                ["Measure", "Hybrid", "Hybrid + reranker"],
                [["Answers containing every key fact, development half", pc(rr["hybrid"]["facts_complete_dev"]), pc(rr["rerank"]["facts_complete_dev"])],
                 ["Answers containing every key fact, test half", pc(rr["hybrid"]["facts_complete_test"]), pc(rr["rerank"]["facts_complete_test"])],
                 ["Time per question (search and sentence selection)", ms(rr["hybrid"]["ms_per_question"]), ms(rr["rerank"]["ms_per_question"])]],
                widths=[3.4, 1.5, 1.5])

# 8.3 discussion: every figure below is read from the results
single = lambda k: max(H["bm25"][k], H["dense"][k])
h1_everywhere = all(H["hybrid"][k] >= single(k) for k in ("hit@1", "hit@3", "hit@5", "mrr"))
gain = {s: RET["hybrid"]["by_style"][s]["hit@3"] - max(RET["bm25"]["by_style"][s]["hit@3"], RET["dense"]["by_style"][s]["hit@3"]) for s in STYLES}
gain_text = join_names([f"{gain[s] * 100:+.1f} points for {STYLE_NAME[s].lower()} questions" for s in STYLES])
c = fill(84, (
    f"Hypothesis H1 (hybrid retrieval). Of the three first-stage retrievers, hybrid fusion has an "
    f"MRR of {f3(H['hybrid']['mrr'])}, against {f3(H['dense']['mrr'])} for dense and "
    f"{f3(H['bm25']['mrr'])} for BM25, and places the labelled passage in the top three for "
    f"{pc(H['hybrid']['hit@3'])} of questions (dense {pc(H['dense']['hit@3'])}, BM25 "
    f"{pc(H['bm25']['hit@3'])}). " +
    ("It is at least as good as either single retriever at every cut-off, so the first part of H1 is supported. "
     if h1_everywhere else
     "It is not the best at every cut-off, so the first part of H1 is only partly supported. ") +
    f"The second part of H1 said that the gain would be largest for questions that do not reuse the "
    f"document's wording. The gain of hybrid over the better single retriever at Hit@3 is {gain_text}. " +
    ("The gain is largest away from direct wording, as predicted, but it is not uniform: "
     if max(gain, key=gain.get) != "direct" else "The prediction is not borne out: ") +
    f"with between {min(by_style_n.values())} and {max(by_style_n.values())} questions in a group, one "
    f"question moves a figure by three to five points, so small differences should not be over-read."))
if DESIGN:
    rw, rr = DESIGN["rewriting"], DESIGN["reranking"]
    c.p(f"Hindi-English questions. Rewriting these questions into rough English before searching "
        f"raises hybrid Hit@1 on them from {pc(rw['without_rewrite']['hinglish']['hit@1'])} to "
        f"{pc(rw['with_rewrite']['hinglish']['hit@1'])} and Hit@3 from "
        f"{pc(rw['without_rewrite']['hinglish']['hit@3'])} to {pc(rw['with_rewrite']['hinglish']['hit@3'])} "
        f"(Table 8.7). English questions are not touched by the rewriting. Finding the passage is "
        f"therefore no longer the main difficulty for this group. The final answers are still the "
        f"weakest ({pc(EX['by_style'].get('hinglish', 0))} correct), because the confidence check "
        f"declines many of them: a rewritten question is a string of keywords, which the embedding "
        f"model finds less similar to a passage than a fluent sentence, and Hindi words missing from "
        f"the word list count as question words that the passages do not contain.")
    if "rerank" in rr and HAS_RR:
        c.p(f"Reranking. The cross-encoder improves the ranking: Hit@1 rises from "
            f"{pc(H['hybrid']['hit@1'])} to {pc(H['rerank']['hit@1'])} and MRR from "
            f"{f3(H['hybrid']['mrr'])} to {f3(H['rerank']['mrr'])}. It does not improve the answers. "
            f"The share of quote-only answers containing every key fact is "
            f"{pc(rr['hybrid']['facts_complete_dev'])} with hybrid passages and "
            f"{pc(rr['rerank']['facts_complete_dev'])} with reranked passages on the development "
            f"half ({pc(rr['hybrid']['facts_complete_test'])} and {pc(rr['rerank']['facts_complete_test'])} "
            f"on the test half), while the time per question rises from {ms(rr['hybrid']['ms_per_question'])} "
            f"to {ms(rr['rerank']['ms_per_question'])} (Table 8.8). The reason is that the generator "
            f"reads four passages, and hybrid fusion already has the labelled passage among its first "
            f"five for {pc(H['hybrid']['hit@5'])} of questions; putting it first instead of second "
            f"changes little. The reranker is therefore kept as an option and is switched off by "
            f"default.")
h2_dev = DEV["answered_when_answerable"] >= 0.8 and DEV["declined_when_unanswerable"] >= 0.8
h2_test = TEST["answered_when_answerable"] >= 0.8 and TEST["declined_when_unanswerable"] >= 0.8
passed = [r["question"] for r in ANS["extractive"]["rows"] if r["type"] == "unanswerable" and not r["abstained"]]
c.p(f"Hypothesis H2 (declining). The target was to answer at least 80% of answerable questions "
    f"while declining at least 80% of out-of-scope ones. On the development half the assistant "
    f"answers {pc(DEV['answered_when_answerable'])} and declines {pc(DEV['declined_when_unanswerable'])}; "
    f"on the held-out test half it answers {pc(TEST['answered_when_answerable'])} and declines "
    f"{pc(TEST['declined_when_unanswerable'])}. H2 is " +
    ("supported." if h2_dev and h2_test else "not supported.") +
    f" Figure 8.9 shows why: the two curves cross, so a threshold that declines more out-of-scope "
    f"questions also refuses more answerable ones. The questions that get through are near misses, "
    f"for example \"{passed[0]}\" and \"{passed[len(passed) // 2]}\". Each retrieves passages on the "
    f"right topic that share most of its words; a retrieval score cannot tell that the passage "
    f"does not state the particular fact asked for.")
c.p("Three other signals for declining were tried: the reranker's relevance score, a second "
    "cross-encoder trained to judge whether a sentence answers a question (QNLI), and a logistic "
    "regression fitted on seven retrieval signals. None carried over from the development half to "
    "the test half. Balanced accuracy on the test half stayed between 0.47 and 0.66 for every "
    "variant, and the fitted model fell from 0.91 on the development half to 0.61 on the test "
    "half, which is over-fitting. The answer-checking model also took about 1.7 seconds per "
    "question. The conclusion is that telling a near miss from an answerable question requires "
    "reading the passage for the specific fact, which is the job of the language model's own "
    "refusal in the second stage. Without a language model the assistant reliably declines only "
    "questions that are clearly unrelated to the documents.")
h3 = EX["accuracy"] >= 0.70 and EX["latency_ms"]["median"] < 1000
c.p(f"Hypothesis H3 (quote-only answers). The target was at least 70% of answers correct, returned "
    f"in under one second. The quote-only generator answers {pc(EX['accuracy'])} of all questions "
    f"correctly ({pc(EX['accuracy_test_split'])} on the test half), with a median response time of "
    f"{EX['latency_ms']['median']} ms and a 95th percentile of {EX['latency_ms']['p95']} ms. H3 is " +
    ("supported. " if h3 else
     ("not supported: the speed target is met, the accuracy target is not. " if EX["latency_ms"]["median"] < 1000
      else "not supported. ")) +
    f"When it does answer, the answer contains {pc(EX['fact_coverage'])} of the labelled key facts "
    f"and cites the labelled document {pc(EX['cited_gold_document'])} of the time. Its errors are "
    f"of two kinds. {pc(EX['answerable_declined'])} of answerable questions are declined by the "
    f"confidence check, and {pc(1 - EX['unanswerable_declined'])} of out-of-scope questions are "
    f"answered with the nearest passage. Accuracy follows the wording of the question: " +
    join_names([f"{pc(EX['by_style'][s])} for {STYLE_NAME[s].lower()} questions" for s in STYLES]) + ".")
c.p("A weakness seen when reading the quote-only answers is that they sometimes include a "
    "neighbouring sentence that is true but not needed, because sentences are selected one at a "
    "time and cannot be rewritten. The answer is still supported by the source, but it reads less "
    "directly than an answer written by a language model.")
DISCUSSION_CURSOR = c

# ---- 9. Conclusions ----------------------------------------------------------------------
fill(86, "This chapter summarises what was achieved, what the work contributes, and where it falls short.")
c = fill(88, (
    f"The project set out to build a RAG chatbot that gives students reliable answers from a "
    f"university knowledge corpus, and this was achieved. The delivered system ingests documents in "
    f"four file formats, retrieves passages with a fusion of keyword and embedding rankings, "
    f"declines when the evidence is weak, writes answers only from the retrieved passages, and "
    f"shows each cited passage with the supporting sentence highlighted. All seven objectives of "
    f"Chapter 4 were met."))
c.p(f"On the labelled set of {n_q} questions, hybrid retrieval placed the correct passage in the "
    f"top three results for {pc(H['hybrid']['hit@3'])} of answerable questions and in the top five "
    f"for {pc(H['hybrid']['hit@5'])}. With no language model at all, {pc(EX['accuracy'])} of answers "
    f"were correct and were returned in about {EX['latency_ms']['median']} ms on a laptop CPU. "
    f"The confidence check declined {pc(EX['unanswerable_declined'])} of out-of-scope questions "
    f"({pc(TEST['declined_when_unanswerable'])} on the held-out half), well short of the 80% that "
    f"was hoped for. The honest reading of the results is that the retrieval half of the system "
    f"works well, and that reliably refusing near-miss questions needs the language-model stage, "
    f"which was built but could not be scored.")
c.p("The contribution of the work is a complete, measured and reproducible example of a grounded "
    "student assistant built from small open components: a labelled evaluation set with four "
    "question styles and out-of-scope questions, separate measurements of retrieval, abstention and "
    "answer quality, and a generator that works without any language model.")
CONCLUSION_CURSOR = c
c = fill(90, "The work has the following limitations.")
c.bullets([
    "Sample data||. The corpus is fictional and small. Results on a real university's documents, "
    "which are longer, less consistent and partly scanned, will differ.",
    "Hindi-English questions||. Rewriting them with a word list fixed most of the retrieval "
    "failures, but they remain the hardest group for final answers. The word list covers common "
    "words only, and the confidence check declines many of these questions.",
    "The confidence check||. A retrieval score cannot tell a near-miss out-of-scope question from "
    "an answerable one, and the alternatives that were tried did not generalise (Section 8.3). "
    "Without a language model, only clearly unrelated questions are declined reliably.",
    f"Small groups||. Choices were made on a development half of {DEV['n_answerable'] + DEV['n_unanswerable']} "
    "questions. A difference of one or two questions is within noise, so the chosen settings are "
    "reasonable ones and not proven best ones.",
    "Answer scoring||. Checking for labelled key facts is strict and automatic, but it does not "
    "judge fluency, and it cannot detect an extra incorrect statement in an answer.",
    "Language models not scored||. The Gemini and Claude generators are implemented but were not "
    "run against the live services, so their answer quality is not measured here.",
    "Deployment||. There is no login, no rate limiting and no optical character recognition, and "
    "conversations are stored only in the user's browser.",
])
c.p("The following extensions are suggested.")
c.bullets([
    "Score the Gemini generator on the question set, in particular how many near-miss questions "
    "its own refusal catches, since that is the stage designed to stop them.",
    "Replace the embedding model with a multilingual one and extend the Hindi-English word list, "
    "so that confidence is not lower for these questions.",
    "Enlarge the evaluation set further using questions collected from real students.",
    "Run the system on the real documents of a university, with optical character recognition for "
    "scanned notices and scheduled re-ingestion when documents change.",
    "Add voice input and regional-language answers, and connect the assistant to the channels "
    "students already use.",
    "Use the \"helpful / not helpful\" feedback that the interface already records to find weak "
    "areas of the corpus.",
])

# ---- 10. References ----------------------------------------------------------------------
fill(92, "References are listed in the order in which they are first cited, in IEEE style.")
REFS = [
    "Ministry of Education, Government of India, \"Smart India Hackathon 2024, Problem Statement SIH1631: AI-Powered Student Assistance Chatbot,\" 2024. [Online]. Available: https://www.sih.gov.in",
    "J. Weizenbaum, \"ELIZA - a computer program for the study of natural language communication between man and machine,\" Communications of the ACM, vol. 9, no. 1, pp. 36-45, 1966.",
    "A. Vaswani et al., \"Attention is all you need,\" in Advances in Neural Information Processing Systems, vol. 30, 2017.",
    "Z. Ji et al., \"Survey of hallucination in natural language generation,\" ACM Computing Surveys, vol. 55, no. 12, pp. 1-38, 2023.",
    "P. Lewis et al., \"Retrieval-augmented generation for knowledge-intensive NLP tasks,\" in Advances in Neural Information Processing Systems, vol. 33, pp. 9459-9474, 2020.",
    "S. Robertson and H. Zaragoza, \"The probabilistic relevance framework: BM25 and beyond,\" Foundations and Trends in Information Retrieval, vol. 3, no. 4, pp. 333-389, 2009.",
    "C. D. Manning, P. Raghavan, and H. Schutze, Introduction to Information Retrieval. Cambridge, U.K.: Cambridge University Press, 2008.",
    "N. Reimers and I. Gurevych, \"Sentence-BERT: Sentence embeddings using Siamese BERT-networks,\" in Proc. Conf. Empirical Methods in Natural Language Processing (EMNLP-IJCNLP), 2019, pp. 3982-3992.",
    "V. Karpukhin et al., \"Dense passage retrieval for open-domain question answering,\" in Proc. Conf. Empirical Methods in Natural Language Processing (EMNLP), 2020, pp. 6769-6781.",
    "S. Xiao, Z. Liu, P. Zhang, and N. Muennighoff, \"C-Pack: Packaged resources to advance general Chinese embedding,\" arXiv:2309.07597, 2023.",
    "G. V. Cormack, C. L. A. Clarke, and S. Buettcher, \"Reciprocal rank fusion outperforms Condorcet and individual rank learning methods,\" in Proc. 32nd Int. ACM SIGIR Conf. Research and Development in Information Retrieval, 2009, pp. 758-759.",
    "Y. Gao et al., \"Retrieval-augmented generation for large language models: A survey,\" arXiv:2312.10997, 2023.",
    "P. Rajpurkar, R. Jia, and P. Liang, \"Know what you don't know: Unanswerable questions for SQuAD,\" in Proc. 56th Annual Meeting of the Association for Computational Linguistics (ACL), 2018, pp. 784-789.",
    "S. Es, J. James, L. Espinosa-Anke, and S. Schockaert, \"RAGAS: Automated evaluation of retrieval augmented generation,\" arXiv:2309.15217, 2023.",
    "Qdrant, \"FastEmbed: Fast, accurate, lightweight Python library to make state of the art embedding,\" software. [Online]. Available: https://github.com/qdrant/fastembed",
    "Google, \"Gemini API documentation,\" 2026. [Online]. Available: https://ai.google.dev/gemini-api/docs",
    "S. Ramirez, \"FastAPI,\" software. [Online]. Available: https://fastapi.tiangolo.com",
    "R. Nogueira and K. Cho, \"Passage re-ranking with BERT,\" arXiv:1901.04085, 2019.",
]
set_text(P[93], REFS[0])
at = P[93]._p
for ref in REFS[1:]:
    par = new_par(at, REF_PROTO, ref)
    at = par._p
P[94]._p.getparent().remove(P[94]._p)

# ---- Appendix ----------------------------------------------------------------------------
c = fill(96, "A. Running the application")
P[96].runs[0].bold = True
c.p("The source code is in the project folder. On Windows, double-click run.bat, or run the "
    "following commands and then open http://127.0.0.1:8000 in a browser.")
c.code("python -m venv .venv\n"
       ".venv\\Scripts\\python -m pip install -r requirements.txt\n"
       ".venv\\Scripts\\python -m uvicorn app.main:app --port 8000\n"
       "\n"
       ".venv\\Scripts\\python -m pytest -q                        (automated tests)\n"
       ".venv\\Scripts\\python -m app.evaluate                     (evaluation, quote-only answers)\n"
       ".venv\\Scripts\\python -m app.evaluate --generator gemini  (also score Gemini answers)")
c.h3("B. Project structure")
c.code("app/config.py      settings and paths\n"
       "app/ingest.py      read .md/.txt/.pdf/.docx, split into passages\n"
       "app/textutil.py    tokenizer, sentence and table-row splitting\n"
       "app/retrieval.py   BM25, dense embeddings, rank fusion, confidence\n"
       "app/generate.py    quote-only, Gemini and Claude answer generators\n"
       "app/pipeline.py    the RAG pipeline (retrieve, gate, generate, cite)\n"
       "app/evaluate.py    evaluation on the labelled question set\n"
       "app/main.py        FastAPI server and API\n"
       "web/               the interface (HTML, CSS, JavaScript)\n"
       "data/corpus/       the knowledge corpus, one folder per category\n"
       "data/eval/         questions.jsonl, results.json, threshold.json\n"
       "tests/             automated tests")
c.h3("C. Settings used in the experiments")
c.table("Table A.1: Parameter values",
        ["Parameter", "Value"],
        [["Maximum section length before windowing", "220 words"],
         ["Window length / overlap", "160 / 40 words"],
         ["BM25 k1, b", "1.5, 0.75"],
         ["Embedding model", "BAAI/bge-small-en-v1.5 (384 dimensions)"],
         ["Candidates per retriever for fusion", "20"],
         ["RRF constant k", "60"],
         ["Passages given to the generator", "4"],
         ["Reranker (measured, off by default)", "Xenova/ms-marco-MiniLM-L-6-v2, 10 candidates"],
         ["Sentence selection, quote-only answers", "0.25 word overlap + 0.75 similarity; keep 72% of best; at most 3"],
         ["Confidence threshold, quote-only answers", str(TH)],
         ["Confidence threshold, language-model answers", str(LOOSE)],
         ["Language model (optional)", "gemini-3.8-flash via the Gemini API"]],
        widths=[3.4, 2.8])
c.h3("D. One record of the labelled question set")
sample = next(q for q in QUESTIONS if q["type"] == "answerable")
c.code(json.dumps(sample, ensure_ascii=False, indent=2))
c.h3("E. Instructions given to the language model")
c.p("The following is a summary of the system prompt in app/generate.py. The model is told that it "
    "is the student help desk assistant of the university; that the numbered passages are the only "
    "source it may use, because a wrong answer about a deadline, a fee or an examination rule can "
    "cost a student marks or money; that it must answer directly in the first sentence in under "
    "120 words, cite each claim as [1], [2], and copy numbers, dates, amounts and names exactly; "
    "and that it must reply NO_ANSWER when the passages do not contain the answer.")

# ---- language-model discussion (figures only when a scored Gemini run exists) -----------------
if LLM:
    better = LLM["accuracy"] - EX["accuracy"]
    direction = "higher than" if better > 0.005 else ("lower than" if better < -0.005 else "the same as")
    DISCUSSION_CURSOR.p(
        f"Language-model answers. With Gemini writing the answers behind the looser threshold, "
        f"{pc(LLM['accuracy'])} of all answers are correct, which is {direction} the quote-only "
        f"generator ({pc(EX['accuracy'])}). It answers {pc(LLM['answerable_correct'])} of answerable "
        f"questions correctly (quote-only: {pc(EX['answerable_correct'])}) and declines "
        f"{pc(LLM['answerable_declined'])} of them (quote-only: {pc(EX['answerable_declined'])}). On "
        f"colloquial questions it reaches {pc(LLM['by_style']['colloquial'])}, against "
        f"{pc(EX['by_style']['colloquial'])} for quote-only. It declines "
        f"{pc(LLM['unanswerable_declined'])} of out-of-scope questions (quote-only: "
        f"{pc(EX['unanswerable_declined'])}). The median response time is "
        f"{LLM['latency_ms']['median'] / 1000:.1f} seconds, against {EX['latency_ms']['median']} ms.")
    CONCLUSION_CURSOR.p(
        f"With Gemini writing the answers, accuracy was {pc(LLM['accuracy'])} and "
        f"{pc(LLM['unanswerable_declined'])} of out-of-scope questions were declined, at a median of "
        f"{LLM['latency_ms']['median'] / 1000:.1f} seconds per answer.")
else:
    DISCUSSION_CURSOR.p(
        "Language-model answers. The Gemini and Claude generators are implemented, and the handling "
        "of the Gemini request and its streamed reply is covered by an automated test. They were not "
        "scored on the question set, because no API key was available when the experiments were run, "
        "so no figures for them are reported. The results in this chapter are therefore those of the "
        "system with no language model.")

# make Word refresh the fields when the file is opened
settings = doc.settings.element
if settings.find(qn("w:updateFields")) is None:
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)

doc.save(str(OUT))
print("written", OUT)
