"""Make Hindi-English ("Hinglish") questions searchable.

Students often type Hindi in Latin letters: "fees ki last date kab hai". The
documents are in English, so neither keyword search nor the English embedding
model can match "kab" to "when" or "kitne din" to "how many days". This module
rewrites such a question into rough English before it is searched:

    "medical certificate kitne din me submit karna hai"
 -> "medical certificate how many day submit"

It is a word list, not a translator: common question words, time words and campus
vocabulary are replaced, grammatical particles are dropped, and every other word
is kept as typed. The rewritten text is used only for searching; a language model
that writes the answer still receives the student's own words.
"""
from __future__ import annotations

import re

# Words that only occur in Hindi. One of these must be present before anything is
# rewritten, so an English question is never touched.
_MARKERS = {
    "hai", "hain", "kya", "kab", "kaise", "kese", "kyu", "kyun", "kyon", "kitna", "kitni", "kitne",
    "kaun", "kaunsa", "kaunsi", "konsa", "konsi", "kahan", "kaha", "nahi", "nahin", "toh", "mein",
    "ka", "ki", "ke", "ko", "hoga", "hogi", "hota", "hoti", "chahiye", "karna", "karni", "karne",
    "milega", "milegi", "milta", "milti", "sakta", "sakti", "sakte", "wala", "wali", "liye",
    "agar", "tha", "thi", "kab", "tak", "baje", "raha", "rahi", "gaya", "gayi", "mera", "meri",
    "mujhe", "aur", "ya", "bhi", "lagega", "lagegi", "lagta", "lagti", "kitne", "abhi", "kaise",
}

