"""
Japanese Learning App
======================
A Flask web app for learning Japanese vocabulary (hiragana, katakana,
kanji) built from a curated dataset extracted from a beginner kanji
textbook, plus a hand-curated set of everyday phrases. Features:

- Search (type in English OR Japanese - kanji, kana, or romaji)
- Hiragana / Katakana charts for learning & memorizing
- Kanji lessons with on-yomi / kun-yomi, stroke count, vocabulary
- Everyday Life word list (300+ words/phrases, categorized, with
  kanji + hiragana + English shown together)
- Practice mode with Easy / Medium / Hard / Mixed difficulty and a
  choice of round length. Learn N words, then get quizzed with a
  real example sentence (6 options). Right OR wrong, you get the
  full explanation: on-yomi, kun-yomi, sentence in kanji/hiragana/
  romaji, meaning, and where the word is commonly used.

Run with:  python app.py
Then open http://127.0.0.1:5000 in your browser.
"""
import json
import os
import random
import re
import secrets
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, session, send_from_directory,
    Response, redirect, url_for,
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
DATA_DIR = Path(__file__).parent / "data"


def _load_or_create_secret_key():
    """A random key, generated once and reused across restarts (so
    existing login sessions survive a restart) instead of a value baked
    into the source - which anyone reading the app's code could use to
    forge a session cookie."""
    key_file = DATA_DIR / "secret_key.txt"
    if key_file.exists():
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    new_key = secrets.token_hex(32)
    try:
        key_file.write_text(new_key, encoding="utf-8")
    except OSError:
        pass  # data dir not writable - key just won't persist across restarts
    return new_key


app.secret_key = _load_or_create_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=180)

# App version, shown in the footer. Bump this when shipping a meaningful
# set of changes so a person (or a bug report) can say which build they're
# on. History:
#   1.0.0 - original app: kana, kanji, verbs, everyday, stories,
#           conversations, flashcards, writing practice, practice rounds
#   1.1.0 - accounts (signup/login), streak tied to accounts, Dashboard
#           progress meters, Kanji Practice (4-option quiz)
#   1.2.0 - JLPT N5-N1 section: level browsing + per-level practice quiz,
#           JLPT badges cross-tagged onto the main Kanji section
#   1.3.0 - full review pass: Kanji/JLPT Practice now count toward the
#           Dashboard, JLPT kanji are searchable, About page and homepage
#           reflect the current feature set, CSRF protection on auth
#           forms, per-install random secret key, debug mode off by
#           default, service worker precache list refreshed
#   1.4.0 - JLPT dataset expanded to 1,000 kanji: N5 (103) and N4 (174)
#           complete, N3 (366) essentially complete, N2 (204) and N1 (153)
#           substantially larger; main Kanji section's JLPT badges
#           re-tagged against the bigger set (276 of 408 now matched)
APP_VERSION = "1.4.0"


