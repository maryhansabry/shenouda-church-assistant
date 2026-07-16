import pickle
import re
import time
import math
import random
import json
from pathlib import Path
from collections import Counter

import requests
from config import (
    CHUNKS_PATH,
    GROQ_API_KEY,
    TOP_K,
    CEREBRAS_API_KEY,
    GROQ_SECONDARY_MODEL,
    GROQ_TERTIARY_MODEL,
)

_chunks: list[str] = []

_AR_STOPWORDS = {
    "في", "من", "الى", "إلى", "على", "عن", "و", "أو", "ثم", "أن", "إن",
    "هذا", "هذه", "ذلك", "تلك", "هو", "هي", "هم", "كان", "كانت", "يكون",
    "لا", "ما", "لم", "لن", "قد", "كل", "بعض", "مع", "بين", "عند",
    "التي", "الذي", "الذين", "له", "لها", "لهم", "به", "بها", "بهم",
}

_word_re = re.compile(r"[\w\u0600-\u06FF]+")


def _tokenize(text: str) -> list[str]:
    words = _word_re.findall(text.lower())
    return [w for w in words if w not in _AR_STOPWORDS and len(w) > 1]


_chunk_token_lists: list[list[str]] = []
_doc_freq: Counter = Counter()
_avg_doc_len: float = 0.0

BM25_K1 = 1.5
BM25_B = 0.75

RETRIEVAL_HISTORY_WINDOW = 2


def _build_bm25_index():
    global _chunk_token_lists, _doc_freq, _avg_doc_len

    _chunk_token_lists = [_tokenize(chunk) for chunk in _chunks]
    _doc_freq = Counter()
    for tokens in _chunk_token_lists:
        for word in set(tokens):
            _doc_freq[word] += 1

    total_len = sum(len(tokens) for tokens in _chunk_token_lists)
    _avg_doc_len = (total_len / len(_chunk_token_lists)) if _chunk_token_lists else 0.0


def _bm25_score(query_tokens: list[str], doc_index: int) -> float:
    doc_tokens = _chunk_token_lists[doc_index]
    doc_len = len(doc_tokens) or 1
    term_freq = Counter(doc_tokens)
    n_docs = len(_chunk_token_lists) or 1

    score = 0.0
    for term in query_tokens:
        tf = term_freq.get(term, 0)
        if tf == 0:
            continue
        df = _doc_freq.get(term, 0)
        idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / (_avg_doc_len or 1))
        score += idf * (tf * (BM25_K1 + 1)) / (denom or 1)

    return score


def _build_retrieval_query(question: str, history: list[dict] | None) -> str:
    parts = [question]
    if history:
        recent = history[-RETRIEVAL_HISTORY_WINDOW:]
        for item in recent:
            content = item.get("content")
            if content:
                parts.append(content)
    return " ".join(parts)


def _retrieve_context(question: str, history: list[dict] | None = None, top_k: int = TOP_K) -> str:
    # بترجع كل الـ chunks مجمعة كسياق كامل للموديل. القاعدة المعرفية
    # هنا صغيرة نسبيًا (وثيقة تاريخ كنيسة واحدة)، فإرسالها كاملة أأمن
    # من فلترة BM25 top-k اللي ممكن تفوّت جزء مهم من المعلومة وتسبب
    # هلوسة أو إجابة ناقصة. لو حجم القاعدة المعرفية كبر أوي مستقبلاً
    # وبقى فيه مشكلة تكلفة/سرعة، يبقى وقتها نرجع لفلترة BM25 (الكود
    # القديم موجود تحت كـ نسخة بديلة).
    return "\n\n---\n\n".join(_chunks)


