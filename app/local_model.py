"""The locally trained answer model.

A FLAN-T5 model fine-tuned on question/passage/answer examples written from this
corpus (see training/). It runs on this machine's CPU: no API key, and no question
or passage leaves the computer.

Contract, same as the other generators: question + retrieved passages in, a short
answer with [n] citations out, or NO_ANSWER when the passages do not contain it.
"""
from __future__ import annotations

import re
import threading
from typing import Iterator

from . import config

NO_ANSWER = "NO_ANSWER"
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_CITATION = re.compile(r"\s*\[(\d+)\]")
_lock = threading.Lock()
_loaded: dict = {}


class UngroundedAnswer(RuntimeError):
    """The model wrote a figure that is not in the passages it was given."""


def is_trained() -> bool:
    """True when a trained model has been saved in the models/ folder."""
    return (config.LOCAL_MODEL_DIR / "config.json").exists()


def runtime_missing() -> str:
    """Check that PyTorch and Transformers are installed.

    Returns "" when everything is there, otherwise a message saying what to install.
    """
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return "Install the model runtime: pip install -r requirements-model.txt"
    return ""


def _flat(text: str) -> str:
    """One line of plain text: T5's tokenizer has no newline, and table pipes only cost tokens."""
    text = re.sub(r"^\s*\|?[\s:|-]{3,}\|?\s*$", " ", text, flags=re.M)      # table rule rows
    text = text.replace("|", " ; ").replace("**", "").replace("`", "")
    text = re.sub(r"(\s*;\s*)+", " ; ", text)
    return re.sub(r"\s+", " ", text).strip(" ;")


def build_input(question: str, passages: list[tuple[str, str, str]]) -> str:
    """The exact text the model reads. passages: (document title, section heading, text)."""
    parts = [f"[{n}] {title} - {section}: {_flat(text)}"
             for n, (title, section, text) in enumerate(passages, start=1)]
    return f"question: {question.strip()} context: " + " ".join(parts)


def passages_of(hits) -> list[tuple[str, str, str]]:
    """Keep the top few retrieved passages as (title, section, text) for the model to read."""
    return [(h.chunk.title, h.chunk.section, h.chunk.text) for h in hits[:config.LOCAL_PASSAGES]]


def load(model_dir=None):
    """Load the model once per process. Returns (tokenizer, model)."""
    key = str(model_dir or config.LOCAL_MODEL_DIR)
    with _lock:
        if key not in _loaded:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(key)
            model = AutoModelForSeq2SeqLM.from_pretrained(key)
            model.eval()
            torch.set_grad_enabled(False)
            _loaded[key] = (tokenizer, model)
        return _loaded[key]


def generate(texts: list[str], model_dir=None, max_new_tokens: int = 96) -> list[str]:
    """Raw model output for each input text (used by the pipeline, training and testing).

    The tokenizer turns text into numbers (tokens), the model produces the answer's
    tokens, and the tokenizer turns those back into text. num_beams means the model
    explores several candidate answers side by side and keeps the best (beam search).
    """
    import torch

    tokenizer, model = load(model_dir)
    batch = tokenizer(texts, return_tensors="pt", padding=True, truncation=True,
                      max_length=config.LOCAL_MAX_INPUT_TOKENS)
    with torch.no_grad():
        out = model.generate(**batch, max_new_tokens=max_new_tokens, num_beams=config.LOCAL_BEAMS,
                             no_repeat_ngram_size=4)
    return [text.strip() for text in tokenizer.batch_decode(out, skip_special_tokens=True)]


def declined(answer: str) -> bool:
    """True when the model said NO_ANSWER (or said nothing), i.e. it refused to answer."""
    return not answer.strip() or NO_ANSWER in answer.upper().replace(" ", "_")


def unsupported_numbers(answer: str, passages: list[tuple[str, str, str]]) -> list[str]:
    """Figures in the answer that appear nowhere in the passages (a made-up fee or date).

    A safety check against hallucination: every number the model writes must also be
    in the passages it read. If one is not, the answer is rejected.
    """
    context = " ".join(f"{title} {section} {text}" for title, section, text in passages).replace(",", "")
    found = set(_NUMBER.findall(context))
    figures = _NUMBER.findall(_CITATION.sub(" ", answer).replace(",", ""))
    return [n for n in figures if n not in found and n.rstrip(".:") not in found]


def tidy(answer: str, n_passages: int) -> str:
    """Drop citations that point at no passage."""
    return _CITATION.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_passages else "", answer).strip()


def local_stream(question: str, hits, history: list[dict]) -> Iterator[str]:
    """Generator used by the pipeline. The answer is short, so it is sent in one piece.

    Steps: build the model input from the question and passages, let the model write,
    pass on NO_ANSWER if it declined, reject an answer containing a number that is not
    in the passages, and finally remove citations that point at no passage.
    """
    passages = passages_of(hits)
    answer = generate([build_input(question, passages)])[0]
    if declined(answer):
        yield NO_ANSWER
        return
    if config.LOCAL_NUMBER_CHECK:
        bad = unsupported_numbers(answer, passages)
        if bad:
            raise UngroundedAnswer(f"it wrote '{bad[0]}', which is not in the passages")
    yield tidy(answer, len(passages))