def load_json(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


KANJI_DATA = load_json("kanji_data.json")                  # 408 kanji entries with vocab
HIRAGANA_DATA = load_json("hiragana.json")                  # hiragana chart
KATAKANA_DATA = load_json("katakana.json")                  # katakana chart
PRACTICE_SENTENCES = load_json("practice_sentences.json")   # curated sentences
EVERYDAY_EXTRA = load_json("everyday_extra.json")           # curated greetings/phrases
COMMON_WORDS = load_json("common_words.json")               # fruits/animals/food not in the kanji book
PICTURE_DICT_WORDS = load_json("picture_dict.json")          # from the Japanese Picture Dictionary (Stout)
VERBS_DATA = load_json("verbs.json")                        # verbs + rule-generated conjugations
STORIES_DATA = load_json("stories.json")                    # original graded short stories
CONVERSATIONS_DATA = load_json("conversations.json")        # original multi-turn dialogues
JLPT_KANJI = load_json("jlpt_kanji.json")                    # N5-N1 kanji, cross-referenced
                                                              # against a Kanji Dictionary for
                                                              # Foreigners-style entry format

for _i, _v in enumerate(VERBS_DATA):
    _v["idx"] = _i

# Build lookup: kanji_id -> sentence entry
SENTENCE_BY_KANJI_ID = {}
for s in PRACTICE_SENTENCES:
    SENTENCE_BY_KANJI_ID.setdefault(s["kanji_id"], s)

# -------------------------------------------------------------- JLPT N5-N1 --

JLPT_LEVELS = ["N5", "N4", "N3", "N2", "N1"]
JLPT_LEVEL_LABELS = {
    "N5": "N5 — Beginner",
    "N4": "N4 — Elementary",
    "N3": "N3 — Intermediate",
    "N2": "N2 — Upper intermediate",
    "N1": "N1 — Advanced",
}
JLPT_LEVEL_DESCRIPTIONS = {k: v.split("—")[1].strip() for k, v in JLPT_LEVEL_LABELS.items()}
JLPT_BY_LEVEL = {lvl: [e for e in JLPT_KANJI if e["level"] == lvl] for lvl in JLPT_LEVELS}
JLPT_BY_CHAR = {e["kanji"]: e for e in JLPT_KANJI}

# Tag the main Kanji-section entries with their JLPT level wherever one of
# our 408 kanji also appears in the JLPT N5-N1 set, so the existing Kanji
# pages can show it without an extra lookup.
for _entry in KANJI_DATA:
    _match = JLPT_BY_CHAR.get(_entry["kanji"])
    _entry["jlpt_level"] = _match["level"] if _match else None


# ------------------------------------------------------ categorization --

CATEGORY_KEYWORDS = [
    ("Numbers & Counting", ["one", "two", "three", "four", "five", "six", "seven",
                             "eight", "nine", "ten", "hundred", "thousand", "counter",
                             "number", "half"]),
    ("Time & Calendar", ["time", "hour", "minute", "month", "week", "year", "today",
                          "tomorrow", "yesterday", "morning", "evening", "night", "day",
                          "now", "sunday", "monday", "tuesday", "wednesday", "thursday",
                          "friday", "saturday", "every", "soon", "interval", "early"]),
    ("Family & People", ["father", "mother", "child", "brother", "sister", "family",
                          "son", "daughter", "parent", "person", "man", "male", "woman",
                          "female", "friend", "teacher", "student", "king", "myself"]),
    ("Nature & Weather", ["mountain", "river", "tree", "wood", "water", "fire", "earth",
                           "ground", "rain", "snow", "sky", "sun", "moon", "star", "wind",
                           "sea", "ocean", "flower", "stone", "field", "grass", "forest",
                           "grove", "heavens", "weather"]),
    ("Body & Health", ["eye", "ear", "mouth", "hand", "foot", "leg", "head", "face",
                        "hair", "heart", "body", "neck"]),
    ("Places & Buildings", ["school", "house", "home", "gate", "temple", "shop", "store",
                             "station", "city", "town", "country", "room", "market",
                             "capital", "library"]),
    ("Food & Drink", ["rice", "food", "tea", "fish", "meat", "vegetable", "fruit", "eat",
                       "drink", "meal"]),
    ("Directions & Position", ["left", "right", "up", "down", "inside", "outside", "near",
                                "far", "north", "south", "east", "west", "front", "back",
                                "middle", "path", "road"]),
    ("Colors", ["white", "black", "red", "blue", "green", "yellow"]),
    ("Animals", ["dog", "cow", "cattle", "bird", "horse", "sheep", "fish", "bug", "cat"]),
    ("Actions & Verbs", ["to "]),  # meanings like "To eat", "To see" start this way
    ("Size & Quantity", ["big", "small", "many", "few", "long", "short", "high", "low"]),
]


def categorize(meaning):
    m = meaning.lower()
    for label, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in m:
                return label
    return "Everyday Objects & Ideas"


def difficulty_for(strokes, word_len):
    """Heuristic difficulty from the parent kanji's stroke count and the
    word's character length (more strokes / longer compounds = harder)."""
    if strokes <= 5 and word_len <= 2:
        return "easy"
    if strokes <= 10 and word_len <= 3:
        return "medium"
    return "hard"


# ---------------------------------------------------------- emoji/images --
# No bundled photos (this is an offline app) — big emoji stand in as a
# lightweight "picture" for each word. Specific words match first; if
# nothing matches, we fall back to one emoji per category.

EMOJI_KEYWORDS = [
    ("dog", "🐶"), ("cow", "🐄"), ("cattle", "🐄"), ("beef", "🥩"), ("horse", "🐴"),
    ("bird", "🐦"), ("fish", "🐟"), ("insect", "🐛"), ("bug", "🐛"), ("cat", "🐱"),
    ("sheep", "🐑"),
    ("mountain", "⛰️"), ("river", "🏞️"), ("tree", "🌳"), ("wood", "🪵"),
    ("water", "💧"), ("fire", "🔥"), ("earth", "🌍"), ("ground", "🌍"),
    ("rain", "🌧️"), ("snow", "❄️"), ("sky", "🌤️"), ("heaven", "🌤️"),
    ("sun", "☀️"), ("moon", "🌙"), ("star", "⭐"), ("wind", "🌬️"),
    ("sea", "🌊"), ("ocean", "🌊"), ("flower", "🌸"), ("stone", "🪨"),
    ("field", "🌾"), ("grass", "🌱"), ("forest", "🌲"), ("grove", "🌲"),
    ("eye", "👁️"), ("ear", "👂"), ("mouth", "👄"), ("hand", "✋"),
    ("foot", "🦶"), ("leg", "🦵"), ("head", "🧠"), ("face", "😊"),
    ("hair", "💇"), ("heart", "❤️"), ("body", "🧍"),
    ("father", "👨"), ("mother", "👩"), ("child", "🧒"), ("brother", "👦"),
    ("sister", "👧"), ("family", "👪"), ("son", "👦"), ("daughter", "👧"),
    ("king", "👑"), ("teacher", "🧑‍🏫"), ("student", "🎓"), ("friend", "🤝"),
    ("woman", "👩"), ("man", "🧑"), ("person", "🧑"),
    ("school", "🏫"), ("house", "🏠"), ("home", "🏠"), ("gate", "🚪"),
    ("temple", "⛩️"), ("shop", "🏪"), ("store", "🏪"), ("station", "🚉"),
    ("city", "🏙️"), ("town", "🏙️"), ("country", "🌏"), ("room", "🛋️"),
    ("library", "📚"), ("market", "🏪"), ("capital", "🏛️"),
    ("rice", "🍚"), ("tea", "🍵"), ("meat", "🥩"), ("vegetable", "🥦"),
    ("fruit", "🍎"), ("meal", "🍱"), ("food", "🍽️"),
    ("white", "⚪"), ("black", "⚫"), ("red", "🔴"), ("blue", "🔵"),
    ("green", "🟢"), ("yellow", "🟡"),
    ("one", "1️⃣"), ("two", "2️⃣"), ("three", "3️⃣"), ("four", "4️⃣"),
    ("five", "5️⃣"), ("six", "6️⃣"), ("seven", "7️⃣"), ("eight", "8️⃣"),
    ("nine", "9️⃣"), ("ten", "🔟"), ("hundred", "💯"), ("thousand", "🔢"),
    ("left", "⬅️"), ("right", "➡️"), ("up", "⬆️"), ("down", "⬇️"),
    ("north", "⬆️"), ("south", "⬇️"), ("east", "➡️"), ("west", "⬅️"),
    ("big", "🔵"), ("small", "🔹"), ("book", "📖"), ("letter", "✉️"),
    ("sword", "⚔️"), ("gold", "🪙"), ("money", "💰"), ("time", "⏰"),
    ("month", "🗓️"), ("year", "📅"), ("day", "🗓️"), ("morning", "🌅"),
    ("night", "🌃"), ("today", "📆"),
]

CATEGORY_EMOJI = {
    "Numbers & Counting": "🔢",
    "Time & Calendar": "🗓️",
    "Family & People": "👪",
    "Nature & Weather": "🌿",
    "Body & Health": "🩺",
    "Places & Buildings": "🏯",
    "Food & Drink": "🍱",
    "Directions & Position": "🧭",
    "Colors": "🎨",
    "Animals": "🐾",
    "Actions & Verbs": "🎬",
    "Size & Quantity": "📏",
    "Greetings & Phrases": "💬",
    "Shopping & Money": "🛍️",
    "Out & About": "🚶",
    "Everyday Objects & Ideas": "📦",
    "Shapes & Sizes": "🔷",
    "Opposites": "↔️",
    "Money & Shopping": "💴",
    "Seasons & Holidays": "🎏",
    "School & Learning": "🏫",
    "Counters": "🔢",
    "Work & Jobs": "💼",
    "Health & Body": "🩺",
    "Environment & Nature": "🌎",
    "Sports & Fitness": "⚽",
    "Travel": "🧳",
    "Countries": "🌐",
    "Languages": "💬",
    "Music": "🎸",
    "Transportation": "🚗",
    "House & Furniture": "🛋️",
}


def get_emoji(meaning, category):
    m = meaning.lower()
    for kw, emo in EMOJI_KEYWORDS:
        if kw in m:
            return emo
    return CATEGORY_EMOJI.get(category, "📖")


# ---------------------------------------------------- sentence templates --
# For everyday words that don't have a hand-curated practice sentence,
# build a natural-ish example sentence from a per-category template so
# clicking any word in the Everyday Life list shows it in context.

def cap(s):
    return s[:1].upper() + s[1:] if s else s


SENTENCE_TEMPLATES = {
    "Animals": (
        "田中さんの{w}です。", "たなかさんの{r}です。",
        "Tanaka-san no {rm} desu.", "This is Mr. Tanaka's {en}.",
        "Used when pointing out or introducing someone's pet or animal."),
    "Family & People": (
        "これは私の{w}です。", "これはわたしの{r}です。",
        "Kore wa watashi no {rm} desu.", "This is my {en}.",
        "Used when introducing a family member or person to someone."),
    "Nature & Weather": (
        "{w}がとてもきれいです。", "{r}がとてもきれいです。",
        "{rm} ga totemo kirei desu.", "The {en} is very beautiful.",
        "Used when commenting on scenery or the weather."),
    "Body & Health": (
        "{w}が痛いです。", "{r}がいたいです。",
        "{rm} ga itai desu.", "My {en} hurts.",
        "A common phrase for describing minor aches, e.g. at a doctor's visit."),
    "Places & Buildings": (
        "明日、{w}に行きます。", "あした、{r}にいきます。",
        "Ashita, {rm} ni ikimasu.", "Tomorrow, I'm going to the {en}.",
        "Used when talking about daily plans and destinations."),
    "Food & Drink": (
        "晩ご飯に{w}を食べました。", "ばんごはんに{r}をたべました。",
        "Bangohan ni {rm} o tabemashita.", "I ate {en} for dinner.",
        "Used at the table or when talking about meals."),
    "Directions & Position": (
        "駅は{w}の方です。", "えきは{r}のほうです。",
        "Eki wa {rm} no hō desu.", "The station is that way, to the {en}.",
        "Used constantly when giving or asking for directions."),
    "Colors": (
        "私は{w}が好きです。", "わたしは{r}がすきです。",
        "Watashi wa {rm} ga suki desu.", "I like {en}.",
        "Used when talking about preferences or describing objects."),
    "Numbers & Counting": (
        "テーブルの上に{w}あります。", "テーブルのうえに{r}あります。",
        "Tēburu no ue ni {rm} arimasu.", "There is/are {en} on the table.",
        "Used for counting objects in everyday situations."),
    "Time & Calendar": (
        "{w}に会いましょう。", "{r}にあいましょう。",
        "{rm} ni aimashou.", "Let's meet {en}.",
        "Used when making plans or arranging to meet someone."),
    "Size & Quantity": (
        "この家は{w}です。", "このいえは{r}です。",
        "Kono ie wa {rm} desu.", "This house is {en}.",
        "Used when describing the size or amount of something."),
    "Shapes & Sizes": (
        "この箱は{w}です。", "このはこは{r}です。",
        "Kono hako wa {rm} desu.", "This box is a {en}.",
        "Used when describing the shape or size of an object."),
    "Opposites": (
        "この二つは{w}です。", "このふたつは{r}です。",
        "Kono futatsu wa {rm} desu.", "These two are {en}.",
        "A key adjective pair to memorize together with its opposite."),
    "Money & Shopping": (
        "これは{w}ですか。", "これは{r}ですか。",
        "Kore wa {rm} desu ka.", "Is this {en}?",
        "Common vocabulary for shopping, prices, and paying."),
    "Seasons & Holidays": (
        "{w}が近づいています。", "{r}がちかづいています。",
        "{rm} ga chikazuite imasu.", "{en} is coming up.",
        "Used when talking about the seasons, festivals, and annual holidays."),
    "School & Learning": (
        "学校で{w}を使います。", "がっこうで{r}をつかいます。",
        "Gakkō de {rm} o tsukaimasu.", "We use {en} at school.",
        "Common vocabulary for the classroom and studying."),
    "Work & Jobs": (
        "彼は{w}です。", "かれは{r}です。",
        "Kare wa {rm} desu.", "He is a {en}.",
        "Common vocabulary for talking about jobs and the workplace."),
    "Health & Body": (
        "{w}が痛いです。", "{r}がいたいです。",
        "{rm} ga itai desu.", "My {en} hurts.",
        "Common vocabulary at a doctor's visit or when describing how you feel."),
    "Environment & Nature": (
        "{w}を守りましょう。", "{r}をまもりましょう。",
        "{rm} o mamorimashō.", "Let's protect the {en}.",
        "Common vocabulary for nature, weather, and environmental topics."),
    "Sports & Fitness": (
        "私は{w}が好きです。", "わたしは{r}がすきです。",
        "Watashi wa {rm} ga suki desu.", "I like {en}.",
        "Common vocabulary for sports and staying active."),
    "Travel": (
        "旅行に{w}を持って行きます。", "りょこうに{r}をもっていきます。",
        "Ryokō ni {rm} o motte ikimasu.", "I'll bring {en} on the trip.",
        "Common vocabulary for traveling and sightseeing."),
    "Countries": (
        "私は{w}に行きたいです。", "わたしは{r}にいきたいです。",
        "Watashi wa {rm} ni ikitai desu.", "I want to go to {en}.",
        "A place name used when talking about countries and travel."),
    "Languages": (
        "私は{w}を勉強しています。", "わたしは{r}をべんきょうしています。",
        "Watashi wa {rm} o benkyō shite imasu.", "I'm studying {en}.",
        "Used when talking about which languages you speak or are learning."),
    "Music": (
        "私は{w}が好きです。", "わたしは{r}がすきです。",
        "Watashi wa {rm} ga suki desu.", "I like {en}.",
        "Common vocabulary for music, instruments, and dance."),
    "Transportation": (
        "{w}で行きます。", "{r}でいきます。",
        "{rm} de ikimasu.", "I'll go by {en}.",
        "Common vocabulary for getting around town."),
    "House & Furniture": (
        "これは私の{w}です。", "これはわたしの{r}です。",
        "Kore wa watashi no {rm} desu.", "This is my {en}.",
        "Common vocabulary for rooms and things around the house."),
}

VERB_TEMPLATE = (
    "「{w}」は「{en}」という意味の動詞です。", "「{r}」は「{en}」という意味の動詞です。",
    "\"{rm}\" means \"{en}.\"", "\"{w}\" is a verb meaning \"{en}.\"",
    "A common everyday verb — try it with a subject and an object, e.g. 何を{w}か.")

GENERIC_TEMPLATE = (
    "「{w}」は「{en}」という意味です。", "「{r}」は「{en}」という意味です。",
    "\"{rm}\" means \"{en}.\"", "\"{w}\" means \"{en}.\"",
    "A general-purpose word — look at the vocabulary list on its kanji page for more context.")


MASS_NOUNS = {"bread", "rice", "cheese", "milk", "coffee", "juice", "tea", "meat",
              "water", "sugar", "salt", "butter", "beef", "ice cream", "curry"}


def with_article(word):
    """Add a/an for the food templates so 'I ate apple' reads naturally.
    Skips plural-looking and mass-noun meanings."""
    w = word.strip()
    low = w.lower()
    if low in MASS_NOUNS or low.endswith("s") or "," in w:
        return w
    return ("an " if low[:1] in "aeiou" else "a ") + w


def build_everyday_sentence(word, reading, romaji, meaning, category):
    reading = reading or word
    romaji = romaji or reading
    meaning_clean = re.sub(r'^to\s+', '', meaning, flags=re.I).strip()

    # Any word whose English gloss reads as a verb ("to eat", "to begin"...)
    # gets the verb template regardless of category - a lot of Opposites,
    # Work, House, and Health entries are verbs, not just Actions & Verbs.
    if category == "Actions & Verbs" or re.match(r'^to\s+\w', meaning.strip(), re.I):
        tmpl = VERB_TEMPLATE
    else:
        tmpl = SENTENCE_TEMPLATES.get(category, GENERIC_TEMPLATE)

    kanji_t, hira_t, romaji_t, en_t, usage_t = tmpl
    en_arg = with_article(meaning_clean) if category == "Food & Drink" else meaning_clean
    return {
        "sentence_kanji": kanji_t.format(w=word, en=meaning_clean),
        "sentence_hiragana": hira_t.format(r=reading, en=meaning_clean),
        "sentence_romaji": cap(romaji_t.format(rm=romaji, en=meaning_clean, w=word)),
        "sentence_en": cap(en_t.format(en=en_arg, w=word)),
        "usage_note": usage_t.format(w=word, r=reading, rm=romaji, en=meaning_clean),
    }


# -------------------------------------------------- conversation builder --
# Each everyday word also gets a short two-person exchange so you can see
# the word used the way it would actually come up in conversation.
# Each line is (speaker, kanji, hiragana, romaji, english).

CONVERSATION_TEMPLATES = {
    "Animals": [
        ("A", "かわいい{w}ですね。", "かわいい{r}ですね。", "Kawaii {rm} desu ne.", "What a cute {en}!"),
        ("B", "ありがとうございます。田中さんの{w}です。", "ありがとうございます。たなかさんの{r}です。",
         "Arigatō gozaimasu. Tanaka-san no {rm} desu.", "Thank you. It's Mr. Tanaka's {en}."),
    ],
    "Family & People": [
        ("A", "この人はどなたですか。", "このひとはどなたですか。", "Kono hito wa donata desu ka.", "Who is this person?"),
        ("B", "私の{w}です。", "わたしの{r}です。", "Watashi no {rm} desu.", "That's my {en}."),
    ],
    "Nature & Weather": [
        ("A", "わあ、{w}がきれいですね。", "わあ、{r}がきれいですね。", "Wā, {rm} ga kirei desu ne.", "Wow, the {en} is beautiful!"),
        ("B", "そうですね。写真を撮りましょう。", "そうですね。しゃしんをとりましょう。",
         "Sō desu ne. Shashin o torimashō.", "It really is. Let's take a photo."),
    ],
    "Body & Health": [
        ("A", "どうしましたか。", "どうしましたか。", "Dō shimashita ka.", "What's wrong?"),
        ("B", "{w}が痛いです。", "{r}がいたいです。", "{rm} ga itai desu.", "My {en} hurts."),
    ],
    "Places & Buildings": [
        ("A", "明日どこへ行きますか。", "あしたどこへいきますか。", "Ashita doko e ikimasu ka.", "Where are you going tomorrow?"),
        ("B", "{w}へ行きます。", "{r}へいきます。", "{rm} e ikimasu.", "I'm going to the {en}."),
    ],
    "Food & Drink": [
        ("A", "晩ご飯は何でしたか。", "ばんごはんはなんでしたか。", "Bangohan wa nan deshita ka.", "What did you have for dinner?"),
        ("B", "{w}を食べました。おいしかったです。", "{r}をたべました。おいしかったです。",
         "{rm} o tabemashita. Oishikatta desu.", "I had {en}. It was delicious."),
    ],
    "Directions & Position": [
        ("A", "すみません、駅はどこですか。", "すみません、えきはどこですか。", "Sumimasen, eki wa doko desu ka.", "Excuse me, where is the station?"),
        ("B", "{w}の方です。", "{r}のほうです。", "{rm} no hō desu.", "It's to the {en}."),
    ],
    "Colors": [
        ("A", "何色が好きですか。", "なにいろがすきですか。", "Nani iro ga suki desu ka.", "What color do you like?"),
        ("B", "{w}が好きです。", "{r}がすきです。", "{rm} ga suki desu.", "I like {en}."),
    ],
    "Numbers & Counting": [
        ("A", "いくつありますか。", "いくつありますか。", "Ikutsu arimasu ka.", "How many are there?"),
        ("B", "{w}あります。", "{r}あります。", "{rm} arimasu.", "There are {en}."),
    ],
    "Time & Calendar": [
        ("A", "いつ会いましょうか。", "いつあいましょうか。", "Itsu aimashō ka.", "When shall we meet?"),
        ("B", "{w}はどうですか。", "{r}はどうですか。", "{rm} wa dō desu ka.", "How about {en}?"),
    ],
    "Size & Quantity": [
        ("A", "この家はどうですか。", "このいえはどうですか。", "Kono ie wa dō desu ka.", "What do you think of this house?"),
        ("B", "とても{w}ですね。", "とても{r}ですね。", "Totemo {rm} desu ne.", "It's very {en}."),
    ],
    "Actions & Verbs": [
        ("A", "今何をしていますか。", "いまなにをしていますか。", "Ima nani o shite imasu ka.", "What are you doing now?"),
        ("B", "「{w}」の練習をしています。", "「{r}」のれんしゅうをしています。",
         "\"{rm}\" no renshū o shite imasu.", "I'm practicing the verb \"{en}\"."),
    ],
    "Greetings & Phrases": [
        ("A", "{w}", "{r}", "{rm}", "{en}"),
        ("B", "はい、こちらこそ。", "はい、こちらこそ。", "Hai, kochira koso.", "Yes, likewise."),
    ],
    "Shopping & Money": [
        ("A", "{w}", "{r}", "{rm}", "{en}"),
        ("B", "はい、少々お待ちください。", "はい、しょうしょうおまちください。",
         "Hai, shōshō omachi kudasai.", "Certainly, one moment please."),
    ],
    "Out & About": [
        ("A", "{w}", "{r}", "{rm}", "{en}"),
        ("B", "はい、大丈夫ですよ。", "はい、だいじょうぶですよ。", "Hai, daijōbu desu yo.", "Yes, of course."),
    ],
    "Shapes & Sizes": [
        ("A", "この箱の形は何ですか。", "このはこのかたちはなんですか。", "Kono hako no katachi wa nan desu ka.", "What shape is this box?"),
        ("B", "{w}です。", "{r}です。", "{rm} desu.", "It's a {en}."),
    ],
    "Opposites": [
        ("A", "これは{w}ですか。", "これは{r}ですか。", "Kore wa {rm} desu ka.", "Is this {en}?"),
        ("B", "いいえ、逆です。", "いいえ、ぎゃくです。", "Iie, gyaku desu.", "No, it's the opposite."),
    ],
    "Money & Shopping": [
        ("A", "これはいくらですか。", "これはいくらですか。", "Kore wa ikura desu ka.", "How much is this?"),
        ("B", "{w}です。", "{r}です。", "{rm} desu.", "It's {en}."),
    ],
    "Seasons & Holidays": [
        ("A", "{w}はいつですか。", "{r}はいつですか。", "{rm} wa itsu desu ka.", "When is {en}?"),
        ("B", "もうすぐですよ。", "もうすぐですよ。", "Mō sugu desu yo.", "It's coming up soon."),
    ],
    "School & Learning": [
        ("A", "これは何ですか。", "これはなんですか。", "Kore wa nan desu ka.", "What is this?"),
        ("B", "{w}です。学校で使います。", "{r}です。がっこうでつかいます。", "{rm} desu. Gakkō de tsukaimasu.", "It's a {en}. We use it at school."),
    ],
    "Counters": [
        ("A", "いくつありますか。", "いくつありますか。", "Ikutsu arimasu ka.", "How many are there?"),
        ("B", "{w}あります。", "{r}あります。", "{rm} arimasu.", "There is/are {en}."),
    ],
    "Work & Jobs": [
        ("A", "お仕事は何ですか。", "おしごとはなんですか。", "Oshigoto wa nan desu ka.", "What's your job?"),
        ("B", "{w}です。", "{r}です。", "{rm} desu.", "I'm a {en}."),
    ],
    "Health & Body": [
        ("A", "どうしましたか。", "どうしましたか。", "Dō shimashita ka.", "What's wrong?"),
        ("B", "{w}が痛いです。", "{r}がいたいです。", "{rm} ga itai desu.", "My {en} hurts."),
    ],
    "Environment & Nature": [
        ("A", "{w}を見てください。", "{r}をみてください。", "{rm} o mite kudasai.", "Please look at the {en}."),
        ("B", "きれいですね。", "きれいですね。", "Kirei desu ne.", "It's beautiful, isn't it."),
    ],
    "Sports & Fitness": [
        ("A", "どんなスポーツをしますか。", "どんなすぽーつをしますか。", "Donna supōtsu o shimasu ka.", "What sports do you play?"),
        ("B", "{w}をします。", "{r}をします。", "{rm} o shimasu.", "I play/do {en}."),
    ],
    "Travel": [
        ("A", "旅行の準備はできましたか。", "りょこうのじゅんびはできましたか。", "Ryokō no junbi wa dekimashita ka.", "Are you ready for the trip?"),
        ("B", "はい、{w}を持ちました。", "はい、{r}をもちました。", "Hai, {rm} o mochimashita.", "Yes, I've got my {en}."),
    ],
    "Countries": [
        ("A", "どこの国から来ましたか。", "どこのくにからきましたか。", "Doko no kuni kara kimashita ka.", "What country are you from?"),
        ("B", "{w}から来ました。", "{r}からきました。", "{rm} kara kimashita.", "I'm from {en}."),
    ],
    "Languages": [
        ("A", "何語を話しますか。", "なにごをはなしますか。", "Nanigo o hanashimasu ka.", "What language do you speak?"),
        ("B", "{w}を話します。", "{r}をはなします。", "{rm} o hanashimasu.", "I speak {en}."),
    ],
    "Music": [
        ("A", "何か楽器をしますか。", "なにかがっきをしますか。", "Nanika gakki o shimasu ka.", "Do you play an instrument?"),
        ("B", "{w}をします。", "{r}をします。", "{rm} o shimasu.", "I play {en}."),
    ],
    "Transportation": [
        ("A", "どうやって行きますか。", "どうやっていきますか。", "Dōyatte ikimasu ka.", "How are you getting there?"),
        ("B", "{w}で行きます。", "{r}でいきます。", "{rm} de ikimasu.", "I'm going by {en}."),
    ],
    "House & Furniture": [
        ("A", "これは何ですか。", "これはなんですか。", "Kore wa nan desu ka.", "What is this?"),
        ("B", "{w}です。", "{r}です。", "{rm} desu.", "It's a {en}."),
    ],
}

GENERIC_CONVERSATION = [
    ("A", "「{w}」はどういう意味ですか。", "「{r}」はどういういみですか。",
     "\"{rm}\" wa dō iu imi desu ka.", "What does \"{w}\" mean?"),
    ("B", "「{en}」という意味です。", "「{en}」といういみです。",
     "\"{en}\" to iu imi desu.", "It means \"{en}\"."),
]


def build_conversation(word, reading, romaji, meaning, category):
    reading = reading or word
    romaji = romaji or reading
    meaning_clean = re.sub(r'^to\s+', '', meaning, flags=re.I).strip()
    tmpl = CONVERSATION_TEMPLATES.get(category, GENERIC_CONVERSATION)
    lines = []
    for speaker, k, h, rm, en in tmpl:
        lines.append({
            "speaker": speaker,
            "kanji": k.format(w=word, r=reading, rm=romaji, en=meaning_clean),
            "hiragana": h.format(w=word, r=reading, rm=romaji, en=meaning_clean),
            "romaji": cap(rm.format(w=word, r=reading, rm=romaji, en=meaning_clean)),
            "english": cap(en.format(w=word, r=reading, rm=romaji, en=meaning_clean)),
        })
    return lines


# --------------------------------------------------------------- words --

# Flatten every vocabulary word (across all kanji entries) into one big
# searchable list, each tagged with its parent kanji's on/kun-yomi info,
# a category, and a difficulty tier.
ALL_WORDS = []
for entry in KANJI_DATA:
    for v in entry["vocab"]:
        ALL_WORDS.append({
            "word": v["word"],
            "reading": v["reading"],
            "romaji": v["romaji"],
            "meaning": v["meaning"],
            "kanji": entry["kanji"],
            "kanji_id": entry["id"],
            "kanji_meaning": entry["meaning"],
            "on_yomi": entry["on_yomi"],
            "kun_yomi": entry["kun_yomi"],
            "strokes": entry["strokes"],
            "category": categorize(v["meaning"]),
            "difficulty": difficulty_for(entry["strokes"], len(v["word"])),
        })
# also add the bare kanji character itself as a searchable "word" for
# any kanji whose vocab list didn't already include the solo character
seen_words = {w["word"] for w in ALL_WORDS}
for entry in KANJI_DATA:
    if entry["kanji"] not in seen_words:
        ALL_WORDS.append({
            "word": entry["kanji"],
            "reading": "",
            "romaji": "",
            "meaning": entry["meaning"],
            "kanji": entry["kanji"],
            "kanji_id": entry["id"],
            "kanji_meaning": entry["meaning"],
            "on_yomi": entry["on_yomi"],
            "kun_yomi": entry["kun_yomi"],
            "strokes": entry["strokes"],
            "category": categorize(entry["meaning"]),
            "difficulty": difficulty_for(entry["strokes"], len(entry["kanji"])),
        })

# Vocabulary transcribed from the Japanese Picture Dictionary (Stout) -
# shapes, opposites, money, seasons/holidays, counters, jobs, health,
# house/furniture, extended family/animals/numbers, sports, travel,
# countries, languages, music, transportation, directions, and more
# food/drink. See gen_picture_dict.py for how each entry was sourced.
for pw in PICTURE_DICT_WORDS:
    ALL_WORDS.append({
        "word": pw["word"],
        "reading": pw["reading"],
        "romaji": pw["romaji"],
        "meaning": pw["meaning"],
        "kanji": "",
        "kanji_id": None,
        "kanji_meaning": "",
        "on_yomi": "",
        "kun_yomi": "",
        "strokes": 0,
        "category": pw["category"],
        "difficulty": "easy",
    })

# Common everyday words (fruits, animals, food, electronics...) that the
# kanji textbook doesn't cover because they aren't built around a lesson
# kanji. These make English-meaning search work for things like "apple".
for cw in COMMON_WORDS:
    ALL_WORDS.append({
        "word": cw["word"],
        "reading": cw["reading"],
        "romaji": cw["romaji"],
        "meaning": cw["meaning"],
        "kanji": "",
        "kanji_id": None,
        "kanji_meaning": "",
        "on_yomi": "",
        "kun_yomi": "",
        "strokes": 0,
        "category": cw["category"],
        "difficulty": "easy",
    })

# The pool of words usable in Practice mode: exactly one entry per kanji
# (its base character), since that's what has on/kun-yomi + a curated or
# generated sentence tied to it.
PRACTICE_POOL = [w for w in ALL_WORDS if w["word"] == w["kanji"]]
PRACTICE_BY_ID = {w["kanji_id"]: w for w in PRACTICE_POOL}

# Everyday-life word list = every kanji-vocab word (already has kanji +
# hiragana + English) plus the hand-curated greetings/phrases. This is
# well over 250 entries (1,300+ from the book alone). Each entry gets an
# example sentence (curated where we have one, template-generated
# otherwise) and an emoji "image" for a bit of visual flavor.
EVERYDAY_WORDS = []
for w in ALL_WORDS:
    curated = SENTENCE_BY_KANJI_ID.get(w["kanji_id"]) if w["word"] == w["kanji"] else None
    if curated and curated["word"] == w["word"]:
        sentence = {
            "sentence_kanji": curated["sentence_kanji"],
            "sentence_hiragana": curated["sentence_hiragana"],
            "sentence_romaji": curated["sentence_romaji"],
            "sentence_en": curated["sentence_en"],
            "usage_note": curated["usage_note"],
        }
    else:
        sentence = build_everyday_sentence(w["word"], w["reading"], w["romaji"], w["meaning"], w["category"])
    EVERYDAY_WORDS.append({
        "word": w["word"],
        "reading": w["reading"] or w["word"],
        "romaji": w["romaji"],
        "meaning": w["meaning"],
        "category": w["category"],
        "emoji": get_emoji(w["meaning"], w["category"]),
        "conversation": build_conversation(w["word"], w["reading"], w["romaji"], w["meaning"], w["category"]),
        **sentence,
    })
for extra in EVERYDAY_EXTRA:
    EVERYDAY_WORDS.append({
        "word": extra["word"],
        "reading": extra["reading"],
        "romaji": extra["romaji"],
        "meaning": extra["meaning"],
        "category": extra["category"],
        "emoji": get_emoji(extra["meaning"], extra["category"]),
        "sentence_kanji": extra["word"],
        "sentence_hiragana": extra["reading"],
        "sentence_romaji": cap(extra["romaji"]),
        "sentence_en": cap(extra["meaning"]),
        "usage_note": f"A common everyday phrase, filed under \u201c{extra['category']}\u201d.",
        "conversation": build_conversation(extra["word"], extra["reading"], extra["romaji"], extra["meaning"], extra["category"]),
    })
EVERYDAY_CATEGORIES = sorted(set(w["category"] for w in EVERYDAY_WORDS))

# Keep the original index alongside each word, then group by category so
# the page can render one clearly-labelled block per category.
for i, w in enumerate(EVERYDAY_WORDS):
    w["idx"] = i
EVERYDAY_BY_CATEGORY = [
    (cat, [w for w in EVERYDAY_WORDS if w["category"] == cat])
    for cat in EVERYDAY_CATEGORIES
]


def normalize(text):
    """Lowercase + strip diacritics/macrons for loose matching (e.g. 'kyo' matches 'kyō')."""
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def contains_japanese(text):
    return bool(re.search(r'[\u3040-\u30FF\u4E00-\u9FFF]', text))


def search_words(query, limit=60):
    """Search across word/reading/romaji/meaning, works for English or Japanese input.
    Covers the main vocab/kanji dataset (ALL_WORDS) plus the separate
    JLPT N5-N1 kanji set, so a JLPT-only kanji (one that isn't among the
    408 in the main Kanji section) is still findable from the search bar."""
    q = query.strip()
    if not q:
        return []
    q_norm = normalize(q)
    q_raw = q  # keep raw for direct Japanese char matching

    results = []
    seen_words = set()
    for w in ALL_WORDS:
        score = 0
        if contains_japanese(q_raw):
            if q_raw in w["word"] or q_raw in w["reading"] or q_raw in w["kanji"]:
                score = 3 if (w["word"] == q_raw or w["kanji"] == q_raw) else 2
        else:
            if q_norm and (q_norm in normalize(w["romaji"]) or q_norm in normalize(w["meaning"])):
                score = 3 if normalize(w["romaji"]) == q_norm else 1
        if score:
            results.append((score, w))
            seen_words.add(w["word"])

    for e in JLPT_KANJI:
        if e["kanji"] in seen_words:
            continue  # already covered by a richer ALL_WORDS/kanji_detail result
        score = 0
        if contains_japanese(q_raw):
            if q_raw == e["kanji"] or q_raw in e["on_yomi"] or q_raw in e["kun_yomi"]:
                score = 3 if q_raw == e["kanji"] else 2
        else:
            if q_norm and q_norm in normalize(e["meaning"]):
                score = 1
        if score:
            results.append((score, {
                "word": e["kanji"], "kanji": e["kanji"], "reading": e["on_yomi"],
                "romaji": "", "meaning": f"{e['meaning']} (JLPT {e['level']})",
                "jlpt_level": e["level"],
            }))
            seen_words.add(e["kanji"])

    results.sort(key=lambda x: -x[0])
    return [w for _, w in results[:limit]]


def build_explanation(word_entry):
    """Given a flattened word dict, build the rich explanation payload
    shown after a practice answer (right or wrong), or on a word detail view."""
    kanji_id = word_entry["kanji_id"]
    sentence = SENTENCE_BY_KANJI_ID.get(kanji_id)
    if not sentence:
        # fallback: auto-build a simple sentence when we have no curated one
        sentence = {
            "word": word_entry["word"],
            "sentence_kanji": f"これは「{word_entry['word']}」です。",
            "sentence_hiragana": f"これは「{word_entry['reading'] or word_entry['word']}」です。",
            "sentence_romaji": f"Kore wa \"{word_entry['romaji'] or word_entry['reading']}\" desu.",
            "sentence_en": f"This is \"{word_entry['meaning']}\".",
            "usage_note": "A generated practice sentence (no curated example available for this word yet).",
        }
    return {
        "word": word_entry["word"],
        "reading": word_entry["reading"],
        "romaji": word_entry["romaji"],
        "meaning": word_entry["meaning"],
        "kanji": word_entry["kanji"],
        "kanji_meaning": word_entry["kanji_meaning"],
        "on_yomi": word_entry["on_yomi"] or "—",
        "kun_yomi": word_entry["kun_yomi"] or "—",
        "strokes": word_entry["strokes"],
        "sentence_kanji": sentence["sentence_kanji"],
        "sentence_hiragana": sentence["sentence_hiragana"],
        "sentence_romaji": sentence["sentence_romaji"],
        "sentence_en": sentence["sentence_en"],
        "usage_note": sentence["usage_note"],
    }



def first_reading(entry):
    """Pull the first kana reading out of an on-yomi/kun-yomi string like
    'ロク ROKU' or 'む mu, むつ mutsu' -> 'ロク' / 'む'."""
    for field in ("kun_yomi", "on_yomi"):
        raw = entry.get(field) or ""
        for part in raw.split(","):
            m = re.match(r'\s*([\u3040-\u30FF]+)', part)
            if m:
                return m.group(1)
    return ""


def unique_take(candidates, correct, n):
    """Take n distinct candidates, skipping blanks and the correct answer."""
    out = []
    for c in candidates:
        if c and c != correct and c not in out:
            out.append(c)
        if len(out) == n:
            break
    return out



# -------------------------------------------------------------- accounts --
# Optional local accounts, so progress (right now: the streak) can belong
# to a person rather than to the device. Kept as flat JSON files, same as
# everything else in this app - no external database, nothing leaves the
# device/server this is running on. Signing in is entirely optional: a
# visitor who never signs up keeps working exactly like before, with the
# device-wide streak.json file.

USERS_FILE = DATA_DIR / "users.json"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def _load_users():
    if not USERS_FILE.exists():
        return []
    try:
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _find_user_by_name(username):
    needle = username.strip().lower()
    for u in _load_users():
        if u["username"].lower() == needle:
            return u
    return None


def _find_user_by_id(user_id):
    for u in _load_users():
        if u["id"] == user_id:
            return u
    return None


def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    return _find_user_by_id(uid)


@app.context_processor
def inject_current_user():
    # Makes `current_user` available in every template (the header uses it
    # to show either "Log in / Sign up" or the signed-in username).
    return {"current_user": current_user()}


def csrf_token():
    """A per-session token for the auth forms (login/signup/logout), so a
    third-party page can't submit those forms on a visitor's behalf.
    Generated once per session and reused - not rotated per-request,
    since these are simple state-changing forms, not a banking app."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def check_csrf():
    submitted = request.form.get("csrf_token", "")
    return submitted and submitted == session.get("csrf_token", "__none__")


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.context_processor
def inject_app_version():
    return {"app_version": APP_VERSION}


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user():
        return redirect(url_for("index"))
    error = None
    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        if not check_csrf():
            error = "Your session expired - please try again."
        elif not USERNAME_RE.match(username):
            error = "Username must be 3-20 characters: letters, numbers, underscore only."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif password != confirm:
            error = "Those passwords don't match."
        elif _find_user_by_name(username):
            error = "That username is already taken."
        else:
            users = _load_users()
            new_id = max((u["id"] for u in users), default=0) + 1
            users.append({
                "id": new_id,
                "username": username,
                "password_hash": generate_password_hash(password),
                "created_at": datetime.utcnow().isoformat(),
            })
            _save_users(users)
            session.clear()
            session["user_id"] = new_id
            session.permanent = True
            return redirect(url_for("index"))
    return render_template("signup.html", error=error, username=username)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    error = None
    username = ""
    next_url = request.values.get("next") or url_for("index")
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = _find_user_by_name(username)
        if not check_csrf():
            error = "Your session expired - please try again."
        elif not user or not check_password_hash(user["password_hash"], password):
            error = "Incorrect username or password."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(next_url)
    return render_template("login.html", error=error, username=username, next=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    if check_csrf():
        session.clear()
    return redirect(request.referrer or url_for("index"))


# --------------------------------------------------------------- streak --
# A simple persistent streak tracker, stored as a flat JSON file so it
# survives app restarts (unlike Flask's cookie-based session). Signed-in
# users get their own entry in user_streaks.json, keyed by user id;
# anyone not signed in keeps the original device-wide streak.json file,
# so nothing changes for people who don't create an account.

STREAK_FILE = DATA_DIR / "streak.json"
USER_STREAK_FILE = DATA_DIR / "user_streaks.json"


def _load_all_user_streaks():
    if not USER_STREAK_FILE.exists():
        return {}
    try:
        with open(USER_STREAK_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_streak_dates(user=None):
    if user is None:
        if not STREAK_FILE.exists():
            return set()
        try:
            with open(STREAK_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return set(data.get("active_dates", []))
        except (json.JSONDecodeError, OSError):
            return set()
    return set(_load_all_user_streaks().get(str(user["id"]), []))


def _save_streak_dates(dates, user=None):
    if user is None:
        with open(STREAK_FILE, "w", encoding="utf-8") as f:
            json.dump({"active_dates": sorted(dates)}, f)
        return
    all_streaks = _load_all_user_streaks()
    all_streaks[str(user["id"])] = sorted(dates)
    with open(USER_STREAK_FILE, "w", encoding="utf-8") as f:
        json.dump(all_streaks, f, ensure_ascii=False, indent=2)


def _compute_streak(dates):
    """current streak (consecutive days ending today or yesterday),
    longest streak ever, and total active days."""
    if not dates:
        return {"current": 0, "longest": 0, "total_days": 0}

    day_set = {datetime.strptime(d, "%Y-%m-%d").date() for d in dates}
    today = date.today()

    # current streak: walk backward from today (or yesterday, so a
    # missed "today" doesn't zero out a streak that's still alive until
    # midnight) while consecutive days are present
    current = 0
    cursor = today if today in day_set else today - timedelta(days=1)
    while cursor in day_set:
        current += 1
        cursor -= timedelta(days=1)

    # longest streak ever, scanning the sorted run of days
    longest = 0
    run = 0
    prev = None
    for d in sorted(day_set):
        if prev is not None and (d - prev).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev = d

    return {"current": current, "longest": longest, "total_days": len(day_set)}


@app.route("/api/streak")
def api_streak_get():
    user = current_user()
    dates = _load_streak_dates(user)
    info = _compute_streak(dates)
    info["active_dates"] = sorted(dates)
    info["logged_in"] = user is not None
    return jsonify(info)


@app.route("/api/streak/mark", methods=["POST"])
def api_streak_mark():
    """Call this whenever the person completes something that should
    count toward today's streak (a practice round, a flashcard deck)."""
    user = current_user()
    dates = _load_streak_dates(user)
    today_str = date.today().isoformat()
    is_new_day = today_str not in dates
    dates.add(today_str)
    _save_streak_dates(dates, user)
    info = _compute_streak(dates)
    info["active_dates"] = sorted(dates)
    info["is_new_day"] = is_new_day
    info["logged_in"] = user is not None
    return jsonify(info)


# ---------------------------------------------------------------- routes --

@app.route("/")
def index():
    return render_template("index.html", kanji_count=len(KANJI_DATA),
                            everyday_count=len(EVERYDAY_WORDS), jlpt_count=len(JLPT_KANJI))


@app.route("/hiragana")
def hiragana():
    return render_template("kana.html", kana_type="Hiragana", data=HIRAGANA_DATA)


@app.route("/katakana")
def katakana():
    return render_template("kana.html", kana_type="Katakana", data=KATAKANA_DATA)


@app.route("/kanji")
def kanji_list():
    return render_template("kanji_list.html", entries=KANJI_DATA)


@app.route("/kanji/practice")
def kanji_practice():
    return render_template("kanji_practice.html")


@app.route("/kanji/<int:kanji_id>")
def kanji_detail(kanji_id):
    entry = next((e for e in KANJI_DATA if e["id"] == kanji_id), None)
    if not entry:
        return "Kanji not found", 404
    word_entry = PRACTICE_BY_ID.get(kanji_id)
    explanation = build_explanation(word_entry) if word_entry else None
    return render_template("kanji_detail.html", entry=entry, explanation=explanation)


KANJI_QUIZ_LEVELS = {"all", "easy", "medium", "hard"}


@app.route("/api/kanji_quiz")
def api_kanji_quiz():
    """Multiple-choice kanji-meaning quiz. ?level=all|easy|medium|hard,
    ?count=up to 40. No correctness is revealed here - the client collects
    every answer and only shows the full breakdown once the round ends."""
    level = (request.args.get("level") or "all").lower()
    if level not in KANJI_QUIZ_LEVELS:
        level = "all"
    try:
        count = int(request.args.get("count", 20))
    except (TypeError, ValueError):
        count = 20
    count = max(4, min(count, 40))

    pool = PRACTICE_POOL if level == "all" else [e for e in PRACTICE_POOL if e["difficulty"] == level]
    if len(pool) < 4:
        pool = PRACTICE_POOL  # too small a pool to build 4 distinct options from

    chosen = random.sample(pool, min(count, len(pool)))

    questions = []
    for entry in chosen:
        correct = entry["kanji_meaning"]
        candidates = [e["kanji_meaning"] for e in pool
                      if e["kanji"] != entry["kanji"] and e["kanji_meaning"] != correct]
        random.shuffle(candidates)
        wrong, seen = [], set()
        for m in candidates:
            if m in seen:
                continue
            seen.add(m)
            wrong.append(m)
            if len(wrong) == 3:
                break
        options = wrong + [correct]
        random.shuffle(options)
        questions.append({
            "kanji": entry["kanji"],
            "on_yomi": entry.get("on_yomi", ""),
            "kun_yomi": entry.get("kun_yomi", ""),
            "correct": correct,
            "options": options,
            "difficulty": entry["difficulty"],
        })
    return jsonify({"level": level, "questions": questions})


# ------------------------------------------------------------- JLPT N5-N1 --
# A separate section from the main Kanji list: every kanji here is tagged
# with its JLPT level (N5 easiest -> N1 hardest), cross-referenced against
# a Kanji-Dictionary-for-Foreigners-style entry (radical-free summary:
# on-yomi, kun-yomi, meaning, plus an easy/medium/hard tier within each
# level for the practice quiz below).

@app.route("/jlpt")
def jlpt_index():
    levels = [{
        "level": lvl,
        "label": JLPT_LEVEL_LABELS[lvl],
        "description": JLPT_LEVEL_DESCRIPTIONS[lvl],
        "count": len(JLPT_BY_LEVEL[lvl]),
    } for lvl in JLPT_LEVELS]
    return render_template("jlpt_index.html", levels=levels)


@app.route("/jlpt/<level>")
def jlpt_level(level):
    level = level.upper()
    if level not in JLPT_LEVELS:
        return "Level not found", 404
    return render_template(
        "jlpt_level.html",
        level=level,
        label=JLPT_LEVEL_LABELS[level],
        entries=JLPT_BY_LEVEL[level],
        levels=JLPT_LEVELS,
    )


@app.route("/jlpt/<level>/practice")
def jlpt_practice(level):
    level = level.upper()
    if level not in JLPT_LEVELS:
        return "Level not found", 404
    return render_template("jlpt_practice.html", level=level, label=JLPT_LEVEL_LABELS[level])


@app.route("/api/jlpt_quiz")
def api_jlpt_quiz():
    """Same 4-option, no-feedback-until-the-end quiz as /api/kanji_quiz,
    but scoped to one JLPT level. ?level=N5..N1 (required),
    ?difficulty=all|easy|medium|hard, ?count= up to 40."""
    level = (request.args.get("level") or "").upper()
    if level not in JLPT_LEVELS:
        return jsonify({"error": "invalid level"}), 400
    difficulty = (request.args.get("difficulty") or "all").lower()
    if difficulty not in {"all", "easy", "medium", "hard"}:
        difficulty = "all"
    try:
        count = int(request.args.get("count", 20))
    except (TypeError, ValueError):
        count = 20
    count = max(4, min(count, 40))

    level_pool = JLPT_BY_LEVEL[level]
    pool = level_pool if difficulty == "all" else [e for e in level_pool if e["difficulty"] == difficulty]
    if len(pool) < 4:
        pool = level_pool  # this level/difficulty combo is too small on its own

    # Distractors are drawn from the whole level (not just the difficulty
    # slice), so a small "hard" tier doesn't run out of distinct options.
    distractor_pool = level_pool if len(level_pool) >= 4 else JLPT_KANJI

    chosen = random.sample(pool, min(count, len(pool)))
    questions = []
    for entry in chosen:
        correct = entry["meaning"]
        candidates = [e["meaning"] for e in distractor_pool
                      if e["kanji"] != entry["kanji"] and e["meaning"] != correct]
        random.shuffle(candidates)
        wrong, seen = [], set()
        for m in candidates:
            if m in seen:
                continue
            seen.add(m)
            wrong.append(m)
            if len(wrong) == 3:
                break
        options = wrong + [correct]
        random.shuffle(options)
        questions.append({
            "kanji": entry["kanji"],
            "on_yomi": entry.get("on_yomi", ""),
            "kun_yomi": entry.get("kun_yomi", ""),
            "correct": correct,
            "options": options,
            "difficulty": entry["difficulty"],
        })
    return jsonify({"level": level, "difficulty": difficulty, "questions": questions})


@app.route("/everyday")
def everyday_words():
    return render_template(
        "everyday.html",
        grouped=EVERYDAY_BY_CATEGORY,
        categories=EVERYDAY_CATEGORIES,
        total=len(EVERYDAY_WORDS),
    )


@app.route("/api/everyday/<int:idx>")
def everyday_detail(idx):
    if idx < 0 or idx >= len(EVERYDAY_WORDS):
        return jsonify({"error": "not found"}), 404
    return jsonify(EVERYDAY_WORDS[idx])


@app.route("/search")
def search_page():
    query = request.args.get("q", "")
    results = search_words(query) if query else []
    return render_template("search.html", query=query, results=results)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "")
    results = search_words(query)
    return jsonify(results)