# -------------------------------------------------------------------
# نسخة بديلة (BM25 top-k) - استخدمها بدل النسخة اللي فوق لو حبيتي تقللي
# حجم الـ context المرسل للموديل بدل إرساله كامل في كل مرة:
# -------------------------------------------------------------------
# def _retrieve_context(question: str, history: list[dict] | None = None, top_k: int = TOP_K) -> str:
#     if not _chunk_token_lists:
#         _build_bm25_index()
#
#     retrieval_query = _build_retrieval_query(question, history)
#     query_tokens = _tokenize(retrieval_query)
#
#     scores = [
#         (_bm25_score(query_tokens, i), i) for i in range(len(_chunks))
#     ]
#     scores.sort(key=lambda pair: pair[0], reverse=True)
#
#     top_indices = [i for score, i in scores[:top_k] if score > 0]
#
#     if not top_indices:
#         top_indices = list(range(min(top_k, len(_chunks))))
#
#     selected = [_chunks[i] for i in top_indices]
#     return "\n\n---\n\n".join(selected)


SYSTEM_PROMPT_TEMPLATE = """You are شنودة, AI assistant for Anba Shenouda Church, Alexandria. Today: {today}
 
- Identity: "أنا شنودة، مساعد ذكي خاص بكنيسة الأنبا شنودة."
- Arabic only.
- Answer only from the provided context.
- Never invent facts or reveal reasoning (<think>).
- Keep answers concise and proportional to the question: answer exactly what was asked, no more.
  A short/specific question ("مين أبونا مينا") gets a short answer (2-3 sentences).
  Only give a longer, fuller answer when the question explicitly asks for a full story/detailed
  account (e.g. "احكيلي قصة الكنيسة كاملة"). Do not pad answers with unrequested extra background.
 
For duration questions: use any explicit duration first; otherwise calculate from the available dates. If the answer cannot be determined from the context, reply exactly:
"عذرًا، لا أملك معلومة مؤكدة عن ذلك. يرجى الرجوع لقدس أبونا ويصا."
- Preserve all names and terminology exactly as they appear in the context. Do not rename or generalize them.
- الألقاب الكهنوتية (القمص، القس، الأنبا، البابا، الدكتور...) جزء من الاسم ومش قابلة للتبديل أو التخمين. انسخي اللقب زي ما هو مكتوب حرفيًا في الجملة/الفقرة اللي بتستخدميها كمصدر للإجابة، ممنوع تستبدليه بلقب تاني حتى لو حسيتي إنه أنسب أو أكتر شيوعًا.
  ملحوظة: بعض الكهنة اتذكروا في الـ context بأكتر من رتبة مختلفة في فترات مختلفة من حياتهم (مثلاً كان "القس فلان" وبعدين اترقّى وبقى "القمص فلان"). في الحالة دي اللقب مش غلط في المصدر - فمينفعش تفرضي لقب واحد ثابت على الشخص في كل إجابة. استخدمي اللقب المكتوب في نفس الجملة/الفترة الزمنية اللي بتتكلمي عنها بالظبط، ولو السؤال عام من غير تحديد فترة، استخدمي اللقب الأحدث/الأخير المذكور له في الـ context.
- عند نقل أي معلومة فيها أكتر من طرف (شخص لقى حاجة، حاجة مكتوب عليها حاجة، حاجة صورتها حاجة تانية...)، حافظ بالظبط على مين بيرجع على مين زي ما هو موجود في الـ context. متلخصش أو تعيد صياغة الجملة بشكل ممكن يبدّل الفاعل بالمفعول أو يخلط بين طرفين مختلفين في الجملة. لو الجملة معقدة، انقلها بنفس ترتيب أحداثها تقريبًا بدل ما "تفهمها وتعيد كتابتها" من عندك.
- ممنوع تضيف أي تفصيلة (تاريخ، اسم، سبب، ترتيب أحداث) مش موجودة حرفيًا في الـ context، حتى لو حسيت إنها منطقية أو متوقعة.
- ممنوع تضيف أي تعليق عن طبيعة الـ context نفسه (زي "لا توجد تواريخ محددة في النص"،
  "المعلومة غير متوفرة بالتفصيل"، "النص لا يذكر كذا"). لو فيه تفصيلة ناقصة، تجاهلها
  تمامًا واستمر في باقي الإجابة من غير ما تنوّه عنها؛ ماتحولش نفسك لناقد على مصدر
  المعلومة ومتتصححش كلمة زي قدس اكتبها زي ما هي .
- For comparisons, count only service at this church.
- Use conversation history for follow-ups.
- Be warm and respectful.
- الكهنة الذين يخدموا حاليا ؟ هم قدس ابونا ويصا وقدس ابونا مينا وقدس ابونا يوساب ربنا يديم كهنوتهم
-اكتر كاهن خدم هو ابونا ويصا عشان خدم 45 سنة
- Name disambiguation: "القمص جرجس مرقس" = the father (served 1959-1975, died 1975). "القمص ويصا القمص جرجس" / "القس ويصا القمص جرجس" / "الدكتور أنسي القمص جرجس" = his son, a different person, same "جرجس" surname only.
  Rule: if query mentions "ويصا" or "أنسي" → use only sentences containing those words; ignore sentences with "جرجس مرقس" alone.
  If query mentions "جرجس"/"جرجس مرقس" without "ويصا"/"أنسي" → use only sentences with "جرجس مرقس"; ignore "ويصا" sentences.
  Never merge both unless explicitly asked about their relation (then: ويصا is جرجس مرقس's son).
"""

