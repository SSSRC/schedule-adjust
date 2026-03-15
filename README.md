# 📅 日程調整 Pro (Schedule Adjust Pro)

Streamlit × Google Apps Script (GAS) で構築された、プロジェクト・団体向けの高機能日程調整ツールです。  
回答者の手間を極限まで減らす「スマートな日程入力」に特化しています。

## 🚀 主な特徴

- **3つの調整モード**:
  - `🕒 時間帯モード`: カレンダーから15分刻みで詳細な空き時間を調整。
  - `🏫 時間割モード`: 大学の1限〜5限・放課後の枠を使って一括集計。
  - `📅 候補リストモード`: 特定のイベント案（飲み会や会議）への出欠アンケート。
- **スマートな自動入力**:
  - **時間割連携**: 自分の時間割を一度登録すれば、あらゆる日程調整に「授業中」として一括反映。
  - **iCal連携**: Googleカレンダー等の「非公開URL」を設定することで、私的な予定を自動でグレーアウト表示。
- **高度な集計機能**:
  - 役職、系、プロジェクトごとのフィルタリング。
  - 「未定(△)」を0.5人とカウントする柔軟な重み付け集計。
  - 誰が回答可能かを視覚的に表示するヒートマップ。
- **プライバシー保護**: 回答者の名前を非公開にする「プライベート調整」設定。
- **Slack通知**: 新規イベント作成時やPINリセット依頼をSlackへ自動通知。

## 🛠️ 技術スタック

- **Frontend**: [Streamlit](https://streamlit.io/) (Python)
- **Backend**: [Google Apps Script (GAS)](https://developers.google.com/apps-script)
- **Database**: [Google Sheets](https://www.google.com/sheets/about/)
- **UI Components**: 
  - [stlite](https://github.com/whitphx/stlite) (一部コンポーネント)
  - Custom HTML/JavaScript (グリッドエディタ、リッチテキストエディタ)

## 📦 構成図



## 🚀 使い方

### 利用者向け
1. アカウントを作成し、自分の「所属プロジェクト」や「時間割」を登録。
2. 届いたイベントURLにアクセス。
3. 「時間割反映」や「カレンダー取得」ボタンを使って、サクッと回答を完了！

### 管理者向け
1. 「イベント新規作成」メニューから、対象メンバーや期間を設定して発行。
2. 集計画面でフィルタを使い、メンバーが揃う最適な時間を特定。
3. 未回答者をワンクリックで抽出。

## ⚙️ セットアップ (開発者向け)

このリポジトリを自身の環境で動作させるには、以下の設定が必要です。

1. **Googleスプレッドシートの準備**: 
   - `users`, `events`, `responses`, `fixed_schedule`, `archive` のシートを作成。
2. **GASのデプロイ**: 
   - 付属の `gas/code.js` をGASプロジェクトに貼り付け、「ウェブアプリ」としてデプロイ。
   - `SPREADSHEET_ID` と `ADMIN_WEBHOOK_URL` を設定。
3. **Streamlitの設定**:
   - `app.py` 内の `GAS_URL` と `APP_BASE_URL` を自身の環境に合わせて書き換え。

---
Produced by Your Name / Organization