# ------------------------------------------------------------ stories --

# ------------------------------------------------------- conversations --

@app.route("/conversations")
def conversations_list():
    return render_template("conversations.html", conversations=CONVERSATIONS_DATA)


@app.route("/conversations/<conv_id>")
def conversation_detail(conv_id):
    conv = next((c for c in CONVERSATIONS_DATA if c["id"] == conv_id), None)
    if not conv:
        return "Conversation not found", 404
    return render_template("conversation_detail.html", conv=conv)


@app.route("/stories")
def stories_list():
    return render_template("stories.html", stories=STORIES_DATA)


@app.route("/stories/<story_id>")
def story_detail(story_id):
    story = next((st for st in STORIES_DATA if st["id"] == story_id), None)
    if not story:
        return "Story not found", 404
    return render_template("story_detail.html", story=story)


# -------------------------------------------------------------- verbs --

VERB_GROUPS = ["godan", "ichidan", "irregular"]
FORM_LABELS = [
    ("masu", "ます形 (polite)"),
    ("masu_neg", "ません (polite negative)"),
    ("past_polite", "ました (polite past)"),
    ("te", "て形 (te-form)"),
    ("past", "た形 (plain past)"),
    ("nai", "ない形 (plain negative)"),
    ("potential", "可能形 (potential)"),
    ("volitional", "意向形 (volitional)"),
]