def _system_prompt() -> str:
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    return SYSTEM_PROMPT_TEMPLATE.format(today=today)


# =========================
# تريجر ترحيب البابا (عند ذكر "معاك قداسة البابا" أو "البابا تواضروس")
# =========================
PAPAL_GREETING_PHRASES = {
    "معاك قداسة البابا",
    "معاك قداسه البابا",
    "معاك كراسة البابا ",
}
# PAPAL_GREETING_REQUIRED_TOKENS = {"معاك", "قداسه", "البابا"}

PAPAL_GREETING_REPLY = "أهلًا وسهلًا يا قداسة البابا، حابين نرحب بقداستك، وهنشغل لحن أفلوجيمينوس."
PAPAL_HYMN_URL = "https://res.cloudinary.com/y7ev5cpa/video/upload/v1783374987/audiomass-output_fqmcn4.mp3"

def _papal_greeting_already_played(history: list[dict] | None) -> bool:
    if not history:
        return False
    return any(
        item.get("role") == "assistant" and item.get("content") == PAPAL_GREETING_REPLY
        for item in history
    )

PAPAL_GREETING_BASE_TOKENS = {"معاك", "البابا"}
PAPAL_GREETING_TITLE_TOKENS = {"قداسه", "كراسه"}


def _check_papal_greeting_trigger(question: str, history: list[dict] | None) -> bool:
    if _papal_greeting_already_played(history):
        return False
    tokens = _text_tokens(question)
    return (
        PAPAL_GREETING_BASE_TOKENS.issubset(tokens)
        and bool(PAPAL_GREETING_TITLE_TOKENS & tokens)
    )


FALLBACK_MESSAGE = "في ضغط عالي على النظام دلوقتي، ممكن تجرب تاني بعد شوية؟"

MAX_RETRIES = 3
NETWORK_ERROR_BASE_DELAY = 2

