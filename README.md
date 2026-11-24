# 📅 SSScheduler

Streamlit × Firebase Firestore × Google Apps Script (GAS) のハイブリッド構成で構築された、プロジェクト・団体向けの高機能日程調整ツールです。  
独自のカスタムコンポーネント（Custom HTML/JS）を採用し、メインデータベースにFirestoreを用いることで、Streamlit特有の再読み込みラグを排除し、スマートフォンからも**圧倒的かつ爆速な入力UI**を実現しています。

## 🚀 主な特徴

- **4つの柔軟な調整モード**:
  - `🕒 時間帯モード`: 15分刻みで詳細な空き時間を直感的にペイント入力（PCの右クリック消去・ダブルクリックメモ、スマホの1本指ペイント＋2本指スクロール＋長押しメモ対応）。
  - `🏫 時間割モード`: 1限〜5限・昼休み・放課後の枠を使って、全メンバーの空きコマを一括集計。
  - `📅 日付指定コマモード`: 特定期間の日付×コマ数（1限〜5限・昼休み・放課後）で調整。
  - `📅 候補リストモード`: 任意のイベント案に対する出欠アンケート（一括選択＆集計内訳表示）。
- **究極の時短入力 ＆ 快適操作 (Smart Input)**:
  - **大型スイッチャー＆自動遷移**: 上部の大型切り替えボタンで「入力」と「みんなの集計」を一目で切り替え可能（提出後は自動で集計画面へ移動）。
  - **詳細メモ機能**: スマホはセル長押し、PCはダブルクリック（またはメモペン）で、遅刻・早退などの補足コメントをセル単位で記録可能。
  - **↩ Undo ＆ 時間割パワー反映**: 入力のやり直し（Undo）や、登録済み時間割のワンクリック反映に対応。
  - **iCal連携**: GoogleカレンダーやiOSカレンダーの非公開URL（.ics）を読み込み、個人の予定を自動でブロック。
- **集計・意思決定・共有の高速化**:
  - **🏆 おすすめ候補日時ランキング ＆ Slackコピー**: 所要時間（15分〜120分）に応じた連続参加可能枠のトップ5を自動算出し、Slack投稿文をワンタップコピー。
  - **⭐ 必須メンバー指定 ＆ 自分の回答重ね合わせ**: キーマンが参加できる枠だけの絞り込みや、集計表上への自分の回答重ね表示に対応。
  - **📌 開催日時確定 ＆ カレンダーワンタップ登録**: 主催者・管理者が日時を確定すると決定バナーが表示され、Googleカレンダーや `.ics` へ1タップ登録可能。
  - **管理者向け機能**: グループ横断フィルター、未回答者リスト抽出・コピー、Slackメンション通知、プライベート調整、自動ログイン保持（localStorage連携）。

## 📦 システム構成図 (Hybrid Architecture)

当アプリは、Firestoreの「爆速な読み書き性能」と、スプレッドシート（GAS）の「非エンジニアにも優しいデータ視認性・バックアップ機能」を両立させたサーバーレスハイブリッドアーキテクチャを採用しています。

```mermaid
graph TD
    subgraph "Frontend (Streamlit Community Cloud)"
        A[User Browser] -- "Interact" --> B(Streamlit App)
        B -- "Zero-Lag UI" --> C[Custom Grid Editor / Options UI]
    end

    subgraph "Main Database (Fast Read/Write)"
        B -- "Realtime Sync" --> F[(Firebase Firestore)]
    end

    subgraph "External API"
        G[Google/iOS Calendar] -- "Fetch .ics" --> B
    end

    subgraph "Backup & Integration (Google Cloud)"
        B -- "Async API (POST)" --> D{Google Apps Script}
        D -- "Backup / Master Data" --> E[(Google Sheets)]
        D -- "Webhook Notification" --> H[Slack]
    end

    style B fill:#ff4b4b,color:#fff
    style F fill:#f58220,color:#fff
    style D fill:#4285f4,color:#fff
    style E fill:#34a853,color:#fff
    style H fill:#4b114b,color:#fff
```

**Why this architecture?**
- **High Performance**: FirestoreをメインDBにすることで、多人数の同時アクセスや膨大なカレンダーデータの読み込みを瞬時に処理。
- **Data Safety & Visibility**: 回答データは裏側（非同期）でGAS経由でスプレッドシートにも保存されるため、データのバックアップと管理者による直接編集（Excel感覚での管理）が可能。
- **Zero Hosting Cost**: Streamlit Community Cloud と Firebase/Google Cloud の無料枠を組み合わせることで、維持費0円で完全稼働。

