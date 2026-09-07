# 貝取 バス発車案内（個人用 PWA）

貝取周辺 8 方向の「次のバス」を iPad のホーム画面から一発で確認するアプリです。
時刻表は京王バスの公式 GTFS（ODPT）から GitHub Actions が毎日自動取得します。

## ファイル構成

| ファイル | 役割 |
|---|---|
| `index.html` | アプリ本体（単一ファイル） |
| `manifest.json` / `icon-*.png` | ホーム画面アイコンと PWA 設定 |
| `sw.js` | オフライン用 Service Worker |
| `data/timetable.json` | 抽出済み時刻表（2026-09-03 版を同梱。Actions が更新します） |
| `scripts/extract.py` | GTFS zip → `data/timetable.json` 変換 |
| `.github/workflows/update.yml` | 毎日 05:00 JST に ODPT を確認して更新 |

## セットアップ手順

### 1. GitHub にリポジトリを作る
1. GitHub で **New repository**。名前は `kaidori-bus` など。**Public** を選ぶ（無料枠で Pages を使うため）
2. このフォルダの中身をすべてアップロード（Web の「Add file → Upload files」でフォルダごとドラッグ可。`.github` フォルダも忘れずに）

### 2. Actions がコミットできるようにする
Settings → Actions → General → **Workflow permissions** → **Read and write permissions** → Save

### 3. ODPT のダウンロード URL を Secret に登録
1. ODPT 開発者サイトで登録・ログインし、アクセストークンを発行
2. ダウンロード URL は次の形です（`date=` を付けないと最新版になります）
   `https://api.odpt.org/api/v4/files/odpt/KeioBus/AllLines.zip?acl:consumerKey=＜アクセストークン＞`
   ※ `date=` 無しで落とせない場合は `date=YYYYMMDD` 付きの URL を使い、改正時に Secret を更新してください
3. Settings → Secrets and variables → Actions → **New repository secret**
   - Name: `ODPT_GTFS_URL`
   - Secret: トークン付きのダウンロード URL 全体

### 4. 動作確認（手動実行）
Actions タブ → 「時刻表を更新」 → **Run workflow**。
成功すると `data/timetable.json` が実データに置き換わるコミットが入ります。
ログに「便が 0 の方向があります」と出た場合は、その方向のデータが京王バス GTFS に無い可能性があります（下記トラブルシュート参照）。

### 5. GitHub Pages を有効にする
Settings → Pages → Source: **Deploy from a branch** → Branch: `main` / `/ (root)` → Save。
数分後に `https://<ユーザ名>.github.io/kaidori-bus/` で開けます。

### 6. iPad のホーム画面に追加
Safari で上の URL を開く → 共有ボタン → **ホーム画面に追加**。
以後はアイコンから全画面で起動し、圏外でも前回取得分で動きます。

## トラブルシュート

- **停留所が見つからない**（ログに「警告: 停留所 '…' が見つかりません」）
  ローカルで `python3 scripts/extract.py keio_bus.zip --list-stops 貝取` を実行し、GTFS 上の正式名称を確認して `scripts/extract.py` の `DIRECTIONS` を直してください。
- **多摩市ミニバス（東西線）が入っていない**
  多摩市が別の GTFS を公開している場合があります。その zip も同じスクリプトで処理できるよう拡張が必要なので、相談してください。
- **Actions が動かなくなった**
  Public リポジトリのスケジュール実行は 60 日間動きがないと止まることがあります。Actions タブで「Run workflow」を押せば再開します。
- **画面が古いまま**
  フッターの「時刻表を再取得」を押すか、ホーム画面のアイコンを一度削除して追加し直してください。

## ローカルで試す
```
python3 -m http.server 8000
```
を実行して http://localhost:8000/ を開きます（`file://` で直接開くと時刻表 JSON が読めず、埋め込みサンプルが表示されます）。

## 画面の構成
駅ごとに「家から」（左）と「駅から帰る」（右）を横並びにしています。カードには次のバスの時刻・系統・乗り場番号、その後 3 本の時刻を表示し、タップすると一日分の時刻表が開きます。

## ファイルを更新するとき
index.html や scripts/extract.py を差し替えるときは、リポジトリで **Add file → Upload files** に新しいファイルをドロップして Commit すれば上書きされます。`sw.js` の `CACHE` の版数（v2, v3 …）を上げると、iPad 側のキャッシュが確実に入れ替わります。