MAX_HISTORY_MESSAGES = 3
TOPIC_KEYWORDS: dict[str, dict] = {
    "شنودة دوس": {
        "phrases": {
            "ابونا شنوده دوس",
            "شنوده دوس",
        },
        "tokens": {
            "شنوده",
            "دوس",
            "ابونا",
        },
        "folders": ["الاباء/ابونا شنودة"],
    },

    "ابراهيم عطية": {
        "phrases": {
            "ابونا ابراهيم عطيه",
            "ابراهيم عطيه",
        },
        "tokens": {
            "ابراهيم",
            "عطيه",
            "ابونا",
        },
        "folders": ["الاباء/ابونا ابراهيم عطية"],
    },
      "ويصا": {
        "phrases": {
            "ابونا ويصا",
            "القمص ويصا",
            "ابونا القمص ويصا",
            "ابونا القمص ويصا جرجس",
            "ويصا جرجس",
            "القمص ويصا القمص جرجس",
            "دكتور انسي",
        },
        "tokens": {
            "ويصا",
            "ابونا",
        },
          "negative_tokens": {"مرقس"},

        "folders": ["الاباء/ابونا ويصا"],
    },

    "جرجس مرقس": {
        "phrases": {
            "ابونا جرجس",
            "القمص جرجس مرقس",
            "ابونا جرجس مرقس",
            "جرجس مرقس",
        },
        "tokens": {
            "جرجس",
            "مرقس",
            "القمص",
            "ابونا",
        },
         "negative_tokens": {"ويصا", "انسي"},
        "folders": ["الاباء/ابونا جرجس"],
    },

    "اغاثون حنا": {
        "phrases": {
            "ابونا اغاثون",
            "اغاثون حنا",
        },
        "tokens": {
            "اغاثون",
            "حنا",
            "ابونا",
        },
        "folders": ["الاباء/ابونا اغاثون"],
    },

    "مينا زكي سليمان": {
        "phrases": {
            "ابونا مينا",
            "مينا زكي سليمان",
        },
        "tokens": {
            "مينا",
            "زكي",
            "سليمان",
            "ابونا",
        },
        "folders": ["الاباء/ابونا مينا"],
    },

    "يوساب حنا": {
        "phrases": {
            "ابونا يوساب",
            "يوساب حنا",
        },
        "tokens": {
            "يوساب",
            "حنا",
            "ابونا",
        },
        "folders": ["الاباء/ابونا يوساب"],
    },



    "البابا شنودة الثالث": {
        "phrases": {
            "البابا شنوده",
            "قداسه البابا شنوده",
            "شنوده الثالث",
        },
        "tokens": {
            "البابا",
            "شنوده",
            "الثالث",
        },
        "folders": ["زيارات البطاركة/البابا شنودة 1977"],
    },

    "البابا كيرلس": {
        "phrases": {
            "البابا كيرلس",
            "قداسه البابا كيرلس",
        },
        "tokens": {
            "كيرلس",
            "البابا",
        },
        "folders": ["زيارات البطاركة/1960البابا كيرلس"],
    },

    "البابا تواضروس": {
        "phrases": {
            "البابا تواضروس",
            "قداسه البابا تواضروس",
             "البابا تواضرس",
        },
        "tokens": {
            "تواضروس",
            "البابا",
            "تواضرس",
        },
        "folders": ["زيارات البطاركة/البابا تواضروس 2015"],
    },
"لوقا وصليب": {
        "phrases": {
            "المعلم لوقا",
            "المعلم صليب",
            "لوقا وصليب",
            "لوقا والمعلم صليب",
        },
        "tokens": {
            "لوقا",
            "صليب",
        },
        "folders": ["المعلم لوقا والمعلم صليب"],
    },
}


def _normalize_arabic(text: str) -> str:
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"[\u064B-\u0652]", "", text)
    return text


def _text_tokens(text: str) -> set[str]:
    normalized = _normalize_arabic(text).lower()
    return set(_word_re.findall(normalized))


def _topic_score(topic: dict, text: str, tokens: set[str]) -> int:
    score = 0
    normalized = _normalize_arabic(text).lower()

    for phrase in topic.get("phrases", set()):
        if phrase in normalized:
            score += 100

    for token in topic.get("tokens", set()):
        if token in tokens:
            score += 2
    for token in topic.get("negative_tokens", set()):
        if token in tokens:
            score -= 100

    for token in topic.get("any_tokens", set()):
        if token in tokens:
            score += 1

    return score


def _topic_matches(topic: dict, text: str, tokens: set[str]) -> bool:
    return _topic_score(topic, text, tokens) > 0


