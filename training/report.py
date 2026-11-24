"""Write the local model's training and testing report from the saved results.

Run:  python -m training.report      (after training.train and training.test_model)

Output: report/Local_Model_Training_and_Testing_Report.md and .docx,
        report/figures/local_model_training.png

Every number in the report is read from the result files, so the report always
matches the model that was actually trained and tested.
"""
from __future__ import annotations

import json

from app import config
from training.data import SUMMARY_FILE
from training.test_model import RESULTS

REPORT_DIR = config.ROOT / "report"
NAME = "Local_Model_Training_and_Testing_Report"
FIGURE = REPORT_DIR / "figures" / "local_model_training.png"
STYLE = {"direct": "Direct", "colloquial": "Casual", "paraphrase": "Reworded", "hinglish": "Hindi-English mix"}
KIND = {"answer": "Answer in the passages (retrieval order)", "shuffled": "Answer in the passages (passages shuffled)",
        "removed": "Answering passage taken out, so the model must decline",
        "outside": "Question the documents do not cover, so the model must decline"}


def pct(value: float) -> str:
    """Format a share as a percentage: 0.875 -> "87.5%"."""
    return f"{100 * value:.1f}%"


def figure(log: dict) -> bool:
    """Draw the training chart: loss going down and dev accuracy after each epoch.

    Saves it as a PNG. Returns False when matplotlib is not installed (the report is
    then written without the chart).
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    epochs = log["epochs"]
    per_epoch = max(s["step"] for s in log["steps"]) / len(epochs)
    fig, left = plt.subplots(figsize=(7.5, 3.6), dpi=160)
    left.plot([s["step"] / per_epoch for s in log["steps"]], [s["loss"] for s in log["steps"]],
              color="#2a78d6", linewidth=1.6, label="Training loss")
    left.set_xlabel("Epoch")
    left.set_ylabel("Training loss")
    left.grid(alpha=0.25)
    right = left.twinx()
    right.plot([e["epoch"] for e in epochs], [100 * e["dev"]["accuracy"] for e in epochs],
               color="#eb6f0a", marker="o", linewidth=1.6, label="Dev accuracy")
    right.set_ylabel("Dev accuracy (%)")
    right.set_ylim(0, 100)
    lines = left.get_lines() + right.get_lines()
    left.legend(lines, [line.get_label() for line in lines], loc="center right", frameon=False)
    for axis in (left, right):
        axis.spines["top"].set_visible(False)
    fig.tight_layout()
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE)
    plt.close(fig)
    return True


def blocks() -> list[tuple]:
    """Build the report's content as a list of blocks (heading, paragraph, table ...).

    Every number is read from the saved training log and test results. The same list
    is then written out twice: as markdown and as a Word file.
    """
    log = json.loads((config.LOCAL_MODEL_DIR / "training_log.json").read_text(encoding="utf-8"))
    data = json.loads(SUMMARY_FILE.read_text(encoding="utf-8"))
    test = json.loads(RESULTS.read_text(encoding="utf-8"))
    model = test["model_only_test"]["summary"]
    base = test["base_model_test"]["summary"]
    local = test["pipeline"]["local_test"]["summary"]
    quote = test["pipeline"]["extractive_test"]["summary"]
    unseen = test["unseen_document"]["summary"]
    faith = test["faithfulness"]
    settings = log["settings"]
    best = next(e for e in log["epochs"] if e["epoch"] == log["best_epoch"])
    minutes = sum(e["minutes"] for e in log["epochs"])
    per_question = 100 / model["n"]
    has_figure = figure(log)

    def versus(a: float, b: float) -> str:
        """Describe the gap between two scores in words, e.g. "2.5 points above"."""
        gap = 100 * (a - b)
        return "the same as" if abs(gap) < 0.05 else f"{abs(gap):.1f} points {'above' if gap > 0 else 'below'}"

    out: list[tuple] = [
        ("h1", "Local answer model: training and testing report"),
        ("p", f"AI Student Assistance Chatbot (P08). Generated {test['generated_at'][:10]} from the saved training log and test results."),

        ("h2", "1. Summary"),
        ("p", f"A {log['parameters'] / 1e6:.0f}-million-parameter language model ({log['base_model']}) was fine-tuned on "
              f"{log['examples']:,} question, passage and answer examples written from the project's {len(data['by_document'])} "
              "documents. It now writes the chatbot's answers on this computer's CPU, with no API key and no internet. "
              f"It was then tested on {model['n']} labelled student questions that were kept out of training."),
        ("table", ["Test", "Result"], [
            ["Model alone, held-out questions: correct", f"{pct(model['accuracy'])} of {model['n']}"],
            ["Same questions, same model before training", pct(base["accuracy"])],
            ["Whole chatbot with the local model", pct(local["accuracy"])],
            ["Whole chatbot quoting the documents (no model)", pct(quote["accuracy"])],
            ["Questions on a document it never saw", f"{pct(unseen['accuracy'])} of {unseen['n']}"],
            ["Answers containing a figure that is not in the passages", pct(model["answers_with_unsupported_number"])],
            ["Time per answer, whole chatbot (median)", f"{local['latency_ms']['median'] / 1000:.1f} s"],
        ]),
        ("p", f"The test set is small: one question is worth {per_question:.1f} percentage points, so differences of a few "
              "points between two rows are within the noise."),

        ("h2", "2. What was trained"),
        ("table", ["Item", "Value"], [
            ["Starting model", f"{log['base_model']} (pretrained, {log['parameters'] / 1e6:.0f}M parameters)"],
            ["Task", "Read the question and the retrieved passages; write a short answer and cite the passage as [n], or reply NO_ANSWER"],
            ["Passages read per question", str(data["passages_per_example"])],
            ["Training examples", f"{log['examples']:,}"],
            ["Epochs / batch size / learning rate", f"{settings['epochs']} / {settings['batch_size']} / {settings['lr']}"],
            ["Input length (tokens)", f"mean {log['input_tokens']['mean']}, longest {log['input_tokens']['max']}"],
            ["Hardware", f"CPU only, {log['threads']} threads"],
            ["Training time", f"{minutes:.0f} minutes"],
        ]),
        ("h3", "2.1 Training data"),
        ("p", f"{data['questions_written']} questions were written for training from the corpus documents, in the four wordings "
              "students use. Each question was run through the chatbot's real retriever, so the model was trained on the same "
              "kind of context it sees in use: the right passage mixed with related wrong ones."),
        ("table", ["Kind of example", "Count"], [[KIND.get(k, k), str(v)] for k, v in data["by_kind"].items()]),
        ("table", ["Wording", "Count"], [[STYLE.get(k, k), str(v)] for k, v in data["by_style"].items()]),
        ("p", "Questions left out of the training set: "
              + "; ".join(f"{v} ({k})" for k, v in data["dropped"].items()) + "."),
        ("h3", "2.2 Keeping the test honest"),
        ("bullets", [
            "The labelled questions in data/eval/questions.jsonl were never used for training. The split is the "
            "project's existing one: the DEV half chose the best epoch, the TEST half is reported here.",
            "The training questions were written without looking at the labelled questions, and any training question sharing "
            "70% or more of its words with a labelled question was removed.",
            "The training and test questions are about the same documents. That is the intended use (a help desk for one "
            "university), but it means the test measures new questions on familiar documents. Section 4.4 tests an unfamiliar document.",
            "The training questions and answers were written by an AI assistant (Claude) from the documents, not collected from "
            "real students.",
        ]),

        ("h2", "3. Training"),
        ("table", ["Epoch", "Training loss", "Dev accuracy", "Dev answerable correct", "Dev out-of-scope declined", "Minutes"],
         [[str(e["epoch"]) + (" (kept)" if e["epoch"] == log["best_epoch"] else ""), f"{e['train_loss']:.3f}", pct(e["dev"]["accuracy"]),
           pct(e["dev"]["answerable_correct"]), pct(e["dev"]["unanswerable_declined"]), f"{e['minutes']:.0f}"] for e in log["epochs"]]),
        ("p", f"The model from epoch {log['best_epoch']} was kept because it scored highest on the dev questions "
              f"({pct(best['dev']['accuracy'])})."),
    ]
    if has_figure:
        out.append(("image", FIGURE, "Training loss (left axis) and accuracy on the dev questions after each epoch (right axis)."))

    out += [
        ("h2", "4. Testing"),
        ("p", "How an answer is marked, the same rule the project's evaluation already uses: an answerable question is correct "
              "when the answer contains every labelled key fact (the date, amount or number a right answer must state); an "
              "out-of-scope question is correct when the assistant declines."),
        ("h3", "4.1 The model alone, before and after training"),
        ("p", f"The model was given each test question with the top {data['passages_per_example']} retrieved passages, with no "
              "confidence gate in front of it. The untrained model was given the same text plus a written instruction."),
        ("table", ["Measure", "Before training", "After training"], [
            ["Correct overall", pct(base["accuracy"]), pct(model["accuracy"])],
            ["Answerable questions answered correctly", pct(base["answerable_correct"]), pct(model["answerable_correct"])],
            ["Answerable questions answered wrongly", pct(base["answerable_wrong"]), pct(model["answerable_wrong"])],
            ["Answerable questions declined", pct(base["answerable_declined"]), pct(model["answerable_declined"])],
            ["Out-of-scope questions declined", pct(base["unanswerable_declined"]), pct(model["unanswerable_declined"])],
            ["Key facts present in the answers given", pct(base["fact_coverage"]), pct(model["fact_coverage"])],
            ["Answers that cite a passage", pct(base["has_citation"]), pct(model["has_citation"])],
            ["Answers that cite the passage holding the answer", pct(base["cites_gold_passage"]), pct(model["cites_gold_passage"])],
            ["Word overlap with the reference answer (F1)", f"{base['token_f1']:.2f}", f"{model['token_f1']:.2f}"],
            ["ROUGE-L against the reference answer", f"{base['rouge_l']:.2f}", f"{model['rouge_l']:.2f}"],
        ]),
        ("p", f"Retrieval sets the ceiling: the passage holding the answer was among the passages for "
              f"{pct(test['retrieval_ceiling_test'])} of the answerable test questions (top {config.TOP_K}; the model reads the "
              f"top {data['passages_per_example']})."),
        ("table", ["Wording of the question", "Answered correctly"], [[STYLE.get(k, k), pct(v)] for k, v in model["by_style"].items()]),
        ("table", ["Document category", "Answered correctly"], [[k.capitalize(), pct(v)] for k, v in model["by_category"].items()]),

        ("h3", "4.2 The whole chatbot"),
        ("p", "Question, retrieval, confidence gate, then the generator, exactly as the website runs it. When the local model "
              "writes a figure that is not in the passages, the chatbot discards the answer and quotes the documents instead."),
        ("table", ["Measure", "Local model", "Quote the documents"], [
            ["Correct overall", pct(local["accuracy"]), pct(quote["accuracy"])],
            ["Answerable questions answered correctly", pct(local["answerable_correct"]), pct(quote["answerable_correct"])],
            ["Answerable questions answered wrongly", pct(local["answerable_wrong"]), pct(quote["answerable_wrong"])],
            ["Answerable questions declined", pct(local["answerable_declined"]), pct(quote["answerable_declined"])],
            ["Out-of-scope questions declined", pct(local["unanswerable_declined"]), pct(quote["unanswerable_declined"])],
            ["Answers replaced by quotes after the figure check", pct(local["fell_back_to_quotes"]), "not applicable"],
            ["Median time per answer", f"{local['latency_ms']['median'] / 1000:.1f} s", f"{quote['latency_ms']['median'] / 1000:.1f} s"],
            ["95th percentile time per answer", f"{local['latency_ms']['p95'] / 1000:.1f} s", f"{quote['latency_ms']['p95'] / 1000:.1f} s"],
        ]),
        ("p", f"With the local model the chatbot scored {versus(local['accuracy'], quote['accuracy'])} the quote-only generator on "
              f"these {local['n']} questions."),
        ("h3", "4.3 Which confidence gate"),
        ("p", "The chatbot declines before generating when retrieval confidence is below a threshold. A model that can decline by "
              "itself can sit behind a looser gate. Both were measured; the dev column is the one to choose by."),
        ("table", ["Gate", "Threshold", "Dev accuracy", "Test accuracy", "Test answerable correct", "Test out-of-scope declined"],
         [[name.capitalize() + (" (better on dev)" if name == test["pipeline"]["gate_chosen_on_dev"] else ""), f"{g['threshold']:.2f}",
           pct(g["dev"]["accuracy"]), pct(g["test"]["accuracy"]), pct(g["test"]["answerable_correct"]),
           pct(g["test"]["unanswerable_declined"])] for name, g in test["pipeline"]["gates"].items()]),
        ("p", "The website uses the loose gate for every language-model generator."),

        ("h3", "4.4 A document the model never saw"),
        ("p", f"\"{test['unseen_document']['document']}\" was written only for this test. It is not in the corpus and no training "
              f"question came from it. It was indexed as if it had just been uploaded, and {unseen['n']} questions were asked "
              f"({unseen['n_answerable']} answerable, {unseen['n_unanswerable']} not). Retrieval found a passage of the new "
              f"document for {pct(test['unseen_document']['retrieved'])} of the answerable ones."),
        ("table", ["Measure", "Unseen document", "Test questions on corpus documents"], [
            ["Correct overall", pct(unseen["accuracy"]), pct(model["accuracy"])],
            ["Answerable questions answered correctly", pct(unseen["answerable_correct"]), pct(model["answerable_correct"])],
            ["Out-of-scope questions declined", pct(unseen["unanswerable_declined"]), pct(model["unanswerable_declined"])],
            ["Answers containing a figure not in the passages", pct(unseen["answers_with_unsupported_number"]),
             pct(model["answers_with_unsupported_number"])],
        ]),

        ("h3", "4.5 Faithfulness: the figure check"),
        ("p", "A small model can write a fee or a date that looks right and is not. Every number in an answer is therefore looked "
              "up in the passages the model was given. Across the answers in 4.1 and 4.4:"),
        ("table", ["", "Count"], [
            ["Answers checked", str(faith["answers_checked"])],
            ["Flagged: a figure was not in the passages", str(faith["flagged"])],
            ["Flagged answers that were wrong (good catches)", str(faith["flagged_that_were_wrong"])],
            ["Flagged answers that were right (false alarms)", str(faith["flagged_that_were_right"])],
            ["Wrong answers the check did not catch", str(faith["wrong_answers_not_flagged"])],
        ]),
        ("p", "The check only sees numbers. A wrong answer that copies a real figure from the wrong sentence passes it."),
    ]
    if faith["examples"]:
        out.append(("table", ["Question", "Model's answer", "Not in the passages"],
                    [[e["question"], e["answer"], ", ".join(e["not_in_passages"])] for e in faith["examples"]]))

    rows = test["model_only_test"]["rows"]
    right = [r for r in rows if r["correct"] and r["type"] == "answerable"][:5]
    wrong = [r for r in rows if not r["correct"]][:8]
    out += [
        ("h3", "4.6 Speed"),
        ("p", f"On this computer's CPU the model alone takes {test['speed']['model_only_seconds_per_answer']:.1f} s per answer. "
              f"The whole chatbot answers in {local['latency_ms']['median'] / 1000:.1f} s (median) with the local model and "
              f"{quote['latency_ms']['median'] / 1000:.1f} s when quoting the documents."),
        ("h2", "5. Sample answers from the test"),
        ("h3", "5.1 Marked correct"),
        ("table", ["Question", "Model's answer"], [[r["question"], r["answer"]] for r in right]),
        ("h3", "5.2 Marked wrong"),
        ("table", ["Question", "Kind", "Model's answer"],
         [[r["question"], "answerable" if r["type"] == "answerable" else "out of scope", r["answer"]] for r in wrong]),

        ("h2", "6. Limits of this test"),
        ("bullets", [
            f"{model['n']} test questions and {unseen['n']} unseen-document questions are few. Treat the percentages as rough.",
            "The corpus is sample data for a fictional university, and the questions were written for the project, not asked by real students.",
            "Marking by key facts is strict and literal: an answer that states the fact in other words (\"three quarters\" for 75%) is marked wrong, "
            "and an answer that contains the fact inside a wrong sentence is marked right.",
            "The model has no memory of the conversation. Follow-up questions work only because the chatbot searches them together with the previous question.",
            "The model was trained once, with one random seed. A second run would give somewhat different numbers.",
        ]),

        ("h2", "7. How to repeat it"),
        ("code", "pip install -r requirements-model.txt\n"
                 "python -m training.data          # build data/train/train.jsonl\n"
                 "python -m training.train         # fine-tune; --resume continues a stopped run\n"
                 "python -m training.test_model    # writes data/eval/local_model_test.json\n"
                 "python -m training.report        # writes this report"),
        ("p", "Files: training questions in data/train/raw/, training log in models/svu-flan-t5/training_log.json, every test "
              "answer in data/eval/local_model_test.json."),
    ]
    return out


def to_markdown(items: list[tuple]) -> str:
    """Write the report blocks as markdown text (# headings, | tables |, - bullets)."""
    lines: list[str] = []
    for kind, *rest in items:
        if kind in ("h1", "h2", "h3"):
            lines += ["#" * int(kind[1]) + " " + rest[0], ""]
        elif kind == "p":
            lines += [rest[0], ""]
        elif kind == "bullets":
            lines += [f"- {text}" for text in rest[0]] + [""]
        elif kind == "code":
            lines += ["```", rest[0], "```", ""]
        elif kind == "image":
            lines += [f"![{rest[1]}]({rest[0].relative_to(REPORT_DIR).as_posix()})", "", f"*{rest[1]}*", ""]
        elif kind == "table":
            header, rows = rest
            cell = lambda text: str(text).replace("|", "\\|").replace("\n", " ")  # noqa: E731
            lines += ["| " + " | ".join(cell(h) for h in header) + " |", "|" + "---|" * len(header)]
            lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows] + [""]
    return "\n".join(lines)


