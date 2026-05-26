import streamlit as st
import pandas as pd
import json
import time
import urllib.parse
import os
from datetime import datetime, timedelta
import requests
import streamlit.components.v1 as components
import numpy as np
from google.oauth2 import service_account
from google.cloud import firestore
import threading
import uuid
import hashlib
import random  

def hash_pin(pin_str):
    """PINをSHA-256でハッシュ化する関数"""
    if not pin_str: return ""
    return hashlib.sha256(pin_str.encode('utf-8')).hexdigest()

st.set_page_config(page_title="SSScheduler", layout="wide")

APP_BASE_URL = "https://schedule-adjust-SSSRC.streamlit.app/"

# ==========================================
# UX改善: ロード中表示＆時間割テーブル用CSS
# ==========================================
st.markdown("""
    <style>
        @media (max-width: 650px) {
            .main .block-container,
            div[data-testid="stAppViewBlockContainer"] {
                padding-left: 1rem !important; 
                padding-right: 1rem !important;
                padding-top: 1rem !important;
            }
            iframe { max-width: 100vw !important; width: 100% !important; }
        }
        
        .stDeployStatus, [data-testid="stStatusWidget"] label { display: none !important; }
        [data-testid="stStatusWidget"] { visibility: visible !important; display: flex !important; position: fixed !important; top: 50% !important; left: 50% !important; transform: translate(-50%, -50%) !important; background: rgba(255, 255, 255, 0.95) !important; color: #333 !important; padding: 20px 40px !important; border-radius: 12px !important; z-index: 999999 !important; border: 2px solid #4CAF50 !important; text-align: center !important; justify-content: center !important; }
        [data-testid="stStatusWidget"]::after { content: "⏳ 通信中 \\A 処理しています..."; white-space: pre-wrap; font-size: 20px !important; font-weight: bold !important; line-height: 1.5 !important; }
        
        .stApp, .stApp [data-testid="stAppViewBlockContainer"], div[data-testid="stVerticalBlock"], div[data-testid="stForm"], iframe { opacity: 1 !important; transition: none !important; filter: none !important; }
        .user-header { display: flex; align-items: center; justify-content: space-between; background: #f8f9fa; padding: 10px 20px; border-radius: 8px; border-left: 5px solid #4CAF50; margin-bottom: 20px; }
        .event-desc { background: #fff8e1; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107; margin-bottom: 20px; font-size: 14px; line-height: 1.6; }
        .event-desc a { color: #2196F3; font-weight: bold; text-decoration: none; }
        .tt-day-header { font-size: 16px; font-weight: bold; background: #4CAF50; color: white; padding: 8px; border-radius: 6px; text-align: center; }
        .tt-time-cell { font-size: 14px; font-weight: bold; background: #f0f2f6; padding: 10px; border-radius: 6px; text-align: center; border-left: 4px solid #4CAF50;}
        .tt-time-sub { font-size: 11px; color: #666; font-weight: normal; }
        .status-on { color: #fff; font-weight: bold; background: linear-gradient(135deg, #4CAF50, #45a049); padding: 4px 0; border-radius: 6px; border: none; font-size: 12px; text-align: center; margin-top: -10px; margin-bottom: 5px; display: block; box-shadow: 0 2px 4px rgba(76,175,80,0.3);}
        .af-status-on { color: #fff; font-weight: bold; background: linear-gradient(135deg, #2196F3, #1976D2); padding: 4px 0; border-radius: 6px; border: none; font-size: 12px; text-align: center; margin-top: -10px; margin-bottom: 5px; display: block; box-shadow: 0 2px 4px rgba(33,150,243,0.3);}
        .status-off { color: #9e9e9e; background: #ffffff; padding: 4px 0; border-radius: 6px; border: 1px dashed #d0d0d0; font-size: 12px; text-align: center; margin-top: -10px; margin-bottom: 5px; display: block;}
        
        .mobile-rotate-guide { display: none; }
        @media (max-width: 650px) and (orientation: portrait) {
            .mobile-rotate-guide {
                display: flex; align-items: center; justify-content: center;
                background: linear-gradient(135deg, #e8f5e9, #c8e6c9); color: #2e7d32;
                padding: 12px 15px; border-radius: 8px; margin-bottom: 20px;
                font-size: 13px; font-weight: bold; border-left: 5px solid #4CAF50;
            }
            .mobile-rotate-guide::before { content: "📱🔄"; font-size: 20px; margin-right: 10px; }
        }
    </style>
""", unsafe_allow_html=True)

GAS_URL = "https://script.google.com/macros/s/AKfycbx8GCHdyb9DDFIUajiKjceSn20-rfuEtsqrxCm-dD_pYsKou2Ie8mDkaM4oX3sKRX4SDQ/exec"

# ==========================================
# Firebase の初期化 ＆ 高速連携関数
# ==========================================
@st.cache_resource
def get_firestore_client():
    key_dict = dict(st.secrets["firebase"])
    if "private_key" in key_dict:
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
    creds = service_account.Credentials.from_service_account_info(key_dict)
    db = firestore.Client(credentials=creds, project=key_dict["project_id"])
    return db

db = get_firestore_client()

def backup_to_gas_async(action, payload=None):
    def _call():
        try:
            p = payload or {}
            p["action"] = action
            requests.post(GAS_URL, json=p)
        except Exception as e:
            print(f"GAS backup failed: {e}")
    threading.Thread(target=_call).start()

