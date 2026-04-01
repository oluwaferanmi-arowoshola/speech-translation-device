import time
from time import perf_counter
import threading
import tkinter as tk
from tkinter import ttk

from Tcore import (
    SOURCE_LANGS,
    TARGET_LANGS,
    play_beep,
    start_recording,
    stop_recording,
    recognize_and_translate,
    synthesize_tts,
    replay_last_tts,
    stop_playback,
    MAX_RECORD_SECONDS,
)

class AppState:
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    READY = "ready"
    PLAYING = "playing"
    ERROR = "error"

class TranslatorGUI:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Speech Translator")
        # Fullscreen for 800x480 touch display
        self.root.attributes("-fullscreen", True)
        self.is_fullscreen = True

        # ───────── State ─────────
        self.state = AppState.IDLE

        # ───────── Variables ──────────────────────────
        self.status_var = tk.StringVar(value="[ READY ]")
        self.source_lang_var = tk.StringVar()
        self.target_lang_var = tk.StringVar()
        self.original_text_var = tk.StringVar(value="")
        self.translated_text_var = tk.StringVar(value="")

        # Build language labels (Name (code))
        self.source_labels = self._build_source_labels()
        self.target_labels = self._build_target_labels()
        self.source_lang_var.set(self.source_labels["en"])

        # Default target: Spanish if available, else English
        default_target_code = "es" if "es" in TARGET_LANGS else "en"
        self.target_lang_var.set(self.target_labels[default_target_code])

        # Build layout
        self._build_layout()

        # Initialize UI for IDLE
        self._set_state(AppState.IDLE)
        self._update_swap_button_state()

    # ─────────── Layout / UI ───────────
    def _build_source_labels(self):

        return {
            code: f"{name} ({code})"

            for code, name in sorted(
                SOURCE_LANGS.items(),
                key=lambda item: item[1].lower()
            )
        }

    def _build_target_labels(self):

        return {
            code: f"{name} ({code})"

            for code, name in sorted(
                TARGET_LANGS.items(),
                key=lambda item: item[1].lower()
            )
        }

    def _source_code_to_label(self, code):
        return self.source_labels.get(code, code)

    def _target_code_to_label(self, code):
        return self.target_labels.get(code, code)

    def _label_to_code(self, label: str) -> str:

        if "(" in label and label.endswith(")"):
            return label.split("(")[-1].rstrip(")")
        return label.strip().lower()
        
    def _is_swap_available(self):
        src_code = self._label_to_code(self.source_lang_var.get())
        tgt_code = self._label_to_code(self.target_lang_var.get())
        missing = []

        # Source must support BOTH STT and TTS
        if src_code not in SOURCE_LANGS:
            missing.append("Source STT")

        if src_code not in TARGET_LANGS:
            missing.append("Source TTS")

        # Target must support BOTH STT and TTS
        if tgt_code not in SOURCE_LANGS:
            missing.append("Target STT")

        if tgt_code not in TARGET_LANGS:
            missing.append("Target TTS")

        return (len(missing) == 0), missing

    def _flash_status(self, message, duration_ms=1200):
        original = self.status_var.get()
        self.status_var.set(message)

        def restore():

            # Don’t overwrite newer status messages
            if self.status_var.get() == message:
                self.status_var.set(original)

        self.root.after(duration_ms, restore)

    def _update_swap_button_state(self):
        allowed, _missing = self._is_swap_available()

        if allowed:

            self.swap_btn.config(
                state="normal",
                bg="#444444",
                fg="white",
            )

        else:

            self.swap_btn.config(
                state="disabled",
                bg="#222222",
                fg="#888888",
            )
        
    def open_lang_picker(self, is_source: bool):
        """Fullscreen language picker with smooth scroll + large scrollbar."""

        win = tk.Toplevel(self.root)
        win.configure(bg="#222222")

        # Fullscreen, hide borders, keep on top
        win.overrideredirect(True)
        win.attributes("-fullscreen", True)
        win.lift()
        win.attributes("-topmost", True)

        # ───────────────── MAIN LAYOUT ──────────────────────────────
        # Use a frame so we can place close button + title cleanly
        outer = tk.Frame(win, bg="#222222")
        outer.pack(fill="both", expand=True)

        # Header row (title + close)
        header = tk.Frame(outer, bg="#111111")
        header.pack(fill="x")

        title = tk.Label(
            header,
            text="Select Source Language" if is_source else "Select Target Language",
            fg="white",
            bg="#111111",
            font=("DejaVu Sans", 22, "bold"),
            pady=12
        )
        title.pack(side="left", padx=20)

        close_btn = tk.Button(
            header,
            text="✕",
            font=("DejaVu Sans", 20, "bold"),
            fg="white",
            bg="#aa3333",
            activebackground="#dd5555",
            bd=0,
            command=win.destroy,
            padx=10,
            pady=5
        )
        close_btn.pack(side="right", padx=20)

        # ───────────── SCROLLABLE AREA ─────────────
        scroll_frame = tk.Frame(outer, bg="#222222")
        scroll_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll_frame, bg="#222222", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        # LARGE TOUCH-FRIENDLY SCROLLBAR
        scrollbar = tk.Scrollbar(
            scroll_frame,
            orient="vertical",
            command=canvas.yview,
            width=40  # bigger scrollbar for fingers
        )
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Inner frame inside canvas
        inner = tk.Frame(canvas, bg="#222222")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        # ─────── SMOOTH TOUCH SCROLL ───────
        def _start_scroll(event):
            canvas._drag_start_y = event.y

        def _drag_scroll(event):

            if not hasattr(canvas, "_drag_start_y"):
                canvas._drag_start_y = event.y
            dy = event.y - canvas._drag_start_y
            canvas.yview_scroll(int(-dy / 25), "units")  # smoother & slower
            canvas._drag_start_y = event.y

        canvas.bind("<ButtonPress-1>", _start_scroll)
        canvas.bind("<B1-Motion>", _drag_scroll)

        # ───────────────── UPDATE SCROLL REGION ─────────────────
        def _update_scroll(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _update_scroll)

        # ───────────────── ADD LANGUAGE BUTTONS ───────────────────────────
        lang_map = self.source_labels if is_source else self.target_labels

        for code, label in lang_map.items():

            btn = tk.Button(
                inner,
                text=label,
                fg="white",
                bg="#444444",
                activebackground="#666666",
                font=("DejaVu Sans", 18),
                height=2,
                bd=0,
                command=lambda c=code: self._set_language_and_close(win, c, is_source),
            )
            btn.pack(fill="x", padx=20, pady=6)
        
    def _set_language_and_close(self, win, code, is_source):

        label = (
            self._source_code_to_label(code)
            if is_source
            else self._target_code_to_label(code)
        )

        if is_source:
            self.source_lang_var.set(label)

        else:
            self.target_lang_var.set(label)
            
        self._update_swap_button_state()
        win.destroy()
        
    def _create_scrollable_text(self, parent, text_variable, fg, bg):
        """Improved scrollable text area with large scrollbar + smooth touch scrolling."""

        # Outer container (grid target)
        container = tk.Frame(parent, bg=bg)
        container.grid_propagate(False)   # keep parent controlling size

        # Scrollable canvas
        canvas = tk.Canvas(container, bg=bg, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        # Large, touch-friendly scrollbar
        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview,
            width=40      # <-- big thumb, easy to drag
        )
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Inner frame inside the canvas
        inner = tk.Frame(canvas, bg=bg)
        canvas.create_window((0, 0), window=inner, anchor="nw")

        # Touch scrolling (smooth)
        def _start(event):
            canvas._drag_start_y = event.y

        def _drag(event):

            if not hasattr(canvas, "_drag_start_y"):
                canvas._drag_start_y = event.y
            dy = event.y - canvas._drag_start_y
            canvas.yview_scroll(int(-dy / 25), "units")  # slower, smoother
            canvas._drag_start_y = event.y

        canvas.bind("<ButtonPress-1>", _start)
        canvas.bind("<B1-Motion>", _drag)

        # Auto-update scrollable region
        def _update(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _update)

        # The actual text
        lbl = tk.Label(
            inner,
            textvariable=text_variable,
            fg=fg,
            bg=bg,
            font=("DejaVu Sans", 13),
            anchor="nw",
            justify="left",
            wraplength=760,
        )
        lbl.pack(fill="both", expand=True)

        return container

    def _build_layout(self):
        root = self.root
        root.rowconfigure(0, weight=0, minsize=50)   # header
        root.rowconfigure(1, weight=2, minsize=110)  # Zone 2 - Languages (taller)
        root.rowconfigure(2, weight=1, minsize=80)   # Zone 3 - Buttons (shorter)
        root.rowconfigure(3, weight=3, minsize=180)  # Zone 4 - Text output
        root.columnconfigure(0, weight=1)

        # ───────── Zone 1: Header ─────────
        header = tk.Frame(root, bg="#222222")
        header.grid(row=0, column=0, sticky="nsew")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=0)
        header.columnconfigure(2, weight=0)
        header.columnconfigure(3, weight=0)

        title_lbl = tk.Label(
            header,
            text="Speech Translator",
            fg="white",
            bg="#222222",
            font=("DejaVu Sans", 18, "bold"),
            anchor="w",
            padx=12,
        )
        title_lbl.grid(row=0, column=0, sticky="w")

        status_lbl = tk.Label(
            header,
            textvariable=self.status_var,
            fg="#00ff88",
            bg="#222222",
            font=("DejaVu Sans", 14),
            anchor="center",
            padx=8,
        )
        status_lbl.grid(row=0, column=1, padx=8)

        self.fullscreen_btn = tk.Button(
            header,
            text=" - ",
            fg="white",
            bg="#444444",
            activebackground="#666666",
            font=("DejaVu Sans", 14, "bold"),
            command=self.toggle_fullscreen,
            bd=0,
            padx=12,
            pady=4,
        )
        self.fullscreen_btn.grid(row=0, column=2, sticky="e", padx=8, pady=4)

        close_btn = tk.Button(
            header,
            text="X",
            fg="white",
            bg="#aa3333",
            activebackground="#ff5555",
            font=("DejaVu Sans", 14, "bold"),
            command=self.root.destroy,
            bd=0,
            padx=12,
            pady=4,
        )
        close_btn.grid(row=0, column=3, sticky="e", padx=8, pady=4)

        # ───────── Zone 2: Language Controls ─────────
        lang_frame = tk.Frame(root, bg="#333333")
        lang_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))

        for c in range(5):
            lang_frame.columnconfigure(c, weight=1)

        # Source
        src_label = tk.Label(
            lang_frame,
            text="From:",
            fg="white",
            bg="#333333",
            font=("DejaVu Sans", 14),
            anchor="w",
        )
        src_label.grid(row=0, column=0, sticky="w", padx=4, pady=(6, 2))

        src_btn = tk.Button(
            lang_frame,
            textvariable=self.source_lang_var,
            fg="white",
            bg="#444444",
            activebackground="#666666",
            font=("DejaVu Sans", 16),
            bd=0,
            height=2,
            command=lambda: self.open_lang_picker(True),
        )
        src_btn.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 8))

        # Swap button
        self.swap_btn = tk.Button(
            lang_frame,
            text="⇄",
            font=("DejaVu Sans", 18, "bold"),
            bg="#444444",
            fg="white",
            activebackground="#666666",
            bd=0,
            command=self.swap_languages,
        )
        self.swap_btn.grid(row=1, column=2, sticky="ew", padx=4, pady=(0, 8))


        # Target
        tgt_label = tk.Label(
            lang_frame,
            text="To:",
            fg="white",
            bg="#333333",
            font=("DejaVu Sans", 14),
            anchor="w",
        )
        tgt_label.grid(row=0, column=3, sticky="w", padx=4, pady=(6, 2))

        tgt_btn = tk.Button(
            lang_frame,
            textvariable=self.target_lang_var,
            fg="white",
            bg="#444444",
            activebackground="#666666",
            font=("DejaVu Sans", 16),
            bd=0,
            height=2,
            command=lambda: self.open_lang_picker(False),
        )
        tgt_btn.grid(row=1, column=3, columnspan=2, sticky="ew", padx=4, pady=(0, 8))

        # ───────── Zone 3: Buttons ─────────
        btn_frame = tk.Frame(root, bg="#111111")
        btn_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 4))

        for c in range(4):
            btn_frame.columnconfigure(c, weight=1)

        btn_font = ("DejaVu Sans", 16, "bold")

        self.record_btn = tk.Button(
            btn_frame,
            text="Record",
            font=btn_font,
            bg="#0066cc",
            fg="white",
            activebackground="#3388ff",
            bd=0,
            command=self.on_record,
            height=2,
        )
        self.record_btn.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        self.translate_btn = tk.Button(
            btn_frame,
            text="Translate",
            font=btn_font,
            bg="#555555",
            fg="white",
            activebackground="#777777",
            bd=0,
            command=self.on_translate,
            height=2,
            state="disabled",
        )
        self.translate_btn.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)

        self.stop_btn = tk.Button(
            btn_frame,
            text="Stop",
            font=btn_font,
            bg="#aa3333",
            fg="white",
            activebackground="#dd4444",
            bd=0,
            command=self.on_stop,
            height=2,
            state="disabled",
        )
        self.stop_btn.grid(row=0, column=2, sticky="nsew", padx=4, pady=4)

        self.replay_btn = tk.Button(
            btn_frame,
            text="Replay",
            font=btn_font,
            bg="#444444",
            fg="white",
            activebackground="#666666",
            bd=0,
            command=self.on_replay,
            height=2,
            state="disabled",
        )
        self.replay_btn.grid(row=0, column=3, sticky="nsew", padx=4, pady=4)

        # ───────── Zone 4: Text output ─────────
        text_frame = tk.Frame(root, bg="#000000")
        text_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))

        text_frame.rowconfigure(0, weight=0)   # "You said:"
        text_frame.rowconfigure(1, weight=1)   # scroll area
        text_frame.rowconfigure(3, weight=0)   # "Translated:"
        text_frame.rowconfigure(4, weight=1)   # scroll area
        text_frame.columnconfigure(0, weight=1)


        you_said_lbl = tk.Label(
            text_frame,
            text="You said:",
            fg="#dddddd",
            bg="#000000",
            font=("DejaVu Sans", 14, "bold"),
            anchor="w",
        )
        you_said_lbl.grid(row=0, column=0, sticky="w", pady=(4, 0))
        
        translated_title_lbl = tk.Label(
            text_frame,
            text="Translated:",
            fg="#dddddd",
            bg="#000000",
            font=("DejaVu Sans", 14, "bold"),
            anchor="w",
        )
        translated_title_lbl.grid(row=3, column=0, sticky="w", pady=(8, 0))

        # Scrollable "You said"
        self.original_scroll = self._create_scrollable_text(
            text_frame,
            self.original_text_var,
            fg="#ffffff",
            bg="#000000"
        )
        self.original_scroll.grid(row=1, column=0, sticky="nsew")

        # Scrollable "Translated"
        self.translated_scroll = self._create_scrollable_text(
            text_frame,
            self.translated_text_var,
            fg="#00ff88",
            bg="#000000"
        )
        self.translated_scroll.grid(row=4, column=0, sticky="nsew")

    # ───────────────── State transitions ─────────────────
    def _set_state(self, new_state, message=None):
        self.state = new_state

        # Reset all buttons first
        self.record_btn.config(state="disabled", bg="#444444")
        self.translate_btn.config(state="disabled", bg="#555555")
        self.stop_btn.config(state="disabled", bg="#aa3333")
        self.replay_btn.config(state="disabled", bg="#444444")

        if new_state == AppState.IDLE:
            self.status_var.set(message or "[ READY ]")
            self.record_btn.config(state="normal", bg="#0066cc")

        elif new_state == AppState.RECORDING:
            self.status_var.set(message or "[ RECORDING ]")
            self.original_text_var.set("")
            self.translated_text_var.set("")
            self.translate_btn.config(state="normal", bg="#009966")
            self.stop_btn.config(state="normal")

        elif new_state == AppState.PROCESSING:
            self.status_var.set(message or "[ TRANSLATING… ]")
            self.stop_btn.config(state="normal")

        elif new_state == AppState.READY:
            self.status_var.set(message or "[ DONE ]")
            self.record_btn.config(state="normal", bg="#0066cc")
            self.replay_btn.config(state="normal", bg="#009966")

        elif new_state == AppState.PLAYING:
            self.status_var.set(message or "[ REPLAYING ]")
            self.stop_btn.config(state="normal")

        elif new_state == AppState.ERROR:
            self.status_var.set(message or "[ ERROR ]")
            self.record_btn.config(state="normal", bg="#0066cc")

    # ───────────────── Button Handlers ─────────────────
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        
        # Update icon
        if self.is_fullscreen:
            self.fullscreen_btn.config(text=" - ")
        else:
            self.fullscreen_btn.config(text=" + ")

    def swap_languages(self):

        if self.state not in (AppState.IDLE, AppState.READY):
            return

        allowed, missing = self._is_swap_available()

        if not allowed:
            reason = ", ".join(missing)
            self._flash_status(f"[ SWAP UNAVAILABLE: {reason} ]")
            self._update_swap_button_state()
            return

        src_code = self._label_to_code(self.source_lang_var.get())
        tgt_code = self._label_to_code(self.target_lang_var.get())
        self.source_lang_var.set(self._source_code_to_label(tgt_code))
        self.target_lang_var.set(self._target_code_to_label(src_code))
        self._update_swap_button_state()
        self._set_state(AppState.IDLE)

    def on_record(self):

        if self.state not in (AppState.IDLE, AppState.READY, AppState.ERROR):
            return

        if not start_recording():
            self._set_state(AppState.ERROR, "[ ERROR STARTING RECORDING ]")
            return

        self._set_state(AppState.RECORDING)

    def on_translate(self):

        if self.state != AppState.RECORDING:
            return

        self.e2e_start = perf_counter()
        self._set_state(AppState.PROCESSING)
        threading.Thread(target=self._do_translate_worker, daemon=True).start()

    def on_stop(self):
        stop_recording(wait=False)
        stop_playback()

        if self.state == AppState.PLAYING:
            self._set_state(AppState.READY, "[ STOPPED ]")

        elif self.state in (AppState.RECORDING, AppState.PROCESSING):
            self._set_state(AppState.IDLE, "[ STOPPED ]")

    def on_replay(self):

        if self.state != AppState.READY:
            return

        self._set_state(AppState.PLAYING)
        threading.Thread(target=self._do_replay_worker, daemon=True).start()

    # ───────────────── Worker Threads ─────────────────
    def _do_translate_worker(self):
        audio_bytes = stop_recording(wait=True)
        stop_playback()

        # Guard 1: user may have stopped/cancelled already
        if self.state != AppState.PROCESSING:
            return

        if not audio_bytes:
            self.root.after(0, lambda: self._set_state(AppState.IDLE, "[ NO AUDIO RECORDED ]"))
            return

        src_code = self._label_to_code(self.source_lang_var.get())
        tgt_code = self._label_to_code(self.target_lang_var.get())
        tts_failed = False

        try:
            original, translated = recognize_and_translate(audio_bytes, src_code, tgt_code)

        except Exception as e:
            print("[TRANSLATE WORKER ERROR]", e)
            self.root.after(0, lambda: self._set_state(AppState.IDLE, "[ COULD NOT UNDERSTAND SPEECH ]"))
            return

        if not original:
            self.root.after(0, lambda: self._set_state(AppState.IDLE, "[ COULD NOT UNDERSTAND SPEECH ]"))
            return

        # Guard 2: state may have changed while recognition/translation was running
        if self.state != AppState.PROCESSING:
            return

        if translated:

            try:
                time.sleep(0.5)
                tts_path = synthesize_tts(translated, tgt_code)

                if not tts_path:
                    tts_failed = True

            except Exception as e:
                print("[TTS WORKER ERROR]", e)
                tts_failed = True

        # Guard 3: state may have changed while TTS was running
        if self.state != AppState.PROCESSING:
            return

        self.root.after(
            0,
            self._update_after_translation,
            original,
            translated,
            tts_failed,
        )

    def _do_replay_worker(self):
        replay_last_tts()
        self.root.after(0, self._after_replay_cleanup)
    
    def _after_replay_cleanup(self):

        if self.state == AppState.PLAYING:
            self._set_state(AppState.READY, "[ READY ]")

    # ───────────────── UI Updates from Workers ─────────────────
    def _handle_no_audio_recorded(self):
        self._set_state(AppState.IDLE, "[ NO AUDIO RECORDED ]")

    def _handle_recognition_failed(self):
        self.original_text_var.set("")
        self.translated_text_var.set("")
        self._set_state(AppState.IDLE, "[ COULD NOT UNDERSTAND SPEECH ]")

    def _update_after_translation(self, original: str, translated: str, tts_failed: bool = False):

        if self.state != AppState.PROCESSING:
            return

        e2e = perf_counter() - getattr(self, "e2e_start", perf_counter())
        print(f"[TIMING] PROCESSING_DONE={e2e:.3f}s")
        self.original_text_var.set(original or "")

        if translated:
            self.translated_text_var.set(translated)

            if tts_failed:
                self._set_state(AppState.READY, "[ TTS TEMPORARILY UNAVAILABLE ]")
                self.replay_btn.config(state="disabled", bg="#444444")

            else:
                self._set_state(AppState.READY)

                def _play_and_log():
                    e2e = perf_counter() - getattr(self, "e2e_start", perf_counter())
                    print(f"[TIMING] E2E={e2e:.3f}s")
                    replay_last_tts()

                threading.Thread(target=_play_and_log, daemon=True).start()

        else:
            self.translated_text_var.set("[ Translation failed ]")
            self._set_state(AppState.IDLE, "[ RECOGNIZED, BUT TRANSLATION FAILED ]")

def main():
    root = tk.Tk()
    app = TranslatorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()