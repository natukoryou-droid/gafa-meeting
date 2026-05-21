# GAFA Online Meeting 自動更新表

ギャンブル依存症家族の自助グループ GAFA のオンラインミーティング一覧を、毎日自動更新するシステムです。

## 🌸 公開ページ

GitHub Pages を有効にすると、以下のURLでアクセスできます：

```
https://natukoryou-droid.github.io/gafa-meeting/gafa_meeting.html
```

## ⚙️ ファイル構成

```
gafa-meeting/
├── gafa_meeting.html          # 表示用のメインHTML
├── meetings.json              # ミーティングデータ
├── requirements.txt           # Python依存パッケージ
├── scripts/
│   ├── scrape.py             # GAFA公式からデータ取得
│   └── update_html.py        # HTML自動更新
└── .github/workflows/
    └── update-meetings.yml   # GitHub Actions（毎日自動実行）
```

## 🔄 自動更新の仕組み

1. 毎日 **日本時間 朝6時** に GitHub Actions が自動実行
2. `scripts/scrape.py` が GAFA 公式サイトからデータ取得
3. `scripts/update_html.py` が `gafa_meeting.html` を更新
4. 変更があれば自動でコミット＆プッシュ
5. GitHub Pages が自動で公開ページを更新

## 📱 セットアップ手順

### 1. GitHub Pages を有効化

1. リポジトリの **Settings** を開く
2. 左メニューの **Pages** をクリック
3. **Source** を **「Deploy from a branch」** に
4. **Branch** を **「main」** に、フォルダは **「/ (root)」** に
5. **Save** をクリック
6. 数分後に公開ページが利用可能になります

### 2. iPhoneのホーム画面に追加（アプリ化）

1. Safari で公開URLを開く
2. 共有ボタン（↑）をタップ
3. **「ホーム画面に追加」** を選択
4. アイコン名を **「GAFA」** などに設定して **追加**
5. ホーム画面からアプリのように起動できます

## 🛠️ ローカルテスト方法

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# データ取得テスト
python scripts/scrape.py

# HTML更新テスト
python scripts/update_html.py
```

## ✅ 機能

- ✅ A4縦1ページに常に収まる自動レイアウト調整
- ✅ 曜日ごとの色分け（日→月→火→水→木→金→土の順）
- ✅ 各曜日内は開始時間順にソート
- ✅ メールアドレスクリックで Gmail 送信画面が開く
- ✅ チェックボックス3つ（メール送信済 / LINE済 / 参加済）の状態保存
- ✅ PDF保存時もカラーが維持される
- ✅ スマホでも見やすいレスポンシブ対応

## 🆘 トラブルシューティング

### スクレイピング失敗時の動作

- `error.log` にエラー情報を記録
- 既存の `meetings.json` を維持
- HTMLは前回のデータのまま表示し続ける（壊れない）

### 手動で更新を実行する

GitHub の **Actions** タブから **「Update GAFA Meetings」** を選択し、**「Run workflow」** ボタンで手動実行できます。
