# PhotoEdit — RAW一括現像ツール

RW2などのRAW画像をプレビューし、同じ設定でJPEGに一括変換するツールです。

## Pythonなしで使う（Windows x64）

1. [Releases](https://github.com/Kinu2012/photoedit/releases)から `PhotoEdit-Windows-x64.zip` をダウンロード。
2. ZIPをすべて展開。
3. `PhotoEdit/PhotoEdit.exe` をダブルクリック。

`_internal` フォルダも必要です。exeだけを移動しないでください。
Releaseがまだない場合はActionsのWindows ZIPの完了を確認してください。

## 使い方

1. 「RAWフォルダ」で写真が入っているフォルダを選択。この画面では写真自体は選べません。
2. 保存フォルダを選択。
3. 「プレビュー用RAWを開く」で代表の1枚を開く。
4. プリセット、明るさ、コントラスト、彩度を調整。
5. 「現像開始」で全写真を開始時点の設定で現像。

RW2が表示されない場合は種類を「Panasonic RAW (RW2)」または「すべてのファイル」に変更してください。
JPEGは入力対象外です。サブフォルダは検索しません。

## 機能

- CR2 / CR3 / NEF / ARW / RAF / RW2 / ORF / PEF。大小文字両対応。
- default / vivid / soft / film / monochrome。
- プリセット変更時にプレビューを再現像。手動調整、進捗とエラーログ。
- JPEG品質95。同名ファイルは上書きせず連番保存。
- 多重実行防止、保存先検証、キャンセル。

キャンセルは実行中のRAW処理や保存が戻ったところで停止します。保存済みJPEGは残ります。
開始後に設定を変えても実行中の一括現像には反映されません。
画質設定は元のpro4から引き継いでいます。プレビューとJPEGには圧縮等の差があります。
カメラ機種ごとの対応はrawpy/LibRawに依存します。

## Pythonから起動

Python 3.12とTkinter/Tcl/Tkを使用します。

```powershell
python -m pip install -r requirements.txt
python pro4.py
```

pro1〜pro3は旧版です。現行版はpro4.pyです。

## ビルド・配布

GitHub Actionsでmain更新、プルリクエスト、手動実行時にWindows ZIPを作成し、Artifactsに保存します。
vで始まるタグをpushすると、テストとビルド成功後にReleasesへZIPを公開します。

ローカルでビルドする場合：

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onedir --windowed --name PhotoEdit --collect-all rawpy --copy-metadata rawpy --copy-metadata numpy --copy-metadata Pillow pro4.py
```

出力はdist/PhotoEditです。フォルダ全体を配布してください。

## 検証範囲

CIでは処理フローの模擬テスト、GUI初期化、合成画像のプレビューとJPEG保存、ビルドしたexeの起動を確認します。
実写RAWでの画質・カメラ互換性、Python未導入の別PCでの手動操作は別途確認が必要です。

参考：[PyInstaller](https://www.pyinstaller.org/en/stable/usage.html)、[GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository?tool=cli)。