def save_response_hybrid(payload):
    try:
        event_id = payload["event_id"]
        user_id = payload["user_id"]
        
        cell_details_dict = json.loads(payload.get("cell_details", "{}"))
        if payload.get("comment"):
            cell_details_dict["global_comment"] = payload["comment"]
            
        final_cell_details_str = json.dumps(cell_details_dict, separators=(',', ':'))
        payload["cell_details"] = final_cell_details_str
        
        doc_ref = db.collection("responses").document(f"{event_id}_{user_id}")
        data = {
            "event_id": event_id,
            "user_id": user_id,
            "cell_details": final_cell_details_str,
            "responses": payload.get("responses", []), 
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        doc_ref.set(data)
    except Exception as e:
        st.error(f"Firestoreへの保存に失敗しました: {e}")
        return False

    backup_to_gas_async("submit_binary_response", {"payload": payload})
    return True

def get_app_data_from_firestore(user):
    user_id = str(user.get("user_id", ""))
    
    all_users = [doc.to_dict() for doc in db.collection("users").stream()]
    user_map = {str(u.get("user_id", "")): u for u in all_users}
    
    answered_ids = set()
    if user_id:
        ans_docs = db.collection("responses").where("user_id", "==", user_id).stream()
        for doc in ans_docs:
            answered_ids.add(doc.to_dict().get("event_id"))

    now = datetime.now()
    active_events = []
    
    user_groups = []
    for g_key in ['group_1', 'group_2', 'group_3', 'group_4']:
        user_groups.extend([g.strip() for g in str(user.get(g_key,"")).split(",") if g.strip()])
    
    expanded_user_groups = set(user_groups)
    if any(m in user_groups for m in ["ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ", "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ"]):
        expanded_user_groups.add("シスマネ")
    if any(k in user_groups for k in ["燃焼系長", "推進系長", "構造系長", "電装系長", "エンジン系長"]):
        expanded_user_groups.add("系長")
        
    all_events_docs = db.collection("events").stream()
    for doc in all_events_docs:
        ev = doc.to_dict()
        if ev.get("status") not in ["open", "closed"]: 
            continue
        
        ev_type = ev.get("type") or ev.get("event_type", "time")
        ev_close_time = ev.get("close_time") or ev.get("deadline", "")
        
        if ev.get("status") == "open" and ev.get("auto_close") and ev_close_time:
            try:
                dl_dt = pd.to_datetime(ev_close_time, errors='coerce')
                if pd.notna(dl_dt):
                    if dl_dt.tzinfo is not None:
                        dl_dt = dl_dt.tz_convert(None)
                    else:
                        dl_dt = dl_dt.tz_localize(None)
                        
                    if now > dl_dt:
                        ev["status"] = "closed"
                        db.collection("events").document(ev["event_id"]).update({"status": "closed"})
                        backup_to_gas_async("update_event_status", {"event_id": ev["event_id"], "status": "closed"})
            except: 
                pass

        is_target = True
        scope_str = ev.get("target_scope", "")
        if scope_str and scope_str.startswith("{"):
            try:
                scope = json.loads(scope_str)
                t_groups = scope.get("groups", [])
                t_users = scope.get("users", [])
                if t_groups or t_users:
                    in_group = any(g in expanded_user_groups for g in t_groups)
                    in_user = user_id in t_users
                    if not in_group and not in_user:
                        is_target = False
            except: 
                pass
            
        if is_target:
            ev["is_answered"] = ev["event_id"] in answered_ids
            if "deadline" not in ev and "close_time" in ev: ev["deadline"] = ev["close_time"]
            if "event_type" not in ev and "type" in ev: ev["event_type"] = ev["type"]
            active_events.append(ev)

    return all_users, active_events, user_map

def fetch_responses_for_event(event_id, user_map):
    docs = db.collection("responses").where("event_id", "==", event_id).stream()
    flat_responses = []
    for doc in docs:
        data = doc.to_dict()
        uid = str(data.get("user_id"))
        uinfo = user_map.get(uid, {})
        
        cell_details_str = data.get("cell_details", "{}")
        try:
            cell_details_dict = json.loads(cell_details_str)
            comment = cell_details_dict.get("global_comment", data.get("comment", ""))
        except:
            comment = data.get("comment", "")
        
        for r in data.get("responses", []):
            b_data = r.get("binary_data") or r.get("binary", "")
            flat_responses.append({
                "user_id": uid,
                "user_name": uinfo.get("name", "不明"),
                "group_1": uinfo.get("group_1", ""),
                "group_2": uinfo.get("group_2", ""),
                "group_3": uinfo.get("group_3", ""),
                "group_4": uinfo.get("group_4", ""),
                "date": r.get("date"),
                "binary_data": b_data,
                "binary": b_data, # 互換用
                "comment": comment,
                "cell_details": cell_details_str
            })
    return flat_responses

# ==========================================
# コンポーネント
# ==========================================
if not os.path.exists("rt_editor"):
    os.makedirs("rt_editor", exist_ok=True)
    with open("rt_editor/index.html", "w", encoding="utf-8") as f:
        f.write("""
        <!DOCTYPE html><html><head><meta charset="utf-8"><style>
            body { font-family: sans-serif; margin: 0; padding: 0; background: transparent;}
            .editor-container { border: 1px solid #ccc; border-radius: 6px; overflow: hidden; background: #fff; }
            .toolbar { background: #f8f9fb; padding: 6px; border-bottom: 1px solid #ccc; display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
            .toolbar button { background: #fff; border: 1px solid #ccc; border-radius: 4px; padding: 4px 10px; font-size: 13px; cursor: pointer; color: #333; transition: 0.2s; }
            .toolbar button:hover { background: #e9ecef; }
            textarea { width: 100%; height: 120px; border: none; padding: 10px; font-size: 14px; resize: vertical; outline: none; box-sizing: border-box; font-family: inherit; line-height: 1.5; }
        </style></head><body>
        <div class="editor-container">
            <div class="toolbar">
                <button onclick="insertTag('<b>', '</b>')" title="太字"><b>B</b> 太字</button>
                <button onclick="insertTag('<i>', '</i>')" title="斜体"><i>I</i> 斜体</button>
                <div style="width: 1px; height: 20px; background: #ccc; margin: 0 4px;"></div>
                <button onclick="insertRed()" title="赤文字"><span style="color:#FF4B4B; font-weight:bold;">A</span> 赤</button>
                <button onclick="insertBlue()" title="青文字"><span style="color:#2196F3; font-weight:bold;">A</span> 青</button>
                <div style="width: 1px; height: 20px; background: #ccc; margin: 0 4px;"></div>
                <button onclick="insertLink()" title="リンク">🔗 リンク追加</button>
            </div>
            <textarea id="editor" placeholder="📝 イベントの説明や注意事項を入力..."></textarea>
        </div>
        <script>
            function sendMessageToStreamlitClient(type, data) { window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*"); }
            function init() { sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1}); }
            function setComponentValue(value) { sendMessageToStreamlitClient("streamlit:setComponentValue", {value: value, dataType: "json"}); }
            const editor = document.getElementById('editor'); let timer;
            function sendValue() { setComponentValue(editor.value); }
            function insertTag(startTag, endTag) {
                const start = editor.selectionStart; const end = editor.selectionEnd; const val = editor.value; const selected = val.substring(start, end);
                editor.value = val.substring(0, start) + startTag + selected + endTag + val.substring(end); editor.focus();
                editor.selectionStart = start + startTag.length; editor.selectionEnd = end + startTag.length; sendValue();
            }
            function insertRed() { insertTag("<span style='color:#FF4B4B; font-weight:bold;'>", "</span>"); }
            function insertBlue() { insertTag("<span style='color:#2196F3; font-weight:bold;'>", "</span>"); }
            function insertLink() {
                const url = prompt('リンク先のURLを入力', 'https://');
                if (url) { const text = prompt('表示するテキストを入力', 'こちらをクリック'); if (text) { const linkTag = `<a href='${url}' target='_blank'>${text}</a>`; const start = editor.selectionStart; const val = editor.value; editor.value = val.substring(0, start) + linkTag + val.substring(editor.selectionEnd); sendValue(); } }
            }
            editor.addEventListener('blur', sendValue);
            window.addEventListener("message", function(event) { if (event.data.type === "streamlit:render") { sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: document.body.scrollHeight + 15}); } });
            init();
        </script></body></html>
        """)
rt_editor = components.declare_component("rt_editor", path="rt_editor")

if not os.path.exists("options_editor"):
    os.makedirs("options_editor", exist_ok=True)
    with open("options_editor/index.html", "w", encoding="utf-8") as f:
        f.write("""
        <!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body{margin:0;font-family:sans-serif;}
        .opt-card { background:#fff; border:1px solid #e0e0e0; border-radius:12px; padding:15px; margin-bottom:15px; box-shadow:0 2px 5px rgba(0,0,0,0.05); }
        .opt-title { font-size:18px; font-weight:bold; color:#2e7d32; margin-bottom:15px; text-align:center; }
        .btn-group { display:flex; gap:12px; }
        .opt-btn { flex:1; padding:20px 0; border-radius:12px; border:2px solid #ddd; background:#fff; font-size:18px; font-weight:bold; cursor:pointer; transition:all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275); color:#555; text-align:center; }
        .opt-btn[data-v="1"].active { background:#4CAF50; color:#fff; border-color:#4CAF50; box-shadow:0 6px 12px rgba(76,175,80,0.4); transform: translateY(-3px); }
        .opt-btn[data-v="2"].active { background:#FFEB3B; color:#333; border-color:#FBC02D; box-shadow:0 6px 12px rgba(255,235,59,0.4); transform: translateY(-3px); }
        .opt-btn[data-v="0"].active { background:#f5f5f5; color:#777; border-color:#ccc; transform: translateY(-3px); }
        #submit-btn { width: 100%; padding: 18px; background-color: #FF4B4B; color: white; border: none; border-radius: 12px; font-size: 20px; cursor: pointer; font-weight: bold; box-shadow: 0 6px 12px rgba(0,0,0,0.15); margin-top: 10px; transition:0.2s; }
        #submit-btn:hover { background-color: #e63946; transform: translateY(-2px); }
        textarea { width: 100%; padding: 15px; border: 1px solid #ccc; border-radius: 12px; font-family: inherit; font-size: 16px; margin-bottom:10px; resize:vertical; box-sizing: border-box; }
        </style></head><body>
        <div id="content"></div>
        <script>
        function sendMessageToStreamlitClient(type, data) { window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*"); }
        function init() { sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1}); }
        function setComponentValue(value) { sendMessageToStreamlitClient("streamlit:setComponentValue", {value: value, dataType: "json"}); }

        let optsData = [];
        let myComment = "";
        
        window.addEventListener("message", function(event) {
            if (event.data.type === "streamlit:render") {
                const args = event.data.args;
                if(window.lastEventId === args.eventId && window.lastSaveTs === args.saveTs) return; 
                window.lastEventId = args.eventId;
                window.lastSaveTs = args.saveTs;
                
                const opts = args.options;
                const myAnsBin = args.myAnsBin;
                myComment = args.myComment || "";
                const isClosed = args.isClosed;
                
                let html = "";
                optsData = [];
                
                opts.forEach((opt, i) => {
                    let v = i < myAnsBin.length ? parseInt(myAnsBin[i]) : 0;
                    optsData.push(v);
                    let pointerEv = isClosed ? "pointer-events:none; opacity:0.7;" : "";
                    
                    html += `
                    <div class="opt-card" style="${pointerEv}">
                        <div class="opt-title">📅 ${opt}</div>
                        <div class="btn-group" id="group-${i}">
                            <button class="opt-btn ${v===0 ? 'active':''}" data-v="0" onclick="setOpt(${i}, 0)">× 不可</button>
                            <button class="opt-btn ${v===2 ? 'active':''}" data-v="2" onclick="setOpt(${i}, 2)">△ 未定</button>
                            <button class="opt-btn ${v===1 ? 'active':''}" data-v="1" onclick="setOpt(${i}, 1)">◯ 可</button>
                        </div>
                    </div>`;
                });
                
                if(!isClosed) {
                    html += `
                    <div class="opt-card">
                        <div style="font-size:16px; font-weight:bold; margin-bottom:10px; color:#333;">📝 自分の備考・コメント</div>
                        <textarea id="comment-box" rows="2" placeholder="遅刻・早退などの連絡事項">${myComment}</textarea>
                        <button id="submit-btn" onclick="submitData()">✅ 回答を保存して提出</button>
                    </div>`;
                } else {
                    html += `
                    <div class="opt-card">
                        <div style="font-size:16px; font-weight:bold; margin-bottom:10px; color:#333;">📝 自分の備考・コメント</div>
                        <div style="padding:15px; background:#eee; border-radius:12px; min-height:50px; font-size:16px;">${myComment}</div>
                    </div>`;
                }
                
                document.getElementById("content").innerHTML = html;
                setTimeout(() => sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: document.getElementById('content').scrollHeight + 50}), 150);
            }
        });
        
        window.setOpt = function(idx, val) {
            optsData[idx] = val;
            const btns = document.getElementById('group-' + idx).querySelectorAll('.opt-btn');
            btns.forEach(b => b.classList.remove('active'));
            document.getElementById('group-' + idx).querySelector(`[data-v="${val}"]`).classList.add('active');
        };
        
        window.submitData = function() {
            const btn = document.getElementById("submit-btn");
            btn.innerText = "⏳ 保存処理中...";
            btn.style.pointerEvents = "none";
            const comment = document.getElementById("comment-box").value;
            setComponentValue({
                trigger_save: true,
                binary: optsData.join(''),
                comment: comment,
                ts: Date.now()
            });
        };
        init();
        </script></body></html>
        """)
options_editor = components.declare_component("options_editor", path="options_editor")


# 🚀 💡 v14へアップデート（レイアウトの左寄りバグ修正＆キャッシュクリア）
if not os.path.exists("custom_editor_v14"):
    os.makedirs("custom_editor_v14", exist_ok=True)
    with open("custom_editor_v14/index.html", "w", encoding="utf-8") as f:
        f.write("""
        <!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body{margin:0;font-family:sans-serif;} *{box-sizing:border-box;}
        .pen-btn { padding: 0; border-radius: 50%; width: 45px; height: 45px; border: none; cursor: pointer; font-weight: bold; font-size: 14px; transition: transform 0.2s, box-shadow 0.2s; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 4px rgba(0,0,0,0.15); margin: 0 auto; }
        .pen-btn:hover { opacity: 0.8; }
        .pen-btn.active { border: 3px solid #333 !important; transform: scale(1.1); box-shadow: 0 4px 8px rgba(0,0,0,0.3); }
        
        #detail-modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:999999;justify-content:center;align-items:center;backdrop-filter:blur(2px);}
        .modal-content{background:#fff;width:320px;padding:20px;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,0.2);position:relative;}
        .modal-title{font-size:16px;font-weight:bold;color:#333;margin-bottom:10px;border-bottom:2px solid #4CAF50;padding-bottom:5px;}
        .modal-label{font-size:12px;font-weight:bold;color:#666;margin-top:15px;display:block;}
        .modal-select, .modal-input{width:100%;padding:8px;margin-top:5px;border:1px solid #ccc;border-radius:6px;font-size:14px;}
        .status-switch{display:flex;gap:8px;margin-top:5px;}
        .sw-btn{flex:1;padding:8px;border:1px solid #ddd;border-radius:6px;cursor:pointer;font-size:13px;font-weight:bold;background:#f9f9f9;color:#555;transition:0.2s;}
        .sw-btn.active[data-v="1"]{background:#4CAF50;color:white;border-color:#4CAF50;}
        .sw-btn.active[data-v="2"]{background:#FFEB3B;color:#333;border-color:#FBC02D;}
        .sw-btn.active[data-v="0"]{background:#fff;color:#333;border-color:#999;}
        .modal-btns{display:flex;gap:10px;margin-top:20px;}
        .modal-btn-save{flex:1;background:#4CAF50;color:white;border:none;padding:12px;border-radius:6px;font-weight:bold;cursor:pointer;}
        .memo-icon{position:absolute;top:1px;right:2px;font-size:10px;line-height:1;filter:drop-shadow(1px 1px 1px rgba(255,255,255,0.8));pointer-events:none;}
        .c{position:relative;transition:filter 0.1s;}
        </style></head><body>
        
        <div id="palette" style="position:fixed; top:20px; right:30px; z-index:99999; background:rgba(255,255,255,0.95); border:1px solid #ddd; border-radius:12px; box-shadow:0 8px 24px rgba(0,0,0,0.2); padding:12px 8px; cursor:move; display:none; flex-direction:column; gap:12px; backdrop-filter: blur(8px);">
            <div style="font-size:12px; font-weight:bold; color:#666; text-align:center; pointer-events:none; user-select:none; margin-bottom:-4px;">🖊️ ペン</div>
            <button class="pen-btn active" onclick="window.setPen(1)" id="pen-1" style="background:#4CAF50; color:#fff;">可</button>
            <button class="pen-btn" onclick="window.setPen(2)" id="pen-2" style="background:#FFEB3B; color:#333;">未定</button>
            <button class="pen-btn" onclick="window.setPen(0)" id="pen-0" style="background:#fff; color:#333; border:1px solid #ccc; font-size:12px;">🧽<br>消す</button>
            <hr style="margin:0; border-top:1px solid #ddd;">
            <button class="pen-btn" onclick="window.setPen(-2)" id="pen--2" style="background:#2196F3; color:#fff; border:2px solid #1976D2; font-size:11px;">ℹ️<br>詳細</button>
            <button class="pen-btn" onclick="window.setPen(-1)" id="pen--1" style="background:#9C27B0; color:#fff; border:2px solid #7B1FA2; font-size:10px; margin-top:0px;">📜<br>ｽｸﾛｰﾙ</button>
        </div>

        <div id="detail-modal">
            <div class="modal-content" id="modal-content-box">
                <div class="modal-title" id="modal-cell-title">詳細設定</div>
                <label class="modal-label">🚥 予定のステータス</label>
                <div class="status-switch">
                    <button class="sw-btn" data-v="1" onclick="setModalStatus(1)">◯ 可</button>
                    <button class="sw-btn" data-v="2" onclick="setModalStatus(2)">△ 未定</button>
                    <button class="sw-btn" data-v="0" onclick="setModalStatus(0)">× 不可</button>
                </div>
                <label class="modal-label">📝 補足コメント (任意)</label>
                <input type="text" id="modal-note" class="modal-input" placeholder="例: 13:30に移動開始, 20分遅延">
                <div class="modal-btns">
                    <button class="modal-btn-save" onclick="saveModal()">💾 保存して閉じる</button>
                </div>
                <div style="text-align:center; font-size:10px; color:#999; margin-top:10px;">※枠外をタップでキャンセル</div>
            </div>
        </div>

        <div id="content"></div><script>
        function sendMessageToStreamlitClient(type, data) { window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*"); }
        function init() { sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1}); }
        function setComponentValue(value) { sendMessageToStreamlitClient("streamlit:setComponentValue", {value: value, dataType: "json"}); }
        
        let currentWeek = 0; let totalDays = 0; let numRows = 0; let unavailColRows = {};
        window.cellDetails = {}; 
        let modalStatus = 1; let selectedMode = 1; let editingCell = null;

        window.changeWeek = function(delta) {
            currentWeek += delta;
            const maxWeek = Math.ceil(totalDays / 7) - 1;
            if(currentWeek < 0) currentWeek = 0;
            if(currentWeek > maxWeek) currentWeek = maxWeek;
            window.renderWeek();
        };

        window.renderWeek = function() {
            const dayCols = document.querySelectorAll('.day-col');
            let visibleCount = 0;
            dayCols.forEach((col, i) => {
                if(currentWeek === 0 && i < 7) { col.style.display = 'block'; visibleCount++; }
                else if(currentWeek === 1 && i >= 7 && i < 14) { col.style.display = 'block'; visibleCount++; }
                else if(currentWeek === 2 && i >= 14 && i < 21) { col.style.display = 'block'; visibleCount++; }
                else if(currentWeek === 3 && i >= 21 && i < 28) { col.style.display = 'block'; visibleCount++; }
                else if(currentWeek === 4 && i >= 28 && i < 35) { col.style.display = 'block'; visibleCount++; }
                else col.style.display = 'none';
            });
            const btnPrev = document.getElementById('btn-prev');
            const btnNext = document.getElementById('btn-next');
            if(btnPrev) btnPrev.disabled = (currentWeek === 0);
            if(btnNext) btnNext.disabled = (currentWeek >= Math.ceil(totalDays / 7) - 1);
            
            const g = document.getElementById('g');
            if (g && visibleCount > 0) {
                g.style.gridTemplateColumns = `65px repeat(${visibleCount}, minmax(85px, 1fr))`;
            }
        };

        const modalBg = document.getElementById('detail-modal');
        modalBg.addEventListener('mousedown', function(e) { if(e.target === this) closeModal(); });
        modalBg.addEventListener('touchstart', function(e) { if(e.target === this) closeModal(); }, {passive: true});

        window.setModalStatus = function(v) {
            modalStatus = v;
            document.querySelectorAll('.sw-btn').forEach(b => { b.classList.toggle('active', parseInt(b.dataset.v) === v); });
        };

        window.openModal = function(cell) {
            editingCell = cell; const r = cell.dataset.r; const c = cell.dataset.c; const key = `${r}_${c}`;
            
            const detail = window.cellDetails[key] || {note: ""};
            setModalStatus(parseInt(cell.dataset.v) || 1);
            document.getElementById('modal-note').value = detail.note || "";
            document.getElementById('detail-modal').style.display = 'flex';
        };

        window.closeModal = function() {
            document.getElementById('detail-modal').style.display = 'none';
            if (editingCell) { editingCell = null; }
        };

        window.saveModal = function() {
            if(!editingCell) return;
            const r = editingCell.dataset.r; const c = editingCell.dataset.c; const key = `${r}_${c}`;
            const note = document.getElementById('modal-note').value.trim();
            if(note || modalStatus === 0) { window.cellDetails[key] = {note: note}; window.upd(editingCell, modalStatus); }
            else { delete window.cellDetails[key]; window.upd(editingCell, modalStatus); }
            closeModal();
        };

        window.paintCell = function(cell, mode) {
            if(!cell) return;
            const key = `${cell.dataset.r}_${cell.dataset.c}`;
            
            if (mode == 1 || mode == 2) {
                let existingNote = window.cellDetails[key] ? window.cellDetails[key].note : "";
                window.cellDetails[key] = {note: existingNote};
            } else if (mode == 0) {
                let detail = window.cellDetails[key];
                if (detail && (detail.note === "バイト/サークル等" || detail.note === "バイト/私用")) { }
                else { delete window.cellDetails[key]; }
            }
            window.upd(cell, mode);
        };

        window.upd = function(el, v) { 
            el.dataset.v = v; const key = `${el.dataset.r}_${el.dataset.c}`; let detail = window.cellDetails[key];
            
            let note = detail ? detail.note : "";
            
            let bgColor = '#fff'; let txt = ''; let txtColor = '#fff'; let opacity = 1.0;

            if (v == 1) {
                bgColor = "#4CAF50"; txt = "◯"; txtColor = "#fff";
            } else if (v == 2) {
                bgColor = "#FFEB3B"; txt = "△"; txtColor = "#333";
            } else if (v == 3) {
                bgColor = '#E0E0E0'; txt = '授'; txtColor = '#555';
            } else if (v == 0 && (note === "バイト/サークル等" || note === "バイト/私用")) {
                bgColor = '#f5f5f5'; txt = '休'; txtColor = '#aaa';
            }
            
            el.style.backgroundColor = bgColor;
            el.style.opacity = opacity;
            el.style.backgroundImage = 'none';
            el.style.color = txtColor;
            el.style.display = 'flex';
            el.style.alignItems = 'center';
            el.style.justifyContent = 'center';

            const showMemo = detail && detail.note !== "";
            let innerHtml = '<span style="font-size:14px; font-weight:bold; pointer-events:none;">' + txt + '</span>';
            if (showMemo) { innerHtml += '<div class="memo-icon">💬</div>'; }
            
            el.innerHTML = innerHtml;
        };
        
        window.doBulk = function(btnEl) {
            const val = document.getElementById('b-val').value;
            const sIdx = parseInt(document.getElementById('b-start').value); const eIdx = parseInt(document.getElementById('b-end').value);
            if(sIdx > eIdx) { alert('エラー：開始時刻は終了時刻より前に設定してください。'); return; }
            document.querySelectorAll('.b-day-chk').forEach(chk => { if(chk.checked) { const cIdx = parseInt(chk.value); for(let r = sIdx; r <= eIdx; r++) { const cell = document.querySelector(`[data-r="${r}"][data-c="${cIdx}"]`); if(cell && cell.classList.contains('c')) window.paintCell(cell, val); } } });
            const origText = btnEl.innerText; btnEl.innerText = "✅ 完了"; setTimeout(() => btnEl.innerText = origText, 1500);
        };
        window.doCopy = function(btnEl) {
            const srcIdx = parseInt(document.getElementById('c-src').value);
            let srcData = []; for(let r = 0; r < numRows; r++) { const cell = document.querySelector(`[data-r="${r}"][data-c="${srcIdx}"]`); srcData.push((cell && cell.classList.contains('c')) ? cell.dataset.v : 0); }
            let copied = false;
            document.querySelectorAll('.c-tgt-chk').forEach(chk => { if(chk.checked) { const cIdx = parseInt(chk.value); if(cIdx !== srcIdx) { copied = true; for(let r = 0; r < numRows; r++) { const cell = document.querySelector(`[data-r="${r}"][data-c="${cIdx}"]`); if(cell && cell.classList.contains('c')) window.paintCell(cell, srcData[r]); } } } });
            if(!copied) { alert('コピー先を選択してください。'); return; }
            const origText = btnEl.innerText; btnEl.innerText = "✅ 完了"; setTimeout(() => btnEl.innerText = origText, 1500);
        };
        
        window.doTimetable = function(btnEl) {
            if(!unavailColRows || Object.keys(unavailColRows).length === 0) { alert('時間割が登録されていないか、対象日がありません。'); return; }
            for(let c = 0; c < totalDays; c++) {
                let key = String(c);
                if (unavailColRows[key]) {
                    unavailColRows[key].forEach(item => {
                        const r = (typeof item === 'object') ? item.row : item; const note = (typeof item === 'object') ? item.campus : ""; const cell = document.querySelector(`[data-r="${r}"][data-c="${c}"]`);
                        if(cell && cell.classList.contains('c')) {
                            const cellKey = `${r}_${c}`;
                            if (note === "💼 バイト/サークル等" || note === "💼 バイト/私用") { window.cellDetails[cellKey] = {note: "バイト/サークル等"}; window.paintCell(cell, 0); }
                            else { window.cellDetails[cellKey] = {note: "定期授業"}; window.paintCell(cell, 3); }
                        }
                    });
                }
            }
            const origText = btnEl.innerHTML; btnEl.innerHTML = "✅ 反映完了！"; setTimeout(() => btnEl.innerHTML = origText, 2000);
        };
        
        window.toggleList = function(id) { const el = document.getElementById(id); el.style.display = el.style.display === 'none' ? 'block' : 'none'; };
        document.addEventListener('click', function(e) { if(!e.target.closest('.ms-container')) { document.querySelectorAll('.ms-options').forEach(el => el.style.display = 'none'); } });

        window.setPen = function(mode) {
            selectedMode = mode;
            [-2, -1, 0, 1, 2].forEach(m => {
                const b = document.getElementById('pen-' + m);
                if(b) b.classList.remove('active');
            });
            const activeBtn = document.getElementById('pen-' + mode);
            if (activeBtn) activeBtn.classList.add('active');
            
            const g = document.getElementById('g');
            if (g) {
                if (mode === -1) { g.style.touchAction = 'pan-x pan-y'; }
                else { g.style.touchAction = 'none'; }
            }
        };

        const palette = document.getElementById('palette');
        let isDraggingPalette = false;
        let offsetX, offsetY;

        palette.addEventListener('mousedown', e => {
            if (e.target.tagName.toLowerCase() === 'button') return;
            isDraggingPalette = true;
            offsetX = e.clientX - palette.getBoundingClientRect().left;
            offsetY = e.clientY - palette.getBoundingClientRect().top;
        });
        document.addEventListener('mousemove', e => {
            if (!isDraggingPalette) return;
            palette.style.left = (e.clientX - offsetX) + 'px';
            palette.style.top = (e.clientY - offsetY) + 'px';
            palette.style.right = 'auto';
        });
        document.addEventListener('mouseup', () => { isDraggingPalette = false; });

        palette.addEventListener('touchstart', e => {
            if (e.target.tagName.toLowerCase() === 'button') return;
            isDraggingPalette = true;
            const touch = e.touches[0];
            offsetX = touch.clientX - palette.getBoundingClientRect().left;
            offsetY = touch.clientY - palette.getBoundingClientRect().top;
        }, {passive: false});
        document.addEventListener('touchmove', e => {
            if (!isDraggingPalette) return;
            const touch = e.touches[0];
            palette.style.left = (touch.clientX - offsetX) + 'px';
            palette.style.top = (touch.clientY - offsetY) + 'px';
            palette.style.right = 'auto';
            e.preventDefault();
        }, {passive: false});
        document.addEventListener('touchend', () => { isDraggingPalette = false; });

        window.addEventListener("message", function(event) {
            if (event.data.type === "streamlit:render") {
                const args = event.data.args; 
                
                if(window.lastEventId === args.eventId && window.lastSaveTs === args.saveTs) {
                    return;
                }
                if(window.lastEventId !== args.eventId) { currentWeek = 0; }
                window.lastEventId = args.eventId;
                window.lastSaveTs = args.saveTs;
                
                document.getElementById("content").innerHTML = args.html_code;
                totalDays = args.cols; numRows = args.rows; unavailColRows = args.unavailColRows || {};
                window.cellDetails = args.cellDetails || {}; 
                
                const detailsEl = document.querySelector('details');
                if (detailsEl) {
                    detailsEl.addEventListener('toggle', () => {
                        setTimeout(() => sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: document.body.scrollHeight + 50}), 150);
                    });
                }
                
                window.renderWeek();
                
                if(args.isClosed) { palette.style.display = 'none'; return; } 
                else { palette.style.display = 'flex'; }
                
                setTimeout(() => { window.setPen(selectedMode); }, 50);
                
                const g = document.getElementById('g'); if(!g) return;
                let down = false;
                
                const handleStart = (e, x, y) => {
                    if (selectedMode === -1) return; // scroll mode
                    const cell = e.target.closest('.c'); if(!cell) return;
                    
                    if (selectedMode === -2) {
                        openModal(cell);
                        return; 
                    }

                    down = true; 
                    window.paintCell(cell, selectedMode);
                };

                const handleMove = (e, x, y) => {
                    if (selectedMode === -1 || selectedMode === -2 || !down) return;
                    if (e.cancelable) e.preventDefault(); 
                    
                    const cell = document.elementFromPoint(x, y)?.closest('.c');
                    if(cell) window.paintCell(cell, selectedMode);
                };

                const handleEnd = () => {
                    down = false;
                };

                g.onmousedown = e => { handleStart(e, e.clientX, e.clientY); };
                g.onmousemove = e => { handleMove(e, e.clientX, e.clientY); }
                window.onmouseup = handleEnd; window.onmouseleave = handleEnd; 

                g.addEventListener('touchstart', e => { 
                    if (e.touches.length > 1) return;
                    handleStart(e, e.touches[0].clientX, e.touches[0].clientY);
                }, {passive: true});
                
                g.addEventListener('touchmove', e => { 
                    if (selectedMode === -1 || selectedMode === -2) return; 
                    if (e.touches.length >= 2) return; 
                    if(down) { 
                        if (e.cancelable) e.preventDefault(); 
                        handleMove(e, e.touches[0].clientX, e.touches[0].clientY); 
                    } 
                }, {passive: false});
                
                g.addEventListener('touchend', handleEnd);
                g.addEventListener('touchcancel', handleEnd);
                
                const btn = document.getElementById("submit-btn");
                if(btn) { btn.onclick = () => { 
                    const res = Array.from({length: numRows}, (_, r) => Array.from({length: totalDays}, (_, c) => {
                        const cellNode = document.querySelector(`[data-r="${r}"][data-c="${c}"]`);
                        const val = cellNode && cellNode.dataset.v ? parseInt(cellNode.dataset.v) : 0;
                        return isNaN(val) ? 0 : val;
                    })); 
                    const commentBox = document.getElementById("comment-box");
                    const commentText = commentBox ? commentBox.value : ""; 
                    
                    setComponentValue({ data: res, comment: commentText, cell_details: window.cellDetails || {}, trigger_save: true, ts: Date.now() }); 
                    btn.innerText = "⏳ 保存処理中..."; btn.style.backgroundColor = "#ff7b7b"; btn.style.pointerEvents = "none"; palette.style.display = 'none'; 
                }; }
                document.querySelectorAll('.c').forEach(cell => { window.upd(cell, cell.dataset.v); });
                setTimeout(() => {
                    sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: document.body.scrollHeight + 50});
                }, 150);
            }
        }); init(); </script></body></html>
        """)

grid_editor = components.declare_component("grid_editor", path="custom_editor_v14")


# ==========================================
# ユーティリティとメイン処理
# ==========================================
def call_gas(action, payload=None, method="GET"):
    try:
        if method == "POST":
            p = payload or {}
            p["action"] = action
            res = requests.post(GAS_URL, json=p)
            return res.json()
        else:
            params = {"action": action}
            if payload:
                for k, v in payload.items():
                    if isinstance(v, (dict, list)):
                        params[k] = json.dumps(v)
                    else:
                        params[k] = v
            params["_t"] = datetime.now().timestamp() 
            res = requests.get(GAS_URL, params=params)
            return res.json()
    except Exception as e: 
        return {"status": "error", "message": str(e)}

def clear_cache():
    if "api_cache" in st.session_state: st.session_state.api_cache.clear()

def idx_to_time(i): return f"{(i*15)//60:02d}:{(i*15)%60:02d}"
time_master = [idx_to_time(i) for i in range(96)]

def get_border_top(t_str, event_type="time"):
    if event_type in ["timetable", "date_timetable"]: return "1px solid #aaa"
    if t_str.endswith(":00"): return "2px solid #555"
    elif t_str.endswith(":30"): return "1px dashed #999"
    else: return "1px solid #f0f0f0"

def format_deadline_jp(date_str):
    if not date_str or str(date_str).strip() == "" or date_str == "None": 
        return "期限なし"
    
    try:
        clean_str = str(date_str).split(' (')[0] 
        dt = pd.to_datetime(clean_str)
        wday = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]
        return f"{dt.month}/{dt.day}({wday}) {dt.strftime('%H:%M')}"
    except:
        return str(date_str)

