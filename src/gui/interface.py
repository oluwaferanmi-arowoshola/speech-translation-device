import time
from time import perf_counter
import threading
import tkinter as tk

from src.core.pipeline import (
    SOURCE_LANGS,
    TARGET_LANGS,
    start_recording,
    stop_recording,
    recognize_and_translate,
    synthesize_tts,
    replay_last_tts,
    stop_playback,
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
        self.root.attributes("-fullscreen", True)
        self.is_fullscreen = True

        self.state = AppState.IDLE

        self.status_var = tk.StringVar(value="[ READY ]")
        self.source_lang_var = tk.StringVar()
        self.target_lang_var = tk.StringVar()
        self.original_text_var = tk.StringVar(value="")
        self.translated_text_var = tk.StringVar(value="")

        self.source_labels = self._build_source_labels()
        self.target_labels = self._build_target_labels()
        self.source_lang_var.set(self.source_labels["en"])

        default_target_code = "es" if "es" in TARGET_LANGS else "en"
        self.target_lang_var.set(self.target_labels[default_target_code])

        self._build_layout()
        self._set_state(AppState.IDLE)
        self._update_swap_button_state()

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

        if src_code not in SOURCE_LANGS:
            missing.append("Source STT")
        if src_code not in TARGET_LANGS:
            missing.append("Source TTS")
        if tgt_code not in SOURCE_LANGS:
            missing.append("Target STT")
        if tgt_code not in TARGET_LANGS:
            missing.append("Target TTS")

        return (len(missing) == 0), missing

    def _flash_status(self, message, duration_ms=1200):
        original = self.status_var.get()
        self.status_var.set(message)

        def restore():
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
        win = tk.Toplevel(self.root)
        win.configure(bg="#222222")
        win.overrideredirect(True)
        win.attributes("-fullscreen", True)
        win.lift()
        win.attributes("-topmost", True)

        outer = tk.Frame(win, bg="#222222")
        outer.pack(fill="both", expand=True)

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

        scroll_frame = tk.Frame(outer, bg="#222222")
        scroll_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_frame, bg="#222222", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            scroll_frame,
            orient="vertical",
            command=canvas.yview,
            width=40
        )
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = tk.Frame(canvas, bg="#222222")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _start_scroll(event):
            canvas._drag_start_y = event.y

        def _drag_scroll(event):
            if not hasattr(canvas, "_drag_start_y"):
                canvas._drag_start_y = event.y
            dy = event.y - canvas._drag_start_y
            canvas.yview_scroll(int(-dy / 25), "units")
            canvas._drag_start_y = event.y

        canvas.bind("<ButtonPress-1>", _start_scroll)
        canvas.bind("<B1-Motion>", _drag_scroll)

        def _update_scroll(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _update_scroll)

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
        container = tk.Frame(parent, bg=bg)
        container.grid_propagate(False)

        canvas = tk.Canvas(container, bg=bg, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview,
            width=40
        )
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = tk.Frame(canvas, bg=bg)
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _start(event):
            canvas._drag_start_y = event.y

        def _drag(event):
            if not hasattr(canvas, "_drag_start_y"):
                canvas._drag_start_y = event.y
            dy = event.y - canvas._drag_start_y
            canvas.yview_scroll(int(-dy / 25), "units")
            canvas._drag_start_y = event.y

        canvas.bind("<ButtonPress-1>", _start)
        canvas.bind("<B1-Motion>", _drag)

        def _update(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", _update)

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
        root.rowconfigure(0, weight=0, minsize=50)
        root.rowconfigure(1, weight=2, minsize=110)
        root.rowconfigure(2, weight=1, minsize=80)
        root.rowconfigure(3, weight=3, minsize=180)
        root.columnconfigure(0, weight=1)

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

        lang_frame = tk.Frame(root, bg="#333333")
        lang_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))

        for c in range(5):
            lang_frame.columnconfigure(c, weight=1)

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

        text_frame = tk.Frame(root, bg="#000000")
        text_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))

        text_frame.rowconfigure(0, weight=0)
        text_frame.rowconfigure(1, weight=1)
        text_frame.rowconfigure(3, weight=0)
        text_frame.rowconfigure(4, weight=1)
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

        self.original_scroll = self._create_scrollable_text(
            text_frame,
            self.original_text_var,
            fg="#ffffff",
            bg="#000000"
        )
        self.original_scroll.grid(row=1, column=0, sticky="nsew")

        self.translated_scroll = self._create_scrollable_text(
            text_frame,
            self.translated_text_var,
            fg="#00ff88",
            bg="#000000"
        )
        self.translated_scroll.grid(row=4, column=0, sticky="nsew")

    def _set_state(self, new_state, message=None):
        self.state = new_state

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

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

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

    def _do_translate_worker(self):
        audio_bytes = stop_recording(wait=True)
        stop_playback()

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