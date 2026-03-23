# 📅 SSScheduler

Streamlit × Firebase Firestore × Google Apps Script (GAS) のハイブリッド構成で構築された、プロジェクト・団体向けの高機能日程調整ツールです。  
独自のカスタムコンポーネント（Custom HTML/JS）を採用し、メインデータベースにFirestoreを用いることで、Streamlit特有の再読み込みラグを排除し、スマートフォンからも**圧倒的かつ爆速な入力UI**を実現しています。

## 🚀 主な特徴

- **3つの柔軟な調整モード**:
  - `🕒 時間帯モード`: 15分刻みで詳細な空き時間を直感的にペイント入力（スマホのタッチ操作対応）。
  - `🏫 時間割モード`: 1限〜5限・放課後の枠を使って、全メンバーの空きコマを一括集計。
  - `📅 候補リストモード`: 任意のイベント案に対する出欠アンケート（集計画面で◯△×のメンバーをコードブロックで綺麗に分類表示）。
- **究極の時短入力 (Smart Input)**:
  - **詳細メモ機能 (New!)**: カレンダーのマスを長押し（長タップ）することで、遅刻や早退などの詳細な補足コメントをセル単位で記録可能。
  - **時間割パワー反映**: 自分の時間割を一度登録しておけば、ワンクリックで「授業等（グレー）」として一括反映。
  - **iCal連携**: GoogleカレンダーやiOSカレンダーの非公開URL（.ics）を読み込み、個人の予定を自動でブロック。
- **管理者向け・高度な集計機能**:
  - プロジェクト、系、委員会、役職などの強力なクロスフィルター集計。
  - 「未定(△)」を0.5人としてカウントする柔軟なヒートマップ表示。
  - 未回答者をワンクリックで抽出し、リスト化。
  - Slack連携（Webhook）による、新規イベント作成時の自動通知＆メンション機能。
  - 回答者の名前を隠す「プライベート調整」機能。

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