# ==========================================
# 時間割マスターの定義（昼休みを追加）
# ==========================================
PERIODS_MASTER = [
    ("1限", "09:00〜", 36, 42, "p1"),
    ("2限", "10:45〜", 43, 49, "p2"),
    ("昼休み", "12:15〜", 49, 53, "lunch"), # 💡 追加
    ("3限", "13:15〜", 53, 59, "p3"),
    ("4限", "15:00〜", 60, 66, "p4"),
    ("5限", "16:45〜", 67, 73, "p5")
]

def main():
    if "app_initialized" not in st.session_state:
        st.session_state.app_initialized = True

    if st.session_state.get("save_success_msg"):
        st.toast(st.session_state.save_success_msg, icon="✅")
        st.session_state.save_success_msg = None

    if "event" in st.query_params:
        st.session_state.jump_to_event = st.query_params["event"]
        st.query_params.clear()

    if "auth" not in st.session_state: st.session_state.auth = None
    
    # 💡 グループの並び順（マスター）を定義
    MASTER_G1 = ["衛星", "ロケット", "BizSat"]
    MASTER_G2 = ["ミッション系", "電源系", "構造系", "通信系", "姿勢系", "熱系", "C＆DH系", "COLOURS燃焼系", "COLOURS推進系", "COLOURS構造系", "COLOURS電装系", "COLOURSエンジン系"]
    MASTER_G3 = ["執行部", "新入生教育", "広報", "イベント", "会計"]
    MASTER_G4_OPTS = ["PMs (衛星)", "PMs (ロケット)", "シスマネ", "系長", "エンジン系長"]

    def sort_groups(lst, master):
        return sorted(lst, key=lambda x: master.index(x) if x in master else 999)
    
    # ==========================================
    # 🔑 未ログイン画面
    # ==========================================
    if not st.session_state.auth:
        _, col_login, _ = st.columns([1, 2, 1])
        with col_login:
            st.title("SSScheduler")
            
            if "jump_to_event" in st.session_state:
                st.info("👋 イベントへの招待が届いています。ログインまたは新規登録をして回答してください。")
                
            login_mode = st.radio("メニュー", ["🔑 ログイン", "📝 新規アカウント作成", "🆘 PIN・パスワード復旧"], horizontal=True)
            st.markdown("---")
            
            if login_mode == "🔑 ログイン":
                with st.form("login_form"):
                    st.subheader("ログイン")
                    n = st.text_input("氏名", autocomplete="username")
                    p = st.text_input("PIN", type="password", autocomplete="current-password")
                    if st.form_submit_button("ログイン", use_container_width=True, type="primary"):
                        users_ref = db.collection("users").where("name", "==", n).stream()
                        user_doc = None
                        for doc in users_ref:
                            user_doc = doc.to_dict()
                            break
                        
                        if user_doc:
                            stored_pin = user_doc.get("pin", "")
                            hashed_input = hash_pin(p)
                            
                            # 1. ハッシュ化されたPINが一致するか確認
                            if stored_pin == hashed_input:
                                st.session_state.auth = user_doc
                                st.rerun()
                                
                            # 2. 【神機能】過去の平文PINのままのユーザーへの救済措置
                            elif stored_pin == p:
                                db.collection("users").document(user_doc["user_id"]).update({"pin": hashed_input})
                                user_doc["pin"] = hashed_input
                                st.session_state.auth = user_doc
                                st.rerun()
                            else:
                                st.error("認証失敗: 氏名またはPINが間違っています")
                        else:
                            st.error("認証失敗: ユーザーが存在しません")
            
            elif login_mode == "📝 新規アカウント作成":
                st.subheader("新規アカウント作成")
                st.info("💡 未所属（プロジェクトや役職なし）の方でも、そのまま下部の登録ボタンを押して利用可能です。")
                reg_n = st.text_input("氏名 (スペースは自動で削除されます)", key="reg_name", autocomplete="username")
                reg_p = st.text_input("PIN (自由な文字列・数字)", type="password", key="reg_pin", autocomplete="new-password")
                reg_s = st.text_input("🔑 秘密の合言葉 (PINを忘れた時に使います)", key="reg_secret")
                
                st.markdown("---")
                g1 = st.multiselect("🚀 プロジェクト", ["衛星", "ロケット", "BizSat"], key="reg_g1")
                g2_opts, g4_opts = [], []
                if "衛星" in g1:
                    g2_opts.extend(["ミッション系", "電源系", "構造系", "通信系", "姿勢系", "熱系", "C＆DH系"])
                    g4_opts.extend(["ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ", "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ", "PMs (衛星)"])
                if "ロケット" in g1:
                    g2_opts.extend(["COLOURS燃焼系", "COLOURS推進系", "COLOURS構造系", "COLOURS電装系", "COLOURSエンジン系"])
                    g4_opts.extend(["燃焼系長", "推進系長", "構造系長", "電装系長", "エンジン系長", "PMs (ロケット)"])
                
                g2_opts = list(dict.fromkeys(g2_opts)); g4_opts = list(dict.fromkeys(g4_opts))
                g2 = st.multiselect("🔧 系", g2_opts, key="reg_g2")
                g3 = st.multiselect("🏢 委員会", ["執行部", "新入生教育", "広報", "イベント", "会計"], key="reg_g3")
                g4 = st.multiselect("👑 役職", g4_opts, key="reg_g4")
                
                if st.button("✅ 登録してログイン", use_container_width=True, type="primary"):
                    clean_name = reg_n.replace(" ", "").replace("　", "")
                    if not clean_name or not reg_p or not reg_s: 
                        st.warning("氏名、PIN、秘密の合言葉はすべて必須です。")
                    else:
                        existing_check = list(db.collection("users").where("name", "==", clean_name).stream())
                        if existing_check:
                            st.error("エラー: その氏名は既に登録されています。")
                        else:
                            all_users_count = len(list(db.collection("users").stream()))
                            new_user_id = f"U{all_users_count + 1:03d}"
                            role = "top_admin" if all_users_count == 0 else "guest"
                            
                            new_u = {
                                "user_id": new_user_id,
                                "name": clean_name,
                                "pin": hash_pin(reg_p), 
                                "secret_word": hash_pin(reg_s),
                                "role": role,
                                "group_1": ", ".join(g1), "group_2": ", ".join(g2),
                                "group_3": ", ".join(g3), "group_4": ", ".join(g4),
                                "calendar_url": "", "fixed_schedule": {}
                            }
                            
                            try:
                                db.collection("users").document(new_user_id).set(new_u)
                                
                                gas_payload = new_u.copy()
                                gas_payload["pin"] = "PROTECTED"
                                gas_payload["secret_word"] = "PROTECTED"
                                backup_to_gas_async("register_user", {"payload": gas_payload})
                                
                                st.session_state.auth = new_u
                                st.rerun()
                            except Exception as e:
                                st.error(f"登録に失敗しました: {e}")
            
            elif login_mode == "🆘 PIN・パスワード復旧":
                st.subheader("PINの再設定")
                with st.expa
