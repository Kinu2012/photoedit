import tkinter as tk
from tkinter import filedialog, messagebox
import rawpy
import imageio
from pathlib import Path

def select_input_folder():
    path = filedialog.askdirectory()
    if path:
        input_var.set(path)

def select_output_folder():
    path = filedialog.askdirectory()
    if path:
        output_var.set(path)

def process_images():
    input_path = Path(input_var.get())
    output_path = Path(output_var.get())
    output_path.mkdir(parents=True, exist_ok=True)

    files = list(input_path.glob("*.RW2"))  # 拡張子変更OK
    if not files:
        messagebox.showwarning("警告", "RAWファイルが見つかりません")
        return

    for raw_file in files:
        with rawpy.imread(str(raw_file)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True)
        out_file = output_path / (raw_file.stem + ".jpg")
        imageio.imwrite(str(out_file), rgb)
    
    messagebox.showinfo("完了", "現像が完了しました。")

# GUIセットアップ
root = tk.Tk()
root.title("HakuAIget")

input_var = tk.StringVar()
output_var = tk.StringVar()

tk.Label(root, text="RAWフォルダ:").pack()
tk.Entry(root, textvariable=input_var, width=50).pack()
tk.Button(root, text="選択", command=select_input_folder).pack()

tk.Label(root, text="保存フォルダ:").pack()
tk.Entry(root, textvariable=output_var, width=50).pack()
tk.Button(root, text="選択", command=select_output_folder).pack()

tk.Button(root, text="現像開始", command=process_images).pack(pady=10)

root.mainloop()
