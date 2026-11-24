"""Fine-tune FLAN-T5 into the chatbot's local answer model. Runs on a CPU.

Run:  python -m training.data                       (once: build data/train/train.jsonl)
      python -m training.train                      (train; add --resume to continue a stopped run)

After every epoch the model answers the DEV half of the labelled questions and the
epoch with the best dev score is kept in models/svu-flan-t5/. The TEST half is not
touched here; training/test_model.py reports on it afterwards.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from app import config
from app.evaluate import load_questions
from app.local_model import build_input, declined, passages_of
from app.pipeline import Engine
from training.data import TRAIN_FILE


def score_answer(question: dict, answer: str) -> bool:
    """Same rule as app/evaluate.py: every key fact present, or a decline when there is no answer."""
    if question["type"] != "answerable":
        return declined(answer)
    norm = lambda text: " ".join(text.lower().replace(",", "").split())  # noqa: E731
    return not declined(answer) and all(norm(f) in norm(answer) for f in question.get("key_facts", []))


def labelled_examples(engine: Engine, split: str) -> list[dict]:
    """The labelled questions of one split, each with the model input the pipeline would build."""
    out = []
    for q in load_questions():
        if q["split"] != split:
            continue
        hits = engine.index.search(q["question"], config.TOP_K)
        out.append({**q, "input": build_input(q["question"], passages_of(hits))})
    return out


@torch.no_grad()
def answer_all(model, tokenizer, texts: list[str], batch_size: int = 8, beams: int = 1) -> list[str]:
    """Let the model answer many inputs, a few at a time (a "batch").

    Inputs are sorted by length first, so each batch holds texts of similar size and
    runs faster; the answers are put back in the original order at the end.
    """
    model.eval()
    answers: list[str] = []
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    for start in range(0, len(order), batch_size):
        ids = order[start:start + batch_size]
        batch = tokenizer([texts[i] for i in ids], return_tensors="pt", padding=True, truncation=True,
                          max_length=config.LOCAL_MAX_INPUT_TOKENS)
        out = model.generate(**batch, max_new_tokens=96, num_beams=beams, no_repeat_ngram_size=4)
        answers += tokenizer.batch_decode(out, skip_special_tokens=True)
    restored = [""] * len(texts)
    for i, answer in zip(order, answers):
        restored[i] = answer.strip()
    return restored


def dev_report(model, tokenizer, dev: list[dict]) -> dict:
    """Test the model on the DEV questions after an epoch and return its accuracy.

    This is how we decide which epoch's model is the best one to keep.
    """
    answers = answer_all(model, tokenizer, [d["input"] for d in dev])
    correct = [score_answer(d, a) for d, a in zip(dev, answers)]
    answerable = [c for d, c in zip(dev, correct) if d["type"] == "answerable"]
    outside = [c for d, c in zip(dev, correct) if d["type"] != "answerable"]
    return {"accuracy": round(sum(correct) / len(correct), 4),
            "answerable_correct": round(sum(answerable) / max(len(answerable), 1), 4),
            "unanswerable_declined": round(sum(outside) / max(len(outside), 1), 4)}


def batches(lengths: list[int], batch_size: int, rng: random.Random) -> list[list[int]]:
    """Batches of similar length (less padding = faster on a CPU), in random order."""
    order = sorted(range(len(lengths)), key=lambda i: (lengths[i], rng.random()))
    chunks = [order[i:i + batch_size] for i in range(0, len(order), batch_size)]
    rng.shuffle(chunks)
    return chunks


def main() -> None:
    """Fine-tune the model: the whole training run.

    FINE-TUNING means starting from a model that already knows language (FLAN-T5) and
    teaching it our specific task with our own examples. The loop, for each epoch
    (one full pass over the training examples):
      1. take a batch of examples and let the model predict the answers
      2. measure how wrong it was (the "loss")
      3. adjust the model's weights slightly to reduce that loss (backpropagation)
      4. after the epoch, test on the dev questions and keep the best model so far
    """
    parser = argparse.ArgumentParser(description="Fine-tune the local answer model.")
    parser.add_argument("--base", default="google/flan-t5-small", help="pretrained model to start from")
    parser.add_argument("--out", default=str(config.LOCAL_MODEL_DIR))
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--threads", type=int, default=0, help="CPU threads (0 = PyTorch default)")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--limit", type=int, default=None, help="train on the first N examples (smoke test)")
    parser.add_argument("--resume", action="store_true", help="continue from the last finished epoch")
    args = parser.parse_args()

    out = Path(args.out)
    last = out / "last"                      # state after the most recent epoch, for --resume
    out.mkdir(parents=True, exist_ok=True)
    log_file = out / "training_log.json"
    torch.manual_seed(args.seed)
    if args.threads:
        torch.set_num_threads(args.threads)
    rng = random.Random(args.seed)

    with TRAIN_FILE.open(encoding="utf-8") as handle:
        examples = [json.loads(line) for line in handle if line.strip()][:args.limit]

    log = {"base_model": args.base, "epochs": [], "steps": [], "settings": vars(args),
           "examples": len(examples), "threads": torch.get_num_threads()}
    start_epoch = 0
    source = args.base
    if args.resume and (last / "config.json").exists() and log_file.exists():
        log = json.loads(log_file.read_text(encoding="utf-8"))
        start_epoch = len(log["epochs"])
        source = str(last)
        print(f"Resuming after epoch {start_epoch}")

    tokenizer = AutoTokenizer.from_pretrained(source)
    model = AutoModelForSeq2SeqLM.from_pretrained(source)
    log["parameters"] = sum(p.numel() for p in model.parameters())

    inputs = tokenizer([e["input"] for e in examples], truncation=True, max_length=config.LOCAL_MAX_INPUT_TOKENS)
    targets = tokenizer([e["target"] for e in examples], truncation=True, max_length=96)
    lengths = [len(ids) for ids in inputs["input_ids"]]
    log["input_tokens"] = {"mean": round(sum(lengths) / len(lengths)), "max": max(lengths),
                           "truncated": sum(1 for n in lengths if n >= config.LOCAL_MAX_INPUT_TOKENS)}

    engine = Engine()
    dev = labelled_examples(engine, "dev")
    print(f"{len(examples)} training examples, {len(dev)} dev questions, "
          f"{log['parameters'] / 1e6:.0f}M parameters, {torch.get_num_threads()} threads")

    steps_per_epoch = math.ceil(len(examples) / args.batch_size)
    total_steps = steps_per_epoch * args.epochs
    warmup = max(1, int(0.06 * total_steps))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.0)
    schedule = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda step: min((step + 1) / warmup, max(0.0, (total_steps - step) / max(total_steps - warmup, 1))))
    if start_epoch and (last / "optimizer.pt").exists():
        state = torch.load(last / "optimizer.pt")
        optimizer.load_state_dict(state["optimizer"])
        schedule.load_state_dict(state["schedule"])

    def collate(ids: list[int]) -> dict:
        """Pack several examples into one batch, padding the shorter ones to equal length."""
        batch = tokenizer.pad({"input_ids": [inputs["input_ids"][i] for i in ids],
                               "attention_mask": [inputs["attention_mask"][i] for i in ids]}, return_tensors="pt")
        labels = tokenizer.pad({"input_ids": [targets["input_ids"][i] for i in ids]}, return_tensors="pt")["input_ids"]
        labels[labels == tokenizer.pad_token_id] = -100          # padding does not count towards the loss
        return {**batch, "labels": labels}

    best = max((e["dev"]["accuracy"] for e in log["epochs"]), default=-1.0)
    for epoch in range(start_epoch, args.epochs):
        model.train()
        started = time.time()
        running, seen = 0.0, 0
        epoch_rng = random.Random(args.seed + epoch)
        for step, ids in enumerate(batches(lengths, args.batch_size, epoch_rng), start=1):
            loss = model(**collate(ids)).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            optimizer.zero_grad()
            running += loss.item()
            seen += 1
            if step % 10 == 0 or step == steps_per_epoch:
                global_step = epoch * steps_per_epoch + step
                log["steps"].append({"step": global_step, "loss": round(running / seen, 4)})
                rate = (time.time() - started) / step
                print(f"epoch {epoch + 1}/{args.epochs} step {step}/{steps_per_epoch} "
                      f"loss {running / seen:.4f} ({rate:.1f} s/step)", flush=True)
                running, seen = 0.0, 0
        train_minutes = (time.time() - started) / 60

        report = dev_report(model, tokenizer, dev)
        epoch_losses = [s["loss"] for s in log["steps"] if (epoch * steps_per_epoch) < s["step"] <= (epoch + 1) * steps_per_epoch]
        entry = {"epoch": epoch + 1, "train_loss": round(sum(epoch_losses) / len(epoch_losses), 4),
                 "minutes": round(train_minutes, 1), "dev": report}
        log["epochs"].append(entry)
        print(f"== epoch {epoch + 1}: train loss {entry['train_loss']}, dev {report}, {train_minutes:.1f} min", flush=True)

        if report["accuracy"] > best:
            best = report["accuracy"]
            log["best_epoch"] = epoch + 1
            model.save_pretrained(out)
            tokenizer.save_pretrained(out)
        model.save_pretrained(last)
        tokenizer.save_pretrained(last)
        torch.save({"optimizer": optimizer.state_dict(), "schedule": schedule.state_dict()}, last / "optimizer.pt")
        log_file.write_text(json.dumps(log, indent=1), encoding="utf-8")

    print(f"Best dev accuracy {best:.1%} at epoch {log.get('best_epoch')}. Model saved to {out}")


if __name__ == "__main__":
    main()