def _build_ambiguous_tokens() -> set[str]:
    token_to_topics: dict[str, set[str]] = {}
    for name, topic in TOPIC_KEYWORDS.items():
        for token in (topic.get("tokens", set()) | topic.get("any_tokens", set())):
            token_to_topics.setdefault(token, set()).add(name)
    return {token for token, names in token_to_topics.items() if len(names) > 1}


_AMBIGUOUS_TOPIC_TOKENS = _build_ambiguous_tokens()


def _earliest_topic_match(text: str) -> list[str] | None:
    tokens = _text_tokens(text)
    normalized = _normalize_arabic(text).lower()
    word_positions = [(m.group(0), m.start()) for m in _word_re.finditer(normalized)]

    best_name = None
    best_pos = None

    for name, topic in TOPIC_KEYWORDS.items():
        if not _topic_matches(topic, text, tokens):
            continue

        positions: list[int] = []

        for phrase in topic.get("phrases", set()):
            idx = normalized.find(phrase)
            if idx != -1:
                positions.append(idx)

        wanted = topic.get("tokens", set()) | topic.get("any_tokens", set())
        distinguishing = wanted - _AMBIGUOUS_TOPIC_TOKENS
        for word, pos in word_positions:
            if word in distinguishing:
                positions.append(pos)

        if not positions:
            continue

        topic_pos = min(positions)
        if best_pos is None or topic_pos < best_pos:
            best_pos = topic_pos
            best_name = name

    if best_name is None:
        return None
    return TOPIC_KEYWORDS[best_name]["folders"]


MIN_IMAGES_PER_ANSWER = 2
MAX_IMAGES_PER_ANSWER = 5

ASSETS_JSON_PATH = "assets.json"

_folder_to_images: dict[str, list[str]] = {}


def _load_assets_json():
    global _folder_to_images

    path = Path(ASSETS_JSON_PATH)
    if not path.exists():
        print(f"ASSETS: {ASSETS_JSON_PATH} غير موجود - الصور مش هتظهر")
        _folder_to_images = {}
        return

    with open(path, "r", encoding="utf-8") as f:
        assets = json.load(f)

    grouped: dict[str, list[str]] = {}
    for asset in assets:
        folder = asset.get("folder", "")
        url = asset.get("url")
        if not folder or not url:
            continue
        grouped.setdefault(folder, []).append(url)

    _folder_to_images = grouped
    total_images = sum(len(v) for v in grouped.values())
    print(f"ASSETS: تم تحميل {total_images} صورة عبر {len(grouped)} مجلد من {ASSETS_JSON_PATH}")

    print("ASSETS: أسماء الفولدرات المتاحة فعليًا:")
    for folder_name in sorted(grouped.keys()):
        print(f"   - '{folder_name}' ({len(grouped[folder_name])} صورة)")

    known_folders = {f for topic in TOPIC_KEYWORDS.values() for f in topic["folders"]}
    missing = known_folders - set(grouped.keys())
    if missing:
        print("⚠️  ASSETS WARNING: الفولدرات دي مكتوبة في TOPIC_KEYWORDS بس مش موجودة في assets.json (هترجع صفر صور دايمًا):")
        for name in sorted(missing):
            print(f"   ✗ '{name}'")


def _detect_topic_folders(
    question: str,
    answer: str,
    history: list[dict] | None = None,
) -> tuple[list[str] | None, str]:
    # اتشالت خطوة البحث في الـ history (كانت بتدور في آخر رسالتين من
    # المحادثة السابقة) لأنها كانت بترجع صور موضوع قديم اتذكر في سؤال/رد
    # سابق، حتى لو السؤال والرد الحاليين مالهومش دعوة بيه - فبتظهر صور
    # غلط. دلوقتي بندور بس في السؤال الحالي، وبعدين في الرد الحالي.
    folders = _earliest_topic_match(question)
    if folders:
        return folders, "question"

    folders = _earliest_topic_match(answer)
    if folders:
        return folders, "answer"

    return None, "no_match"


