import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import rawpy
import numpy as np
import imageio
from pathlib import Path
from PIL import Image, ImageTk, ImageEnhance
import threading
import datetime

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
        self.root.title("RAW一括現像ツール v2")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(True, True)

        # 状態変数
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.preset_var = tk.StringVar(value="vivid")
        self.preview_raw = None       # 現在プレビュー中のrawpyオブジェクト用データ
        self.preview_base_rgb = None  # プリセット適用済みの元画像（numpy）
        self.preview_tk = None        # PhotoImage（GC防止）

        self._build_ui()

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

        ctrl = tk.Frame(main_frame, bg=PANEL, bd=0, relief="flat", width=340)
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

        def entry_row(parent, var, btn_cmd, btn_text="選択"):
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
        tk.Button(ctrl, text="⚡  現像開始",
                  bg=ACCENT, fg=DARK, relief="flat",
                  font=("Consolas", 11, "bold"), pady=8,
                  command=self.start_processing
                  ).pack(fill="x", padx=10, pady=(8, 4))

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
        path = filedialog.askdirectory()
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
        if self.preview_raw is not None:
            self._reload_preview_base()
        self._update_preview()

    # ── プレビュー用RAWを開く ─────────────────────────────────────────────────
    def open_preview_file(self):
        path = filedialog.askopenfilename(
            title="プレビュー用RAWファイルを選択",
            filetypes=[("RAW files",
                        "*.CR2 *.cr2 *.CR3 *.cr3 *.NEF *.nef "
                        "*.ARW *.arw *.RAF *.raf *.RW2 *.rw2 "
                        "*.ORF *.orf *.PEF *.pef")]
        )
        if not path:
            return
        self._log(f"プレビュー読み込み中: {Path(path).name}")
        self.status_label.config(text="プレビュー読み込み中...")
        threading.Thread(target=self._load_preview, args=(path,), daemon=True).start()

    def _load_preview(self, path):
        try:
            with rawpy.imread(path) as raw:
                self.preview_raw = process_with_preset(raw, self.preset_var.get())
            self.preview_base_rgb = self.preview_raw
            self.root.after(0, self._update_preview)
            self.root.after(0, lambda: self.status_label.config(text="プレビュー完了"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"プレビューエラー: {e}"))

    def _reload_preview_base(self):
        # プリセット変更時は再現像が必要だが、すでにrawpyオブジェクトは閉じているため
        # 現在のbase_rgbを保持したまま調整のみ更新
        pass  # 再オープンが必要な場合はopen_preview_fileから再実行

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

    # ── 現像処理（スレッド起動） ──────────────────────────────────────────────
    def start_processing(self):
        if not self.input_var.get() or not self.output_var.get():
            messagebox.showwarning("警告", "RAWフォルダと保存フォルダを指定してください。")
            return
        threading.Thread(target=self._process_images, daemon=True).start()

    def _process_images(self):
        input_path  = Path(self.input_var.get())
        output_path = Path(self.output_var.get())
        preset      = self.preset_var.get()
        brightness  = self.brightness_var.get()
        contrast    = self.contrast_var.get()
        saturation  = self.saturation_var.get()
        output_path.mkdir(parents=True, exist_ok=True)

        files = []
        for ext in RAW_EXTENSIONS:
            files.extend(input_path.glob(ext))
        files = list(set(files))  # 重複除去

        if not files:
            self.root.after(0, lambda: messagebox.showwarning(
                "警告", "RAWファイルが見つかりません。"))
            return

        total = len(files)
        self._log(f"現像開始: {total}ファイル  プリセット={preset}")
        self.root.after(0, lambda: self.progress_var.set(0))

        ok_count, err_count = 0, 0
        for i, raw_file in enumerate(files, 1):
            self.root.after(0, lambda f=raw_file.name:
                            self.status_label.config(text=f"処理中: {f}"))
            try:
                with rawpy.imread(str(raw_file)) as raw:
                    rgb = process_with_preset(raw, preset=preset)
                img = apply_adjustments(rgb, brightness, contrast, saturation)
                out_file = output_path / (raw_file.stem + ".jpg")
                img.save(str(out_file), quality=95)
                self._log(f"✓ {raw_file.name}")
                ok_count += 1
            except Exception as e:
                self._log(f"✗ {raw_file.name}: {e}")
                err_count += 1
            pct = i / total * 100
            self.root.after(0, lambda p=pct: self.progress_var.set(p))

        self._log(f"完了: 成功{ok_count} / 失敗{err_count}")
        self.root.after(0, lambda: self.status_label.config(text="完了"))
        self.root.after(0, lambda: messagebox.showinfo(
            "完了", f"現像完了！\n成功: {ok_count}件  失敗: {err_count}件"))

    # ── ログ書き込み ──────────────────────────────────────────────────────────
    def _log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        def _write():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{ts}] {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _write)


# ─── エントリーポイント ──────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1000x680")
    app = RawDeveloperApp(root)
    root.mainloop()