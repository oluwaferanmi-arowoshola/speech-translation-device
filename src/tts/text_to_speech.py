import os
import time
from time import perf_counter

from gtts import gTTS
from gtts.tts import gTTSError

from src.translation.translator import TTS_CODE_ALIASES, TTS_LANGS

_last_tts_file = "output.mp3"


def synthesize_tts(text: str, lang: str):
    if not text:
        return None

    t0 = perf_counter()
    tts_lang = TTS_CODE_ALIASES.get(lang, lang)

    if tts_lang not in TTS_LANGS:
        tts_lang = "en"

    for attempt in range(3):
        try:
            tts = gTTS(text=text, lang=tts_lang)
            tts.save(_last_tts_file)
            print(f"[TIMING] TTS={perf_counter() - t0:.3f}s")
            return _last_tts_file
        except gTTSError as e:
            print(f"[TTS WARNING] attempt {attempt + 1} failed: {e}")
            time.sleep(1)

    print("[TTS ERROR] failed after retries")
    return None


def replay_last_tts():
    if os.path.exists(_last_tts_file):
        os.system(f"mpg123 -q {_last_tts_file} 2>/dev/null")


def stop_playback():
    os.system("pkill mpg123")