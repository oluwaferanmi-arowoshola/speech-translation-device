from googletrans import Translator, LANGUAGES
from gtts import lang as gtts_lang

PIVOT_LANGS = ["en", "fr", "es", "ar", "pt"]

GT_LANGS = set(LANGUAGES.keys())
TTS_LANGS = set(gtts_lang.tts_langs().keys())

TTS_CODE_ALIASES = {
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "pt": "pt",
    "jw": "jv",
    "he": "iw",
}

STT_LANGS = set(GT_LANGS)

SOURCE_LANGS = {
    code: LANGUAGES[code].capitalize()
    for code in GT_LANGS
}

TARGET_LANGS = {}
for code, name in LANGUAGES.items():
    tts_code = TTS_CODE_ALIASES.get(code, code)
    if tts_code in TTS_LANGS:
        TARGET_LANGS[code] = name.capitalize()

_translator = Translator()


def translate_with_pivots(text: str, src: str, tgt: str):
    if not text or src == tgt:
        return text

    try:
        result = _translator.translate(text, src=src, dest=tgt).text
        print(f"[ROUTING] {src} → {tgt} (direct)")
        return result
    except Exception:
        pass

    for pivot in PIVOT_LANGS:
        try:
            intermediate = text

            if src != pivot:
                intermediate = _translator.translate(
                    intermediate, src=src, dest=pivot
                ).text

            if tgt != pivot:
                intermediate = _translator.translate(
                    intermediate, src=pivot, dest=tgt
                ).text

            print(f"[ROUTING] {src} → {pivot} → {tgt}")
            return intermediate
        except Exception:
            continue

    return None