## 🛠️ 技術スタック

- **Frontend**: Python 3, Streamlit, Pandas, HTML/CSS/Vanilla JS (スマホ極限最適化済み Custom Components)
- **Backend / API**: Google Apps Script (GAS)
- **Database**: Firebase Firestore (Main) + Google Sheets (Backup)
- **Integration**: Slack Webhook, iCalendar (.ics) parsing
- **Auth & Tools**: Google Cloud Service Account, Python Sync Script

---

## ⚙️ セットアップ手順 (Getting Started)

ご自身の環境でこのアプリを動かすための初期設定手順です。

### 1. Firebase (Firestore) の準備
1. [Firebase Console](https://console.firebase.google.com/) で新規プロジェクトを作成します。
2. 左メニューの `Build` > `Firestore Database` からデータベースを作成します。
3. `Rules（ルール）` タブを開き、以下の設定にして `Publish` します（サービスアカウントからのアクセスはルールをバイパスするため安全です）。
   ```javascript
   rules_version = '2';
   service cloud.firestore {
     match /databases/{database}/documents {
       allow read, write: if true; 
     }
   }
   ```
4. `Project settings` (歯車マーク) > `Service accounts` タブを開き、**「Generate new private key」** をクリックして JSONファイルをダウンロードします。

### 2. Google スプレッドシート & GAS の準備
1. 新規スプレッドシートを作成し、以下のシート名とヘッダー（1行目）を設定します。
   - **`users`**: `user_id`, `name`, `pin`, `role`, `group_1`, `group_2`, `group_3`, `group_4`, `secret_word`, `calendar_url`, `slack_id`
   - **`events`**: `event_id`, `title`, `start_date`, `end_date`, `status`, `start_idx`, `end_idx`, `description`, `event_type`, `event_options`, `deadline`, `auto_close`, `target_scope`, `is_private`
   - **`responses`**: `event_id`, `user_id`, `date`, `binary_data`, `comment`, `cell_details`
   - **`fixed_schedule`**: `user_id`, `day_of_week`, `binary_data`
   - **`archive`**: （`responses` と同じヘッダー）
2. `拡張機能` > `Apps Script` を開き、付属の GASコード を貼り付けます。
3. コード冒頭の `SPREADSHEET_ID` と `ADMIN_WEBHOOK_URL` (Slack用) を設定し、「ウェブアプリ」としてデプロイしてURLを取得します。

### 3. Streamlit アプリの設定と公開
1. このリポジトリをGitHubにフォーク（またはプッシュ）します。
2. `app.py` 内の `GAS_URL` と `APP_BASE_URL` をご自身の環境に合わせて変更します。
3. `requirements.txt` がリポジトリのルートに存在し、`streamlit`, `pandas`, `requests`, `numpy`, `google-auth`, `google-cloud-firestore` が記載されていることを確認します。
4. [Streamlit Community Cloud](https://streamlit.io/cloud) にデプロイします。
5. デプロイ後、アプリの `Settings` > `Secrets` に、手順1でダウンロードしたFirebaseのJSONキー情報を以下のTOML形式で登録します。
   ```toml
   [firebase]
   type = "service_account"
   project_id = "your-project-id"
   private_key_id = "your-private-key-id"
   private_key = "-----BEGIN PRIVATE KEY-----\nMIIE... (改行は \n のまま)\n-----END PRIVATE KEY-----\n"
   client_email = "your-client-email"
   client_id = "your-client-id"
   auth_uri = "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)"
   token_uri = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
   auth_provider_x509_cert_url = "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)"
   client_x509_cert_url = "your-cert-url"
   universe_domain = "googleapis.com"
   ```

### 4. 既存データの移行 (オプション)
すでにスプレッドシート上で運用していたデータがある場合や、手動でスプレッドシートを修正した場合は、付属の `sync_from_gas.py` を手元のPCで実行することで、GASから最新の全データを取得し、Firestoreへ完全同期（全単射）させることができます。

---
*Developed by: Tomoki Ueno (SSSRC)* *Powered by: Streamlit, Firebase & Google Apps Script* *Assistant: Gemini (AI)*
