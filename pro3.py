import tkinter as tk
from tkinter import filedialog, messagebox
import rawpy
import numpy as np
import imageio
from pathlib import Path

# 拡張子対応リスト
RAW_EXTENSIONS = ["*.CR2", "*.CR3", "*.NEF", "*.ARW", "*.RAF", "*.RW2", "*.ORF", "*.PEF"]

# プリセット処理関数
def process_with_preset(raw, preset="default"):
    rgb = raw.postprocess(
        use_camera_wb=True,
        no_auto_bright=True,
        gamma=(1.0, 1.0),
        output_bps=8
    )

    if preset == "vivid":
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            gamma=(1.8, 1),
            output_bps=8,
            use_auto_wb=False,
        )
    elif preset == "soft":
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            gamma=(1.3, 1),
            output_bps=8,
        )
        rgb = np.clip(rgb * 0.95 + 10, 0, 255).astype('uint8')  # ふんわり補正
    elif preset == "film":
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            gamma=(2.2, 1),
            output_bps=8,
        )
        rgb = np.clip(rgb * 0.9, 0, 255).astype('uint8')  # 少し暗めに
    elif preset == "monochrome":
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            gamma=(1.0, 1),
            output_bps=8,
        )
        gray = (rgb[...,0]*0.3 + rgb[...,1]*0.59 + rgb[...,2]*0.11).astype('uint8')
        rgb = np.stack([gray]*3, axis=-1)  # R=G=Bでモノクロ化

    return rgb

# RAW→JPEG一括処理
def process_images():
    input_path = Path(input_var.get())
    output_path = Path(output_var.get())
    preset = preset_var.get()
    output_path.mkdir(parents=True, exist_ok=True)

    files = []
    for ext in RAW_EXTENSIONS:
        files.extend(input_path.glob(ext))

    if not files:
        messagebox.showwarning("警告", "RAWファイルが見つかりません。")
        return

    for raw_file in files:
        try:
            with rawpy.imread(str(raw_file)) as raw:
                rgb = process_with_preset(raw, preset=preset)
            out_file = output_path / (raw_file.stem + ".jpg")
            imageio.imwrite(str(out_file), rgb)
            print(f"現像完了: {out_file}")
        except Exception as e:
            print(f"エラー: {raw_file.name} - {e}")

    messagebox.showinfo("完了", "現像が完了しました。")

# フォルダ選択系
def select_input_folder():
    path = filedialog.askdirectory()
    if path:
        input_var.set(path)

def select_output_folder():
    path = filedialog.askdirectory()
    if path:
        output_var.set(path)

# GUIセットアップ
root = tk.Tk()
root.title("RAW一括現像ツール")

input_var = tk.StringVar()
output_var = tk.StringVar()
preset_var = tk.StringVar(value="vivid")

tk.Label(root, text="RAWフォルダ:").pack()
tk.Entry(root, textvariable=input_var, width=50).pack()
tk.Button(root, text="選択", command=select_input_folder).pack(pady=2)

tk.Label(root, text="保存フォルダ:").pack()
tk.Entry(root, textvariable=output_var, width=50).pack()
tk.Button(root, text="選択", command=select_output_folder).pack(pady=2)

tk.Label(root, text="プリセット:").pack()
tk.OptionMenu(root, preset_var, "default", "vivid", "soft", "film", "monochrome").pack(pady=2)


tk.Button(root, text="現像開始", command=process_images).pack(pady=10)

root.mainloop()
