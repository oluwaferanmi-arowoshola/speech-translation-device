import os
import time
import threading
import pyaudio

MAX_RECORD_SECONDS = 99

AUDIO_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
FRAMES_PER_BUFFER = 1024

_recording_event = threading.Event()
_recording_lock = threading.Lock()
_recording_frames = []
_recording_thread = None
_pa_instance = None
_mic_open_lock = threading.Lock()


def get_pa():
    global _pa_instance
    if _pa_instance is None:
        _pa_instance = pyaudio.PyAudio()
    return _pa_instance


def find_input_device():
    pa = get_pa()

    preferred_keywords = [
        "usb pnp audio device",
        "usb audio",
        "usb",
        "audio",
    ]

    fallback = None

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        name = info.get("name", "").lower()
        max_in = info.get("maxInputChannels", 0)

        if max_in < 1:
            continue

        for keyword in preferred_keywords:
            if keyword in name:
                print(f"[AUDIO] Matched input device: '{info['name']}' at index {i}")
                return i

        if fallback is None:
            fallback = i

    return fallback


INPUT_DEVICE_INDEX = find_input_device()
print("Using input device index:", INPUT_DEVICE_INDEX)


def play_beep():
    if os.path.exists("beep.wav"):
        os.system("aplay -q beep.wav 2>/dev/null")


def _record_worker(max_seconds: int):
    global _recording_frames

    pa = get_pa()
    stream = None
    last_err = None

    with _mic_open_lock:
        for attempt in range(6):
            try:
                stream = pa.open(
                    format=AUDIO_FORMAT,
                    channels=AUDIO_CHANNELS,
                    rate=AUDIO_RATE,
                    input=True,
                    frames_per_buffer=FRAMES_PER_BUFFER,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(0.1 * (2 ** attempt))

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


def start_recording(max_seconds: int = MAX_RECORD_SECONDS) -> bool:
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
        daemon=True,
    )
    _recording_thread.start()
    return True


def stop_recording(wait: bool = True):
    global _recording_thread

    _recording_event.clear()

    if _recording_thread and wait:
        _recording_thread.join(timeout=1.0)

    with _recording_lock:
        if not _recording_frames:
            return None
        return b"".join(_recording_frames)