def _get_images(
    folders: list[str],
    min_count: int = MIN_IMAGES_PER_ANSWER,
    max_count: int = MAX_IMAGES_PER_ANSWER,
) -> list[str]:
    if not _folder_to_images:
        _load_assets_json()

    all_urls: list[str] = []
    for folder in folders:
        all_urls.extend(_folder_to_images.get(folder, []))

    if not all_urls:
        return []

    random.shuffle(all_urls)
    count = min(len(all_urls), max_count)
    return all_urls[:count]


NO_INFO_ANSWERS = {
    FALLBACK_MESSAGE,
    "عذرًا، لا أملك معلومة مؤكدة عن ذلك. يرجى الرجوع لقدس أبونا ويصا.",
}


def _detect_priest_images(
    question: str,
    answer: str,
    history: list[dict] | None = None,
) -> list[str]:
    if answer.strip() in NO_INFO_ANSWERS:
        print("IMAGES: الرد اعتذار/فولباك - مفيش صور هترجع مهما كان السؤال")
        return []

    folders, source = _detect_topic_folders(question, answer, history)

    if not folders:
        print(f"IMAGES: مفيش تطابق موضوع (source={source}) - مفيش صور هترجع")
        return []

    images = _get_images(folders)

    available = sum(len(_folder_to_images.get(f, [])) for f in folders)
    print(
        f"IMAGES: matched folders={folders} (source={source}) - "
        f"available={available}, sending={len(images)}"
    )

    return images


def load_resources():
    global _chunks
    print("Loading chunks...")
    with open(CHUNKS_PATH, "rb") as f:
        _chunks = pickle.load(f)
    _chunks = [c["text"] if isinstance(c, dict) else c for c in _chunks]

    _build_bm25_index()
    _load_assets_json()

    print(f"✅ Ready — {len(_chunks)} chunks")


def _extract_retry_seconds(response: requests.Response, default: float = 5.0) -> float:
    try:
        message = response.json().get("error", {}).get("message", "")
        match = re.search(r"try again in ([\d.]+)s", message)
        if match:
            return float(match.group(1)) + 0.5
    except Exception:
        pass
    return default


_LATIN_RE = re.compile(r"[a-zA-Z]")


def _has_language_leak(text: str) -> bool:
    letters = re.findall(r"[^\W\d_]", text, flags=re.UNICODE)
    if not letters:
        return False
    latin_count = len(_LATIN_RE.findall(text))
    return latin_count > 0 and (latin_count / len(letters)) > 0.05


_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_thinking(text: str) -> str:
    cleaned = _THINK_TAG_RE.sub("", text).strip()

    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1]

    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0]

    return cleaned.strip()


_FEWSHOT_CONTEXT_1 = (
    "[نشأة الكنيسة وشراء الأرض]\n"
    "كان شعب القباري القليل في ذلك الحين يجتمع في جمعية المحبة القبطية الأرثوذكسية، "
    "ولم تكن له كنيسة. ففكر المعلم لوقا والمعلم صليب يوسف في شراء قطعة أرض تبعد عدة أمتار "
    "عن الجمعية، وبالفعل تم ذلك. وهذه الأرض تم شراؤها على جزئين، وتم التنازل عنهما "
    "للبطريركية سنة 1957 / 1958."
)
_FEWSHOT_ANSWER_1 = "المعلم لوقا والمعلم صليب يوسف."

_FEWSHOT_ANSWER_2 = (
    "بدأت الخدمة لما شعب القباري كان قليل ومكانش ليه كنيسة، وكان بيجتمع في جمعية "
    "المحبة القبطية الأرثوذكسية. فكر المعلم لوقا والمعلم صليب يوسف يشتروا قطعة أرض "
    "على بعد كام متر من الجمعية، واشتروها فعلاً، وتم التنازل عن الأرض للبطريركية "
    "سنة 1957/1958."
)

