import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import rawpy
import numpy as np
import queue
import tempfile
from pathlib import Path
from PIL import Image, ImageTk, ImageEnhance
import threading
import datetime
import sys

# ─── 拡張子対応リスト（大文字・小文字両対応） ───────────────────────────────
RAW_EXTENSIONS = [
    "*.CR2", "*.cr2", "*.CR3", "*.cr3",
    "*.NEF", "*.nef", "*.ARW", "*.arw",
    "*.RAF", "*.raf", "*.RW2", "*.rw2",
    "*.ORF", "*.orf", "*.PEF", "*.pef",
]

# ─── プリセット設定 ──────────────────────────────────────────────────────────
PRESETS = {
    "default":    {"gamma": (1.0, 1.0), "scale": 1.0,  "offset": 0,  "mono": False},
    "vivid":      {"gamma": (1.8, 1.0), "scale": 1.0,  "offset": 0,  "mono": False},
    "soft":       {"gamma": (1.3, 1.0), "scale": 0.95, "offset": 10, "mono": False},
    "film":       {"gamma": (2.2, 1.0), "scale": 0.9,  "offset": 0,  "mono": False},
    "monochrome": {"gamma": (1.0, 1.0), "scale": 1.0,  "offset": 0,  "mono": True},
}

# ─── RAW現像コア（バグ修正済み：無駄な初期postprocessを削除） ──────────────
def process_with_preset(raw, preset="default"):
    cfg = PRESETS.get(preset, PRESETS["default"])
    rgb = raw.postprocess(
        use_camera_wb=True,
        no_auto_bright=True,
        gamma=cfg["gamma"],
        output_bps=8,
    )
    if cfg["scale"] != 1.0 or cfg["offset"] != 0:
        rgb = np.clip(rgb * cfg["scale"] + cfg["offset"], 0, 255).astype("uint8")
    if cfg["mono"]:
        gray = (rgb[..., 0] * 0.3 + rgb[..., 1] * 0.59 + rgb[..., 2] * 0.11).astype("uint8")
        rgb = np.stack([gray] * 3, axis=-1)
    return rgb

# ─── 手動調整の適用（PIL使用） ───────────────────────────────────────────────
def apply_adjustments(rgb_array, brightness=1.0, contrast=1.0, saturation=1.0):
    img = Image.fromarray(rgb_array)
    img = ImageEnhance.Brightness(img).enhance(brightness)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    img = ImageEnhance.Color(img).enhance(saturation)
    return img

