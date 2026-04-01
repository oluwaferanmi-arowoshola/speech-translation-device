import os
import time
from time import perf_counter
import threading
import pyaudio
import speech_recognition as sr
from gtts import gTTS, lang as gtts_lang
from googletrans import Translator, LANGUAGES


# ──────────────────────────────
# DEVICE SETTINGS / CONSTANTS
# ──────────────────────────────
MAX_RECORD_SECONDS = 99

AUDIO_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
FRAMES_PER_BUFFER = 1024

# recording globals
_recording_event = threading.Event()
_recording_lock = threading.Lock()
_recording_frames = []
_recording_thread = None
_pa_instance = None
_mic_open_lock = threading.Lock()


# ──────────────────────────────
# INTERNAL HELPERS  ← MUST COME FIRST
# ──────────────────────────────
def _get_pa():
    global _pa_instance

    if _pa_instance is None:
        _pa_instance = pyaudio.PyAudio()
    return _pa_instance

def _find_input_device():
    pa = _get_pa()

    preferred_keywords = [
        "usb pnp audio device",
        "usb audio",
        "usb",
        "audio"
    ]

    best_match = None
    fallback = None

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        name = info.get("name", "").lower()
        max_in = info.get("maxInputChannels", 0)

        if max_in < 1:
            continue

        # Strong match rules
        for keyword in preferred_keywords:

            if keyword in name:
                print(f"[AUDIO] Matched input device: '{info['name']}' at index {i}")
                return i

        # weaker fallback (any input device)
        if fallback is None:
            fallback = i

    return fallback

INPUT_DEVICE_INDEX = _find_input_device()
print("Using input device index:", INPUT_DEVICE_INDEX)


# ──────────────────────────────
# LANGUAGE MODEL (ENGLISH PIVOT)
# ──────────────────────────────

# Ordered by priority (shortest / highest quality first)
PIVOT_LANGS = ["en", "fr", "es", "ar", "pt"]

# googletrans language set
GT_LANGS = set(LANGUAGES.keys())

# gTTS language set
TTS_LANGS = set(gtts_lang.tts_langs().keys())

# googletrans to gTTS language code normalization
TTS_CODE_ALIASES = {
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "pt": "pt",
    "jw": "jv",
    "he": "iw",
}

# Google STT accepts essentially the same set
STT_LANGS = set(GT_LANGS)

# Source languages:
# STT-capable AND translatable TO English
SOURCE_LANGS = {
    code: LANGUAGES[code].capitalize()
    for code in GT_LANGS
}

# Target languages:
# TTS-capable AND translatable FROM English
TARGET_LANGS = {}

for code, name in LANGUAGES.items():
    tts_code = TTS_CODE_ALIASES.get(code, code)

    if tts_code in TTS_LANGS:
        TARGET_LANGS[code] = name.capitalize()

_last_tts_file = "output.mp3"
_translator = Translator()

def translate_with_pivots(text: str, src: str, tgt: str):

    if not text or src == tgt:
        return text

    # 1. Try direct translation first
    try:
        result = _translator.translate(text, src=src, dest=tgt).text
        print(f"[ROUTING] {src} → {tgt} (direct)")
        return result

    except Exception:
        pass

    # 2. Try pivot-based translation (shortest path first)
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

    # 3. No path exists
    return None

def play_beep():
    """Play beep if beep.wav exists."""
    os.system("aplay -q beep.wav 2>/dev/null")

def _record_worker(max_seconds: int):
    """Worker thread that records audio into memory."""
    global _recording_frames
    pa = _get_pa()
    stream = None
    last_err = None

    with _mic_open_lock:

        for attempt in range(6):  # ~0.1 + 0.2 + 0.4 + 0.8 + 1.6 + 3.2 = ~6.3s max

            try:

                stream = pa.open(
                    format=AUDIO_FORMAT,
                    channels=AUDIO_CHANNELS,
                    rate=AUDIO_RATE,
                    input=True,
                    frames_per_buffer=FRAMES_PER_BUFFER
                )
                last_err = None
                break

            except Exception as e:
                last_err = e
                time.sleep(0.1 * (2 ** attempt))  # exponential backoff

    if stream is None:
        print("MIC ERROR:", last_err)
        _recording_event.clear()
        return

    start_time = time.time()
    try:

        while _recording_event.is_set() and (time.time() - start_time) < max_seconds:
            data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)

            with _recording_lock:
                _recording_frames.append(data)

    finally:
        stream.stop_stream()
        stream.close()
        _recording_event.clear()


# ──────────────────────────────
# PUBLIC API (USED BY GUI)
# ──────────────────────────────
def start_recording(max_seconds: int = MAX_RECORD_SECONDS) -> bool:
    """Starts audio capture."""
    global _recording_thread, _recording_frames

    if _recording_event.is_set():
        return False

    with _recording_lock:
        _recording_frames = []

    play_beep()
    _recording_event.set()

    _recording_thread = threading.Thread(
        target=_record_worker,
        args=(max_seconds,),
        daemon=True
    )
    _recording_thread.start()
    return True

def stop_recording(wait: bool = True):
    """Stops recording and returns combined audio bytes."""
    global _recording_thread
    _recording_event.clear()

    if _recording_thread and wait:
        _recording_thread.join(timeout=1.0)

    with _recording_lock:

        if not _recording_frames:
            return None
        return b"".join(_recording_frames)


def recognize_and_translate(audio_bytes: bytes, source_lang: str, target_lang: str):
    """Speech → Text → Translate"""

    if not audio_bytes:
        return None, None

    recognizer = sr.Recognizer()
    t0 = perf_counter()
    audio_data = sr.AudioData(audio_bytes, AUDIO_RATE, 2)

    # ───── STT TIMING ─────
    t_stt0 = perf_counter()
    try:
        original = recognizer.recognize_google(audio_data, language=source_lang)
        detected_lang = source_lang

    except (sr.UnknownValueError, sr.RequestError, ConnectionResetError, OSError) as e:
        print("[STT ERROR]", e)
        return None, None

    t_stt1 = perf_counter()
    stt_sec = t_stt1 - t_stt0

    # ───── TRANSLATION TIMING ─────
    t_tr0 = perf_counter()
    translated = translate_with_pivots(
        original,
        detected_lang,
        target_lang
    )
    t_tr1 = perf_counter()
    tr_sec = t_tr1 - t_tr0
    total_sec = perf_counter() - t0
    print(f"[TIMING] STT={stt_sec:.3f}s  TRANS={tr_sec:.3f}s  STT+TRANS={total_sec:.3f}s")
    return original, translated

from gtts.tts import gTTSError

def synthesize_tts(text: str, lang: str):
    """Generate TTS to output.mp3 with retry protection."""
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