_FEWSHOT_CONTEXT_2 = (
    "[زيارات قداسة البابا تواضروس الثاني للكنيسة]\n"
    "قبل أن يصير بطريركًا، كان نيافة الأنبا تواضروس أسقفًا عامًّا، وزار الكنيسة "
    "مرات كثيرة في نهضات الأنبا شنودة. وبعد أن صار بطريركًا، زار الكنيسة يوم "
    "الأربعاء الموافق 30/12/2014 برفقة خمسة أساقفة، وألقى العظة الأسبوعية، ووعد "
    "بتدشين الكنيسة. وقد تم تنفيذ هذا الوعد يوم 9 شهر سبعة، وبيزور قداسته "
    "الكنيسة مرة أخرى وحضر التدشين."
)
_FEWSHOT_ANSWER_3 = (
    "قداسة البابا تواضروس الثاني زار الكنيسة عدة مرات؛ كان أسقفًا عامًّا فزارها "
    "كثيرًا في نهضات الأنبا شنودة، ثم زارها بصفته بطريركًا في الأربعاء 30/12/2014 "
    "مع خمسة أساقفة، حيث ألقى العظة الأسبوعية ووعد بتدشينها. وقد تم تنفيذ الوعد "
    "يوم 9 شهر سبعة وقداسته بيزورنا."
)

FEWSHOT_EXAMPLES: list[dict] = [
    {
        "role": "user",
        "content": (
            f"Church knowledge base:\n{_FEWSHOT_CONTEXT_1}\n\n"
            "Question: مين صاحب فكرة بناء الكنيسة؟\n\nAnswer in Arabic only."
        ),
    },
    {"role": "assistant", "content": _FEWSHOT_ANSWER_1},
    {
        "role": "user",
        "content": (
            f"Church knowledge base:\n{_FEWSHOT_CONTEXT_1}\n\n"
            "Question: كيف بدأت الخدمة في القباري؟\n\nAnswer in Arabic only."
        ),
    },
    {"role": "assistant", "content": _FEWSHOT_ANSWER_2},
    {
        "role": "user",
        "content": (
            f"Church knowledge base:\n{_FEWSHOT_CONTEXT_2}\n\n"
            "Question: كم مرة زار قداسة البابا تواضروس الكنيسة؟\n\nAnswer in Arabic only."
        ),
    },
    {"role": "assistant", "content": _FEWSHOT_ANSWER_3},
]


def _build_messages(question: str, context: str, history: list[dict] | None) -> list[dict]:
    messages = [{"role": "system", "content": _system_prompt()}]
    messages.extend(FEWSHOT_EXAMPLES)

    if history:
        recent_history = history[-MAX_HISTORY_MESSAGES:]
        for item in recent_history:
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append(
        {
            "role": "user",
            "content": f"Church knowledge base:\n{context}\n\nQuestion: {question}\n\nAnswer in Arabic only.",
        }
    )

    return messages


CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_CHAT_MODEL = "gpt-oss-120b"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_RETRIES_PRIMARY = MAX_RETRIES
FALLBACK_MAX_RETRIES = 1


def _call_chat_completions(
    messages: list[dict],
    url: str,
    api_key: str,
    model: str,
) -> requests.Response:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 500,
        "messages": messages,
    }

    model_lower = model.lower()

    if "qwen" in model_lower:
        payload["reasoning_effort"] = "none"
        payload["reasoning_format"] = "hidden"
    elif "gpt-oss" in model_lower:
        payload["reasoning_effort"] = "low"
        if "groq.com" in url:
            payload["reasoning_format"] = "hidden"
    elif "llama" in model_lower:
        pass

    return requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )


def _attempt_completion(
    messages: list[dict],
    url: str,
    api_key: str,
    model: str,
    max_retries: int,
) -> requests.Response | None:
    for attempt in range(max_retries + 1):
        is_last_attempt = attempt == max_retries

        try:
            resp = _call_chat_completions(messages, url, api_key, model)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            print(f"[{model}] NETWORK ERROR (attempt {attempt + 1}/{max_retries + 1}): {exc}")
            if is_last_attempt:
                return None
            time.sleep(NETWORK_ERROR_BASE_DELAY * (2 ** attempt))
            continue
        except requests.exceptions.RequestException as exc:
            print(f"[{model}] UNEXPECTED REQUEST ERROR (attempt {attempt + 1}/{max_retries + 1}): {exc}")
            if is_last_attempt:
                return None
            time.sleep(NETWORK_ERROR_BASE_DELAY * (2 ** attempt))
            continue

        print(f"[{model}] STATUS:", resp.status_code)
        print(f"[{model}] BODY:", resp.text)

        if resp.status_code == 429:
            if is_last_attempt:
                return None
            wait_seconds = _extract_retry_seconds(resp)
            print(f"[{model}] RATE LIMITED — waiting {wait_seconds}s before retry")
            time.sleep(wait_seconds)
            continue

        if resp.status_code >= 500:
            if is_last_attempt:
                return None
            time.sleep(NETWORK_ERROR_BASE_DELAY * (2 ** attempt))
            continue

        resp.raise_for_status()
        return resp

    return None


def answer_question(question: str, history: list[dict] | None = None) -> tuple[str, list[str], str | None]:
    # تريجر ترحيب البابا - بيتفحص الأول قبل أي RAG أو نداء LLM
    if _check_papal_greeting_trigger(question, history):
        print("PAPAL GREETING TRIGGERED — skipping RAG/LLM, returning hymn directly")
        return PAPAL_GREETING_REPLY, [], PAPAL_HYMN_URL

    # *** الإصلاح الأساسي ***
    # كانت هنا: context = (question, history)  -> ده tuple مش سياق حقيقي،
    # فكان بيتحول لسترينج غريب زي ('السؤال', [...history...]) ويترسل
    # للموديل بدل محتوى الـ knowledge base الفعلي. ده كان السبب في إن
    # الموديل بيهلوس/يجاوب غلط، لأنه أساسًا مكانش شايف أي معلومة حقيقية
    # عن الكنيسة.
    context = _retrieve_context(question, history)
    print("CONTEXT LENGTH (chars):", len(context))
    messages = _build_messages(question, context, history)

    try:
        resp = _attempt_completion(
            messages, CEREBRAS_URL, CEREBRAS_API_KEY, CEREBRAS_CHAT_MODEL, MAX_RETRIES_PRIMARY
        )
    except requests.exceptions.HTTPError as exc:
        print(f"[{CEREBRAS_CHAT_MODEL}] Bad request (not retrying): {exc}")
        resp = None

    if resp is None:
        print(f"{CEREBRAS_CHAT_MODEL} (Cerebras) failed - trying {GROQ_SECONDARY_MODEL} (Groq)")
        try:
            resp = _attempt_completion(
                messages, GROQ_URL, GROQ_API_KEY, GROQ_SECONDARY_MODEL, FALLBACK_MAX_RETRIES
            )
        except requests.exceptions.HTTPError as exc:
            print(f"[{GROQ_SECONDARY_MODEL}] Bad request (not retrying): {exc}")
            resp = None

    if resp is None:
        print(f"{GROQ_SECONDARY_MODEL} failed - trying {GROQ_TERTIARY_MODEL} (Groq)")
        try:
            resp = _attempt_completion(
                messages, GROQ_URL, GROQ_API_KEY, GROQ_TERTIARY_MODEL, FALLBACK_MAX_RETRIES
            )
        except requests.exceptions.HTTPError as exc:
            print(f"[{GROQ_TERTIARY_MODEL}] Bad request (not retrying): {exc}")
            resp = None

    if resp is None:
        return FALLBACK_MESSAGE, [], None

    answer = resp.json()["choices"][0]["message"]["content"].strip()
    answer = _strip_thinking(answer)

    if _has_language_leak(answer):
        print("LANGUAGE LEAK DETECTED (not retrying, logged for monitoring):", answer[:150])

    images = _detect_priest_images(question, answer, history)

    return answer, images, None
