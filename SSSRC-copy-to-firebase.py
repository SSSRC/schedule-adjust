import requests
import pandas as pd
from google.oauth2 import service_account
from google.cloud import firestore

# ==========================================
# 1. 設定情報
# ==========================================
# 💡 デプロイしたGASのURL（action=get_all_data_raw に対応しているもの）
GAS_URL = "https://script.google.com/macros/s/AKfycbx8GCHdyb9DDFIUajiKjceSn20-rfuEtsqrxCm-dD_pYsKou2Ie8mDkaM4oX3sKRX4SDQ/exec"

# 💡 Firebaseサービスアカウントキーのパス
KEY_PATH = "schedule-adjust-sssrc-firebase-adminsdk-fbsvc-ae880ff8de.json"

creds = service_account.Credentials.from_service_account_file(KEY_PATH)
db = firestore.Client(credentials=creds, project=creds.project_id)

def clean_dict(d):
    """不要な空白や、スプレッドシート起因の欠損値をきれいにする"""
    cleaned = {}
    for k, v in d.items():
        if pd.isna(v) or v is None or str(v).strip() in ["nan", "NaN", ""]:
            cleaned[k] = ""
        elif isinstance(v, float) and v.is_integer():
            cleaned[k] = int(v)
        elif isinstance(v, str):
            cleaned[k] = v.strip()
        else:
            cleaned[k] = v
    return cleaned

# ==========================================
# 2. 同期処理のメイン関数
# ==========================================
def sync_spreadsheet_to_firestore():
    print("🚀 GASからSlack版データベースを取得中...")
    
    try:
        # GASから全データを一括取得
        res = requests.get(GAS_URL, params={"action": "get_all_data_raw"})
        data = res.json()
        
        if data.get("status") != "success":
            print("❌ GASからのデータ取得に失敗しました。")
            return

        payload = data.get("data", {})
        
        # ------------------------------------------------
        # [1] Users & Fixed Schedule の同期
        # ------------------------------------------------
        print("👥 ユーザー情報 (Slack対応版) を同期中...")
        users = payload.get("users", [])
        fixed_scheds = payload.get("fixed_schedule", [])
        
        # 🌟 変更点: Firestoreの既存ユーザー情報を先に取得し、機密データを保護する
        existing_users = {doc.id: doc.to_dict() for doc in db.collection("users").stream()}

        # 固定スケジュールのマッピング { "user_id": {"0": "000...", "1": "..."} }
        user_fixed_map = {}
        for fs in fixed_scheds:
            uid = str(fs.get('user_id', '')).strip()
            if not uid: continue
            if uid not in user_fixed_map: user_fixed_map[uid] = {}
            user_fixed_map[uid][str(fs.get('day_of_week', '')).strip()] = str(fs.get('binary_data', '')).strip()

        current_uids = set()
        batch = db.batch()
        for u in users:
            uid = str(u.get('user_id', '')).strip()
            if not uid: continue
            
            current_uids.add(uid)
            user_data = clean_dict(u)
            user_data['fixed_schedule'] = user_fixed_map.get(uid, {})
            
            # 🌟 変更点: Firestoreに既に存在するユーザーの場合、スプレッドシートのダミー文字で上書きしない
            if uid in existing_users:
                exist_u = existing_users[uid]
                
                # PINの保護
                if user_data.get('pin') == 'PROTECTED' or not user_data.get('pin'):
                    user_data['pin'] = exist_u.get('pin', '')
                # 秘密の合言葉の保護
                if user_data.get('secret_word') == 'PROTECTED' or not user_data.get('secret_word'):
                    user_data['secret_word'] = exist_u.get('secret_word', '')
                # カレンダーURLの保護
                if user_data.get('calendar_url') == 'LINKED' or not user_data.get('calendar_url'):
                    user_data['calendar_url'] = exist_u.get('calendar_url', '')
            
            doc_ref = db.collection("users").document(uid)
            batch.set(doc_ref, user_data)
        
        # 削除処理（シートにいないユーザーをFirestoreから消す）
        for doc in db.collection("users").stream():
            if doc.id not in current_uids:
                batch.delete(doc.reference)
                print(f"  🗑️ 削除(User): {doc.id}")
        batch.commit()

        # ------------------------------------------------
        # [2] Events の同期
        # ------------------------------------------------
        print("📅 イベント情報を同期中...")
        events = payload.get("events", [])
        current_eids = set()
        batch = db.batch()
        for ev in events:
            eid = str(ev.get('event_id', '')).strip()
            if not eid: continue
            current_eids.add(eid)
            
            # 数値型とBoolean型の調整
            for k in ['start_time_idx', 'end_time_idx', 'start_idx', 'end_idx']:
                if k in ev and str(ev[k]).isdigit(): ev[k] = int(ev[k])
            for k in ['auto_close', 'is_private']:
                if k in ev: ev[k] = (str(ev[k]).lower() == 'true')
                
            event_data = clean_dict(ev)
            doc_ref = db.collection("events").document(eid)
            batch.set(doc_ref, event_data)
            
        for doc in db.collection("events").stream():
            if doc.id not in current_eids:
                batch.delete(doc.reference)
                print(f"  🗑️ 削除(Event): {doc.id}")
        batch.commit()

        # ------------------------------------------------
        # [3] Responses (回答) の同期
        # ------------------------------------------------
        print("📝 回答データを同期中...")
        responses_raw = payload.get("responses", [])
        
        # event_id _ user_id 単位で集約
        resp_agg = {}
        for r in responses_raw:
            eid = str(r.get('event_id', '')).strip()
            uid = str(r.get('user_id', '')).strip()
            if not eid or not uid: continue
            
            key = f"{eid}_{uid}"
            comment_str = str(r.get("comment", "")).strip()
            
            # 🌟 変更点: セルの個別メモ（cell_details）を取得
            cell_details_str = str(r.get("cell_details", "{}")).strip()
            if cell_details_str in ["nan", "NaN", ""]: cell_details_str = "{}"
            
            if key not in resp_agg:
                resp_agg[key] = {
                    "event_id": eid,
                    "user_id": uid,
                    "responses": [],
                    "comment": comment_str,
                    "cell_details": cell_details_str # 初期セット
                }
            resp_agg[key]["responses"].append({
                "date": str(r.get("date", "")).strip(),
                "binary_data": str(r.get("binary_data", "")).strip()
            })
            
            # コメントやメモがあれば上書き更新
            if comment_str and comment_str not in ["nan", "NaN"]:
                resp_agg[key]["comment"] = comment_str
            if cell_details_str != "{}":
                resp_agg[key]["cell_details"] = cell_details_str

        current_rids = set(resp_agg.keys())
        batch = db.batch()
        count = 0
        for rid, rdata in resp_agg.items():
            doc_ref = db.collection("responses").document(rid)
            batch.set(doc_ref, rdata)
            count += 1
            # Firestoreの1回のバッチ制限(500)対策
            if count % 400 == 0:
                batch.commit()
                batch = db.batch()

        for doc in db.collection("responses").stream():
            if doc.id not in current_rids:
                batch.delete(doc.reference)
                print(f"  🗑️ 削除(Response): {doc.id}")
                count += 1
                if count % 400 == 0:
                    batch.commit()
                    batch = db.batch()
                    
        if count % 400 != 0:
            batch.commit()

        print("✅ 全データの同期（全単射）が完了しました！")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")

if __name__ == "__main__":
    sync_spreadsheet_to_firestore()
