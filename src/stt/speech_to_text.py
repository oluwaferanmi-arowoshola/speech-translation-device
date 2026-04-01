from time import perf_counter
import speech_recognition as sr

from src.audio.recorder import AUDIO_RATE
from src.translation.translator import translate_with_pivots


def recognize_and_translate(audio_bytes: bytes, source_lang: str, target_lang: str):
    if not audio_bytes:
        return None, None

    recognizer = sr.Recognizer()
    t0 = perf_counter()
    audio_data = sr.AudioData(audio_bytes, AUDIO_RATE, 2)

    t_stt0 = perf_counter()
    try:
        original = recognizer.recognize_google(audio_data, language=source_lang)
        detected_lang = source_lang
    except (sr.UnknownValueError, sr.RequestError, ConnectionResetError, OSError) as e:
        print("[STT ERROR]", e)
        return None, None

    t_stt1 = perf_counter()
    stt_sec = t_stt1 - t_stt0

    t_tr0 = perf_counter()
    translated = translate_with_pivots(original, detected_lang, target_lang)
    t_tr1 = perf_counter()
    tr_sec = t_tr1 - t_tr0

    total_sec = perf_counter() - t0
    print(f"[TIMING] STT={stt_sec:.3f}s  TRANS={tr_sec:.3f}s  STT+TRANS={total_sec:.3f}s")

    return original, translated