@app.route("/verbs")
def verbs_list():
    grouped = [(g, [v for v in VERBS_DATA if v["group"] == g]) for g in VERB_GROUPS]
    return render_template("verbs.html", grouped=grouped, total=len(VERBS_DATA),
                           form_labels=FORM_LABELS)


@app.route("/api/verb/<int:idx>")
def verb_detail(idx):
    if idx < 0 or idx >= len(VERBS_DATA):
        return jsonify({"error": "not found"}), 404
    v = dict(VERBS_DATA[idx])
    v["form_labels"] = FORM_LABELS
    return jsonify(v)


# --------------------------------------------------------- flashcards --

@app.route("/flashcards")
def flashcards():
    return render_template("flashcards.html")


@app.route("/api/flashcards")
def api_flashcards():
    """Build a flashcard deck. deck = hiragana | katakana | kanji | vocab | verbs"""
    deck = (request.args.get("deck") or "kanji").lower()
    level = (request.args.get("difficulty") or "mixed").lower()
    try:
        count = int(request.args.get("count", 20))
    except ValueError:
        count = 20
    count = max(5, min(count, 100))

    cards = []
    if deck == "hiragana":
        cards = [{"front": k["char"], "back": k["romaji"], "sub": k["type"]}
                 for k in HIRAGANA_DATA]
    elif deck == "katakana":
        cards = [{"front": k["char"], "back": k["romaji"], "sub": k["type"]}
                 for k in KATAKANA_DATA]
    elif deck == "vocab":
        pool = ALL_WORDS if level == "mixed" else [w for w in ALL_WORDS if w["difficulty"] == level]
        cards = [{"front": w["word"], "back": w["meaning"],
                  "sub": w["reading"] or w["romaji"]} for w in pool]
    elif deck == "verbs":
        pool = VERBS_DATA if level == "mixed" else [v for v in VERBS_DATA if v["difficulty"] == level]
        cards = [{"front": v["word"], "back": v["meaning"],
                  "sub": v["reading"] + " · " + v["forms"]["masu"]["kanji"]} for v in pool]
    else:  # kanji
        pool = PRACTICE_POOL if level == "mixed" else [w for w in PRACTICE_POOL if w["difficulty"] == level]
        cards = [{"front": w["kanji"], "back": w["meaning"],
                  "sub": (w["kun_yomi"] or w["on_yomi"] or "")[:40]} for w in pool]

    random.shuffle(cards)
    return jsonify({"deck": deck, "cards": cards[:count]})