# Hindi word -> English replacement. An empty string drops the word.
_WORDS = {
    # question words
    "kya": "what", "kab": "when", "kahan": "where", "kaha": "where", "kaun": "who",
    "kaise": "how", "kese": "how", "kaisa": "how", "kaisi": "how", "kyu": "why", "kyun": "why", "kyon": "why",
    "kitna": "how much", "kitni": "how much", "kitne": "how many",
    "kaunsa": "which", "kaunsi": "which", "konsa": "which", "konsi": "which", "kis": "which", "kiska": "whose",
    # particles and auxiliaries: carry no searchable meaning
    "hai": "", "hain": "", "h": "", "tha": "", "thi": "", "the": "", "ho": "", "hota": "", "hoti": "",
    "hote": "", "hoga": "", "hogi": "", "honge": "", "hua": "", "hui": "", "hue": "",
    "raha": "", "rahi": "", "rahe": "", "gaya": "", "gayi": "", "gaye": "", "jata": "", "jati": "", "jate": "",
    "ka": "", "ki": "", "ke": "", "ko": "", "se": "", "me": "", "mein": "", "par": "", "pe": "",
    "kar": "", "karna": "", "karni": "", "karne": "", "karu": "", "karun": "", "kare": "", "karein": "",
    "karte": "", "karta": "", "karti": "", "kiya": "", "karwana": "", "karwani": "",
    "toh": "", "to": "", "bhi": "", "hi": "", "na": "", "wala": "", "wali": "", "wale": "", "liye": "",
    "mera": "", "meri": "", "mere": "", "mujhe": "", "mujhko": "", "hum": "", "humko": "", "hume": "",
    "apna": "", "apni": "", "apne": "", "ye": "", "yeh": "", "wo": "", "woh": "", "is": "", "us": "",
    "sakta": "", "sakti": "", "sakte": "", "paega": "", "paunga": "", "abhi": "", "ab": "", "koi": "any",
    "kuch": "any", "sab": "all", "sabhi": "all", "ek": "one", "aur": "and", "ya": "or", "agar": "if",
    "lekin": "but", "par": "", "kyunki": "because", "matlab": "",
    # negation and need
    "nahi": "not", "nahin": "not", "mat": "not", "bina": "without", "saath": "with", "sath": "with",
    "chahiye": "required", "zaroori": "required", "zaruri": "required", "jaruri": "required",
    "zarurat": "required", "jarurat": "required", "allowed": "allowed",
    # time
    "din": "days", "dino": "days", "hafta": "week", "hafte": "weeks", "mahina": "month", "mahine": "months",
    "saal": "year", "ghanta": "hour", "ghante": "hours", "baje": "time", "raat": "night", "subah": "morning",
    "shaam": "evening", "dopahar": "afternoon", "aaj": "today", "kal": "tomorrow", "tak": "until",
    "baad": "after", "pehle": "before", "pahle": "before", "dauran": "during", "jaldi": "early",
    "der": "late", "late": "late", "samay": "time", "time": "time", "tarikh": "date", "tareekh": "date",
    # amounts
    "kam": "less", "zyada": "more", "jyada": "more", "poora": "full", "pura": "full", "aadha": "half",
    "paisa": "fee", "paise": "fee", "rupay": "rupees", "rupaye": "rupees", "shulk": "fee",
    "jurmana": "fine", "fine": "fine", "kharcha": "cost", "lagega": "cost", "lagegi": "cost",
    "lagta": "cost", "lagti": "cost", "lagte": "cost",
    # verbs students use
    "milega": "get", "milegi": "get", "milta": "get", "milti": "get", "milte": "get", "milna": "get",
    "dena": "pay", "deni": "pay", "dene": "pay", "bharna": "pay", "bharni": "pay", "bharne": "pay",
    "jama": "submit", "lena": "take", "leni": "take", "lene": "take", "jana": "go", "jaana": "go",
    "jaye": "go", "jaun": "go", "aana": "come", "aaye": "come", "band": "close", "khulta": "open",
    "khulti": "open", "khula": "open", "khulega": "open", "badalna": "change", "badal": "change",
    "chhodna": "drop", "chhod": "drop", "chod": "drop", "nikalna": "withdraw", "wapas": "refund back",
    "vapas": "refund back", "dobara": "again", "dubara": "again", "phir": "again", "likhna": "write",
    "padhna": "study", "padhai": "study", "banwana": "apply", "banana": "make", "milna": "get",
    "bhejna": "send", "puchna": "ask", "batao": "", "bata": "", "bataiye": "", "pata": "",
    "kho": "lost", "khogaya": "lost", "toot": "damaged", "chahta": "want", "chahti": "want",
    # campus vocabulary
    "chutti": "leave", "chhutti": "leave", "chuttiyan": "holidays", "avkash": "leave",
    "bimar": "medical illness", "bimaar": "medical illness", "bukhar": "medical illness", "tabiyat": "medical illness",
    "pariksha": "examination", "imtihan": "examination", "paper": "paper", "ank": "marks", "number": "marks",
    "hazri": "attendance", "haazri": "attendance", "upasthiti": "attendance",
    "kamra": "room", "khana": "mess food", "kitab": "book", "kitabe": "books", "kitabein": "books",
    "dakhila": "admission", "pravesh": "admission", "anumati": "permission", "ijazat": "permission",
    "niyam": "rule", "suchna": "notice", "chhatravas": "hostel", "pustakalaya": "library",
    "vishay": "course", "subject": "course", "sem": "semester", "galti": "mistake", "nakal": "copying plagiarism",
    "saza": "penalty", "dand": "penalty", "shikayat": "grievance complaint", "dost": "friend",
    "ghar": "home", "mata": "parent", "pita": "parent", "bahar": "outside", "andar": "inside",
}

_WORD = re.compile(r"[A-Za-z0-9%.'-]+|[^A-Za-z0-9\s]")


def looks_hinglish(text: str) -> bool:
    """True when the text contains at least one Hindi-only word such as "kab" or "hai"."""
    words = {w.lower().strip(".'-") for w in _WORD.findall(text)}
    return bool(words & _MARKERS)


def to_search_english(text: str) -> str:
    """Rewrite a Hinglish question for searching; return other text unchanged.

    Goes through the question word by word: a known Hindi word is replaced by its
    English meaning (or dropped when it is only grammar), every other word is kept.
    Example: "fees ki last date kab hai" -> "fees last date when".
    """
    if not looks_hinglish(text):
        return text
    out = []
    for token in _WORD.findall(text):
        key = token.lower().strip(".'-")
        if key in _WORDS:
            if _WORDS[key]:
                out.append(_WORDS[key])
        else:
            out.append(token)
    return " ".join(out) or text