def to_docx(items: list[tuple], path) -> None:
    """Write the same report blocks as a Word (.docx) file, using the python-docx library."""
    from docx import Document
    from docx.shared import Inches, Pt

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    for kind, *rest in items:
        if kind in ("h1", "h2", "h3"):
            doc.add_heading(rest[0], level=int(kind[1]) - 1)
        elif kind == "p":
            doc.add_paragraph(rest[0])
        elif kind == "bullets":
            for text in rest[0]:
                doc.add_paragraph(text, style="List Bullet")
        elif kind == "code":
            run = doc.add_paragraph().add_run(rest[0])
            run.font.name, run.font.size = "Consolas", Pt(9)
        elif kind == "image":
            doc.add_picture(str(rest[0]), width=Inches(6.2))
            doc.add_paragraph(rest[1]).runs[0].italic = True
        elif kind == "table":
            header, rows = rest
            table = doc.add_table(rows=1, cols=len(header))
            table.style = "Light Grid Accent 1"
            for cell, text in zip(table.rows[0].cells, header):
                cell.text = str(text)
            for row in rows:
                for cell, text in zip(table.add_row().cells, row):
                    cell.text = str(text)
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(9.5)
            doc.add_paragraph()
    doc.save(str(path))


def main() -> None:
    """Build the report once and save it in both formats."""
    items = blocks()
    (REPORT_DIR / f"{NAME}.md").write_text(to_markdown(items), encoding="utf-8")
    to_docx(items, REPORT_DIR / f"{NAME}.docx")
    print(f"Report written to {REPORT_DIR / (NAME + '.md')} and .docx")


if __name__ == "__main__":
    main()