# ----------------------------------------------------------------- progress --
# Tracks which flashcards a person has marked "Knew it" for, per deck, so
# the dashboard can show a real completion meter instead of just the
# streak. Same guest-file / per-user-file split as the streak: a signed-in
# person's progress is saved to their account, a guest's is saved to this
# device only.

PROGRESS_DECKS = {
    "kanji": ("Kanji", lambda: len(PRACTICE_POOL)),
    "vocab": ("Vocabulary", lambda: len(ALL_WORDS)),
    "verbs": ("Verbs", lambda: len(VERBS_DATA)),
    "hiragana": ("Hiragana", lambda: len(HIRAGANA_DATA)),
    "katakana": ("Katakana", lambda: len(KATAKANA_DATA)),
    "jlpt": ("JLPT (N5–N1)", lambda: len(JLPT_KANJI)),
}

PROGRESS_FILE = DATA_DIR / "progress.json"
USER_PROGRESS_FILE = DATA_DIR / "user_progress.json"


def _load_all_user_progress():
    if not USER_PROGRESS_FILE.exists():
        return {}
    try:
        with open(USER_PROGRESS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _load_progress(user=None):
    """Returns {deck: set(known fronts)}."""
    if user is None:
        if not PROGRESS_FILE.exists():
            return {}
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    else:
        raw = _load_all_user_progress().get(str(user["id"]), {})
    return {deck: set(items) for deck, items in raw.items() if deck in PROGRESS_DECKS}


def _save_progress(progress, user=None):
    serialisable = {deck: sorted(items) for deck, items in progress.items()}
    if user is None:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(serialisable, f, ensure_ascii=False, indent=2)
        return
    all_progress = _load_all_user_progress()
    all_progress[str(user["id"])] = serialisable
    with open(USER_PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_progress, f, ensure_ascii=False, indent=2)


def _progress_summary(user=None):
    progress = _load_progress(user)
    decks = []
    total_known = total_all = 0
    for key, (label, count_fn) in PROGRESS_DECKS.items():
        known = len(progress.get(key, set()))
        total = count_fn()
        known = min(known, total)
        pct = round(100 * known / total) if total else 0
        decks.append({"deck": key, "label": label, "known": known, "total": total, "pct": pct})
        total_known += known
        total_all += total
    overall_pct = round(100 * total_known / total_all) if total_all else 0
    return {
        "decks": decks,
        "known": total_known,
        "total": total_all,
        "pct": overall_pct,
        "logged_in": user is not None,
    }


@app.route("/api/progress")
def api_progress_get():
    return jsonify(_progress_summary(current_user()))


@app.route("/api/progress/mark", methods=["POST"])
def api_progress_mark():
    payload = request.get_json(silent=True) or {}
    deck = (payload.get("deck") or "").lower()
    front = payload.get("front")
    if deck not in PROGRESS_DECKS or not front:
        return jsonify({"error": "invalid deck or front"}), 400
    user = current_user()
    progress = _load_progress(user)
    progress.setdefault(deck, set()).add(str(front))
    _save_progress(progress, user)
    return jsonify(_progress_summary(user))


# -------------------------------------------------- writing practice --

@app.route("/write")
@app.route("/writing-practice")
def write_page():
    """The section is called "Writing Practice" in the UI. /write stays
    registered so older bookmarks and any cached service-worker entry
    from a previous version still resolve."""
    return render_template(
        "write.html",
        hiragana=HIRAGANA_DATA,
        katakana=KATAKANA_DATA,
    )


# ------------------------------------------------- about & feedback --

DEVELOPER = {
    "name": "Aryan Raj",
    "role": "Software Engineer",
    "email": "Aryanrajr868@gmail.com",
}

FEEDBACK_FILE = DATA_DIR / "feedback.json"
MAX_FEEDBACK_ENTRIES = 200
MAX_FEEDBACK_CHARS = 4000


@app.route("/about")
def about_page():
    return render_template("about.html", developer=DEVELOPER,
                            jlpt_total=len(JLPT_KANJI), verb_total=len(VERBS_DATA))


@app.route("/feedback")
def feedback_page():
    return render_template("feedback.html", feedback_email=DEVELOPER["email"])


def _load_feedback():
    if not FEEDBACK_FILE.exists():
        return []
    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        return entries if isinstance(entries, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_feedback(entries):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=1)


@app.route("/api/feedback", methods=["GET", "POST", "DELETE"])
def api_feedback():
    """Feedback notes, stored in a flat JSON file beside the app's data.

    This is deliberately local-only: the packaged app has no server to
    talk to, so a note is kept on the device and the person decides
    whether to mail it on from the Feedback page.
    """
    if request.method == "GET":
        return jsonify({"entries": _load_feedback()})

    if request.method == "DELETE":
        try:
            _save_feedback([])
        except OSError:
            return jsonify({"ok": False, "error": "could not write feedback file"}), 500
        return jsonify({"ok": True, "entries": []})

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"ok": False, "error": "message is required"}), 400

    try:
        rating = int(payload.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0

    entry = {
        "topic": str(payload.get("topic", "Other"))[:60],
        "rating": rating if 1 <= rating <= 5 else 0,
        "message": message[:MAX_FEEDBACK_CHARS],
        "name": str(payload.get("name", "")).strip()[:120],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    entries = _load_feedback()
    entries.append(entry)
    # keep the file bounded - this is a scratchpad, not an archive
    entries = entries[-MAX_FEEDBACK_ENTRIES:]

    try:
        _save_feedback(entries)
    except OSError:
        return jsonify({"ok": False, "error": "could not write feedback file"}), 500

    return jsonify({"ok": True, "entries": entries})


@app.route("/sw.js")
def service_worker():
    # Served from the root (not /static/sw.js) so its default scope is
    # "/" and it can control every page, not just /static/.
    resp = send_from_directory(app.static_folder, "sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/streak")
@app.route("/dashboard")
def streak_page():
    return render_template("streak.html", progress=_progress_summary(current_user()))


@app.route("/api/kanji_pool")
def api_kanji_pool():
    """Lightweight list for the kanji-tracing picker."""
    return jsonify([
        {"id": e["id"], "kanji": e["kanji"], "meaning": e["meaning"], "strokes": e["strokes"]}
        for e in KANJI_DATA
    ])


@app.route("/practice")
def practice_start():
    return render_template("practice.html")


def pool_for_difficulty(level):
    if level == "mixed" or not level:
        return list(PRACTICE_POOL)
    return [w for w in PRACTICE_POOL if w["difficulty"] == level]


@app.route("/api/practice/new_session", methods=["POST"])
def new_practice_session():
    """Pick N words for a new practice round, filtered by difficulty.
    Prefer words that have a curated sentence so quizzes are richest,
    then fill with other words from the same difficulty pool."""
    payload = request.get_json(silent=True) or {}
    level = payload.get("difficulty", "mixed")
    count = int(payload.get("count", 10))
    count = max(5, min(count, 40))

    base_pool = pool_for_difficulty(level)
    if not base_pool:
        base_pool = list(PRACTICE_POOL)

    curated_ids = set(SENTENCE_BY_KANJI_ID.keys())
    curated_words = [w for w in base_pool if w["kanji_id"] in curated_ids]
    random.shuffle(curated_words)
    pool = curated_words[:count]

    if len(pool) < count:
        remaining = [w for w in base_pool if w not in pool]
        random.shuffle(remaining)
        pool += remaining[: count - len(pool)]

    session["practice_words"] = [w["kanji_id"] for w in pool]
    session["practice_score"] = 0
    session["practice_difficulty"] = level

    return jsonify({
        "words": pool,
        "total": len(pool),
        "difficulty": level,
    })


@app.route("/api/practice/quiz/<int:kanji_id>")
def practice_quiz(kanji_id):
    """Return one clearly-worded multiple-choice question about this kanji.

    Every question type is built straight from the dataset, so the
    question and its answer are always consistent:
      - meaning:  What does X mean?
      - kanji:    Which kanji means "Y"?
      - reading:  How is X read?
      - sentence: fill the blank (only for words with a curated
                  sentence, so the sentence always reads naturally)
    """
    word_entry = PRACTICE_BY_ID.get(kanji_id)
    if not word_entry:
        return jsonify({"error": "not found"}), 404

    requested = (request.args.get("mode") or "mixed").lower()
    sentence = SENTENCE_BY_KANJI_ID.get(kanji_id)

    if requested == "kanji":
        qtype = random.choice(["meaning", "kanji", "reading"])
    elif requested == "sentence" and sentence:
        qtype = "sentence"
    else:
        choices = ["meaning", "kanji", "reading"]
        if sentence:
            choices.append("sentence")
        qtype = random.choice(choices)

    # reading questions need a kana reading to test
    if qtype == "reading" and not first_reading(word_entry):
        qtype = "meaning"

    pool = [w for w in PRACTICE_POOL if w["kanji_id"] != kanji_id]
    same_tier = [w for w in pool if w["difficulty"] == word_entry["difficulty"]]
    random.shuffle(same_tier)
    random.shuffle(pool)
    ordered = same_tier + [w for w in pool if w not in same_tier]

    if qtype == "meaning":
        question = f"What does {word_entry['kanji']} mean?"
        hint = "Pick the English meaning."
        correct = word_entry["meaning"]
        distractors = unique_take([w["meaning"] for w in ordered], correct, 5)
        prompt_big = word_entry["kanji"]

    elif qtype == "kanji":
        question = f"Which kanji means \u201c{word_entry['meaning']}\u201d?"
        hint = "Pick the matching character."
        correct = word_entry["kanji"]
        distractors = unique_take([w["kanji"] for w in ordered], correct, 5)
        prompt_big = ""

    elif qtype == "reading":
        question = f"How is {word_entry['kanji']} read?"
        hint = "Pick the correct kana reading."
        correct = first_reading(word_entry)
        cands = [first_reading(w) for w in ordered]
        distractors = unique_take([c for c in cands if c], correct, 5)
        prompt_big = word_entry["kanji"]

    else:  # sentence
        target = sentence["word"]
        question = "Which word completes this sentence?"
        hint = sentence["sentence_en"]
        correct = target
        distractors = unique_take([w["word"] for w in ordered], correct, 5)
        prompt_big = sentence["sentence_kanji"].replace(target, "＿＿＿", 1)

    options = distractors + [correct]
    random.shuffle(options)

    return jsonify({
        "kanji_id": kanji_id,
        "type": qtype,
        "question": question,
        "hint": hint,
        "prompt_big": prompt_big,
        "options": options,
        "correct_word": correct,
        "difficulty": word_entry["difficulty"],
    })


@app.route("/api/practice/check", methods=["POST"])
def practice_check():
    """Check the answer and ALWAYS return the full explanation for the
    correct word — whether the person got it right or made a mistake."""
    payload = request.get_json(force=True)
    kanji_id = payload.get("kanji_id")
    answer = payload.get("answer", "")
    correct_word = payload.get("correct_word", "")

    is_correct = answer.strip() == correct_word.strip()
    result = {"correct": is_correct, "your_answer": answer}

    word_entry = PRACTICE_BY_ID.get(kanji_id)
    if word_entry:
        result["explanation"] = build_explanation(word_entry)

    if is_correct:
        session["practice_score"] = session.get("practice_score", 0) + 1

    return jsonify(result)


@app.route("/api/practice/score")
def practice_score():
    return jsonify({
        "score": session.get("practice_score", 0),
        "total": len(session.get("practice_words", [])),
    })


if __name__ == "__main__":
    # Debug mode enables Werkzeug's interactive debugger, which can run
    # arbitrary code from an error page - fine for local development,
    # not something to ship on by default now that real accounts exist.
    # Opt in explicitly with: FLASK_DEBUG=1 python app.py
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
