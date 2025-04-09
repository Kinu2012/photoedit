import tkinter as tk
from tkinter import filedialog, messagebox
import rawpy
import imageio
from pathlib import Path

# 拡張子対応リスト
RAW_EXTENSIONS = ["*.CR2", "*.CR3", "*.NEF", "*.ARW", "*.RAF", "*.RW2", "*.ORF", "*.PEF"]

# プリセット処理関数
def process_with_preset(raw, preset="default"):
    if preset == "vivid":
        return raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            gamma=(1.8, 1),         # 明るさ寄りのガンマ設定
            output_bps=8,
            use_auto_wb=False,
        )
    else:
        return raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
        )


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
tk.OptionMenu(root, preset_var, "vivid", "default").pack(pady=2)

tk.Button(root, text="現像開始", command=process_images).pack(pady=10)

root.mainloop()