# ─── GUIクラス ───────────────────────────────────────────────────────────────
class RawDeveloperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RAW一括現像ツール v3")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(True, True)

        # 状態変数
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.preset_var = tk.StringVar(value="vivid")
        self.preview_path = None
        self.preview_generation = 0
        self.preview_busy = False
        self.preview_pending = None
        self.events = queue.Queue()
        self.processing = False
        self.closing = False
        self.cancel_event = threading.Event()
        self.preview_base_rgb = None  # プリセット適用済みの元画像（numpy）
        self.preview_tk = None        # PhotoImage（GC防止）

        self._build_ui()
        self.root.after(50, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # ── UI構築 ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        DARK   = "#1e1e2e"
        PANEL  = "#2a2a3e"
        ACCENT = "#89b4fa"
        TEXT   = "#cdd6f4"
        SUBTEXT= "#a6adc8"
        BTN_BG = "#313244"

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor=PANEL, background=ACCENT, thickness=12)
        style.configure("TScale", background=PANEL, troughcolor=BTN_BG)

        # ─ メインフレーム（左：コントロール　右：プレビュー）
        main_frame = tk.Frame(self.root, bg=DARK)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctrl = tk.Frame(main_frame, bg=PANEL, bd=0, relief="flat", width=420)
        ctrl.pack(side="left", fill="y", padx=(0, 8), pady=0)
        ctrl.pack_propagate(False)

        preview_frame = tk.Frame(main_frame, bg=PANEL, bd=0)
        preview_frame.pack(side="left", fill="both", expand=True)

        # ── コントロールパネル ───────────────────────────────────────────
        def label(parent, text, sub=False):
            fg = SUBTEXT if sub else TEXT
            sz = 9 if sub else 11
            tk.Label(parent, text=text, bg=PANEL, fg=fg,
                     font=("Consolas", sz)).pack(anchor="w", padx=14, pady=(10, 2))

        def entry_row(parent, var, btn_cmd, btn_text="フォルダ選択"):
            f = tk.Frame(parent, bg=PANEL)
            f.pack(fill="x", padx=10, pady=2)
            tk.Entry(f, textvariable=var, width=24, bg=BTN_BG, fg=TEXT,
                     insertbackground=TEXT, relief="flat",
                     font=("Consolas", 9)).pack(side="left", fill="x", expand=True, ipady=4)
            tk.Button(f, text=btn_text, bg=ACCENT, fg=DARK, relief="flat",
                      font=("Consolas", 9, "bold"), command=btn_cmd,
                      padx=8).pack(side="left", padx=(4, 0))

        label(ctrl, "▸ RAWフォルダ")
        entry_row(ctrl, self.input_var, self.select_input_folder)

        label(ctrl, "▸ 保存フォルダ")
        entry_row(ctrl, self.output_var, self.select_output_folder)

        label(ctrl, "▸ プリセット")
        preset_frame = tk.Frame(ctrl, bg=PANEL)
        preset_frame.pack(fill="x", padx=10, pady=4)
        for p in PRESETS:
            tk.Radiobutton(
                preset_frame, text=p, variable=self.preset_var, value=p,
                bg=PANEL, fg=TEXT, selectcolor=BTN_BG, activebackground=PANEL,
                font=("Consolas", 9), command=self._on_preset_change,
            ).pack(side="left", padx=4)

        # ── 手動調整スライダー ──────────────────────────────────────────
        label(ctrl, "▸ 手動調整")

        self.brightness_var = tk.DoubleVar(value=1.0)
        self.contrast_var   = tk.DoubleVar(value=1.0)
        self.saturation_var = tk.DoubleVar(value=1.0)

        def slider_row(parent, label_text, var, from_, to, res):
            f = tk.Frame(parent, bg=PANEL)
            f.pack(fill="x", padx=10, pady=2)
            tk.Label(f, text=label_text, bg=PANEL, fg=SUBTEXT,
                     font=("Consolas", 9), width=10, anchor="w").pack(side="left")
            sl = tk.Scale(f, variable=var, from_=from_, to=to, resolution=res,
                          orient="horizontal", bg=PANEL, fg=TEXT, troughcolor=BTN_BG,
                          highlightthickness=0, sliderrelief="flat",
                          font=("Consolas", 8), length=160,
                          command=lambda _: self._update_preview())
            sl.pack(side="left")

        slider_row(ctrl, "明るさ",     self.brightness_var, 0.3, 3.0, 0.05)
        slider_row(ctrl, "コントラスト", self.contrast_var,   0.3, 3.0, 0.05)
        slider_row(ctrl, "彩度",       self.saturation_var, 0.0, 3.0, 0.05)

        tk.Button(ctrl, text="リセット", bg=BTN_BG, fg=SUBTEXT, relief="flat",
                  font=("Consolas", 9), command=self._reset_sliders
                  ).pack(anchor="e", padx=14, pady=2)

        # ── プレビューボタン ────────────────────────────────────────────
        tk.Button(ctrl, text="📂  プレビュー用RAWを開く",
                  bg=BTN_BG, fg=TEXT, relief="flat",
                  font=("Consolas", 10), pady=6,
                  command=self.open_preview_file
                  ).pack(fill="x", padx=10, pady=(16, 4))

        # ── 現像開始 ────────────────────────────────────────────────────
        self.start_button = tk.Button(ctrl, text="⚡  現像開始",
                  bg=ACCENT, fg=DARK, relief="flat",
                  font=("Consolas", 11, "bold"), pady=8,
                  command=self.start_processing)
        self.start_button.pack(fill="x", padx=10, pady=(8, 4))
        self.cancel_button = tk.Button(ctrl, text="キャンセル", command=self.cancel_processing,
                                       bg=BTN_BG, fg=TEXT, state="disabled")
        self.cancel_button.pack(fill="x", padx=10, pady=2)
        tk.Label(ctrl, text="同名JPEGは連番で保存・設定は開始時に固定",
                 bg=PANEL, fg=SUBTEXT, font=("Consolas", 8)).pack(pady=2)

        # ── 進捗バー ────────────────────────────────────────────────────
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(ctrl, variable=self.progress_var,
                                            maximum=100, style="TProgressbar")
        self.progress_bar.pack(fill="x", padx=10, pady=4)

        self.status_label = tk.Label(ctrl, text="待機中", bg=PANEL, fg=SUBTEXT,
                                     font=("Consolas", 8))
        self.status_label.pack(anchor="w", padx=14)

        # ── ログ表示 ────────────────────────────────────────────────────
        label(ctrl, "▸ ログ", sub=True)
        log_frame = tk.Frame(ctrl, bg=BTN_BG)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_box = tk.Text(log_frame, bg=BTN_BG, fg=SUBTEXT,
                               font=("Consolas", 8), relief="flat",
                               state="disabled", height=8, wrap="word")
        sb = tk.Scrollbar(log_frame, command=self.log_box.yview, bg=DARK)
        self.log_box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_box.pack(fill="both", expand=True)

        # ── プレビューパネル ─────────────────────────────────────────────
        tk.Label(preview_frame, text="PREVIEW", bg=PANEL, fg=SUBTEXT,
                 font=("Consolas", 9)).pack(pady=(10, 4))

        self.preview_canvas = tk.Canvas(preview_frame, bg="#111120",
                                        highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._draw_placeholder()

    # ── プレースホルダー描画 ─────────────────────────────────────────────────
    def _draw_placeholder(self):
        self.preview_canvas.update_idletasks()
        w = self.preview_canvas.winfo_width() or 400
        h = self.preview_canvas.winfo_height() or 300
        self.preview_canvas.create_text(w//2, h//2,
                                        text="RAWファイルを開くとここにプレビューが表示されます",
                                        fill="#444466", font=("Consolas", 10))

    # ── フォルダ選択 ─────────────────────────────────────────────────────────
    def select_input_folder(self):
        path = filedialog.askdirectory(title="RAWファイルが入っているフォルダを選択", mustexist=True)
        if path:
            self.input_var.set(path)

    def select_output_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.output_var.set(path)

    # ── スライダーリセット ────────────────────────────────────────────────────
    def _reset_sliders(self):
        self.brightness_var.set(1.0)
        self.contrast_var.set(1.0)
        self.saturation_var.set(1.0)
        self._update_preview()

    # ── プリセット変更 → プレビュー更新 ──────────────────────────────────────
    def _on_preset_change(self):
        if self.preview_path:
            self._reload_preview_base()

    def open_preview_file(self):
        path = filedialog.askopenfilename(
            title="プレビュー用RAWファイルを選択",
            filetypes=[("RAW画像", tuple(RAW_EXTENSIONS)),
                       ("Panasonic RAW (RW2)", ("*.RW2", "*.rw2")),
                       ("すべてのファイル", "*")])
        if path:
            if Path(path).suffix.lower() not in {p[1:].lower() for p in RAW_EXTENSIONS}:
                messagebox.showwarning("形式の確認", "RW2などの対応RAWファイルを選択してください。")
                return
            self.preview_path = path
            self._reload_preview_base()

    def _reload_preview_base(self):
        self.preview_generation += 1
        self.preview_base_rgb = None
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(20, 20, anchor="nw", fill="#cdd6f4",
                                        text="プレビュー読み込み中...")
        self.preview_pending = (self.preview_path, self.preset_var.get(),
                                self.preview_generation)
        self._start_pending_preview()

    def _start_pending_preview(self):
        if self.preview_busy or self.preview_pending is None or self.closing:
            return
        args = self.preview_pending
        self.preview_pending = None
        self.preview_busy = True
        threading.Thread(target=self._load_preview, args=args, daemon=True).start()

    def _load_preview(self, path, preset, generation):
        # ワーカーはTk変数やウィジェットに触れない。
        try:
            with rawpy.imread(path) as raw:
                rgb = process_with_preset(raw, preset)
            self.events.put(("preview", generation, rgb, None))
        except Exception as exc:
            self.events.put(("preview", generation, None, str(exc)))

    # ── プレビュー更新（スライダー変更時） ────────────────────────────────────
    def _update_preview(self):
        if self.preview_base_rgb is None:
            return
        img = apply_adjustments(
            self.preview_base_rgb,
            brightness=self.brightness_var.get(),
            contrast=self.contrast_var.get(),
            saturation=self.saturation_var.get(),
        )
        self.preview_canvas.update_idletasks()
        cw = self.preview_canvas.winfo_width()  or 600
        ch = self.preview_canvas.winfo_height() or 400
        img.thumbnail((cw, ch), Image.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(cw//2, ch//2,
                                         anchor="center", image=self.preview_tk)

    def start_processing(self):
        if self.processing or self.closing:
            return
        input_text = self.input_var.get().strip()
        output_text = self.output_var.get().strip()
        if not input_text or not output_text:
            messagebox.showwarning("警告", "RAWフォルダと保存フォルダを指定してください。")
            return
        settings = (self.preset_var.get(), self.brightness_var.get(),
                    self.contrast_var.get(), self.saturation_var.get())
        self.processing = True
        self.cancel_event.clear()
        self.start_button.config(state="disabled")
        self.cancel_button.config(state="normal")
        self.progress_var.set(0)
        self.status_label.config(text="フォルダ確認中...")
        threading.Thread(target=self._process_images,
                         args=(Path(input_text), Path(output_text), settings),
                         daemon=True).start()

    def cancel_processing(self):
        if self.processing:
            self.cancel_event.set()
            self.cancel_button.config(state="disabled")
            self.status_label.config(text="中止待ち（実行中の処理が戻るまでお待ちください）")

    def _process_images(self, input_path, output_path, settings):
        ok_count = err_count = attempted = total = 0
        fatal = None
        try:
            if not input_path.is_dir():
                raise ValueError("RAWフォルダが存在しないか、フォルダではありません。")
            suffixes = {pattern[1:].lower() for pattern in RAW_EXTENSIONS}
            files = sorted((p for p in input_path.iterdir()
                            if p.is_file() and p.suffix.lower() in suffixes),
                           key=lambda p: p.name.casefold())
            total = len(files)
            if not files:
                raise ValueError("RAWファイルが見つかりません。")
            output_path.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=output_path):
                pass
            preset, brightness, contrast, saturation = settings
            self.events.put(("log", f"現像開始: {total}件 / {preset} / 明るさ{brightness}・コントラスト{contrast}・彩度{saturation}"))
            for raw_file in files:
                if self.cancel_event.is_set():
                    break
                self.events.put(("status", f"処理中: {raw_file.name}"))
                try:
                    with rawpy.imread(str(raw_file)) as raw:
                        rgb = process_with_preset(raw, preset)
                    if self.cancel_event.is_set():
                        break
                    img = apply_adjustments(rgb, brightness, contrast, saturation)
                    if self.cancel_event.is_set():
                        break
                    out_file = save_unique_jpeg(img, output_path, raw_file.stem)
                    ok_count += 1
                    self.events.put(("log", f"✓ {raw_file.name} → {out_file.name}"))
                except Exception as exc:
                    err_count += 1
                    self.events.put(("log", f"✗ {raw_file.name}: {exc}"))
                attempted += 1
                self.events.put(("progress", attempted / total * 100))
        except Exception as exc:
            fatal = str(exc)
        finally:
            self.events.put(("done", ok_count, err_count, total - attempted,
                             self.cancel_event.is_set(), fatal))

    def _drain_events(self):
        # Tkの操作はすべてメインスレッドで実行する。
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, *values = event
            if kind == "preview":
                generation, rgb, error = values
                self.preview_busy = False
                if generation == self.preview_generation and not self.closing:
                    if error is None:
                        self.preview_base_rgb = rgb
                        self._update_preview()
                        self._log("プレビュー更新完了")
                    else:
                        self._log(f"プレビューエラー: {error}")
                        self.preview_canvas.delete("all")
                        self.preview_canvas.create_text(20, 20, anchor="nw",
                            fill="#cdd6f4", text="プレビューの読み込みに失敗しました。")
                        messagebox.showerror("プレビューエラー", error)
                self._start_pending_preview()
            elif kind == "log":
                self._log(values[0])
            elif kind == "status":
                if not self.cancel_event.is_set():
                    self.status_label.config(text=values[0])
            elif kind == "progress":
                self.progress_var.set(values[0])
            elif kind == "done":
                ok, errors, remaining, cancelled, fatal = values
                self.processing = False
                self.start_button.config(state="normal")
                self.cancel_button.config(state="disabled")
                title = "エラー" if fatal else ("中止" if cancelled else "完了")
                detail = f"成功: {ok}件 / 失敗: {errors}件 / 未処理: {remaining}件"
                if fatal:
                    detail += "\n" + fatal
                self.status_label.config(text=title)
                self._log(title + ": " + detail)
                if not self.closing:
                    if fatal or errors:
                        messagebox.showwarning(title, detail)
                    else:
                        messagebox.showinfo(title, detail)
        if self.closing and not self.processing:
            self.root.destroy()
            return
        self.root.after(50, self._drain_events)

    def _close(self):
        self.closing = True
        self.preview_pending = None
        if self.processing:
            self.cancel_processing()
            self.status_label.config(text="処理の終了を待って閉じます...")
        else:
            self.root.destroy()

    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


def save_unique_jpeg(img, output_path, stem):
    """排他的作成で既存ファイルを保護し、衝突時は連番を付ける。"""
    index = 0
    while True:
        name = f"{stem}.jpg" if index == 0 else f"{stem}_{index}.jpg"
        target = output_path / name
        try:
            stream = target.open("xb")
        except FileExistsError:
            index += 1
            continue
        try:
            with stream:
                img.save(stream, format="JPEG", quality=95)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target


# ─── エントリーポイント ──────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    if "--smoke-test" in sys.argv:
        root.withdraw()
        app = RawDeveloperApp(root)
        app.preview_base_rgb = np.full((32, 32, 3), 128, dtype=np.uint8)
        app._update_preview()
        root.update()
        with tempfile.TemporaryDirectory() as folder:
            target = save_unique_jpeg(apply_adjustments(app.preview_base_rgb), Path(folder), "test")
            with Image.open(target) as saved:
                assert saved.size == (32, 32)
        root.destroy()
        if "--smoke-report" in sys.argv:
            Path(sys.argv[sys.argv.index("--smoke-report") + 1]).write_text("OK", encoding="utf-8")
        sys.exit(0)
    root.geometry("1100x800")
    root.minsize(950, 760)
    app = RawDeveloperApp(root)
    root.mainloop()
