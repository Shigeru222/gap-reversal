# 翌朝ギャップ反転スキャナー

前日比で上がった日は翌朝安く寄り、下がった日は翌朝高く寄る。この「引け→寄りの反転」が偶然以上に起きている国内株を探すWebアプリです。

## ファイル
- `app.py`：画面（Streamlit）
- `core.py`：分析ロジック
- `requirements.txt`：必要なライブラリ

## 公開手順（Streamlit Community Cloud・無料）
1. GitHubにログインし、右上の「＋」→「New repository」。名前（例：gap-reversal）を付け、Public で作成
2. 作成したリポジトリで「Add file」→「Upload files」。`app.py`・`core.py`・`requirements.txt`・`README.md` の4つをドラッグして「Commit changes」
3. https://share.streamlit.io を開き、「Continue with GitHub」でログイン
4. 「Create app」→「Deploy a public app from GitHub」。Repository に作ったリポジトリ、Branch は main、Main file path は `app.py` を指定して「Deploy」
5. 数分で `https://〜.streamlit.app` のURLが発行されます。スマホのブラウザでも開けます

## 手元で動かす場合
```
pip install -r requirements.txt
streamlit run app.py
```

## 注意
- 株価は非公式ライブラリ yfinance 経由（Yahoo Finance）。取得が混雑で失敗したら数分おいて再実行
- 無料プランのアプリはしばらく使わないと休止します。開いたときに「Wake up」を押せば再開します
- 過去の統計は将来の利益を保証しません
