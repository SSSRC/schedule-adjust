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
import hashlib
import random
import html as html_lib


# ==========================================
# 基本設定・定数
# ==========================================
st.set_page_config(page_title="SSScheduler", layout="wide", initial_sidebar_state="auto")

APP_BASE_URL = "https://schedule-adjust-SSSRC.streamlit.app/"
GAS_URL = "https://script.google.com/macros/s/AKfycbx8GCHdyb9DDFIUajiKjceSn20-rfuEtsqrxCm-dD_pYsKou2Ie8mDkaM4oX3sKRX4SDQ/exec"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MASTER_G1 = ["衛星", "ロケット", "BizSat"]
MASTER_G2 = [
    "ミッション系", "電源系", "構造系", "通信系", "姿勢系", "熱系", "C＆DH系",
    "COLOURS燃焼系", "COLOURS推進系", "COLOURS構造系", "COLOURS電装系", "COLOURSエンジン系",
]
MASTER_G3 = ["執行部", "新入生教育", "広報", "イベント", "会計"]
MASTER_G4_OPTS = ["PMs (衛星)", "PMs (ロケット)", "シスマネ", "系長", "エンジン系長"]

PERIODS_MASTER = [
    ("1限", "09:00〜", 36, 42, "p1"),
    ("2限", "10:45〜", 43, 49, "p2"),
    ("昼休み", "12:15〜", 49, 53, "lunch"),
    ("3限", "13:15〜", 53, 59, "p3"),
    ("4限", "15:00〜", 60, 66, "p4"),
    ("5限", "16:45〜", 67, 73, "p5"),
]

# 時間割モード(timetable)は昼休みを追加して7行表示にしつつ、
# 既存6行データ(bits[0..5])との後方互換性を100%維持するビット位置マップ
TIMETABLE_LABELS = ["1限", "2限", "昼休み", "3限", "4限", "5限", "放課後"]
TIMETABLE_BIT_MAP = {0: 0, 1: 1, 2: 6, 3: 2, 4: 3, 5: 4, 6: 5}

PERIOD_CLOCK_RANGES = {
    "1限": ("09:00", "10:30"),
    "2限": ("10:45", "12:15"),
    "昼休み": ("12:15", "13:15"),
    "3限": ("13:15", "14:45"),
    "4限": ("15:00", "16:30"),
    "5限": ("16:45", "18:15"),
    "放課後": ("18:30", "21:00"),
}

EVENT_TYPE_LABELS = {
    "time": "🕒 時間帯",
    "timetable": "🏫 時間割",
    "date_timetable": "📅 日付コマ",
    "options": "🗳️ 候補選択",
}


def _compact_html(raw_html):
    """Markdownの4スペースコードブロック誤判定を防ぐため、各行の先頭空白と空行を除去する"""
    return "\n".join(line.strip() for line in raw_html.splitlines() if line.strip())


# ==========================================
# グローバルCSS
# ==========================================
st.markdown(_compact_html("""
<style>
:root {
    --sss-menu-label: "メニュー";
}
.main .block-container,
div[data-testid="stAppViewBlockContainer"] {
    padding-top: 2.3rem !important;
    padding-bottom: 2rem !important;
}
@media (max-width: 650px) {
    .main .block-container,
    div[data-testid="stAppViewBlockContainer"] {
        padding-left: 0.65rem !important;
        padding-right: 0.65rem !important;
        padding-top: 2.6rem !important;
        padding-bottom: 1.5rem !important;
    }
    iframe { max-width: 100vw !important; width: 100% !important; }
}

iframe { border: none !important; background: transparent !important; }

/* 上部ヘッダーを極薄＆透過にしつつ、左上のサイドバー開閉ボタンを「メニュー」ピルとして目立たせる */
header[data-testid="stHeader"] {
    height: 2.5rem !important;
    min-height: 2.5rem !important;
    background: transparent !important;
    pointer-events: none !important;
}
header[data-testid="stHeader"] button,
header[data-testid="stHeader"] a,
div[data-testid="collapsedControl"],
div[data-testid="stSidebarCollapsedControl"],
div[data-testid="stToolbar"] {
    pointer-events: auto !important;
}
button[data-testid="stExpandSidebarButton"],
div[data-testid="collapsedControl"] button,
div[data-testid="stSidebarCollapsedControl"] button {
    background: linear-gradient(135deg, #0f172a, #1e293b) !important;
    color: #ffffff !important;
    border: 1.5px solid #10b981 !important;
    border-radius: 999px !important;
    padding: 4px 12px 4px 8px !important;
    height: 33px !important;
    min-height: 33px !important;
    width: auto !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 5px !important;
    box-shadow: 0 3px 10px rgba(15, 23, 42, 0.22) !important;
    margin-top: 2px !important;
    margin-left: 4px !important;
}
button[data-testid="stExpandSidebarButton"]:hover,
div[data-testid="collapsedControl"] button:hover,
div[data-testid="stSidebarCollapsedControl"] button:hover {
    background: #047857 !important;
    border-color: #34d399 !important;
}
button[data-testid="stExpandSidebarButton"] svg,
div[data-testid="collapsedControl"] button svg,
div[data-testid="stSidebarCollapsedControl"] button svg {
    fill: #34d399 !important;
    color: #34d399 !important;
}
button[data-testid="stExpandSidebarButton"]::after,
div[data-testid="collapsedControl"] button::after,
div[data-testid="stSidebarCollapsedControl"] button::after {
    content: var(--sss-menu-label, "メニュー");
    font-size: 12px !important;
    font-weight: 800 !important;
    color: #ffffff !important;
    letter-spacing: 0.02em !important;
    white-space: nowrap !important;
}

section[data-testid="stSidebar"] {
    background: #f8fafc !important;
    border-right: 1px solid #e2e8f0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {
    padding-top: 0.8rem !important;
}

/* localStorage用非表示コンポーネントが空白や白い枠を作らないようにする */
div.element-container:has(iframe[title*="auth_storage"]),
div[data-testid="stElementContainer"]:has(iframe[title*="auth_storage"]) {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}
iframe[title*="auth_storage"] {
    height: 0 !important;
    min-height: 0 !important;
    display: none !important;
}

.stDeployStatus, [data-testid="stStatusWidget"] label { display: none !important; }
[data-testid="stStatusWidget"] {
    visibility: visible !important; display: flex !important;
    position: fixed !important; top: 50% !important; left: 50% !important;
    transform: translate(-50%, -50%) !important;
    background: rgba(255, 255, 255, 0.95) !important; color: #333 !important;
    padding: 20px 40px !important; border-radius: 12px !important;
    z-index: 999999 !important; border: 2px solid #4CAF50 !important;
    text-align: center !important; justify-content: center !important;
}
[data-testid="stStatusWidget"]::after {
    content: "⏳ 通信中 \\A 処理しています...";
    white-space: pre-wrap; font-size: 18px !important; font-weight: bold !important; line-height: 1.5 !important;
}

.stApp, .stApp [data-testid="stAppViewBlockContainer"], div[data-testid="stVerticalBlock"], div[data-testid="stForm"], iframe {
    opacity: 1 !important; transition: none !important; filter: none !important;
}

/* サイドバー内ユーザーカード・イベント詳細コンパクトヘッダー */
.sb-user-card {
    background: linear-gradient(135deg, #ffffff, #ecfdf5);
    padding: 10px 12px; border-radius: 12px;
    border: 1px solid #d1fae5; border-left: 4px solid #10b981;
    margin-bottom: 10px; box-shadow: 0 2px 6px rgba(16,185,129,0.06);
}
.event-hero {
    background: linear-gradient(135deg, #ffffff, #f8fafc);
    border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 8px 12px; margin: 2px 0 5px 0;
    box-shadow: 0 1px 6px rgba(15,23,42,0.04);
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px;
}
.event-hero-title {
    font-size: 18px; font-weight: 800; color: #0f172a; margin: 0; line-height: 1.25;
}
@media (max-width: 650px) {
    .event-hero { padding: 7px 10px; margin: 0 0 4px 0; }
    .event-hero-title { font-size: 16px; }
}
.event-hero-pills {
    display: flex; flex-wrap: wrap; gap: 5px; align-items: center;
}
.hero-pill {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
}
.pill-answered { background: #dcfce7; color: #166534; }
.pill-unanswered { background: #fef3c7; color: #92400e; }
.pill-deadline { background: #fce7f3; color: #be185d; }
.pill-closed { background: #fee2e2; color: #b91c1c; }
.pill-private { background: #ede9fe; color: #5b21b6; }
.pill-outscope { background: #fff7ed; color: #c2410c; }

.event-desc {
    background: #f8fafc; padding: 7px 11px; border-radius: 9px;
    border: 1px solid #e2e8f0; border-left: 4px solid #10b981;
    margin: 2px 0 5px 0; font-size: 12.5px; line-height: 1.5; color: #334155;
    max-height: 86px; overflow-y: auto;
}
.event-desc a { color: #2563eb; font-weight: 700; text-decoration: none; }

/* 開催日時確定の統一カード（通知・カレンダー追加・コピー・取消を1区画に集約） */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sss-confirmed-box-marker) {
    background: linear-gradient(135deg, #ecfdf5, #f0fdf4) !important;
    border: 2px solid #10b981 !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 14px rgba(16,185,129,0.12) !important;
    margin: 4px 0 8px 0 !important;
}
.confirmed-banner-title {
    font-size: 12px; font-weight: 800; color: #047857; letter-spacing: 0.04em; margin-bottom: 3px;
}
.confirmed-banner-dt {
    font-size: 18px; font-weight: 800; color: #064e3b; margin-bottom: 4px;
}
.confirmed-banner-meta {
    font-size: 12.5px; color: #334155; line-height: 1.45; margin-bottom: 6px;
}

.dash-stats {
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 4px 0 12px 0;
}
.dash-stat-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 5px 12px; border-radius: 999px; font-size: 12.5px; font-weight: 800;
    border: 1px solid transparent;
}
.menu-hint-banner {
    display: inline-flex; align-items: center; gap: 6px;
    background: #f1f5f9; border: 1px solid #cbd5e1; color: #334155;
    padding: 4px 10px; border-radius: 999px; font-size: 11.5px; font-weight: 700;
}

.rank-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 10px 12px; margin-bottom: 6px;
    box-shadow: 0 2px 6px rgba(15,23,42,0.04);
}
.rank-card-1 { border-left: 5px solid #f59e0b; background: linear-gradient(90deg, #fffbeb, #ffffff 40%); }
.rank-card-2 { border-left: 5px solid #94a3b8; background: linear-gradient(90deg, #f8fafc, #ffffff 40%); }
.rank-card-3 { border-left: 5px solid #d97706; background: linear-gradient(90deg, #fff7ed, #ffffff 40%); }
.rank-dt { font-size: 14.5px; font-weight: 800; color: #0f172a; line-height: 1.3; margin-bottom: 5px; }
.rank-chips { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.r-chip { display: inline-block; font-size: 11.5px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }
.r-chip-score { background: #dcfce7; color: #166534; }
.r-chip-yes { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.r-chip-maybe { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.r-chip-no { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }

.active-filter-pill {
    display: inline-flex; align-items: center; gap: 6px; flex-wrap: wrap;
    background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af;
    border-radius: 10px; padding: 6px 12px; font-size: 12.5px; font-weight: 700;
    margin: 4px 0 10px 0;
}

.sss-badge {
    display: inline-block; font-size: 11px; font-weight: 700;
    padding: 2px 8px; border-radius: 999px; margin-right: 5px; margin-bottom: 3px;
}
.sss-badge-type { background: #e0f2fe; color: #0369a1; }
.sss-badge-confirmed { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
.sss-badge-closed { background: #fee2e2; color: #b91c1c; }

/* マーカー用空divの余白をゼロにする */
div.element-container:has(.sss-tab-switcher-marker),
div.element-container:has(.sss-top-action-marker),
div.element-container:has(.sss-rank-row-marker),
div.element-container:has(.sss-tt-row-marker),
div[data-testid="stElementContainer"]:has(.sss-tab-switcher-marker),
div[data-testid="stElementContainer"]:has(.sss-top-action-marker),
div[data-testid="stElementContainer"]:has(.sss-rank-row-marker),
div[data-testid="stElementContainer"]:has(.sss-tt-row-marker) {
    margin: 0 !important;
    padding: 0 !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
}

/* スマホでも上部操作・ランキング・入力/結果スイッチを省スペース横並びに最適化 */
@media (max-width: 650px) {
    div[data-testid="stVerticalBlock"]:has(> div .sss-tab-switcher-marker) div[data-testid="stHorizontalBlock"],
    div[data-testid="stVerticalBlock"]:has(> div .sss-top-action-marker) div[data-testid="stHorizontalBlock"],
    div[data-testid="stVerticalBlock"]:has(> div .sss-rank-row-marker) div[data-testid="stHorizontalBlock"],
    div[data-testid="stVerticalBlock"]:has(> div .sss-tt-row-marker) div[data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 6px !important;
        align-items: center !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-tab-switcher-marker) div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        flex: 1 1 48% !important;
        min-width: 0 !important;
        width: auto !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-top-action-marker) div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
        flex: 0 0 32% !important;
        min-width: 0 !important;
        width: auto !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-top-action-marker) div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child {
        flex: 1 1 66% !important;
        min-width: 0 !important;
        width: auto !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-top-action-marker) button {
        min-height: 36px !important;
        padding: 4px 8px !important;
        font-size: 12.5px !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-rank-row-marker) div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {
        flex: 1 1 auto !important;
        min-width: 0 !important;
        width: auto !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-rank-row-marker) div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:last-child {
        flex: 0 0 74px !important;
        min-width: 74px !important;
        width: 74px !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-rank-row-marker) button {
        padding: 6px 4px !important;
        font-size: 12px !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .sss-tt-row-marker) div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        flex: 1 1 0 !important;
        min-width: 0 !important;
        width: auto !important;
    }
}

/* 入力/集計 セグメントスイッチャー（すぐ下に予定表が見えるよう縦幅をスリム化） */
div[data-testid="stVerticalBlock"]:has(> div .sss-tab-switcher-marker) div[data-testid="stHorizontalBlock"] {
    background: #f1f5f9;
    padding: 4px;
    border-radius: 12px;
    border: 1px solid #cbd5e1;
    margin: 2px 0 6px 0;
}
div[data-testid="stVerticalBlock"]:has(> div .sss-tab-switcher-marker) button {
    border-radius: 9px !important;
    font-weight: 800 !important;
    min-height: 38px !important;
    padding: 4px 8px !important;
    font-size: 13.5px !important;
}

/* 時間割設定テーブル用 */
.tt-day-header { font-size: 15px; font-weight: bold; background: #4CAF50; color: white; padding: 6px 2px; border-radius: 6px; text-align: center; }
.tt-time-cell { font-size: 13px; font-weight: bold; background: #f0f2f6; padding: 8px 4px; border-radius: 6px; text-align: center; border-left: 4px solid #4CAF50; }
.tt-time-sub { font-size: 10px; color: #666; font-weight: normal; }
.status-on { color: #fff; font-weight: bold; background: linear-gradient(135deg, #4CAF50, #45a049); padding: 4px 0; border-radius: 6px; font-size: 11px; text-align: center; margin-top: -10px; margin-bottom: 4px; display: block; }
.af-status-on { color: #fff; font-weight: bold; background: linear-gradient(135deg, #2196F3, #1976D2); padding: 4px 0; border-radius: 6px; font-size: 11px; text-align: center; margin-top: -10px; margin-bottom: 4px; display: block; }
.status-off { color: #9e9e9e; background: #ffffff; padding: 4px 0; border-radius: 6px; border: 1px dashed #d0d0d0; font-size: 11px; text-align: center; margin-top: -10px; margin-bottom: 4px; display: block; }
</style>
"""), unsafe_allow_html=True)


# ==========================================
# Firebase 初期化 & キャッシュ層
# ==========================================
def hash_pin(pin_str):
    """PINをSHA-256でハッシュ化する"""
    if not pin_str:
        return ""
    return hashlib.sha256(pin_str.encode("utf-8")).hexdigest()


def make_auth_token(user_id, hashed_pin):
    """localStorage保持用の検証トークンを生成する（平文PINは保存しない）"""
    raw = f"{user_id}:{hashed_pin}:ssscheduler_v2"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@st.cache_resource
def get_firestore_client():
    key_dict = dict(st.secrets["firebase"])
    if "private_key" in key_dict:
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])


db = get_firestore_client()


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_all_users_cached():
    return [doc.to_dict() for doc in db.collection("users").stream()]


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_all_events_cached():
    return [doc.to_dict() for doc in db.collection("events").stream()]


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_user_answered_ids_cached(user_id):
    if not user_id:
        return set()
    ans_docs = db.collection("responses").where("user_id", "==", user_id).stream()
    return {doc.to_dict().get("event_id") for doc in ans_docs}


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_event_responses_raw_cached(event_id):
    docs = db.collection("responses").where("event_id", "==", event_id).stream()
    return [doc.to_dict() for doc in docs]


def invalidate_cache(scope="all"):
    """指定されたスコープのFirestoreキャッシュを即時クリアする"""
    if scope in ("all", "users"):
        _fetch_all_users_cached.clear()
    if scope in ("all", "events"):
        _fetch_all_events_cached.clear()
    if scope in ("all", "responses"):
        _fetch_user_answered_ids_cached.clear()
        _fetch_event_responses_raw_cached.clear()


def backup_to_gas_async(action, payload=None):
    def _call():
        try:
            p = dict(payload) if payload else {}
            p["action"] = action
            requests.post(GAS_URL, json=p, timeout=20)
        except Exception as e:
            print(f"GAS backup failed: {e}")
    threading.Thread(target=_call, daemon=True).start()


def call_gas(action, payload=None, method="GET"):
    try:
        if method == "POST":
            p = dict(payload) if payload else {}
            p["action"] = action
            res = requests.post(GAS_URL, json=p, timeout=25)
            return res.json()
        params = {"action": action}
        if payload:
            for k, v in payload.items():
                params[k] = json.dumps(v) if isinstance(v, (dict, list)) else v
        params["_t"] = datetime.now().timestamp()
        res = requests.get(GAS_URL, params=params, timeout=25)
        return res.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==========================================
# ドメイン・後方互換ユーティリティ関数
# ==========================================
def idx_to_time(i):
    return f"{(i * 15) // 60:02d}:{(i * 15) % 60:02d}"


time_master = [idx_to_time(i) for i in range(96)]


def sort_groups(lst, master):
    return sorted(lst, key=lambda x: master.index(x) if x in master else 999)


def expand_user_groups(user):
    """ユーザーの全所属グループを展開して集合で返す"""
    user_groups = []
    for g_key in ["group_1", "group_2", "group_3", "group_4"]:
        user_groups.extend([g.strip() for g in str(user.get(g_key, "")).split(",") if g.strip()])
    exp = set(user_groups)
    if any(m in user_groups for m in [
        "ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ",
        "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ",
    ]):
        exp.add("シスマネ")
    if any(k in user_groups for k in ["燃焼系長", "推進系長", "構造系長", "電装系長", "エンジン系長"]):
        exp.add("系長")
    return exp


def is_in_scope(user_groups_list, user_id, scope_str):
    """ユーザーがイベントのターゲット範囲内か判定する"""
    if not scope_str or not str(scope_str).startswith("{"):
        return True
    try:
        scope = json.loads(scope_str)
        t_groups = scope.get("groups", [])
        t_users = scope.get("users", [])
        if not t_groups and not t_users:
            return True

        exp_groups = set(user_groups_list)
        if any(m in user_groups_list for m in [
            "ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ",
            "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ",
        ]):
            exp_groups.add("シスマネ")
        if any(k in user_groups_list for k in ["燃焼系長", "推進系長", "構造系長", "電装系長", "エンジン系長"]):
            exp_groups.add("系長")

        return any(g in exp_groups for g in t_groups) or (str(user_id) in [str(u) for u in t_users])
    except Exception:
        return True


def format_deadline_jp(date_str):
    if not date_str or str(date_str).strip() == "" or str(date_str) == "None":
        return "期限なし"
    try:
        clean_str = str(date_str).split(" (")[0]
        dt = pd.to_datetime(clean_str)
        wday = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]
        return f"{dt.month}/{dt.day}({wday}) {dt.strftime('%H:%M')}"
    except Exception:
        return str(date_str)


def format_target_scope(scope_str, user_map):
    if not scope_str:
        return "全員"
    try:
        scope = json.loads(scope_str)
        groups = scope.get("groups", [])
        user_ids = scope.get("users", [])
        parts = []
        if groups:
            parts.append("Gr: " + ", ".join(groups))
        if user_ids:
            names = [str(user_map.get(str(uid), str(uid))) for uid in user_ids]
            parts.append("User: " + ", ".join(names))
        return " / ".join(parts) if parts else "全員"
    except Exception:
        return "全員"


def normalize_event_dict(raw_ev):
    """古いイベントデータのフィールド名ゆれを吸収したコピーを返す"""
    ev = dict(raw_ev)
    if "deadline" not in ev and "close_time" in ev:
        ev["deadline"] = ev["close_time"]
    if "event_type" not in ev and "type" in ev:
        ev["event_type"] = ev["type"]
    return ev


def compute_date_grid(start_date_val, end_date_val):
    """
    対象期間(start_date_val..end_date_val)のみの実日付列を生成する。
    旧UIの日曜〜土曜パディング列は廃止しつつ、旧cell_details復元用の
    legacy_col_map ({date_str: old_padded_col_idx}) も併せて返す。
    """
    try:
        curr = pd.to_datetime(start_date_val, errors="coerce").date()
        end_d = pd.to_datetime(end_date_val, errors="coerce").date()
        if pd.isna(curr) or pd.isna(end_d):
            raise ValueError("invalid date")
    except Exception:
        curr = datetime.today().date()
        end_d = curr + timedelta(days=7)

    if end_d < curr:
        end_d = curr

    days_to_subtract = (curr.weekday() + 1) % 7
    legacy_calendar_start = curr - timedelta(days=days_to_subtract)

    date_objs = []
    d = curr
    while d <= end_d:
        date_objs.append(d)
        d += timedelta(days=1)

    wday_jp = ["月", "火", "水", "木", "金", "土", "日"]
    date_strs = [x.strftime("%Y-%m-%d") for x in date_objs]
    clean_date_labels = [f"{x.strftime('%m/%d')}({wday_jp[x.weekday()]})" for x in date_objs]
    week_breaks = [(i > 0 and x.weekday() == 0) for i, x in enumerate(date_objs)]
    day_kinds = ["sat" if x.weekday() == 5 else ("sun" if x.weekday() == 6 else "weekday") for x in date_objs]
    legacy_col_map = {x.strftime("%Y-%m-%d"): (x - legacy_calendar_start).days for x in date_objs}

    return date_objs, date_strs, clean_date_labels, week_breaks, day_kinds, legacy_col_map


def _has_new_date_keys(cd_dict):
    for k in cd_dict.keys():
        ks = str(k)
        if ks == "global_comment" or "_" not in ks:
            continue
        suffix = ks.split("_", 1)[1]
        if not suffix.lstrip("-").isdigit():
            return True
    return False


def get_cell_note(cd_dict, orig_r_idx, date_str, legacy_col_idx=None, event_type="time"):
    """
    セルの補足メモを取得する。
    新形式 '{row}_{date_str}' を優先し、存在しない場合は旧形式 '{row}_{legacy_col_idx}' を参照する。
    """
    if not isinstance(cd_dict, dict):
        return ""
    new_key = f"{orig_r_idx}_{date_str}"
    val = cd_dict.get(new_key)
    if isinstance(val, dict) and val.get("note"):
        return str(val["note"])

    if legacy_col_idx is not None and not _has_new_date_keys(cd_dict):
        if event_type == "timetable":
            if orig_r_idx == 2:
                return ""
            leg_r = orig_r_idx - 1 if orig_r_idx >= 3 else orig_r_idx
        else:
            leg_r = orig_r_idx
        leg_key = f"{leg_r}_{legacy_col_idx}"
        leg_val = cd_dict.get(leg_key)
        if isinstance(leg_val, dict) and leg_val.get("note"):
            return str(leg_val["note"])
    return ""


def normalize_cell_details_for_editor(cd_dict, date_strs, legacy_col_map, num_rows, event_type="time"):
    """エディタへ渡す cellDetails を新形式 '{r}_{date_str}' に正規化する"""
    if not isinstance(cd_dict, dict):
        return {}
    out = {}
    for r in range(num_rows):
        for d_str in date_strs:
            note = get_cell_note(
                cd_dict,
                r,
                d_str,
                legacy_col_idx=legacy_col_map.get(d_str),
                event_type=event_type,
            )
            if note:
                out[f"{r}_{d_str}"] = {"note": note}
    return out


def decode_binary_to_matrix(responses, user_id, date_strs, time_labels, event_type, s_idx=0):
    """回答配列から自分の入力DataFrame・コメント・セル詳細を復元する"""
    df = pd.DataFrame(0, index=time_labels, columns=date_strs)
    my_comment = ""
    my_cell_details = {}
    uid_str = str(user_id)

    for r in responses:
        if str(r.get("user_id")) != uid_str:
            continue
        d_id = r.get("date")
        my_comment = r.get("comment", "") or ""
        if not my_cell_details and r.get("cell_details"):
            try:
                parsed = json.loads(r["cell_details"])
                if isinstance(parsed, dict):
                    my_cell_details = parsed
            except Exception:
                pass
        if d_id in date_strs:
            b_str = str(r.get("binary_data") or r.get("binary", "")).replace("'", "").zfill(96)
            for i in range(len(time_labels)):
                if event_type == "time":
                    v = int(b_str[s_idx + i]) if (s_idx + i) < len(b_str) else 0
                elif event_type == "date_timetable":
                    if i < len(PERIODS_MASTER):
                        p_start = PERIODS_MASTER[i][2]
                        v = int(b_str[p_start]) if p_start < len(b_str) else 0
                    else:
                        v = int(b_str[74]) if 74 < len(b_str) else 0
                else:
                    bit_pos = TIMETABLE_BIT_MAP.get(i, i)
                    v = int(b_str[bit_pos]) if bit_pos < len(b_str) else 0
                df.loc[time_labels[i], d_id] = v

    return df, my_comment, my_cell_details


def encode_matrix_to_responses(df_input, date_strs, time_labels, event_type, s_idx=0):
    """入力DataFrameをFirestore保存用のresponses配列へ変換する"""
    all_res = []
    for d_id in date_strs:
        bits = ["0"] * 96
        has_data = False
        for t_idx in range(len(time_labels)):
            val = int(df_input.loc[time_labels[t_idx], d_id])
            if val > 0:
                has_data = True
            if event_type == "time":
                if s_idx + t_idx < 96:
                    bits[s_idx + t_idx] = str(val)
            elif event_type == "date_timetable":
                if t_idx < len(PERIODS_MASTER):
                    p_start = PERIODS_MASTER[t_idx][2]
                    p_end = PERIODS_MASTER[t_idx][3]
                    for bit_i in range(p_start, p_end):
                        bits[bit_i] = str(val)
                else:
                    for bit_i in range(74, 96):
                        bits[bit_i] = str(val)
            else:
                bit_pos = TIMETABLE_BIT_MAP.get(t_idx, t_idx)
                if bit_pos < 96:
                    bits[bit_pos] = str(val)
        if has_data:
            all_res.append({"date": d_id, "binary_data": "".join(bits)})

    if not all_res and date_strs:
        all_res.append({"date": date_strs[0], "binary_data": "0" * 96})
    return all_res


def save_response_hybrid(payload):
    try:
        event_id = payload["event_id"]
        user_id = payload["user_id"]

        cell_details_dict = json.loads(payload.get("cell_details", "{}"))
        if not isinstance(cell_details_dict, dict):
            cell_details_dict = {}
        if payload.get("comment"):
            cell_details_dict["global_comment"] = payload["comment"]
        else:
            cell_details_dict.pop("global_comment", None)

        final_cell_details_str = json.dumps(cell_details_dict, separators=(",", ":"))
        payload["cell_details"] = final_cell_details_str

        doc_ref = db.collection("responses").document(f"{event_id}_{user_id}")
        data = {
            "event_id": event_id,
            "user_id": user_id,
            "cell_details": final_cell_details_str,
            "responses": payload.get("responses", []),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(data)
        invalidate_cache("responses")
    except Exception as e:
        st.error(f"Firestoreへの保存に失敗しました: {e}")
        return False

    backup_to_gas_async("submit_binary_response", {"payload": payload})
    return True


def get_app_data_from_firestore(user, target_ev_id=""):
    user_id = str(user.get("user_id", ""))
    all_users = _fetch_all_users_cached()
    user_map = {str(u.get("user_id", "")): u for u in all_users}
    answered_ids = _fetch_user_answered_ids_cached(user_id)

    now = datetime.now()
    active_events = []
    expanded_user_groups = expand_user_groups(user)

    raw_events = _fetch_all_events_cached()
    events_cache_dirty = False

    for raw_ev in raw_events:
        ev = normalize_event_dict(raw_ev)
        if ev.get("status") not in ["open", "closed"]:
            continue

        ev_close_time = ev.get("close_time") or ev.get("deadline", "")

        if ev.get("status") == "open" and ev.get("auto_close") and ev_close_time:
            try:
                dl_dt = pd.to_datetime(ev_close_time, errors="coerce")
                if pd.notna(dl_dt):
                    dl_dt = dl_dt.tz_convert(None) if dl_dt.tzinfo is not None else dl_dt.tz_localize(None)
                    if now > dl_dt:
                        ev["status"] = "closed"
                        db.collection("events").document(ev["event_id"]).update({"status": "closed"})
                        backup_to_gas_async("update_event_status", {"payload": {"event_id": ev["event_id"], "status": "closed"}})
                        events_cache_dirty = True
            except Exception:
                pass

        if ev.get("status") in ["open", "closed"] and ev.get("auto_archive", True) and ev_close_time:
            try:
                dl_dt = pd.to_datetime(ev_close_time, errors="coerce")
                if pd.notna(dl_dt):
                    dl_dt = dl_dt.tz_convert(None) if dl_dt.tzinfo is not None else dl_dt.tz_localize(None)
                    if now > (dl_dt + timedelta(days=7)):
                        ev["status"] = "archived"
                        db.collection("events").document(ev["event_id"]).update({"status": "archived"})
                        backup_to_gas_async("update_event_status", {"payload": {"event_id": ev["event_id"], "status": "archived"}})
                        events_cache_dirty = True
                        continue
            except Exception:
                pass

        is_target = is_in_scope(expanded_user_groups, user_id, ev.get("target_scope", ""))
        is_bypassed = False
        if not is_target and ev["event_id"] == target_ev_id:
            is_target = True
            is_bypassed = True

        if is_target:
            ev["is_answered"] = ev["event_id"] in answered_ids
            ev["is_out_of_scope"] = is_bypassed
            active_events.append(ev)

    if events_cache_dirty:
        invalidate_cache("events")

    return all_users, active_events, user_map


def fetch_responses_for_event(event_id, user_map):
    raw_docs = _fetch_event_responses_raw_cached(event_id)
    flat_responses = []
    for data in raw_docs:
        uid = str(data.get("user_id"))
        uinfo = user_map.get(uid, {})
        cell_details_str = data.get("cell_details", "{}")
        try:
            cell_details_dict = json.loads(cell_details_str)
            comment = cell_details_dict.get("global_comment", data.get("comment", ""))
        except Exception:
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
                "binary": b_data,
                "comment": comment,
                "cell_details": cell_details_str,
            })
    return flat_responses


def filter_responses(all_res_data, f_names, f_g1, f_g2, f_g3, f_g4):
    """回答者条件(名前・プロジェクト・系・委員会・役職)で回答リストを絞り込む"""
    filtered = []
    for r in all_res_data:
        u_g1 = [x.strip() for x in str(r.get("group_1", "")).split(",") if x.strip()]
        u_g2 = [x.strip() for x in str(r.get("group_2", "")).split(",") if x.strip()]
        u_g3 = [x.strip() for x in str(r.get("group_3", "")).split(",") if x.strip()]
        u_g4 = [x.strip() for x in str(r.get("group_4", "")).split(",") if x.strip()]
        if f_names and r.get("user_name") not in f_names:
            continue
        if f_g1 and not set(f_g1).intersection(set(u_g1)):
            continue
        if f_g2 and not set(f_g2).intersection(set(u_g2)):
            continue
        if f_g3 and not set(f_g3).intersection(set(u_g3)):
            continue
        if f_g4:
            match_g4 = False
            for fg in f_g4:
                if fg == "シスマネ" and any("シスマネ" in ug for ug in u_g4):
                    match_g4 = True
                    break
                if fg == "系長" and any("系長" in ug for ug in u_g4):
                    match_g4 = True
                    break
                if fg in u_g4:
                    match_g4 = True
                    break
            if not match_g4:
                continue
        filtered.append(r)
    return filtered


# ==========================================
# 新機能ロジック（ランキング・確定バナー・GCal/.ics・コピー）
# ==========================================
def parse_confirmed_info(raw_val):
    if not raw_val:
        return None
    if isinstance(raw_val, dict):
        return raw_val if raw_val.get("label") else None
    if isinstance(raw_val, str):
        try:
            d = json.loads(raw_val)
            return d if isinstance(d, dict) and d.get("label") else None
        except Exception:
            return None
    return None


def build_gcal_url(title, start_dt_str, end_dt_str, location="", details=""):
    """Googleカレンダー予定追加用URLを生成する"""
    try:
        s_dt = datetime.strptime(start_dt_str.strip(), "%Y-%m-%d %H:%M")
        e_dt = datetime.strptime(end_dt_str.strip(), "%Y-%m-%d %H:%M")
    except Exception:
        return ""
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{s_dt.strftime('%Y%m%dT%H%M%S')}/{e_dt.strftime('%Y%m%dT%H%M%S')}",
        "ctz": "Asia/Tokyo",
        "details": details or "",
        "location": location or "",
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)


def _escape_ics_text(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def build_ics_content(title, start_dt_str, end_dt_str, location="", details="", uid_prefix="ssscheduler"):
    """iPhone/Outlook/Googleカレンダー対応のICSテキストを生成する"""
    try:
        s_dt = datetime.strptime(start_dt_str.strip(), "%Y-%m-%d %H:%M")
        e_dt = datetime.strptime(end_dt_str.strip(), "%Y-%m-%d %H:%M")
    except Exception:
        return ""
    now_utc = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    uid = f"{uid_prefix}-{s_dt.strftime('%Y%m%dT%H%M%S')}@ssscheduler"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SSSRC//SSScheduler//JP",
        "CALSCALE:GREGORIAN",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Tokyo",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0900",
        "TZOFFSETTO:+0900",
        "TZNAME:JST",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_utc}",
        f"DTSTART;TZID=Asia/Tokyo:{s_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID=Asia/Tokyo:{e_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_escape_ics_text(title)}",
        f"LOCATION:{_escape_ics_text(location)}",
        f"DESCRIPTION:{_escape_ics_text(details)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def compute_best_slots_grid(
    user_grid,
    user_meta,
    disp_date_strs,
    disp_clean_date_labels,
    disp_time_labels,
    time_labels,
    event_type,
    policy=0.5,
    required_user_ids=None,
    allow_maybe_for_required=True,
    duration_slots=1,
    top_n=5,
):
    """
    グリッド形式(time / timetable / date_timetable)におけるベスト候補日時トップNを算出する。
    timeモードでは連続 duration_slots コマ全てに参加可能な人のみを厳密にカウントし、
    同一日の重複スライド枠を整理して見やすい上位候補を返す。
    """
    req_ids = {str(u) for u in (required_user_ids or set())}
    k = max(1, int(duration_slots))
    candidates = []
    n_rows = len(disp_time_labels)

    if n_rows < k or not disp_date_strs:
        return []

    for c_idx, d_str in enumerate(disp_date_strs):
        d_label = disp_clean_date_labels[c_idx]
        for r_start in range(0, n_rows - k + 1):
            # 時間帯フィルター等で飛んでいない連続枠か確認
            if event_type == "time" and k > 1:
                orig_indices = [time_labels.index(disp_time_labels[r_start + off]) for off in range(k)]
                if any(orig_indices[j + 1] - orig_indices[j] != 1 for j in range(k - 1)):
                    continue

            score = 0.0
            yes_cnt = 0
            maybe_cnt = 0
            no_cnt = 0
            req_ok = True

            for uid, uinfo in user_meta.items():
                vals = [user_grid.get(uid, {}).get((d_str, r_start + off), 0) for off in range(k)]
                # 3(授業等)は不可(0)扱い
                norm_vals = [0 if v == 3 else v for v in vals]
                if all(v == 1 for v in norm_vals):
                    status = 1
                    score += 1.0
                    yes_cnt += 1
                elif all(v in (1, 2) for v in norm_vals):
                    status = 2
                    score += policy
                    maybe_cnt += 1
                else:
                    status = 0
                    no_cnt += 1

                if uid in req_ids:
                    if status == 0 or (status == 2 and not allow_maybe_for_required):
                        req_ok = False

            if not req_ok or score <= 0:
                continue

            start_lbl = disp_time_labels[r_start]
            start_dt_str, end_dt_str = "", ""
            if event_type == "time":
                try:
                    s_dt = datetime.strptime(f"{d_str} {start_lbl}", "%Y-%m-%d %H:%M")
                    e_dt = s_dt + timedelta(minutes=15 * k)
                    start_dt_str = s_dt.strftime("%Y-%m-%d %H:%M")
                    end_dt_str = e_dt.strftime("%Y-%m-%d %H:%M")
                    slot_label = f"{d_label} {start_lbl}〜{e_dt.strftime('%H:%M')}"
                except Exception:
                    slot_label = f"{d_label} {start_lbl}"
            elif event_type == "date_timetable":
                slot_label = f"{d_label} {start_lbl}"
                if start_lbl in PERIOD_CLOCK_RANGES:
                    st_t, en_t = PERIOD_CLOCK_RANGES[start_lbl]
                    start_dt_str = f"{d_str} {st_t}"
                    end_dt_str = f"{d_str} {en_t}"
            else:
                slot_label = f"{d_label} {start_lbl}"

            candidates.append({
                "label": slot_label,
                "date_str": d_str,
                "c_idx": c_idx,
                "r_start": r_start,
                "r_end": r_start + k,
                "score": score,
                "yes": yes_cnt,
                "maybe": maybe_cnt,
                "no": no_cnt,
                "start_dt": start_dt_str,
                "end_dt": end_dt_str,
            })

    # スコア降順 -> 完全◯人数降順 -> 日付順 -> 時刻順
    candidates.sort(key=lambda x: (-x["score"], -x["yes"], x["c_idx"], x["r_start"]))

    selected = []
    for cand in candidates:
        overlaps = any(
            s["date_str"] == cand["date_str"]
            and max(s["r_start"], cand["r_start"]) < min(s["r_end"], cand["r_end"])
            for s in selected
        )
        if not overlaps:
            selected.append(cand)
            if len(selected) >= top_n:
                break
    return selected


def compute_best_slots_options(
    opts,
    filtered_data,
    policy=0.5,
    required_user_ids=None,
    allow_maybe_for_required=True,
    top_n=5,
):
    """候補リスト(options)モードにおけるベスト候補ランキングを算出する"""
    req_ids = {str(u) for u in (required_user_ids or set())}
    candidates = []

    user_rows = {}
    for r in filtered_data:
        uid = str(r.get("user_id"))
        b_str = str(r.get("binary_data") or r.get("binary", "")).replace("'", "").zfill(96)
        user_rows[uid] = b_str

    for i, opt in enumerate(opts):
        score = 0.0
        yes_cnt = 0
        maybe_cnt = 0
        no_cnt = 0
        req_ok = True

        for uid, b_str in user_rows.items():
            v = int(b_str[i]) if i < len(b_str) else 0
            if v == 1:
                score += 1.0
                yes_cnt += 1
            elif v == 2:
                score += policy
                maybe_cnt += 1
            else:
                no_cnt += 1

            if uid in req_ids:
                if v == 0 or (v == 2 and not allow_maybe_for_required):
                    req_ok = False

        if not req_ok or score <= 0:
            continue

        candidates.append({
            "label": opt,
            "idx": i,
            "score": score,
            "yes": yes_cnt,
            "maybe": maybe_cnt,
            "no": no_cnt,
            "start_dt": "",
            "end_dt": "",
        })

    candidates.sort(key=lambda x: (-x["score"], -x["yes"], x["idx"]))
    return candidates[:top_n]


def format_slack_ranking_text(event, best_slots, share_url):
    title = event.get("title", "日程調整")
    lines = [f"📊 *{title}* のおすすめ候補日時です！"]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    for idx, s in enumerate(best_slots):
        m = medals[idx] if idx < len(medals) else f"{idx + 1}."
        lines.append(f"{m} {s['label']}（目安 {s['score']:g}名 / ◯{s['yes']}・△{s['maybe']}）")
    lines.append(f"🔗 回答・確認: {share_url}")
    return "\n".join(lines)


def format_confirmed_announce_text(event, confirmed_info, share_url):
    title = event.get("title", "日程調整")
    lines = [
        f"📌 *{title}* の開催日時が決定しました！",
        f"📅 日時: {confirmed_info.get('label', '')}",
    ]
    if confirmed_info.get("location"):
        lines.append(f"📍 場所/URL: {confirmed_info['location']}")
    if confirmed_info.get("note"):
        lines.append(f"📝 連絡: {confirmed_info['note']}")
    lines.append(f"🔗 詳細・カレンダー登録: {share_url}")
    return "\n".join(lines)


def render_copy_button(
    text_to_copy,
    btn_label="🔗 リンクをコピー",
    share_title="",
    share_url="",
    key_suffix="",
    full_width=False,
):
    """iframe環境でも確実に動くワンタップコピー＆Web Shareボタンを描画する"""
    safe_text = json.dumps(text_to_copy)
    safe_label = html_lib.escape(btn_label)
    safe_share_title = json.dumps(share_title or "")
    safe_share_url = json.dumps(share_url or "")
    btn_flex = "flex: 1 1 auto; min-width: 0;" if full_width else "flex: 0 1 auto;"
    share_html = (
        '<button id="share-btn" class="sss-act-btn sss-share-btn" style="display:none;">📤 共有</button>'
        if share_url
        else ""
    )
    uid_dom = html_lib.escape(str(key_suffix or "copy"))

    components.html(
        f"""
        <!DOCTYPE html><html><head><meta charset="utf-8"><style>
        html, body {{ margin: 0; padding: 0; background: transparent; overflow: hidden; font-family: sans-serif; }}
        .wrap {{ display: flex; gap: 5px; align-items: center; width: 100%; box-sizing: border-box; }}
        .sss-act-btn {{
            {btn_flex}
            height: 38px; padding: 0 10px; border-radius: 8px;
            border: 1px solid #cbd5e1; background: #ffffff; color: #1e293b;
            font-size: 12.5px; font-weight: 700; cursor: pointer;
            display: inline-flex; align-items: center; justify-content: center; gap: 3px;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            box-sizing: border-box; transition: 0.15s;
        }}
        .sss-act-btn:hover {{ background: #f1f5f9; border-color: #94a3b8; }}
        .sss-act-btn.copied {{ background: #e8f5e9; border-color: #4CAF50; color: #2e7d32; }}
        .sss-share-btn {{ flex: 0 0 auto; padding: 0 9px; background: #e0f2fe; border-color: #7dd3fc; color: #0369a1; }}
        @media (max-width: 240px) {{
            .sss-act-btn {{ font-size: 11.5px; padding: 0 6px; }}
        }}
        </style></head><body>
        <div class="wrap" id="wrap-{uid_dom}">
            <button id="copy-btn" class="sss-act-btn">{safe_label}</button>
            {share_html}
        </div>
        <script>
        const copyVal = {safe_text};
        const origLabel = {json.dumps(btn_label)};
        const shareTitle = {safe_share_title};
        const shareUrl = {safe_share_url};
        const copyBtn = document.getElementById('copy-btn');
        const shareBtn = document.getElementById('share-btn');

        function fallbackCopy(txt) {{
            const ta = document.createElement('textarea');
            ta.value = txt;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            try {{ document.execCommand('copy'); }} catch (e) {{}}
            document.body.removeChild(ta);
        }}

        copyBtn.addEventListener('click', async () => {{
            try {{
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    await navigator.clipboard.writeText(copyVal);
                }} else {{
                    fallbackCopy(copyVal);
                }}
            }} catch (e) {{
                fallbackCopy(copyVal);
            }}
            copyBtn.textContent = "✅ コピーしました！";
            copyBtn.classList.add("copied");
            setTimeout(() => {{
                copyBtn.textContent = origLabel;
                copyBtn.classList.remove("copied");
            }}, 1800);
        }});

        if (shareBtn && navigator.share && shareUrl) {{
            shareBtn.style.display = 'inline-flex';
            shareBtn.addEventListener('click', async () => {{
                try {{
                    await navigator.share({{ title: shareTitle, url: shareUrl }});
                }} catch (e) {{}}
            }});
        }}
        </script></body></html>
        """,
        height=42,
    )


# ==========================================
# カスタムHTMLコンポーネント群（生成＆宣言）
# ==========================================
RT_EDITOR_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body { font-family: sans-serif; margin: 0; padding: 0; background: transparent; }
.editor-container { border: 1px solid #ccc; border-radius: 6px; overflow: hidden; background: #fff; }
.toolbar { background: #f8f9fb; padding: 6px; border-bottom: 1px solid #ccc; display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.toolbar button { background: #fff; border: 1px solid #ccc; border-radius: 4px; padding: 4px 10px; font-size: 13px; cursor: pointer; color: #333; transition: 0.2s; }
.toolbar button:hover { background: #e9ecef; }
textarea { width: 100%; height: 120px; border: none; padding: 10px; font-size: 14px; resize: vertical; outline: none; box-sizing: border-box; font-family: inherit; line-height: 1.5; }
</style></head><body>
<div class="editor-container" id="app-root">
    <div class="toolbar">
        <button type="button" onclick="insertTag('<b>', '</b>')" title="太字"><b>B</b> 太字</button>
        <button type="button" onclick="insertTag('<i>', '</i>')" title="斜体"><i>I</i> 斜体</button>
        <div style="width: 1px; height: 20px; background: #ccc; margin: 0 4px;"></div>
        <button type="button" onclick="insertRed()" title="赤文字"><span style="color:#FF4B4B; font-weight:bold;">A</span> 赤</button>
        <button type="button" onclick="insertBlue()" title="青文字"><span style="color:#2196F3; font-weight:bold;">A</span> 青</button>
        <div style="width: 1px; height: 20px; background: #ccc; margin: 0 4px;"></div>
        <button type="button" onclick="insertLink()" title="リンク">🔗 リンク追加</button>
    </div>
    <textarea id="editor" placeholder="📝 イベントの説明や注意事項を入力..."></textarea>
</div>
<script>
function sendMessageToStreamlitClient(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
}
function init() { sendMessageToStreamlitClient("streamlit:componentReady", {apiVersion: 1}); }
function setComponentValue(value) { sendMessageToStreamlitClient("streamlit:setComponentValue", {value: value, dataType: "json"}); }
const editor = document.getElementById('editor');
function sendValue() { setComponentValue(editor.value); }
function insertTag(startTag, endTag) {
    const start = editor.selectionStart; const end = editor.selectionEnd; const val = editor.value;
    const selected = val.substring(start, end);
    editor.value = val.substring(0, start) + startTag + selected + endTag + val.substring(end);
    editor.focus();
    editor.selectionStart = start + startTag.length;
    editor.selectionEnd = end + startTag.length;
    sendValue();
}
function insertRed() { insertTag("<span style='color:#FF4B4B; font-weight:bold;'>", "</span>"); }
function insertBlue() { insertTag("<span style='color:#2196F3; font-weight:bold;'>", "</span>"); }
function insertLink() {
    const url = prompt('リンク先のURLを入力', 'https://');
    if (url) {
        const text = prompt('表示するテキストを入力', 'こちらをクリック');
        if (text) {
            const linkTag = `<a href='${url}' target='_blank'>${text}</a>`;
            const start = editor.selectionStart;
            const val = editor.value;
            editor.value = val.substring(0, start) + linkTag + val.substring(editor.selectionEnd);
            sendValue();
        }
    }
}
editor.addEventListener('blur', sendValue);
window.addEventListener("message", function(event) {
    if (event.data.type === "streamlit:render") {
        sendMessageToStreamlitClient("streamlit:setFrameHeight", {height: document.getElementById('app-root').scrollHeight + 8});
    }
});
init();
</script></body></html>
"""

AUTH_STORAGE_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; padding: 0; height: 0; overflow: hidden; background: transparent; }
</style></head><body><script>
const STORAGE_KEY = "ssscheduler_auth_v2";
function sendMsg(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
}
let didRead = false;
let lastOpId = null;

window.addEventListener("message", function(event) {
    if (!event.data || event.data.type !== "streamlit:render") return;
    sendMsg("streamlit:setFrameHeight", {height: 0});
    const args = event.data.args || {};
    const mode = args.mode || "read";

    if (mode === "write") {
        if (args.opId !== lastOpId && args.payload) {
            lastOpId = args.opId;
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(args.payload)); } catch (e) {}
        }
    } else if (mode === "clear") {
        if (args.opId !== lastOpId) {
            lastOpId = args.opId;
            try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
        }
    } else if (mode === "read") {
        if (didRead) return;
        didRead = true;
        let saved = null;
        try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); } catch (e) {}
        if (saved && saved.uid && saved.token) {
            sendMsg("streamlit:setComponentValue", {
                value: {status: "found", uid: String(saved.uid), token: String(saved.token)},
                dataType: "json"
            });
        } else {
            sendMsg("streamlit:setComponentValue", {value: {status: "empty"}, dataType: "json"});
        }
    }
});
sendMsg("streamlit:componentReady", {apiVersion: 1});
</script></body></html>
"""

OPTIONS_EDITOR_V2_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: transparent; }
* { box-sizing: border-box; }
#app-root { padding: 2px 2px 6px 2px; }
.bulk-bar {
    display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 8px 12px; margin-bottom: 12px;
}
.bulk-label { font-size: 12px; font-weight: 700; color: #475569; margin-right: 4px; }
.bulk-btn {
    border: 1px solid #cbd5e1; background: #fff; border-radius: 999px;
    padding: 5px 12px; font-size: 12px; font-weight: 700; cursor: pointer; color: #334155;
    transition: 0.15s;
}
.bulk-btn:hover { background: #f1f5f9; }
.opt-card {
    background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 14px; margin-bottom: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.04);
}
.opt-title { font-size: 16px; font-weight: 700; color: #1b5e20; margin-bottom: 12px; }
.btn-group { display: flex; gap: 10px; }
.opt-btn {
    flex: 1; padding: 14px 4px; border-radius: 10px; border: 2px solid #e2e8f0;
    background: #fff; font-size: 15px; font-weight: 700; cursor: pointer;
    transition: 0.15s; color: #475569; text-align: center;
}
.opt-btn[data-v="1"].active { background: #4CAF50; color: #fff; border-color: #4CAF50; box-shadow: 0 4px 10px rgba(76,175,80,0.35); }
.opt-btn[data-v="2"].active { background: #FFEB3B; color: #333; border-color: #FBC02D; box-shadow: 0 4px 10px rgba(251,192,45,0.35); }
.opt-btn[data-v="0"].active { background: #f1f5f9; color: #475569; border-color: #94a3b8; }
textarea {
    width: 100%; padding: 12px; border: 1px solid #cbd5e1; border-radius: 10px;
    font-family: inherit; font-size: 14px; margin-bottom: 10px; resize: vertical;
}
.dirty-badge {
    display: none; background: #fff8e1; color: #b45309; border: 1px solid #fcd34d;
    border-radius: 8px; padding: 8px 12px; font-size: 13px; font-weight: 700;
    margin-bottom: 10px; text-align: center;
}
.dirty-badge.show { display: block; }
#submit-btn {
    width: 100%; padding: 15px; background: #FF4B4B; color: #fff; border: none;
    border-radius: 10px; font-size: 17px; font-weight: 800; cursor: pointer;
    box-shadow: 0 4px 12px rgba(255,75,75,0.28); transition: 0.15s;
}
#submit-btn:hover { background: #e03e3e; }
</style></head><body>
<div id="app-root">
    <div id="content"></div>
</div>
<script>
function sendMsg(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
}
function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function updateHeight() {
    const root = document.getElementById('app-root');
    if (!root) return;
    const h = Math.ceil(root.getBoundingClientRect().height) + 6;
    sendMsg("streamlit:setFrameHeight", {height: h});
}

let optsData = [];
let lastSig = null;

function markDirty() {
    const b = document.getElementById('dirty-badge');
    if (b) b.classList.add('show');
    updateHeight();
}

window.setOpt = function(idx, val) {
    optsData[idx] = val;
    const grp = document.getElementById('group-' + idx);
    if (!grp) return;
    grp.querySelectorAll('.opt-btn').forEach(b => b.classList.remove('active'));
    const target = grp.querySelector(`[data-v="${val}"]`);
    if (target) target.classList.add('active');
    markDirty();
};

window.setAllOpts = function(val) {
    for (let i = 0; i < optsData.length; i++) {
        window.setOpt(i, val);
    }
};

window.submitData = function() {
    const btn = document.getElementById("submit-btn");
    if (btn) {
        btn.innerText = "⏳ 保存処理中...";
        btn.style.pointerEvents = "none";
        btn.style.opacity = "0.7";
    }
    const cb = document.getElementById("comment-box");
    const comment = cb ? cb.value : "";
    sendMsg("streamlit:setComponentValue", {
        value: {trigger_save: true, binary: optsData.join(''), comment: comment, ts: Date.now()},
        dataType: "json"
    });
    setTimeout(() => {
        if (btn) {
            btn.innerText = "✅ 回答を保存して提出";
            btn.style.pointerEvents = "auto";
            btn.style.opacity = "1";
        }
    }, 5000);
};

window.addEventListener("message", function(event) {
    if (!event.data || event.data.type !== "streamlit:render") return;
    const args = event.data.args || {};
    const sig = `${args.eventId}|${args.saveTs}|${args.isClosed}|${(args.options || []).length}`;
    if (lastSig === sig) {
        updateHeight();
        return;
    }
    lastSig = sig;

    const opts = args.options || [];
    const myAnsBin = args.myAnsBin || "";
    const myComment = args.myComment || "";
    const isClosed = !!args.isClosed;

    let html = "";
    if (!isClosed && opts.length > 1) {
        html += `
        <div class="bulk-bar">
            <span class="bulk-label">⚡ 一括選択:</span>
            <button type="button" class="bulk-btn" onclick="setAllOpts(1)">🟢 すべて ◯ 可</button>
            <button type="button" class="bulk-btn" onclick="setAllOpts(2)">🟡 すべて △ 未定</button>
            <button type="button" class="bulk-btn" onclick="setAllOpts(0)">⚪ すべて × 不可</button>
        </div>`;
    }

    optsData = [];
    opts.forEach((opt, i) => {
        const v = i < myAnsBin.length ? (parseInt(myAnsBin[i], 10) || 0) : 0;
        optsData.push(v);
        const lockStyle = isClosed ? "pointer-events:none; opacity:0.75;" : "";
        html += `
        <div class="opt-card" style="${lockStyle}">
            <div class="opt-title">📅 ${escapeHtml(opt)}</div>
            <div class="btn-group" id="group-${i}">
                <button type="button" class="opt-btn ${v===0 ? 'active':''}" data-v="0" onclick="setOpt(${i}, 0)">× 不可</button>
                <button type="button" class="opt-btn ${v===2 ? 'active':''}" data-v="2" onclick="setOpt(${i}, 2)">△ 未定</button>
                <button type="button" class="opt-btn ${v===1 ? 'active':''}" data-v="1" onclick="setOpt(${i}, 1)">◯ 可</button>
            </div>
        </div>`;
    });

    if (!isClosed) {
        html += `
        <div class="opt-card">
            <div style="font-size:14px; font-weight:700; margin-bottom:8px; color:#334155;">📝 自分の備考・コメント</div>
            <textarea id="comment-box" rows="2" placeholder="遅刻・早退などの連絡事項">${escapeHtml(myComment)}</textarea>
            <div id="dirty-badge" class="dirty-badge">⚠️ 未保存の変更があります（「提出」を押すと保存されます）</div>
            <button type="button" id="submit-btn" onclick="submitData()">✅ 回答を保存して提出</button>
        </div>`;
    } else {
        html += `
        <div class="opt-card">
            <div style="font-size:14px; font-weight:700; margin-bottom:8px; color:#334155;">📝 自分の備考・コメント</div>
            <div style="padding:12px; background:#f1f5f9; border-radius:8px; min-height:42px; font-size:14px; white-space:pre-wrap;">${escapeHtml(myComment || "（なし）")}</div>
        </div>`;
    }

    document.getElementById("content").innerHTML = html;
    const cb = document.getElementById("comment-box");
    if (cb) cb.addEventListener("input", markDirty);
    setTimeout(updateHeight, 30);
});

const ro = new ResizeObserver(() => updateHeight());
ro.observe(document.getElementById('app-root'));
sendMsg("streamlit:componentReady", {apiVersion: 1});
</script></body></html>
"""

CUSTOM_EDITOR_V15_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: transparent; }
* { box-sizing: border-box; }
#app-root {
    --cell-h: 36px; --col-w: 66px; --time-w: 58px; --head-h: 46px;
    --cell-font: 13px; --head-font: 11.5px;
    padding: 2px 2px 6px 2px; position: relative;
}

/* 便利ツール */
.tools-grid { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
.tool-card {
    background: #fff; padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 8px;
    flex: 1 1 220px; min-width: 200px;
}
.tool-header { font-size: 13.5px; font-weight: 700; color: #1e293b; margin-bottom: 8px; }
.st-sel { padding: 5px 6px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12.5px; background: #fff; }
.st-btn {
    padding: 6px 12px; border: none; border-radius: 6px; background: #4CAF50;
    color: #fff; cursor: pointer; font-weight: 700; font-size: 12.5px;
}
.st-btn:hover { opacity: 0.9; }
.ms-container { position: relative; display: inline-block; flex: 1; min-width: 125px; }
.ms-header {
    border: 1px solid #cbd5e1; padding: 5px 9px; border-radius: 6px; cursor: pointer;
    background: #fff; font-size: 12.5px; user-select: none; display: flex; justify-content: space-between;
}
.ms-options {
    position: absolute; top: 100%; left: 0; right: 0; background: #fff; border: 1px solid #cbd5e1;
    border-radius: 6px; z-index: 200; max-height: 200px; overflow-y: auto;
    box-shadow: 0 6px 14px rgba(0,0,0,0.12); padding: 6px; margin-top: 2px;
}
.ms-opt { display: block; padding: 5px 8px; font-size: 12.5px; cursor: pointer; border-radius: 4px; }
.ms-opt:hover { background: #f1f5f9; }

/* 上部ツールバー */
.editor-toolbar {
    position: sticky; top: 0; z-index: 60;
    background: rgba(255, 255, 255, 0.97); backdrop-filter: blur(6px);
    border: 1px solid #cbd5e1; border-radius: 10px;
    padding: 6px 9px; margin-bottom: 6px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    display: flex; flex-direction: column; gap: 5px;
}
.tb-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px; }
.tb-group { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.pen-pill {
    border: 2px solid #cbd5e1; background: #fff; color: #334155;
    padding: 5px 10px; border-radius: 999px; font-size: 12.5px; font-weight: 800;
    cursor: pointer; transition: 0.12s; display: inline-flex; align-items: center; gap: 3px;
    user-select: none;
}
.pen-pill:hover { background: #f8fafc; }
.pen-pill.active[data-mode="1"] { background: #4CAF50; border-color: #2e7d32; color: #fff; box-shadow: 0 2px 6px rgba(76,175,80,0.35); }
.pen-pill.active[data-mode="2"] { background: #FFEB3B; border-color: #F59E0B; color: #333; box-shadow: 0 2px 6px rgba(245,158,11,0.3); }
.pen-pill.active[data-mode="0"] { background: #475569; border-color: #1e293b; color: #fff; }
.pen-pill.active[data-mode="-2"] { background: #2196F3; border-color: #1565C0; color: #fff; box-shadow: 0 2px 6px rgba(33,150,243,0.35); }

.act-pill {
    border: 1px solid #cbd5e1; background: #f8fafc; color: #334155;
    padding: 5px 9px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer;
    user-select: none;
}
.act-pill:hover:not(:disabled) { background: #e2e8f0; }
.act-pill:disabled { opacity: 0.4; cursor: not-allowed; }
.act-pill.active-toggle { background: #ecfdf5; border-color: #10b981; color: #047857; }

.zoom-group {
    display: inline-flex; align-items: center; border: 1px solid #cbd5e1;
    border-radius: 8px; overflow: hidden; background: #fff;
}
.zoom-btn {
    border: none; background: #f8fafc; color: #1e293b; padding: 4px 8px;
    font-size: 12.5px; font-weight: 800; cursor: pointer; line-height: 1.2;
}
.zoom-btn:hover { background: #e2e8f0; }
.zoom-lbl {
    border: none; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0;
    background: #fff; color: #334155; padding: 4px 7px; font-size: 11px; font-weight: 800;
    cursor: pointer; min-width: 44px; text-align: center;
}

.hint-bar {
    font-size: 11px; color: #475569; background: #f1f5f9;
    padding: 3px 8px; border-radius: 6px; line-height: 1.35;
}
.hint-touch { display: none; }
@media (pointer: coarse) {
    .hint-pc { display: none; }
    .hint-touch { display: inline; }
}

/* 動かせるフローティングペンパレット（スマホの上下移動コスト解消） */
.fp-box {
    position: absolute; z-index: 400;
    touch-action: none; user-select: none; -webkit-user-select: none;
}
.fp-main {
    display: flex; align-items: center; gap: 4px;
    background: rgba(15, 23, 42, 0.92); backdrop-filter: blur(8px);
    border: 1.5px solid rgba(255,255,255,0.22); border-radius: 999px;
    padding: 5px 8px; box-shadow: 0 8px 24px rgba(15,23,42,0.38);
}
.fp-box.fp-vert .fp-main {
    flex-direction: column; border-radius: 18px; padding: 8px 5px;
}
.fp-grip {
    color: #94a3b8; font-size: 15px; font-weight: 900; padding: 2px 4px;
    cursor: grab; line-height: 1; letter-spacing: -1px;
}
.fp-grip:active { cursor: grabbing; }
.fp-pen {
    width: 34px; height: 34px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.25);
    background: rgba(255,255,255,0.12); color: #f8fafc; font-size: 14px; font-weight: 900;
    display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
    padding: 0; transition: transform 0.1s, background 0.1s;
}
.fp-pen.active[data-mode="1"] { background: #4CAF50; border-color: #bbf7d0; color: #fff; transform: scale(1.08); box-shadow: 0 0 10px rgba(76,175,80,0.65); }
.fp-pen.active[data-mode="2"] { background: #FFEB3B; border-color: #fef08a; color: #1e293b; transform: scale(1.08); box-shadow: 0 0 10px rgba(255,235,59,0.6); }
.fp-pen.active[data-mode="0"] { background: #f8fafc; border-color: #94a3b8; color: #0f172a; transform: scale(1.08); }
.fp-pen.active[data-mode="-2"] { background: #38bdf8; border-color: #bae6fd; color: #0f172a; transform: scale(1.08); }
.fp-sep { width: 1px; height: 22px; background: rgba(255,255,255,0.2); margin: 0 1px; }
.fp-box.fp-vert .fp-sep { width: 22px; height: 1px; margin: 1px 0; }
.fp-act {
    height: 30px; min-width: 28px; padding: 0 6px; border-radius: 999px;
    border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.1);
    color: #f1f5f9; font-size: 12px; font-weight: 800; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
}
.fp-act:disabled { opacity: 0.35; cursor: not-allowed; }
.fp-fab {
    background: rgba(15, 23, 42, 0.92); color: #fff; border: 1.5px solid #10b981;
    border-radius: 999px; padding: 7px 12px; font-size: 12.5px; font-weight: 800;
    box-shadow: 0 6px 18px rgba(15,23,42,0.35); cursor: pointer;
}

/* 上部同期スクロールバー */
.top-scroll-wrap {
    overflow-x: auto; overflow-y: hidden; width: 100%; height: 14px;
    margin-bottom: 3px; display: none;
    scrollbar-width: auto; scrollbar-color: #94a3b8 #f1f5f9;
}
.top-scroll-wrap::-webkit-scrollbar { height: 9px; }
.top-scroll-wrap::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
.top-scroll-wrap::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 6px; }
.top-scroll-inner { height: 1px; }

/* メインスクロール枠（スマホでは1画面内に収まる高さにして上下往復をなくす） */
.scroll-wrapper {
    width: 100%; overflow: auto; -webkit-overflow-scrolling: touch;
    border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; position: relative;
    scrollbar-width: auto; scrollbar-color: #94a3b8 #f1f5f9;
}
.scroll-wrapper.time-scroll { max-height: 550px; height: auto; }
@media (max-width: 650px) {
    .scroll-wrapper.time-scroll { max-height: 430px; }
    .pen-pill { padding: 4px 8px; font-size: 12px; }
}
.scroll-wrapper.auto-scroll { max-height: none; height: auto; }
.scroll-wrapper::-webkit-scrollbar { width: 10px; height: 10px; }
.scroll-wrapper::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
.scroll-wrapper::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 6px; border: 2px solid #f1f5f9; }
.scroll-wrapper::-webkit-scrollbar-thumb:hover { background: #64748b; }

#g {
    display: grid; width: 100%; min-width: max-content; user-select: none;
}
.time-col {
    position: sticky; left: 0; z-index: 15; background: #f1f5f9;
    box-shadow: 2px 0 6px rgba(0,0,0,0.08); grid-column: 1 / 2;
    touch-action: pan-x pan-y;
}
.top-left-cell {
    position: sticky; top: 0; left: 0; z-index: 25; background: #f1f5f9;
    border-right: 1px solid #cbd5e1; border-bottom: 2px solid #475569;
    height: var(--head-h); box-shadow: 2px 2px 6px rgba(0,0,0,0.08);
    display: flex; align-items: center; justify-content: center;
    font-size: 10.5px; color: #64748b; font-weight: 700;
}
.time-cell {
    background: #f1f5f9; text-align: center; font-size: 10.5px; font-weight: 700; color: #475569;
    height: var(--cell-h); line-height: var(--cell-h);
    border-right: 1px solid #cbd5e1; overflow: hidden;
}
.day-col { box-sizing: border-box; }
.day-col.week-break { border-left: 2px solid #64748b; }
.header-cell {
    position: sticky; top: 0; z-index: 12; background: #f8fafc;
    text-align: center; font-size: var(--head-font); font-weight: 800; color: #1e293b;
    padding: 3px 2px; border-bottom: 2px solid #475569; border-right: 1px solid #e2e8f0;
    height: var(--head-h); display: flex; align-items: center; justify-content: center; line-height: 1.2;
    touch-action: pan-x pan-y; overflow: hidden;
}
.header-cell.day-sat { background: #eff6ff; color: #1d4ed8; }
.header-cell.day-sun { background: #fef2f2; color: #dc2626; }

.c {
    display: flex; align-items: center; justify-content: center;
    height: var(--cell-h); cursor: pointer; position: relative;
    border-right: 1px solid #e2e8f0; touch-action: none;
    transition: filter 0.08s; overflow: hidden;
}
@media (hover: hover) and (pointer: fine) {
    .c:hover { filter: brightness(0.96); }
}
.cell-txt { font-size: var(--cell-font); font-weight: 800; pointer-events: none; line-height: 1; }
.memo-icon {
    position: absolute; top: 1px; right: 2px; font-size: 9px; line-height: 1; pointer-events: none;
}

/* 提出バー */
.submit-area {
    margin-top: 10px; background: #fff; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 10px 12px;
}
#comment-box {
    width: 100%; padding: 8px 10px; margin-top: 5px; border: 1px solid #cbd5e1;
    border-radius: 8px; font-family: inherit; font-size: 13.5px; resize: vertical;
}
.dirty-badge {
    display: none; margin-top: 8px; background: #fff8e1; color: #b45309;
    border: 1px solid #fcd34d; border-radius: 8px; padding: 7px 10px;
    font-size: 12.5px; font-weight: 700; text-align: center;
}
.dirty-badge.show { display: block; }
#submit-btn {
    margin-top: 8px; width: 100%; padding: 13px; background: #FF4B4B; color: #fff;
    border: none; border-radius: 10px; font-size: 15.5px; font-weight: 800; cursor: pointer;
    box-shadow: 0 4px 10px rgba(255,75,75,0.28); transition: 0.15s;
}
#submit-btn:hover { background: #e03e3e; }

/* 詳細モーダル */
#detail-modal {
    display: none; position: fixed; inset: 0; background: rgba(15,23,42,0.5);
    z-index: 999999; justify-content: center; align-items: center; backdrop-filter: blur(2px);
}
.modal-content {
    background: #fff; width: min(340px, 92vw); max-height: calc(100vh - 20px); overflow-y: auto;
    padding: 18px; border-radius: 12px; box-shadow: 0 10px 28px rgba(0,0,0,0.25);
}
.modal-title {
    font-size: 15px; font-weight: 800; color: #1e293b; margin-bottom: 10px;
    border-bottom: 2px solid #4CAF50; padding-bottom: 6px;
}
.modal-label { font-size: 12px; font-weight: 700; color: #475569; margin-top: 12px; display: block; }
.status-switch { display: flex; gap: 8px; margin-top: 6px; }
.sw-btn {
    flex: 1; padding: 9px; border: 1px solid #cbd5e1; border-radius: 8px; cursor: pointer;
    font-size: 13px; font-weight: 700; background: #f8fafc; color: #475569;
}
.sw-btn.active[data-v="1"] { background: #4CAF50; color: #fff; border-color: #4CAF50; }
.sw-btn.active[data-v="2"] { background: #FFEB3B; color: #333; border-color: #FBC02D; }
.sw-btn.active[data-v="0"] { background: #475569; color: #fff; border-color: #334155; }
.modal-input {
    width: 100%; padding: 9px; margin-top: 6px; border: 1px solid #cbd5e1;
    border-radius: 8px; font-size: 14px;
}
.preset-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.preset-chip {
    background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 999px;
    padding: 4px 10px; font-size: 11px; font-weight: 700; color: #334155; cursor: pointer;
}
.preset-chip:hover { background: #e2e8f0; }
.modal-btns { display: flex; gap: 8px; margin-top: 16px; }
.modal-btn-save {
    flex: 1; background: #4CAF50; color: #fff; border: none; padding: 11px;
    border-radius: 8px; font-weight: 800; cursor: pointer; font-size: 14px;
}
.modal-btn-cancel {
    background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; padding: 11px 14px;
    border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 13px;
}
</style></head><body>

<div id="detail-modal">
    <div class="modal-content">
        <div class="modal-title" id="modal-cell-title">詳細設定</div>
        <label class="modal-label">🚥 予定のステータス</label>
        <div class="status-switch">
            <button type="button" class="sw-btn" data-v="1" onclick="setModalStatus(1)">◯ 可</button>
            <button type="button" class="sw-btn" data-v="2" onclick="setModalStatus(2)">△ 未定</button>
            <button type="button" class="sw-btn" data-v="0" onclick="setModalStatus(0)">× 不可</button>
        </div>
        <label class="modal-label">📝 補足メモ (任意)</label>
        <input type="text" id="modal-note" class="modal-input" placeholder="例: 13:30到着, 途中抜けあり">
        <div class="preset-row">
            <button type="button" class="preset-chip" onclick="appendNote('遅刻します')">遅刻します</button>
            <button type="button" class="preset-chip" onclick="appendNote('早退します')">早退します</button>
            <button type="button" class="preset-chip" onclick="appendNote('オンライン可')">オンライン可</button>
            <button type="button" class="preset-chip" onclick="document.getElementById('modal-note').value=''">🗑️ クリア</button>
        </div>
        <div class="modal-btns">
            <button type="button" class="modal-btn-cancel" onclick="closeModal()">キャンセル</button>
            <button type="button" class="modal-btn-save" onclick="saveModal()">💾 保存</button>
        </div>
    </div>
</div>

<div id="app-root"></div>

<script>
function sendMsg(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
}
function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function updateFrameHeight() {
    const root = document.getElementById('app-root');
    if (!root) return;
    const h = Math.ceil(root.getBoundingClientRect().height) + 6;
    sendMsg("streamlit:setFrameHeight", {height: h});
}

let stateArgs = null;
let selectedMode = 1;
let cellDetails = {};
let undoStack = [];
let editingCell = null;
let modalStatus = 1;
let lastSig = null;

// ズーム状態管理（縦横同時スケール）
let zoomScale = 1.0;
let baseCellH = 36;
const BASE_COL_W = 66;
const BASE_TIME_W = 58;

// フローティングパレット状態管理
let paletteVisible = null;
let fpVertical = false;
let fpMinimized = false;
let fpCustomPos = false;
let fpLeft = 10;
let fpTop = 120;
let fpJustDraggedUntil = 0;

function isMobileOrTouch() {
    return window.innerWidth <= 768 || (window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
}

function markDirty() {
    const b = document.getElementById('dirty-badge');
    if (b) b.classList.add('show');
}

function getBorderTop(tStr, eventType) {
    if (eventType === "timetable" || eventType === "date_timetable") return "1px solid #cbd5e1";
    if (tStr.endsWith(":00")) return "2px solid #475569";
    if (tStr.endsWith(":30")) return "1px dashed #94a3b8";
    return "1px solid #f1f5f9";
}

function cellKey(r, c) {
    const dStr = stateArgs.dateStrs[parseInt(c, 10)];
    return `${r}_${dStr}`;
}

function updCell(el, v) {
    const val = parseInt(v, 10) || 0;
    el.dataset.v = String(val);
    const key = cellKey(el.dataset.r, el.dataset.c);
    const detail = cellDetails[key];
    const note = detail ? (detail.note || "") : "";

    let bgColor = "#ffffff";
    let bgImg = "none";
    let txt = "";
    let txtColor = "#333";

    if (val === 1) {
        bgColor = "#4CAF50"; txt = "◯"; txtColor = "#ffffff";
    } else if (val === 2) {
        bgColor = "#FFEB3B"; txt = "△"; txtColor = "#333333";
    } else if (val === 3) {
        bgColor = "#e2e8f0";
        bgImg = "repeating-linear-gradient(45deg, transparent, transparent 5px, rgba(255,255,255,0.7) 5px, rgba(255,255,255,0.7) 10px)";
        txt = "授"; txtColor = "#475569";
    } else if (val === 0 && (note === "バイト/サークル等" || note === "バイト/私用")) {
        bgColor = "#f1f5f9"; txt = "休"; txtColor = "#94a3b8";
    }

    el.style.backgroundColor = bgColor;
    el.style.backgroundImage = bgImg;
    el.style.color = txtColor;

    let html = `<span class="cell-txt">${txt}</span>`;
    if (note !== "") {
        html += `<div class="memo-icon">💬</div>`;
    }
    el.innerHTML = html;
}

function paintCell(cell, mode) {
    if (!cell) return;
    const key = cellKey(cell.dataset.r, cell.dataset.c);
    const m = parseInt(mode, 10);
    if (m === 1 || m === 2 || m === 3) {
        const existingNote = cellDetails[key] ? (cellDetails[key].note || "") : "";
        if (existingNote) cellDetails[key] = {note: existingNote};
    } else if (m === 0) {
        const d = cellDetails[key];
        if (!(d && (d.note === "バイト/サークル等" || d.note === "バイト/私用"))) {
            delete cellDetails[key];
        }
    }
    updCell(cell, m);
}

function captureSnapshot() {
    const cells = [];
    document.querySelectorAll('#g .c').forEach(c => {
        cells.push(parseInt(c.dataset.v, 10) || 0);
    });
    return {
        cells: cells,
        details: JSON.parse(JSON.stringify(cellDetails))
    };
}

function snapshotsEqual(a, b) {
    if (!a || !b || a.cells.length !== b.cells.length) return false;
    for (let i = 0; i < a.cells.length; i++) {
        if (a.cells[i] !== b.cells[i]) return false;
    }
    return JSON.stringify(a.details) === JSON.stringify(b.details);
}

function restoreSnapshot(snap) {
    if (!snap) return;
    cellDetails = JSON.parse(JSON.stringify(snap.details));
    const nodes = document.querySelectorAll('#g .c');
    nodes.forEach((c, idx) => {
        if (idx < snap.cells.length) {
            updCell(c, snap.cells[idx]);
        }
    });
}

function pushUndo(snap) {
    const cur = captureSnapshot();
    if (snapshotsEqual(snap, cur)) return false;
    undoStack.push(snap);
    if (undoStack.length > 30) undoStack.shift();
    updateUndoBtn();
    markDirty();
    return true;
}

function updateUndoBtn() {
    const dis = (undoStack.length === 0);
    const b = document.getElementById('btn-undo');
    if (b) b.disabled = dis;
    const fpb = document.getElementById('fp-undo');
    if (fpb) fpb.disabled = dis;
}

window.doUndo = function() {
    if (undoStack.length === 0) return;
    const snap = undoStack.pop();
    restoreSnapshot(snap);
    updateUndoBtn();
    markDirty();
};

window.doClearAll = function() {
    if (!confirm("入力した内容をすべて白紙(×)に戻しますか？")) return;
    const snap = captureSnapshot();
    cellDetails = {};
    document.querySelectorAll('#g .c').forEach(c => updCell(c, 0));
    pushUndo(snap);
};

window.setPen = function(mode) {
    selectedMode = mode;
    document.querySelectorAll('.pen-pill, .fp-pen').forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.mode, 10) === mode);
    });
};

window.fpSetPen = function(mode) {
    if (Date.now() < fpJustDraggedUntil) return;
    setPen(mode);
};

window.fpAction = function(fn) {
    if (Date.now() < fpJustDraggedUntil) return;
    fn();
};

function applyZoom(newScale, anchor) {
    zoomScale = Math.max(0.55, Math.min(1.65, Math.round(newScale * 100) / 100));
    const root = document.getElementById('app-root');
    if (!root) return;

    const cellH = Math.max(18, Math.round(baseCellH * zoomScale));
    const colW = Math.max(36, Math.round(BASE_COL_W * zoomScale));
    const timeW = Math.max(44, Math.round(BASE_TIME_W * Math.max(0.76, Math.min(1.15, zoomScale))));
    const headH = Math.max(34, Math.round(46 * Math.max(0.78, Math.min(1.15, zoomScale))));
    const cellFont = Math.max(9.5, Math.round(13 * Math.max(0.74, Math.min(1.25, zoomScale)) * 10) / 10);
    const headFont = Math.max(9.5, Math.round(11.5 * Math.max(0.78, Math.min(1.15, zoomScale)) * 10) / 10);

    root.style.setProperty('--cell-h', cellH + 'px');
    root.style.setProperty('--col-w', colW + 'px');
    root.style.setProperty('--time-w', timeW + 'px');
    root.style.setProperty('--head-h', headH + 'px');
    root.style.setProperty('--cell-font', cellFont + 'px');
    root.style.setProperty('--head-font', headFont + 'px');

    const pctTxt = Math.round(zoomScale * 100) + '%';
    const zLbl = document.getElementById('zoom-pct-lbl');
    if (zLbl) zLbl.textContent = pctTxt;

    if (anchor && anchor.sc) {
        anchor.sc.scrollLeft = Math.max(0, anchor.ratioX * anchor.sc.scrollWidth - anchor.relX);
        anchor.sc.scrollTop = Math.max(0, anchor.ratioY * anchor.sc.scrollHeight - anchor.relY);
    }

    requestAnimationFrame(() => {
        syncTopScrollbar();
        clampPalettePosition();
        updateFrameHeight();
    });
}

window.stepZoom = function(delta) {
    applyZoom(zoomScale + delta, null);
};

window.resetZoom = function() {
    applyZoom(1.0, null);
};

function clampPalettePosition() {
    const fp = document.getElementById('floating-palette');
    const root = document.getElementById('app-root');
    const sc = document.getElementById('scroll-container');
    if (!fp || !root || fp.style.display === 'none') return;

    const rW = root.clientWidth;
    const rH = root.clientHeight;
    const pW = fp.offsetWidth || 260;
    const pH = fp.offsetHeight || 46;

    if (!fpCustomPos && sc) {
        fpLeft = Math.max(4, Math.min(rW - pW - 6, rW - pW - 8));
        fpTop = Math.max(54, sc.offsetTop + sc.clientHeight - pH - 10);
    } else {
        fpLeft = Math.max(2, Math.min(Math.max(2, rW - pW - 2), fpLeft));
        fpTop = Math.max(2, Math.min(Math.max(2, rH - pH - 2), fpTop));
    }
    fp.style.left = fpLeft + 'px';
    fp.style.top = fpTop + 'px';
}

function updatePaletteUI() {
    const fp = document.getElementById('floating-palette');
    const toggleBtn = document.getElementById('btn-fp-toggle');
    if (!fp) return;
    fp.style.display = paletteVisible ? 'block' : 'none';
    fp.classList.toggle('fp-vert', fpVertical);
    const fpMain = document.getElementById('fp-main');
    const fpFab = document.getElementById('fp-fab');
    if (fpMain && fpFab) {
        fpMain.style.display = fpMinimized ? 'none' : 'flex';
        fpFab.style.display = fpMinimized ? 'inline-flex' : 'none';
    }
    if (toggleBtn) {
        toggleBtn.classList.toggle('active-toggle', !!paletteVisible);
    }
    if (paletteVisible) {
        requestAnimationFrame(clampPalettePosition);
    }
}

window.togglePaletteVisibility = function() {
    paletteVisible = !paletteVisible;
    if (paletteVisible) fpMinimized = false;
    updatePaletteUI();
};

window.toggleFpDir = function() {
    fpVertical = !fpVertical;
    fpCustomPos = true;
    updatePaletteUI();
};

window.setFpMinimized = function(val) {
    fpMinimized = !!val;
    updatePaletteUI();
};

function attachPaletteDrag() {
    const fp = document.getElementById('floating-palette');
    const root = document.getElementById('app-root');
    if (!fp || !root) return;

    let dragState = null;

    fp.addEventListener('touchstart', e => {
        e.stopPropagation();
        if (e.touches.length !== 1) return;
        const t = e.touches[0];
        dragState = {
            startX: t.clientX,
            startY: t.clientY,
            origLeft: fpLeft,
            origTop: fpTop,
            moved: false
        };
    }, {passive: true});

    fp.addEventListener('touchmove', e => {
        e.stopPropagation();
        if (!dragState || e.touches.length !== 1) return;
        const t = e.touches[0];
        const dx = t.clientX - dragState.startX;
        const dy = t.clientY - dragState.startY;
        if (!dragState.moved && Math.hypot(dx, dy) > 7) {
            dragState.moved = true;
        }
        if (dragState.moved) {
            if (e.cancelable) e.preventDefault();
            fpJustDraggedUntil = Date.now() + 350;
            fpCustomPos = true;
            const maxL = Math.max(2, root.clientWidth - fp.offsetWidth - 2);
            const maxT = Math.max(2, root.clientHeight - fp.offsetHeight - 2);
            fpLeft = Math.max(2, Math.min(maxL, dragState.origLeft + dx));
            fpTop = Math.max(2, Math.min(maxT, dragState.origTop + dy));
            fp.style.left = fpLeft + 'px';
            fp.style.top = fpTop + 'px';
        }
    }, {passive: false});

    fp.addEventListener('touchend', e => {
        e.stopPropagation();
        dragState = null;
    }, {passive: true});

    fp.addEventListener('mousedown', e => {
        e.stopPropagation();
        if (e.button !== 0) return;
        dragState = {
            startX: e.clientX,
            startY: e.clientY,
            origLeft: fpLeft,
            origTop: fpTop,
            moved: false
        };
        const onMove = ev => {
            if (!dragState) return;
            const dx = ev.clientX - dragState.startX;
            const dy = ev.clientY - dragState.startY;
            if (!dragState.moved && Math.hypot(dx, dy) > 6) {
                dragState.moved = true;
            }
            if (dragState.moved) {
                fpJustDraggedUntil = Date.now() + 300;
                fpCustomPos = true;
                const maxL = Math.max(2, root.clientWidth - fp.offsetWidth - 2);
                const maxT = Math.max(2, root.clientHeight - fp.offsetHeight - 2);
                fpLeft = Math.max(2, Math.min(maxL, dragState.origLeft + dx));
                fpTop = Math.max(2, Math.min(maxT, dragState.origTop + dy));
                fp.style.left = fpLeft + 'px';
                fp.style.top = fpTop + 'px';
            }
        };
        const onUp = () => {
            dragState = null;
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    });
}

window.scrollGridX = function(delta) {
    const sc = document.getElementById('scroll-container');
    if (sc) sc.scrollBy({left: delta, behavior: 'smooth'});
};

window.toggleList = function(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = (el.style.display === 'none' ? 'block' : 'none');
};

window.doBulk = function(btnEl) {
    const val = parseInt(document.getElementById('b-val').value, 10);
    const sIdx = parseInt(document.getElementById('b-start').value, 10);
    const eIdx = parseInt(document.getElementById('b-end').value, 10);
    if (sIdx > eIdx) { alert('エラー：開始時刻は終了時刻より前に設定してください。'); return; }
    const snap = captureSnapshot();
    document.querySelectorAll('.b-day-chk').forEach(chk => {
        if (chk.checked) {
            const cIdx = parseInt(chk.value, 10);
            for (let r = sIdx; r <= eIdx; r++) {
                const cell = document.querySelector(`[data-r="${r}"][data-c="${cIdx}"]`);
                if (cell && cell.classList.contains('c')) paintCell(cell, val);
            }
        }
    });
    pushUndo(snap);
    const orig = btnEl.innerText;
    btnEl.innerText = "✅ 完了";
    setTimeout(() => btnEl.innerText = orig, 1400);
};

window.toggleToolsDrawer = function() {
    const dr = document.getElementById('tools-drawer');
    const btn = document.getElementById('btn-tools-toggle');
    if (!dr) return;
    const isOpen = dr.style.display !== 'none';
    dr.style.display = isOpen ? 'none' : 'block';
    if (btn) {
        btn.style.background = isOpen ? '#f8fafc' : '#e0f2fe';
        btn.style.borderColor = isOpen ? '#cbd5e1' : '#38bdf8';
    }
    setTimeout(() => { clampPalettePosition(); updateFrameHeight(); }, 30);
};

window.doCopy = function(btnEl) {
    const srcIdx = parseInt(document.getElementById('c-src').value, 10);
    const numRows = stateArgs.timeLabels.length;
    const srcVals = [];
    for (let r = 0; r < numRows; r++) {
        const cell = document.querySelector(`[data-r="${r}"][data-c="${srcIdx}"]`);
        srcVals.push((cell && cell.classList.contains('c')) ? parseInt(cell.dataset.v, 10) : 0);
    }
    const snap = captureSnapshot();
    let copied = false;
    document.querySelectorAll('.c-tgt-chk').forEach(chk => {
        if (chk.checked) {
            const cIdx = parseInt(chk.value, 10);
            if (cIdx !== srcIdx) {
                copied = true;
                for (let r = 0; r < numRows; r++) {
                    const cell = document.querySelector(`[data-r="${r}"][data-c="${cIdx}"]`);
                    if (cell && cell.classList.contains('c')) paintCell(cell, srcVals[r]);
                }
            }
        }
    });
    if (!copied) { alert('コピー先を選択してください。'); return; }
    pushUndo(snap);
    const orig = btnEl.innerText;
    btnEl.innerText = "✅ 完了";
    setTimeout(() => btnEl.innerText = orig, 1400);
};

window.doTimetable = function(btnEl) {
    const unavail = stateArgs.unavailColRows || {};
    if (Object.keys(unavail).length === 0) {
        alert('時間割が登録されていないか、対象日がありません。');
        return;
    }
    const snap = captureSnapshot();
    for (let c = 0; c < stateArgs.dateStrs.length; c++) {
        const key = String(c);
        if (unavail[key]) {
            unavail[key].forEach(item => {
                const r = (typeof item === 'object') ? item.row : item;
                const campus = (typeof item === 'object') ? (item.campus || "") : "";
                const cell = document.querySelector(`[data-r="${r}"][data-c="${c}"]`);
                if (cell && cell.classList.contains('c')) {
                    const cKey = cellKey(r, c);
                    if (campus === "💼 バイト/サークル等" || campus === "💼 バイト/私用") {
                        cellDetails[cKey] = {note: "バイト/サークル等"};
                        paintCell(cell, 0);
                    } else {
                        cellDetails[cKey] = {note: "定期授業"};
                        paintCell(cell, 3);
                    }
                }
            });
        }
    }
    pushUndo(snap);
    const orig = btnEl.innerHTML;
    btnEl.innerHTML = "✅ 反映完了！";
    setTimeout(() => btnEl.innerHTML = orig, 1600);
};

window.setModalStatus = function(v) {
    modalStatus = v;
    document.querySelectorAll('.sw-btn').forEach(b => {
        b.classList.toggle('active', parseInt(b.dataset.v, 10) === v);
    });
};

window.appendNote = function(txt) {
    const inp = document.getElementById('modal-note');
    if (!inp) return;
    inp.value = inp.value ? (inp.value + " " + txt) : txt;
};

window.openModal = function(cell) {
    if (!cell || stateArgs.isClosed) return;
    editingCell = cell;
    const r = parseInt(cell.dataset.r, 10);
    const c = parseInt(cell.dataset.c, 10);
    const titleEl = document.getElementById('modal-cell-title');
    if (titleEl) {
        titleEl.textContent = `💬 ${stateArgs.cleanLabels[c]} ${stateArgs.timeLabels[r]}`;
    }
    const key = cellKey(r, c);
    const detail = cellDetails[key] || {note: ""};
    const curVal = parseInt(cell.dataset.v, 10);
    setModalStatus(curVal === 3 ? 0 : (isNaN(curVal) ? 1 : curVal));
    document.getElementById('modal-note').value = detail.note || "";
    document.getElementById('detail-modal').style.display = 'flex';
};

window.closeModal = function() {
    document.getElementById('detail-modal').style.display = 'none';
    editingCell = null;
};

window.saveModal = function() {
    if (!editingCell) return;
    const snap = captureSnapshot();
    const key = cellKey(editingCell.dataset.r, editingCell.dataset.c);
    const note = document.getElementById('modal-note').value.trim();
    if (note) {
        cellDetails[key] = {note: note};
    } else {
        delete cellDetails[key];
    }
    updCell(editingCell, modalStatus);
    pushUndo(snap);
    closeModal();
};

const modalBg = document.getElementById('detail-modal');
modalBg.addEventListener('mousedown', e => { if (e.target === modalBg) closeModal(); });
modalBg.addEventListener('touchstart', e => { if (e.target === modalBg) closeModal(); }, {passive: true});

document.addEventListener('click', e => {
    if (!e.target.closest('.ms-container')) {
        document.querySelectorAll('.ms-options').forEach(el => el.style.display = 'none');
    }
});

let isSyncingScroll = false;
function syncTopScrollbar() {
    const sc = document.getElementById('scroll-container');
    const topWrap = document.getElementById('top-scroll-wrap');
    const topInner = document.getElementById('top-scroll-inner');
    if (!sc || !topWrap || !topInner) return;
    if (sc.scrollWidth > sc.clientWidth + 2) {
        topWrap.style.display = 'block';
        topInner.style.width = sc.scrollWidth + 'px';
        topWrap.scrollLeft = sc.scrollLeft;
    } else {
        topWrap.style.display = 'none';
    }
}

function attachGridEvents() {
    const g = document.getElementById('g');
    const sc = document.getElementById('scroll-container');
    const topWrap = document.getElementById('top-scroll-wrap');
    if (!g || !sc) return;

    if (topWrap) {
        topWrap.addEventListener('scroll', () => {
            if (isSyncingScroll) return;
            isSyncingScroll = true;
            sc.scrollLeft = topWrap.scrollLeft;
            isSyncingScroll = false;
        });
        sc.addEventListener('scroll', () => {
            if (isSyncingScroll) return;
            isSyncingScroll = true;
            topWrap.scrollLeft = sc.scrollLeft;
            isSyncingScroll = false;
        });
    }

    let lastTouchEventAt = 0;
    let isMousePainting = false;
    let mousePaintMode = 1;
    let mouseSnapshot = null;

    let isTouchPainting = false;
    let touchSnapshot = null;
    let touchStartTime = 0;
    let touchMoved = false;
    let isTwoFingerPan = false;
    let blockPaintUntilLift = false;
    let lastPinchCenter = null;
    let longPressTimer = null;
    let longPressOrigin = null;
    let longPressTriggered = false;
    let tapTargetCell = null;

    let autoScrollTimer = null;
    let lastClientX = 0;
    let lastClientY = 0;

    function stopAutoScroll() {
        if (autoScrollTimer) {
            clearInterval(autoScrollTimer);
            autoScrollTimer = null;
        }
    }

    function startAutoScroll(paintModeFn) {
        if (autoScrollTimer) return;
        autoScrollTimer = setInterval(() => {
            const rect = sc.getBoundingClientRect();
            const margin = 34;
            let dx = 0, dy = 0;
            if (lastClientY < rect.top + margin) dy = -12;
            else if (lastClientY > rect.bottom - margin) dy = 12;
            if (lastClientX < rect.left + margin) dx = -12;
            else if (lastClientX > rect.right - margin) dx = 12;
            if (dx !== 0 || dy !== 0) {
                sc.scrollBy(dx, dy);
                const cell = document.elementFromPoint(lastClientX, lastClientY)?.closest('.c');
                if (cell) paintCell(cell, paintModeFn());
            }
        }, 35);
    }

    function getTouchCenter(touches) {
        return {
            x: (touches[0].clientX + touches[1].clientX) / 2,
            y: (touches[0].clientY + touches[1].clientY) / 2
        };
    }

    g.addEventListener('contextmenu', e => e.preventDefault());

    // PC専用のダブルクリックメモ（スマホ連続タップ時の誤発動を完全防止）
    g.addEventListener('dblclick', e => {
        if (stateArgs.isClosed) return;
        if (Date.now() - lastTouchEventAt < 1600) return;
        if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) return;
        const cell = e.target.closest('.c');
        if (cell) openModal(cell);
    });

    g.addEventListener('mousedown', e => {
        if (stateArgs.isClosed) return;
        if (Date.now() - lastTouchEventAt < 1000) return;
        const cell = e.target.closest('.c');
        if (!cell) return;
        if (e.button === 2) {
            e.preventDefault();
            mousePaintMode = 0;
        } else if (e.button === 0) {
            if (selectedMode === -2) {
                openModal(cell);
                return;
            }
            mousePaintMode = selectedMode;
        } else {
            return;
        }
        mouseSnapshot = captureSnapshot();
        isMousePainting = true;
        lastClientX = e.clientX;
        lastClientY = e.clientY;
        paintCell(cell, mousePaintMode);
        startAutoScroll(() => mousePaintMode);
    });

    window.addEventListener('mousemove', e => {
        if (!isMousePainting) return;
        lastClientX = e.clientX;
        lastClientY = e.clientY;
        const cell = document.elementFromPoint(e.clientX, e.clientY)?.closest('.c');
        if (cell) paintCell(cell, mousePaintMode);
    });

    window.addEventListener('mouseup', () => {
        if (!isMousePainting) return;
        isMousePainting = false;
        stopAutoScroll();
        pushUndo(mouseSnapshot);
        mouseSnapshot = null;
    });

    g.addEventListener('touchstart', e => {
        lastTouchEventAt = Date.now();
        clearTimeout(longPressTimer);

        if (e.touches.length >= 2) {
            stopAutoScroll();
            if (isTouchPainting && (Date.now() - touchStartTime) < 300 && touchSnapshot) {
                restoreSnapshot(touchSnapshot);
            }
            isTouchPainting = false;
            isTwoFingerPan = true;
            blockPaintUntilLift = true;
            lastPinchCenter = getTouchCenter(e.touches);
            if (e.cancelable) e.preventDefault();
            return;
        }

        if (stateArgs.isClosed) return;
        if (e.target.closest('.time-col') || e.target.closest('.header-cell')) return;

        if (e.touches.length === 1 && !blockPaintUntilLift) {
            const cell = e.target.closest('.c');
            if (!cell) return;
            const t = e.touches[0];
            touchMoved = false;
            longPressTriggered = false;
            tapTargetCell = cell;

            if (selectedMode === -2) {
                longPressOrigin = {x: t.clientX, y: t.clientY, cell: cell};
                return;
            }

            touchSnapshot = captureSnapshot();
            touchStartTime = Date.now();
            isTouchPainting = true;
            lastClientX = t.clientX;
            lastClientY = t.clientY;
            longPressOrigin = {x: t.clientX, y: t.clientY, cell: cell};

            paintCell(cell, selectedMode);
            startAutoScroll(() => selectedMode);

            longPressTimer = setTimeout(() => {
                if (isTouchPainting && !touchMoved && !isTwoFingerPan) {
                    longPressTriggered = true;
                    isTouchPainting = false;
                    stopAutoScroll();
                    if (touchSnapshot) restoreSnapshot(touchSnapshot);
                    try { if (navigator.vibrate) navigator.vibrate(15); } catch (err) {}
                    openModal(cell);
                }
            }, 580);
        }
    }, {passive: false});

    g.addEventListener('touchmove', e => {
        lastTouchEventAt = Date.now();

        if (isTwoFingerPan || e.touches.length >= 2) {
            if (e.cancelable) e.preventDefault();
            if (!isTwoFingerPan && e.touches.length >= 2) {
                clearTimeout(longPressTimer);
                stopAutoScroll();
                if (isTouchPainting && (Date.now() - touchStartTime) < 300 && touchSnapshot) {
                    restoreSnapshot(touchSnapshot);
                }
                isTouchPainting = false;
                isTwoFingerPan = true;
                blockPaintUntilLift = true;
                lastPinchCenter = getTouchCenter(e.touches);
            }
            if (e.touches.length >= 2 && lastPinchCenter) {
                const center = getTouchCenter(e.touches);
                const dx = center.x - lastPinchCenter.x;
                const dy = center.y - lastPinchCenter.y;
                lastPinchCenter = center;

                sc.scrollLeft -= dx;
                const prevTop = sc.scrollTop;
                sc.scrollTop -= dy;
                const appliedY = prevTop - sc.scrollTop;
                const remY = (-dy) - appliedY;
                if (Math.abs(remY) > 0.5) {
                    try { window.parent.scrollBy(0, remY); } catch (err) {}
                }
            }
            return;
        }

        if (stateArgs.isClosed) return;

        if (selectedMode === -2 && longPressOrigin && e.touches.length === 1) {
            const t = e.touches[0];
            if (Math.hypot(t.clientX - longPressOrigin.x, t.clientY - longPressOrigin.y) > 8) {
                touchMoved = true;
            }
            return;
        }

        if (isTouchPainting && e.touches.length === 1 && !longPressTriggered) {
            const t = e.touches[0];
            if (longPressOrigin && Math.hypot(t.clientX - longPressOrigin.x, t.clientY - longPressOrigin.y) > 8) {
                touchMoved = true;
                clearTimeout(longPressTimer);
            }
            if (e.cancelable) e.preventDefault();
            lastClientX = t.clientX;
            lastClientY = t.clientY;
            const cell = document.elementFromPoint(t.clientX, t.clientY)?.closest('.c');
            if (cell) paintCell(cell, selectedMode);
        }
    }, {passive: false});

    const handleTouchEnd = (e) => {
        lastTouchEventAt = Date.now();
        clearTimeout(longPressTimer);
        stopAutoScroll();
        if (e.touches.length === 0) {
            if (!stateArgs.isClosed && selectedMode === -2 && !isTwoFingerPan && !touchMoved && tapTargetCell) {
                openModal(tapTargetCell);
            } else if (isTouchPainting && !longPressTriggered && touchSnapshot) {
                pushUndo(touchSnapshot);
            }
            isTouchPainting = false;
            isTwoFingerPan = false;
            blockPaintUntilLift = false;
            lastPinchCenter = null;
            touchSnapshot = null;
            tapTargetCell = null;
        }
    };
    g.addEventListener('touchend', handleTouchEnd);
    g.addEventListener('touchcancel', handleTouchEnd);
}

function buildEditor(args) {
    stateArgs = args;
    cellDetails = JSON.parse(JSON.stringify(args.cellDetails || {}));
    undoStack = [];
    const cols = args.dateStrs.length;
    const rows = args.timeLabels.length;
    const isClosed = !!args.isClosed;
    const isTimeMode = !!args.isTimeMode;
    baseCellH = args.defaultCellH || (isTimeMode ? 34 : 48);

    if (paletteVisible === null) {
        paletteVisible = !isClosed && isMobileOrTouch();
    }

    const timeOptsHtml = args.timeLabels.map((t, i) => `<option value="${i}">${escapeHtml(t)}</option>`).join('');
    const timeEndOptsHtml = args.timeLabels.map((t, i) => `<option value="${i}" ${i === rows - 1 ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('');
    const srcOptsHtml = args.cleanLabels.map((l, i) => `<option value="${i}">${escapeHtml(l)}</option>`).join('');
    const bDayOptsHtml = args.cleanLabels.map((l, i) => `<label class="ms-opt"><input type="checkbox" class="b-day-chk" value="${i}" checked> ${escapeHtml(l)}</label>`).join('');
    const cTgtOptsHtml = args.cleanLabels.map((l, i) => `<label class="ms-opt"><input type="checkbox" class="c-tgt-chk" value="${i}"> ${escapeHtml(l)}</label>`).join('');

    const zoomControls = `
        <div class="zoom-group" title="予定表の縮小・拡大">
            <button type="button" class="zoom-btn" onclick="stepZoom(-0.15)">🔍−</button>
            <button type="button" class="zoom-lbl" id="zoom-pct-lbl" onclick="resetZoom()">100%</button>
            <button type="button" class="zoom-btn" onclick="stepZoom(0.15)">＋</button>
        </div>`;

    const jumpBtns = cols > 6 ? `
        <div class="tb-group">
            <button type="button" class="act-pill" onclick="scrollGridX(-240)">◀</button>
            <button type="button" class="act-pill" onclick="scrollGridX(240)">▶</button>
        </div>` : "";

    let toolsDrawer = "";
    if (!isClosed) {
        const ttBtnText = args.eventType === "time"
            ? "🚫 登録済みの時間割をすべて反映する"
            : "🚫 登録済みの時間割をそのまま反映する";
        toolsDrawer = `
        <div id="tools-drawer" style="display:none; background:#f8fafc; border:1px solid #cbd5e1; border-radius:10px; padding:10px 12px; margin-bottom:8px;">
            <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; padding-bottom:8px; margin-bottom:6px; border-bottom:1px solid #e2e8f0;">
                <span style="font-size:12px; font-weight:700; color:#475569;">🪄 一括入力・コピー・時間割反映</span>
                <button type="button" class="act-pill" style="color:#b91c1c; border-color:#fecaca; background:#fef2f2;" onclick="doClearAll()">🗑️ すべて白紙に戻す</button>
            </div>
            <div class="tools-grid" style="margin-top:0;">
                <div class="tool-card" style="display:${args.eventType === 'timetable' ? 'none' : 'block'};">
                    <div class="tool-header">🪄 一括指定</div>
                    <div style="display:flex; gap:6px; margin-bottom:8px; align-items:center; flex-wrap:wrap; font-size:12px;">
                        <select id="b-val" class="st-sel"><option value="1">◯ 可</option><option value="2">△ 未定</option><option value="0">× 不可</option></select>
                        <select id="b-start" class="st-sel">${timeOptsHtml}</select>〜<select id="b-end" class="st-sel">${timeEndOptsHtml}</select>
                    </div>
                    <div style="display:flex; gap:6px; align-items:center;">
                        <div class="ms-container">
                            <div class="ms-header" onclick="toggleList('b-days-list')">対象日を選択 <span>▼</span></div>
                            <div id="b-days-list" class="ms-options" style="display:none;">
                                <label class="ms-opt" style="font-weight:700;"><input type="checkbox" onchange="document.querySelectorAll('.b-day-chk').forEach(c => c.checked = this.checked)" checked> 全て選択 / 解除</label>
                                <hr style="margin:4px 0; border:0; border-top:1px solid #e2e8f0;">
                                ${bDayOptsHtml}
                            </div>
                        </div>
                        <button type="button" class="st-btn" onclick="doBulk(this)">適用</button>
                    </div>
                </div>
                <div class="tool-card">
                    <div class="tool-header">📋 日程コピー</div>
                    <div style="display:flex; gap:6px; margin-bottom:8px; align-items:center; font-size:12px;">
                        元: <select id="c-src" class="st-sel" style="flex:1;">${srcOptsHtml}</select>
                    </div>
                    <div style="display:flex; gap:6px; align-items:center;">
                        <div class="ms-container">
                            <div class="ms-header" onclick="toggleList('c-tgt-list')">コピー先を選択 <span>▼</span></div>
                            <div id="c-tgt-list" class="ms-options" style="display:none;">
                                <label class="ms-opt" style="font-weight:700;"><input type="checkbox" onchange="document.querySelectorAll('.c-tgt-chk').forEach(c => c.checked = this.checked)"> 全て選択 / 解除</label>
                                <hr style="margin:4px 0; border:0; border-top:1px solid #e2e8f0;">
                                ${cTgtOptsHtml}
                            </div>
                        </div>
                        <button type="button" class="st-btn" style="background:#FF9800;" onclick="doCopy(this)">コピー</button>
                    </div>
                </div>
                <div class="tool-card">
                    <div class="tool-header">⏰ 時間割反映</div>
                    <p style="font-size:11.5px; color:#64748b; margin:0 0 8px 0;">登録済みの時間割を「授」として一括反映します。</p>
                    <button type="button" class="st-btn" style="background:#E91E63; width:100%;" onclick="doTimetable(this)">${ttBtnText}</button>
                </div>
            </div>
        </div>`;
    }

    const penControls = !isClosed ? `
        <div class="tb-row">
            <div class="tb-group">
                <button type="button" class="pen-pill ${selectedMode===1?'active':''}" data-mode="1" onclick="setPen(1)">🟢 ◯ 可</button>
                <button type="button" class="pen-pill ${selectedMode===2?'active':''}" data-mode="2" onclick="setPen(2)">🟡 △ 未定</button>
                <button type="button" class="pen-pill ${selectedMode===0?'active':''}" data-mode="0" onclick="setPen(0)">⚪ 消す</button>
                <button type="button" class="pen-pill ${selectedMode===-2?'active':''}" data-mode="-2" onclick="setPen(-2)">💬 メモ</button>
            </div>
            <div class="tb-group">
                <button type="button" class="act-pill" id="btn-undo" onclick="doUndo()" disabled>↩ 戻す</button>
                ${zoomControls}
                <button type="button" class="act-pill" id="btn-fp-toggle" onclick="togglePaletteVisibility()">🎨 パレット</button>
                <button type="button" class="act-pill" id="btn-tools-toggle" onclick="toggleToolsDrawer()">⚙️ 便利機能</button>
                ${jumpBtns}
            </div>
        </div>` : `
        <div class="tb-row">
            <div class="tb-group">${zoomControls}</div>
            ${jumpBtns}
        </div>`;

    const toolbarHtml = `
        <div class="editor-toolbar">
            ${penControls}
            ${!isClosed ? `<div class="hint-bar">
                <span class="hint-pc">💡 ドラッグで塗る ／ 右クリックで消す ／ ダブルクリックでメモ</span>
                <span class="hint-touch">💡 1本指で塗る ／ 2本指でスクロール ／ 🔍−＋で縮小・拡大 ／ 長押しでメモ ／ 🎨パレットは移動可</span>
            </div>` : ''}
        </div>`;

    const floatingPaletteHtml = !isClosed ? `
        <div id="floating-palette" class="fp-box" style="display:none;">
            <div class="fp-main" id="fp-main">
                <div class="fp-grip" id="fp-grip" title="ドラッグして移動">⠿</div>
                <button type="button" class="fp-pen ${selectedMode===1?'active':''}" data-mode="1" onclick="fpSetPen(1)" title="◯ 可">◯</button>
                <button type="button" class="fp-pen ${selectedMode===2?'active':''}" data-mode="2" onclick="fpSetPen(2)" title="△ 未定">△</button>
                <button type="button" class="fp-pen ${selectedMode===0?'active':''}" data-mode="0" onclick="fpSetPen(0)" title="× 消す">×</button>
                <button type="button" class="fp-pen ${selectedMode===-2?'active':''}" data-mode="-2" onclick="fpSetPen(-2)" title="メモ">💬</button>
                <div class="fp-sep"></div>
                <button type="button" class="fp-act" id="fp-undo" onclick="fpAction(doUndo)" disabled title="戻す">↩</button>
                <button type="button" class="fp-act" onclick="fpAction(function(){stepZoom(-0.15);})" title="縮小">−</button>
                <button type="button" class="fp-act" onclick="fpAction(function(){stepZoom(0.15);})" title="拡大">＋</button>
                <button type="button" class="fp-act" onclick="fpAction(toggleFpDir)" title="縦横切替">⇄</button>
                <button type="button" class="fp-act" onclick="fpAction(function(){setFpMinimized(true);})" title="最小化">＿</button>
            </div>
            <button type="button" class="fp-fab" id="fp-fab" style="display:none;" onclick="fpAction(function(){setFpMinimized(false);})">🎨 ペンを開く</button>
        </div>` : "";

    let timeCellsHtml = "";
    for (let r = 0; r < rows; r++) {
        const tStr = args.timeLabels[r];
        const bTop = getBorderTop(tStr, args.eventType);
        const showLbl = (!isTimeMode || tStr.endsWith(":00") || tStr.endsWith(":30")) ? escapeHtml(tStr) : "";
        timeCellsHtml += `<div class="time-cell" style="border-top:${bTop};">${showLbl}</div>`;
    }
    const timeColHtml = `<div class="time-col"><div class="top-left-cell">時間</div>${timeCellsHtml}</div>`;

    let dayColsHtml = "";
    for (let c = 0; c < cols; c++) {
        const lbl = escapeHtml(args.cleanLabels[c]).replace("(", "<br>(");
        const dKind = args.dayKinds[c] || "weekday";
        const kindCls = dKind === "sat" ? "day-sat" : (dKind === "sun" ? "day-sun" : "");
        const wkCls = args.weekBreaks[c] ? "week-break" : "";
        let cellsHtml = "";
        for (let r = 0; r < rows; r++) {
            const bTop = getBorderTop(args.timeLabels[r], args.eventType);
            const val = (args.matrix[r] && args.matrix[r][c] !== undefined) ? args.matrix[r][c] : 0;
            cellsHtml += `<div class="c" data-r="${r}" data-c="${c}" data-v="${val}" style="border-top:${bTop};"></div>`;
        }
        dayColsHtml += `<div class="day-col ${wkCls}" data-c="${c}"><div class="header-cell ${kindCls}">${lbl}</div>${cellsHtml}</div>`;
    }

    const submitSection = !isClosed ? `
        <div class="submit-area">
            <label style="font-size:13px; font-weight:700; color:#334155;">📝 全体へのコメント（任意）</label>
            <textarea id="comment-box" rows="2" placeholder="遅刻・早退などの連絡があれば入力">${escapeHtml(args.myComment || "")}</textarea>
            <div id="dirty-badge" class="dirty-badge">⚠️ 未保存の変更があります（「提出」を押すと保存されます）</div>
            <button type="button" id="submit-btn">✅ 回答を保存して提出する</button>
        </div>` : `
        <div class="submit-area">
            <label style="font-size:13px; font-weight:700; color:#334155;">📝 全体へのコメント</label>
            <div style="margin-top:6px; padding:10px; background:#f1f5f9; border-radius:8px; font-size:14px; min-height:40px; white-space:pre-wrap;">${escapeHtml(args.myComment || "（なし）")}</div>
        </div>`;

    const scrollClass = isTimeMode ? "time-scroll" : "auto-scroll";
    const lockGridStyle = isClosed ? "opacity:0.85;" : "";

    const root = document.getElementById('app-root');
    root.innerHTML = `
        ${toolbarHtml}
        ${toolsDrawer}
        <div class="top-scroll-wrap" id="top-scroll-wrap"><div class="top-scroll-inner" id="top-scroll-inner"></div></div>
        <div class="scroll-wrapper ${scrollClass}" id="scroll-container">
            <div id="g" style="grid-template-columns: var(--time-w) repeat(${cols}, minmax(var(--col-w), 1fr)); ${lockGridStyle}">
                ${timeColHtml}
                ${dayColsHtml}
            </div>
        </div>
        ${floatingPaletteHtml}
        ${submitSection}
    `;

    document.querySelectorAll('#g .c').forEach(cell => updCell(cell, cell.dataset.v));

    const cb = document.getElementById('comment-box');
    if (cb) cb.addEventListener('input', markDirty);

    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
        submitBtn.addEventListener('click', () => {
            const res = Array.from({length: rows}, (_, r) =>
                Array.from({length: cols}, (_, c) => {
                    const node = document.querySelector(`[data-r="${r}"][data-c="${c}"]`);
                    const v = node ? parseInt(node.dataset.v, 10) : 0;
                    return isNaN(v) ? 0 : v;
                })
            );
            const commentText = cb ? cb.value : "";
            submitBtn.innerText = "⏳ 保存処理中...";
            submitBtn.style.opacity = "0.7";
            submitBtn.style.pointerEvents = "none";
            sendMsg("streamlit:setComponentValue", {
                value: {
                    data: res,
                    comment: commentText,
                    cell_details: cellDetails,
                    trigger_save: true,
                    ts: Date.now()
                },
                dataType: "json"
            });
            setTimeout(() => {
                submitBtn.innerText = "✅ 回答を保存して提出する";
                submitBtn.style.opacity = "1";
                submitBtn.style.pointerEvents = "auto";
            }, 5000);
        });
    }

    attachGridEvents();
    attachPaletteDrag();
    applyZoom(zoomScale, null);
    updatePaletteUI();
    setTimeout(() => { syncTopScrollbar(); clampPalettePosition(); updateFrameHeight(); }, 45);
}

window.addEventListener("message", function(event) {
    if (!event.data || event.data.type !== "streamlit:render") return;
    const args = event.data.args || {};
    const sig = `${args.eventId}|${args.saveTs}|${args.importTs}|${args.isClosed}|${args.eventType}|${(args.dateStrs||[]).length}`;
    if (lastSig === sig) {
        syncTopScrollbar();
        clampPalettePosition();
        updateFrameHeight();
        return;
    }
    lastSig = sig;
    buildEditor(args);
});

window.addEventListener('resize', () => { syncTopScrollbar(); clampPalettePosition(); updateFrameHeight(); });
const ro = new ResizeObserver(() => updateFrameHeight());
ro.observe(document.getElementById('app-root'));
sendMsg("streamlit:componentReady", {apiVersion: 1});
</script></body></html>
"""

AGG_VIEWER_V1_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: transparent; }
* { box-sizing: border-box; }
#app-root {
    --cell-h: 36px; --col-w: 66px; --time-w: 58px; --head-h: 46px;
    --cell-font: 13.5px; --head-font: 11.5px;
    padding: 2px 2px 6px 2px;
}

.agg-toolbar {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
    gap: 6px; background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px;
    padding: 6px 10px; margin-bottom: 6px;
}
.tb-group { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 12px; color: #334155; font-weight: 700; }
.grad-bar {
    width: 64px; height: 10px; border-radius: 999px; border: 1px solid #cbd5e1;
    background: linear-gradient(90deg, #f3faf4, #1b5e20); display: inline-block;
}
.jump-pill {
    border: 1px solid #cbd5e1; background: #fff; color: #334155;
    padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 700; cursor: pointer;
}
.jump-pill:hover { background: #e2e8f0; }

.zoom-group {
    display: inline-flex; align-items: center; border: 1px solid #cbd5e1;
    border-radius: 8px; overflow: hidden; background: #fff;
}
.zoom-btn {
    border: none; background: #f8fafc; color: #1e293b; padding: 4px 8px;
    font-size: 12px; font-weight: 800; cursor: pointer; line-height: 1.2;
}
.zoom-btn:hover { background: #e2e8f0; }
.zoom-lbl {
    border: none; border-left: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0;
    background: #fff; color: #334155; padding: 4px 7px; font-size: 11px; font-weight: 800;
    cursor: pointer; min-width: 44px; text-align: center;
}

.top-scroll-wrap {
    overflow-x: auto; overflow-y: hidden; width: 100%; height: 14px;
    margin-bottom: 3px; display: none;
    scrollbar-width: auto; scrollbar-color: #94a3b8 #f1f5f9;
}
.top-scroll-wrap::-webkit-scrollbar { height: 9px; }
.top-scroll-wrap::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
.top-scroll-wrap::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 6px; }
.top-scroll-inner { height: 1px; }

.agg-scroll {
    width: 100%; overflow: auto; -webkit-overflow-scrolling: touch;
    touch-action: pan-x pan-y;
    border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; position: relative;
    scrollbar-width: auto; scrollbar-color: #94a3b8 #f1f5f9;
}
.agg-scroll.time-scroll { max-height: 550px; height: auto; }
@media (max-width: 650px) {
    .agg-scroll.time-scroll { max-height: 450px; }
}
.agg-scroll.auto-scroll { max-height: none; height: auto; }
.agg-scroll::-webkit-scrollbar { width: 10px; height: 10px; }
.agg-scroll::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
.agg-scroll::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 6px; border: 2px solid #f1f5f9; }
.agg-scroll::-webkit-scrollbar-thumb:hover { background: #64748b; }

#agg-grid { display: grid; width: 100%; min-width: max-content; user-select: none; }
.agg-time-col {
    position: sticky; left: 0; z-index: 15; background: #f1f5f9;
    box-shadow: 2px 0 6px rgba(0,0,0,0.08); grid-column: 1 / 2;
}
.agg-top-left {
    position: sticky; top: 0; left: 0; z-index: 25; background: #f1f5f9;
    border-right: 1px solid #cbd5e1; border-bottom: 2px solid #475569;
    height: var(--head-h); box-shadow: 2px 2px 6px rgba(0,0,0,0.08);
    display: flex; align-items: center; justify-content: center;
    font-size: 10.5px; color: #64748b; font-weight: 700;
}
.agg-time-cell {
    background: #f1f5f9; font-size: 10.5px; font-weight: 700; color: #475569;
    display: flex; align-items: center; justify-content: center;
    height: var(--cell-h); border-right: 1px solid #cbd5e1; overflow: hidden;
}
.agg-day-col { box-sizing: border-box; }
.agg-day-col.week-break { border-left: 2px solid #64748b; }
.agg-header {
    position: sticky; top: 0; z-index: 12; background: #f8fafc;
    font-size: var(--head-font); font-weight: 800; text-align: center; color: #1e293b;
    border-bottom: 2px solid #475569; border-right: 1px solid #e2e8f0;
    height: var(--head-h); display: flex; align-items: center; justify-content: center;
    padding: 3px 2px; line-height: 1.2; overflow: hidden;
}
.agg-header.day-sat { background: #eff6ff; color: #1d4ed8; }
.agg-header.day-sun { background: #fef2f2; color: #dc2626; }

.agg-cell {
    border-right: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: center;
    height: var(--cell-h); font-size: var(--cell-font); font-weight: 800; position: relative; cursor: pointer;
    transition: filter 0.1s; -webkit-tap-highlight-color: rgba(16,185,129,0.22); overflow: hidden;
}
@media (hover: hover) and (pointer: fine) {
    .agg-cell:hover { filter: brightness(0.95); }
}
.agg-cell.agg-selected { outline: 3px solid #0f172a; outline-offset: -3px; z-index: 5; }
.agg-cell.req-blocked {
    background-image: repeating-linear-gradient(45deg, rgba(148,163,184,0.22), rgba(148,163,184,0.22) 5px, transparent 5px, transparent 10px) !important;
    opacity: 0.55;
}
.agg-cell.my-yes { box-shadow: inset 0 0 0 2.5px #1565C0; }
.agg-cell.my-maybe { box-shadow: inset 0 0 0 2.5px #EF6C00; }
.my-badge {
    position: absolute; top: 1px; right: 2px; font-size: 9px; font-weight: 900;
    line-height: 1; padding: 1px 3px; border-radius: 3px; pointer-events: none;
}
.my-badge-yes { background: #1565C0; color: #fff; }
.my-badge-maybe { background: #EF6C00; color: #fff; }

/* PC用ホバープレビュー */
#agg-hover {
    display: none; position: fixed; z-index: 99998; pointer-events: none;
    width: 240px; max-height: calc(100vh - 16px); overflow: hidden;
    background: rgba(15, 23, 42, 0.96); color: #f8fafc;
    border-radius: 10px; padding: 10px 12px; font-size: 12px; line-height: 1.45;
    box-shadow: 0 10px 26px rgba(0,0,0,0.35);
}

/* スマホ・PC共通 タップ/クリック即時モーダル */
#agg-modal {
    display: none; position: fixed; inset: 0; z-index: 999999;
    background: rgba(15, 23, 42, 0.48); backdrop-filter: blur(2px);
    align-items: center; justify-content: center; padding: 12px;
}
#agg-modal.open { display: flex; }
.agg-modal-card {
    background: #fff; width: min(440px, 94vw); max-height: calc(100vh - 24px);
    overflow-y: auto; -webkit-overflow-scrolling: touch;
    border-radius: 14px; padding: 16px; border: 2px solid #10b981;
    box-shadow: 0 16px 40px rgba(15,23,42,0.3);
    animation: modalPop 0.14s ease-out;
}
@keyframes modalPop {
    from { opacity: 0; transform: scale(0.95) translateY(6px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
}
.dp-head {
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;
    border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 10px;
}
.dp-title { font-size: 15px; font-weight: 800; color: #0f172a; }
.dp-actions { display: flex; gap: 6px; align-items: center; }
.dp-btn {
    border: 1px solid #cbd5e1; background: #f8fafc; color: #334155;
    padding: 5px 10px; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer;
}
.dp-btn:hover { background: #e2e8f0; }
.dp-section { margin-bottom: 10px; }
.dp-section:last-child { margin-bottom: 0; }
.dp-sec-title { font-size: 12px; font-weight: 800; margin-bottom: 5px; }
.chip-wrap { display: flex; flex-wrap: wrap; gap: 5px; }
.m-chip {
    display: inline-block; font-size: 12px; padding: 3px 9px; border-radius: 999px; font-weight: 600;
}
.chip-yes { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
.chip-maybe { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
.chip-no { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }
.req-warn {
    background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;
    border-radius: 8px; padding: 7px 10px; font-size: 12px; font-weight: 700; margin-bottom: 10px;
}
</style></head><body>

<div id="agg-hover"></div>
<div id="agg-modal"><div class="agg-modal-card" id="agg-modal-card"></div></div>
<div id="app-root"></div>

<script>
function sendMsg(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
}
function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function updateFrameHeight() {
    const root = document.getElementById('app-root');
    if (!root) return;
    const h = Math.ceil(root.getBoundingClientRect().height) + 6;
    sendMsg("streamlit:setFrameHeight", {height: h});
}

let aggArgs = null;
let selectedCellKey = null;
let lastTouchTime = 0;
let lastTapHandledAt = 0;
let isSyncingScroll = false;

let aggZoomScale = 1.0;
let aggBaseCellH = 36;
const AGG_BASE_COL_W = 66;
const AGG_BASE_TIME_W = 58;

function getBorderTop(tStr, eventType) {
    if (eventType === "timetable" || eventType === "date_timetable") return "1px solid #cbd5e1";
    if (tStr.endsWith(":00")) return "2px solid #475569";
    if (tStr.endsWith(":30")) return "1px dashed #94a3b8";
    return "1px solid #f1f5f9";
}

function syncTopScrollbar() {
    const sc = document.getElementById('agg-scroll');
    const topWrap = document.getElementById('agg-top-scroll');
    const topInner = document.getElementById('agg-top-inner');
    if (!sc || !topWrap || !topInner) return;
    if (sc.scrollWidth > sc.clientWidth + 2) {
        topWrap.style.display = 'block';
        topInner.style.width = sc.scrollWidth + 'px';
        topWrap.scrollLeft = sc.scrollLeft;
    } else {
        topWrap.style.display = 'none';
    }
}

function applyAggZoom(newScale, anchor) {
    aggZoomScale = Math.max(0.55, Math.min(1.65, Math.round(newScale * 100) / 100));
    const root = document.getElementById('app-root');
    if (!root) return;

    const cellH = Math.max(18, Math.round(aggBaseCellH * aggZoomScale));
    const colW = Math.max(36, Math.round(AGG_BASE_COL_W * aggZoomScale));
    const timeW = Math.max(44, Math.round(AGG_BASE_TIME_W * Math.max(0.76, Math.min(1.15, aggZoomScale))));
    const headH = Math.max(34, Math.round(46 * Math.max(0.78, Math.min(1.15, aggZoomScale))));
    const cellFont = Math.max(9.5, Math.round(13.5 * Math.max(0.72, Math.min(1.25, aggZoomScale)) * 10) / 10);
    const headFont = Math.max(9.5, Math.round(11.5 * Math.max(0.78, Math.min(1.15, aggZoomScale)) * 10) / 10);

    root.style.setProperty('--cell-h', cellH + 'px');
    root.style.setProperty('--col-w', colW + 'px');
    root.style.setProperty('--time-w', timeW + 'px');
    root.style.setProperty('--head-h', headH + 'px');
    root.style.setProperty('--cell-font', cellFont + 'px');
    root.style.setProperty('--head-font', headFont + 'px');

    const zLbl = document.getElementById('agg-zoom-lbl');
    if (zLbl) zLbl.textContent = Math.round(aggZoomScale * 100) + '%';

    if (anchor && anchor.sc) {
        anchor.sc.scrollLeft = Math.max(0, anchor.ratioX * anchor.sc.scrollWidth - anchor.relX);
        anchor.sc.scrollTop = Math.max(0, anchor.ratioY * anchor.sc.scrollHeight - anchor.relY);
    }

    requestAnimationFrame(() => {
        syncTopScrollbar();
        updateFrameHeight();
    });
}

window.stepAggZoom = function(delta) {
    applyAggZoom(aggZoomScale + delta, null);
};

window.resetAggZoom = function() {
    applyAggZoom(1.0, null);
};

window.scrollAggX = function(delta) {
    const sc = document.getElementById('agg-scroll');
    if (sc) sc.scrollBy({left: delta, behavior: 'smooth'});
};

window.closeDetailPanel = function() {
    selectedCellKey = null;
    document.querySelectorAll('.agg-cell.agg-selected').forEach(el => el.classList.remove('agg-selected'));
    const modal = document.getElementById('agg-modal');
    if (modal) modal.classList.remove('open');
    const root = document.getElementById('app-root');
    if (root) root.style.minHeight = '';
    updateFrameHeight();
};

const modalBackdrop = document.getElementById('agg-modal');
if (modalBackdrop) {
    modalBackdrop.addEventListener('click', e => {
        if (e.target === modalBackdrop) closeDetailPanel();
    });
}

window.copyYesNames = function(r, c) {
    const info = (aggArgs.cellInfo || {})[`${r}_${c}`];
    if (!info || !info.yes || info.yes.length === 0) return;
    const text = info.yes.join('\\n');
    const btn = document.getElementById('dp-copy-btn');
    const done = () => {
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = "✅ コピー済み";
            setTimeout(() => btn.textContent = orig, 1500);
        }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = text; document.body.appendChild(ta); ta.select();
            try { document.execCommand('copy'); } catch (e) {}
            document.body.removeChild(ta); done();
        });
    }
};

function openDetailPanel(cell, r, c) {
    const key = `${r}_${c}`;
    selectedCellKey = key;
    document.querySelectorAll('.agg-cell.agg-selected').forEach(el => el.classList.remove('agg-selected'));
    cell.classList.add('agg-selected');

    const info = (aggArgs.cellInfo || {})[key] || {};
    const modal = document.getElementById('agg-modal');
    const card = document.getElementById('agg-modal-card');
    if (!modal || !card) return;

    const titleText = `${aggArgs.cleanLabels[c]} ${aggArgs.timeLabels[r]}`;
    const scoreTxt = info.scoreText || "0";

    let bodyHtml = "";
    if (info.isReqBlocked && info.reqFailNames && info.reqFailNames.length > 0) {
        bodyHtml += `<div class="req-warn">⭐ 必須メンバー条件NG（参加不可: ${info.reqFailNames.map(escapeHtml).join(', ')}）</div>`;
    }

    if (!aggArgs.canViewDetails) {
        bodyHtml += `<div style="font-size:13px; color:#475569;">🔒 プライベート設定のためメンバー名は非表示です（参加可能目安: <b>${escapeHtml(scoreTxt)}人</b>）</div>`;
    } else {
        const yesList = info.yes || [];
        const maybeList = info.maybe || [];
        const noList = info.no || [];

        bodyHtml += `
            <div class="dp-section">
                <div class="dp-sec-title" style="color:#166534;">🟢 ◯ 参加可能 (${yesList.length}名)</div>
                <div class="chip-wrap">${yesList.length ? yesList.map(n => `<span class="m-chip chip-yes">${escapeHtml(n)}</span>`).join('') : '<span style="font-size:12px;color:#94a3b8;">なし</span>'}</div>
            </div>
            <div class="dp-section">
                <div class="dp-sec-title" style="color:#92400e;">🟡 △ 未定 (${maybeList.length}名)</div>
                <div class="chip-wrap">${maybeList.length ? maybeList.map(n => `<span class="m-chip chip-maybe">${escapeHtml(n)}</span>`).join('') : '<span style="font-size:12px;color:#94a3b8;">なし</span>'}</div>
            </div>
            <div class="dp-section">
                <div class="dp-sec-title" style="color:#64748b;">🔴 × 不可・授業等 (${noList.length}名)</div>
                <div class="chip-wrap">${noList.length ? noList.map(n => `<span class="m-chip chip-no">${escapeHtml(n)}</span>`).join('') : '<span style="font-size:12px;color:#94a3b8;">なし</span>'}</div>
            </div>`;
    }

    const copyBtnHtml = (aggArgs.canViewDetails && info.yes && info.yes.length > 0)
        ? `<button type="button" id="dp-copy-btn" class="dp-btn" onclick="copyYesNames(${r}, ${c})">📋 ◯をコピー</button>`
        : "";

    card.innerHTML = `
        <div class="dp-head">
            <div class="dp-title">📅 ${escapeHtml(titleText)}（<span style="color:#047857;">${escapeHtml(scoreTxt)}人</span>）</div>
            <div class="dp-actions">
                ${copyBtnHtml}
                <button type="button" class="dp-btn" onclick="closeDetailPanel()">✕ 閉じる</button>
            </div>
        </div>
        ${bodyHtml}
        <div style="text-align:center; font-size:11px; color:#94a3b8; margin-top:10px;">枠外をタップしても閉じられます</div>
    `;

    const root = document.getElementById('app-root');
    if (root && root.getBoundingClientRect().height < 360) {
        root.style.minHeight = '360px';
        updateFrameHeight();
    }
    modal.classList.add('open');
}

function showHover(cell, r, c) {
    if (Date.now() - lastTouchTime < 900) return;
    const pop = document.getElementById('agg-hover');
    const info = (aggArgs.cellInfo || {})[`${r}_${c}`];
    if (!pop || !info) return;

    let html = `<div style="font-weight:800; margin-bottom:4px; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:4px;">
        ${escapeHtml(aggArgs.cleanLabels[c])} ${escapeHtml(aggArgs.timeLabels[r])}（<b>${escapeHtml(info.scoreText)}人</b>）
    </div>`;
    if (info.isReqBlocked && info.reqFailNames && info.reqFailNames.length > 0) {
        html += `<div style="color:#fca5a5; font-size:11px; margin-bottom:4px;">⭐ 必須NG: ${info.reqFailNames.map(escapeHtml).join(', ')}</div>`;
    }
    if (!aggArgs.canViewDetails) {
        html += `<div>プライベート設定のためメンバー非表示</div>`;
    } else {
        const y = info.yes || [];
        const m = info.maybe || [];
        if (y.length) html += `<div style="color:#86efac;">◯ ${y.slice(0, 8).map(escapeHtml).join(', ')}${y.length > 8 ? ` 他${y.length - 8}名` : ''}</div>`;
        if (m.length) html += `<div style="color:#fde047;">△ ${m.slice(0, 6).map(escapeHtml).join(', ')}${m.length > 6 ? ` 他${m.length - 6}名` : ''}</div>`;
        if (!y.length && !m.length) html += `<div style="color:#94a3b8;">参加可能者なし</div>`;
        html += `<div style="color:#94a3b8; font-size:10px; margin-top:4px;">クリックで全員・×内訳・メモを表示</div>`;
    }
    pop.innerHTML = html;
    pop.style.display = 'block';

    const rect = cell.getBoundingClientRect();
    const popRect = pop.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = rect.left + rect.width / 2 - popRect.width / 2;
    left = Math.max(8, Math.min(vw - popRect.width - 8, left));

    let top = rect.top - popRect.height - 8;
    if (top < 8) {
        top = rect.bottom + 8;
        if (top + popRect.height > vh - 8) {
            top = Math.max(8, vh - popRect.height - 8);
        }
    }
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
}

function hideHover() {
    const pop = document.getElementById('agg-hover');
    if (pop) pop.style.display = 'none';
}

function buildAgg(args) {
    aggArgs = args;
    selectedCellKey = null;
    const cols = args.dateStrs.length;
    const rows = args.timeLabels.length;
    const isTimeMode = !!args.isTimeMode;
    aggBaseCellH = args.defaultCellH || (isTimeMode ? 34 : 46);

    const myLegend = args.showMyOverlay
        ? `<span style="color:#1565C0;">■ 自分の◯</span> <span style="color:#EF6C00;">■ 自分の△</span>`
        : "";
    const reqLegend = args.hasRequiredFilter
        ? `<span style="color:#64748b;">▨ 必須条件NG</span>`
        : "";

    const zoomBtns = `
        <div class="zoom-group" title="集計表の縮小・拡大">
            <button type="button" class="zoom-btn" onclick="stepAggZoom(-0.15)">🔍−</button>
            <button type="button" class="zoom-lbl" id="agg-zoom-lbl" onclick="resetAggZoom()">100%</button>
            <button type="button" class="zoom-btn" onclick="stepAggZoom(0.15)">＋</button>
        </div>`;
    const jumpBtns = cols > 6 ? `
        <button type="button" class="jump-pill" onclick="scrollAggX(-240)">◀</button>
        <button type="button" class="jump-pill" onclick="scrollAggX(240)">▶</button>` : "";

    const toolbar = `
        <div class="agg-toolbar">
            <div class="tb-group">
                <span>少</span><span class="grad-bar"></span><span>多</span>
                ${reqLegend}
                ${myLegend}
                <span style="font-weight:500; color:#64748b;">（タップで内訳 ／ 🔍−＋ボタンで縮小・拡大）</span>
            </div>
            <div class="tb-group">${zoomBtns}${jumpBtns}</div>
        </div>`;

    let timeCells = "";
    for (let r = 0; r < rows; r++) {
        const tStr = args.timeLabels[r];
        const bTop = getBorderTop(tStr, args.eventType);
        const lbl = (!isTimeMode || tStr.endsWith(":00") || tStr.endsWith(":30")) ? escapeHtml(tStr) : "";
        timeCells += `<div class="agg-time-cell" style="border-top:${bTop};">${lbl}</div>`;
    }
    const timeCol = `<div class="agg-time-col"><div class="agg-top-left">時間</div>${timeCells}</div>`;

    const maxZ = args.maxZ > 0 ? args.maxZ : 1;
    let dayCols = "";
    for (let c = 0; c < cols; c++) {
        const lbl = escapeHtml(args.cleanLabels[c]).replace("(", "<br>(");
        const dKind = args.dayKinds[c] || "weekday";
        const kindCls = dKind === "sat" ? "day-sat" : (dKind === "sun" ? "day-sun" : "");
        const wkCls = args.weekBreaks[c] ? "week-break" : "";
        let cells = "";
        for (let r = 0; r < rows; r++) {
            const val = (args.z[r] && args.z[r][c] !== undefined) ? args.z[r][c] : 0;
            const info = (args.cellInfo || {})[`${r}_${c}`] || {};
            const bTop = getBorderTop(args.timeLabels[r], args.eventType);

            let bg = "#ffffff", txtCol = "#cbd5e1", valTxt = "-";
            if (val > 0) {
                const ratio = Math.min(1, val / maxZ);
                const rc = Math.round(240 - (240 - 27) * ratio);
                const gc = Math.round(250 - (250 - 94) * ratio);
                const bc = Math.round(242 - (242 - 32) * ratio);
                bg = `rgb(${rc},${gc},${bc})`;
                txtCol = ratio < 0.55 ? "#0f172a" : "#ffffff";
                valTxt = info.scoreText || String(val);
            }
            const reqCls = info.isReqBlocked ? "req-blocked" : "";
            let myCls = "", myBadge = "";
            if (args.showMyOverlay) {
                if (info.myVal === 1) {
                    myCls = "my-yes";
                    myBadge = `<span class="my-badge my-badge-yes">◯</span>`;
                } else if (info.myVal === 2) {
                    myCls = "my-maybe";
                    myBadge = `<span class="my-badge my-badge-maybe">△</span>`;
                }
            }
            cells += `<div class="agg-cell ${reqCls} ${myCls}" data-r="${r}" data-c="${c}" style="background-color:${bg}; color:${txtCol}; border-top:${bTop};">${escapeHtml(valTxt)}${myBadge}</div>`;
        }
        dayCols += `<div class="agg-day-col ${wkCls}"><div class="agg-header ${kindCls}">${lbl}</div>${cells}</div>`;
    }

    const scrollCls = isTimeMode ? "time-scroll" : "auto-scroll";
    const root = document.getElementById('app-root');
    root.innerHTML = `
        ${toolbar}
        <div class="top-scroll-wrap" id="agg-top-scroll"><div class="top-scroll-inner" id="agg-top-inner"></div></div>
        <div class="agg-scroll ${scrollCls}" id="agg-scroll">
            <div id="agg-grid" style="grid-template-columns: var(--time-w) repeat(${cols}, minmax(var(--col-w), 1fr));">
                ${timeCol}
                ${dayCols}
            </div>
        </div>
    `;

    const sc = document.getElementById('agg-scroll');
    const topWrap = document.getElementById('agg-top-scroll');
    if (sc && topWrap) {
        topWrap.addEventListener('scroll', () => {
            if (isSyncingScroll) return;
            isSyncingScroll = true; sc.scrollLeft = topWrap.scrollLeft; isSyncingScroll = false;
        });
        sc.addEventListener('scroll', () => {
            hideHover();
            if (isSyncingScroll) return;
            isSyncingScroll = true; topWrap.scrollLeft = sc.scrollLeft; isSyncingScroll = false;
        });
    }

    const grid = document.getElementById('agg-grid');
    if (grid) {
        let tapStart = null;
        grid.addEventListener('touchstart', e => {
            lastTouchTime = Date.now();
            if (e.touches.length === 1) {
                const cell = e.target.closest('.agg-cell');
                tapStart = cell ? {
                    x: e.touches[0].clientX,
                    y: e.touches[0].clientY,
                    t: Date.now(),
                    cell: cell
                } : null;
            } else {
                tapStart = null;
            }
        }, {passive: true});

        grid.addEventListener('touchmove', e => {
            if (e.touches.length >= 2) {
                tapStart = null;
                return;
            }
            if (tapStart && e.touches.length === 1) {
                const dx = e.touches[0].clientX - tapStart.x;
                const dy = e.touches[0].clientY - tapStart.y;
                if (Math.hypot(dx, dy) > 10) tapStart = null;
            }
        }, {passive: true});

        grid.addEventListener('touchend', e => {
            if (!tapStart || e.changedTouches.length !== 1) { tapStart = null; return; }
            const ct = e.changedTouches[0];
            const dist = Math.hypot(ct.clientX - tapStart.x, ct.clientY - tapStart.y);
            const elapsed = Date.now() - tapStart.t;
            const cell = tapStart.cell;
            tapStart = null;
            if (dist < 12 && elapsed < 500 && cell) {
                lastTapHandledAt = Date.now();
                hideHover();
                openDetailPanel(cell, parseInt(cell.dataset.r, 10), parseInt(cell.dataset.c, 10));
            }
        }, {passive: true});

        grid.addEventListener('touchcancel', () => {
            tapStart = null;
        }, {passive: true});

        grid.addEventListener('mouseover', e => {
            const cell = e.target.closest('.agg-cell');
            if (cell) showHover(cell, parseInt(cell.dataset.r, 10), parseInt(cell.dataset.c, 10));
        });
        grid.addEventListener('mouseout', e => {
            if (!e.relatedTarget || !e.relatedTarget.closest || !e.relatedTarget.closest('.agg-cell')) {
                hideHover();
            }
        });
        grid.addEventListener('click', e => {
            if (Date.now() - lastTapHandledAt < 500) return;
            const cell = e.target.closest('.agg-cell');
            if (!cell) return;
            hideHover();
            openDetailPanel(cell, parseInt(cell.dataset.r, 10), parseInt(cell.dataset.c, 10));
        });
    }

    applyAggZoom(aggZoomScale, null);
    setTimeout(() => { syncTopScrollbar(); updateFrameHeight(); }, 40);
}

window.addEventListener("message", function(event) {
    if (!event.data || event.data.type !== "streamlit:render") return;
    buildAgg(event.data.args || {});
});
window.addEventListener('resize', () => { syncTopScrollbar(); updateFrameHeight(); });
const ro = new ResizeObserver(() => updateFrameHeight());
ro.observe(document.getElementById('app-root'));
sendMsg("streamlit:componentReady", {apiVersion: 1});
</script></body></html>
"""

TYPE_PICKER_V1_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: transparent; }
* { box-sizing: border-box; }
#app-root { padding: 4px 2px 6px 2px; }
.tp-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
}
@media (max-width: 720px) {
    .tp-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
}
.tp-card {
    position: relative; background: #ffffff; border: 2px solid #e2e8f0;
    border-radius: 14px; padding: 12px 10px 10px 10px; text-align: center;
    cursor: pointer; transition: all 0.16s ease; user-select: none;
    box-shadow: 0 2px 6px rgba(15,23,42,0.04);
    display: flex; flex-direction: column; justify-content: space-between;
}
.tp-card:hover { border-color: #94a3b8; transform: translateY(-2px); box-shadow: 0 6px 14px rgba(15,23,42,0.08); }
.tp-card.selected {
    border-color: #10b981; background: linear-gradient(180deg, #ecfdf5 0%, #ffffff 65%);
    box-shadow: 0 6px 18px rgba(16,185,129,0.22); transform: translateY(-2px);
}
.tp-check {
    position: absolute; top: 7px; right: 7px; width: 22px; height: 22px;
    border-radius: 50%; background: #10b981; color: #fff; font-size: 12px; font-weight: 900;
    display: none; align-items: center; justify-content: center;
    box-shadow: 0 2px 6px rgba(16,185,129,0.4);
}
.tp-card.selected .tp-check { display: flex; }
.tp-title { font-size: 13.5px; font-weight: 800; color: #0f172a; margin-bottom: 3px; }
.tp-sub { font-size: 11px; color: #64748b; margin-bottom: 8px; line-height: 1.3; }
.mini-box {
    font-size: 10px; border: 1px solid #e2e8f0; border-radius: 7px; overflow: hidden; background: #fff;
}
</style></head><body>
<div id="app-root">
    <div class="tp-grid">
        <div class="tp-card" data-type="time" onclick="pick('time')">
            <div class="tp-check">✓</div>
            <div>
                <div class="tp-title">🕒 時間帯</div>
                <div class="tp-sub">15分刻みの細かい調整に</div>
            </div>
            <div class="mini-box">
                <div style="background:#f1f5f9; padding:2px; font-weight:700;">4/1 (月)</div>
                <div style="display:flex; border-top:1px solid #e2e8f0;"><div style="width:32px; background:#f8fafc;">9:00</div><div style="flex:1; background:#4CAF50; color:#fff; font-weight:700;">◯</div></div>
                <div style="display:flex; border-top:1px dashed #e2e8f0;"><div style="width:32px; background:#f8fafc;">9:15</div><div style="flex:1; background:#FFEB3B; color:#333; font-weight:700;">△</div></div>
                <div style="display:flex; border-top:1px dashed #e2e8f0;"><div style="width:32px; background:#f8fafc;">9:30</div><div style="flex:1; background:#4CAF50; color:#fff; font-weight:700;">◯</div></div>
            </div>
        </div>
        <div class="tp-card" data-type="timetable" onclick="pick('timetable')">
            <div class="tp-check">✓</div>
            <div>
                <div class="tp-title">🏫 時間割 (月〜金)</div>
                <div class="tp-sub">定例MTG・空きコマ調査に</div>
            </div>
            <div class="mini-box">
                <div style="display:flex; background:#f1f5f9; border-bottom:1px solid #e2e8f0; font-weight:700;"><div style="width:28px;"></div><div style="flex:1;">月</div><div style="flex:1;">火</div></div>
                <div style="display:flex; border-bottom:1px solid #e2e8f0;"><div style="width:28px; background:#f8fafc;">1限</div><div style="flex:1; background:#4CAF50; color:#fff; border-right:1px solid #fff;">◯</div><div style="flex:1; background:#e2e8f0; color:#475569;">授</div></div>
                <div style="display:flex; border-bottom:1px solid #e2e8f0;"><div style="width:28px; background:#f8fafc;">2限</div><div style="flex:1; background:#FFEB3B; color:#333; border-right:1px solid #fff;">△</div><div style="flex:1; background:#4CAF50; color:#fff;">◯</div></div>
                <div style="display:flex;"><div style="width:28px; background:#f8fafc;">昼</div><div style="flex:1; background:#4CAF50; color:#fff; border-right:1px solid #fff;">◯</div><div style="flex:1; background:#4CAF50; color:#fff;">◯</div></div>
            </div>
        </div>
        <div class="tp-card" data-type="date_timetable" onclick="pick('date_timetable')">
            <div class="tp-check">✓</div>
            <div>
                <div class="tp-title">📅 日付指定コマ</div>
                <div class="tp-sub">特定日の1〜5限・放課後に</div>
            </div>
            <div class="mini-box">
                <div style="display:flex; background:#f1f5f9; border-bottom:1px solid #e2e8f0; font-weight:700;"><div style="width:28px;"></div><div style="flex:1;">4/10</div><div style="flex:1;">4/12</div></div>
                <div style="display:flex; border-bottom:1px solid #e2e8f0;"><div style="width:28px; background:#f8fafc;">1限</div><div style="flex:1; background:#4CAF50; color:#fff; border-right:1px solid #fff;">◯</div><div style="flex:1; background:#FFEB3B; color:#333;">△</div></div>
                <div style="display:flex; border-bottom:1px solid #e2e8f0;"><div style="width:28px; background:#f8fafc;">2限</div><div style="flex:1; background:#fff; color:#cbd5e1; border-right:1px solid #e2e8f0;">×</div><div style="flex:1; background:#4CAF50; color:#fff;">◯</div></div>
                <div style="display:flex;"><div style="width:28px; background:#f8fafc;">放課</div><div style="flex:1; background:#4CAF50; color:#fff; border-right:1px solid #fff;">◯</div><div style="flex:1; background:#4CAF50; color:#fff;">◯</div></div>
            </div>
        </div>
        <div class="tp-card" data-type="options" onclick="pick('options')">
            <div class="tp-check">✓</div>
            <div>
                <div class="tp-title">🗳️ 複数の予定</div>
                <div class="tp-sub">候補リストの出欠アンケートに</div>
            </div>
            <div class="mini-box" style="padding:5px; text-align:left;">
                <div style="font-weight:800; color:#166534; margin-bottom:4px;">📅 4/1 19:00 新歓</div>
                <div style="display:flex; gap:3px; margin-bottom:5px;">
                    <div style="flex:1; border:1px solid #cbd5e1; text-align:center; border-radius:4px;">×</div>
                    <div style="flex:1; background:#FFEB3B; text-align:center; border-radius:4px; font-weight:700;">△</div>
                    <div style="flex:1; background:#4CAF50; color:#fff; text-align:center; border-radius:4px; font-weight:700;">◯</div>
                </div>
                <div style="font-weight:800; color:#166534; margin-bottom:2px;">📅 4/3 18:00 説明会</div>
            </div>
        </div>
    </div>
</div>
<script>
function sendMsg(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data), "*");
}
function updateHeight() {
    const root = document.getElementById('app-root');
    if (!root) return;
    sendMsg("streamlit:setFrameHeight", {height: Math.ceil(root.getBoundingClientRect().height) + 4});
}
let currentSelected = "time";
function applySelected(val) {
    currentSelected = val || "time";
    document.querySelectorAll('.tp-card').forEach(el => {
        el.classList.toggle('selected', el.dataset.type === currentSelected);
    });
}
window.pick = function(val) {
    if (val === currentSelected) return;
    applySelected(val);
    sendMsg("streamlit:setComponentValue", {value: val, dataType: "json"});
};
window.addEventListener("message", function(event) {
    if (!event.data || event.data.type !== "streamlit:render") return;
    const args = event.data.args || {};
    applySelected(args.selected || "time");
    setTimeout(updateHeight, 30);
});
const ro = new ResizeObserver(() => updateHeight());
ro.observe(document.getElementById('app-root'));
sendMsg("streamlit:componentReady", {apiVersion: 1});
</script></body></html>
"""


@st.cache_resource
def ensure_components():
    """各カスタムコンポーネントHTMLを最新状態で出力する"""
    specs = {
        "rt_editor": RT_EDITOR_HTML,
        "auth_storage_v1": AUTH_STORAGE_HTML,
        "options_editor_v2": OPTIONS_EDITOR_V2_HTML,
        "custom_editor_v18": CUSTOM_EDITOR_V15_HTML,
        "agg_viewer_v4": AGG_VIEWER_V1_HTML,
        "type_picker_v1": TYPE_PICKER_V1_HTML,
    }
    for folder, content in specs.items():
        dirpath = os.path.join(BASE_DIR, folder)
        os.makedirs(dirpath, exist_ok=True)
        filepath = os.path.join(dirpath, "index.html")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    return True


ensure_components()

rt_editor = components.declare_component("rt_editor", path=os.path.join(BASE_DIR, "rt_editor"))
auth_storage = components.declare_component("auth_storage", path=os.path.join(BASE_DIR, "auth_storage_v1"))
options_editor = components.declare_component("options_editor", path=os.path.join(BASE_DIR, "options_editor_v2"))
grid_editor = components.declare_component("grid_editor", path=os.path.join(BASE_DIR, "custom_editor_v18"))
agg_viewer = components.declare_component("agg_viewer", path=os.path.join(BASE_DIR, "agg_viewer_v4"))
type_picker = components.declare_component("type_picker", path=os.path.join(BASE_DIR, "type_picker_v1"))


# ==========================================
# 未ログイン画面（自動ログイン維持対応）
# ==========================================
def _trigger_auto_login_save(user_doc, remember_me):
    if remember_me:
        st.session_state.pending_auth_save = {
            "uid": str(user_doc["user_id"]),
            "token": make_auth_token(user_doc["user_id"], user_doc.get("pin", "")),
        }
        st.session_state.auth_op_id = f"w_{time.time()}"
    else:
        st.session_state.pending_auth_clear = True
        st.session_state.auth_op_id = f"c_{time.time()}"
    st.session_state.manual_logout = False


def render_login_view():
    if (
        not st.session_state.get("manual_logout")
        and not st.session_state.get("auto_login_checked")
    ):
        stored = auth_storage(mode="read", key="auth_storage_read")
        if isinstance(stored, dict):
            st.session_state.auto_login_checked = True
            if stored.get("status") == "found":
                uid = str(stored.get("uid", ""))
                token = str(stored.get("token", ""))
                all_users = _fetch_all_users_cached()
                matched = next((u for u in all_users if str(u.get("user_id", "")) == uid), None)
                if matched and make_auth_token(uid, matched.get("pin", "")) == token:
                    st.session_state.auth = matched
                    st.rerun()
                else:
                    st.session_state.pending_auth_clear = True
                    st.session_state.auth_op_id = f"c_{time.time()}"

    _, col_login, _ = st.columns([1, 2, 1])
    with col_login:
        st.title("SSScheduler")

        if "jump_to_event" in st.session_state:
            st.info("👋 イベントへの招待が届いています。ログインまたは新規登録をして回答してください。")

        login_mode = st.radio(
            "メニュー",
            ["🔑 ログイン", "📝 新規アカウント作成", "🆘 PIN・パスワード復旧"],
            horizontal=True,
        )
        st.markdown("---")

        if login_mode == "🔑 ログイン":
            with st.form("login_form"):
                st.subheader("ログイン")
                n = st.text_input("氏名", autocomplete="username")
                p = st.text_input("PIN", type="password", autocomplete="current-password")
                remember = st.checkbox("✅ 次回から自動ログインする", value=True)
                if st.form_submit_button("ログイン", use_container_width=True, type="primary"):
                    clean_n = n.replace(" ", "").replace("　", "")
                    users_ref = db.collection("users").where("name", "==", clean_n).stream()
                    user_doc = None
                    for doc in users_ref:
                        user_doc = doc.to_dict()
                        break

                    if user_doc:
                        stored_pin = user_doc.get("pin", "")
                        hashed_input = hash_pin(p)
                        if stored_pin == hashed_input:
                            _trigger_auto_login_save(user_doc, remember)
                            st.session_state.auth = user_doc
                            st.rerun()
                        elif stored_pin == p:
                            db.collection("users").document(user_doc["user_id"]).update({"pin": hashed_input})
                            user_doc["pin"] = hashed_input
                            invalidate_cache("users")
                            _trigger_auto_login_save(user_doc, remember)
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

            g2_opts = list(dict.fromkeys(g2_opts))
            g4_opts = list(dict.fromkeys(g4_opts))
            g2 = st.multiselect("🔧 系", g2_opts, key="reg_g2")
            g3 = st.multiselect("🏢 委員会", ["執行部", "新入生教育", "広報", "イベント", "会計"], key="reg_g3")
            g4 = st.multiselect("👑 役職", g4_opts, key="reg_g4")
            reg_remember = st.checkbox("✅ 次回から自動ログインする", value=True, key="reg_remember")

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
                            "group_1": ", ".join(g1),
                            "group_2": ", ".join(g2),
                            "group_3": ", ".join(g3),
                            "group_4": ", ".join(g4),
                            "calendar_url": "",
                            "fixed_schedule": {},
                        }
                        try:
                            db.collection("users").document(new_user_id).set(new_u)
                            invalidate_cache("users")
                            gas_payload = new_u.copy()
                            gas_payload["pin"] = "PROTECTED"
                            gas_payload["secret_word"] = "PROTECTED"
                            backup_to_gas_async("register_user", {"payload": gas_payload})
                            _trigger_auto_login_save(new_u, reg_remember)
                            st.session_state.auth = new_u
                            st.rerun()
                        except Exception as e:
                            st.error(f"登録に失敗しました: {e}")

        elif login_mode == "🆘 PIN・パスワード復旧":
            st.subheader("PINの再設定")
            with st.expander("🔑 秘密の合言葉を使って自分で復旧する", expanded=True):
                with st.form("recovery_auth_form"):
                    st.markdown("<small>登録時に設定した合言葉がわかる方はこちら</small>", unsafe_allow_html=True)
                    rec_n = st.text_input("氏名", autocomplete="username")
                    rec_s = st.text_input("秘密の合言葉")
                    new_p = st.text_input("設定したい新しいPIN", type="password", autocomplete="new-password")
                    if st.form_submit_button("新しいPINで更新する", use_container_width=True, type="primary"):
                        clean_n = rec_n.replace(" ", "").replace("　", "")
                        users_ref = db.collection("users").where("name", "==", clean_n).stream()
                        target_doc = None
                        for doc in users_ref:
                            doc_data = doc.to_dict()
                            stored_secret = doc_data.get("secret_word", "")
                            if stored_secret == hash_pin(rec_s) or stored_secret == rec_s:
                                target_doc = doc_data
                                break
                        if target_doc and new_p:
                            hashed_new_pin = hash_pin(new_p)
                            hashed_secret = hash_pin(rec_s)
                            db.collection("users").document(target_doc["user_id"]).update({
                                "pin": hashed_new_pin,
                                "secret_word": hashed_secret,
                            })
                            invalidate_cache("users")
                            backup_to_gas_async("update_user", {"payload": {"user_id": target_doc["user_id"], "pin": "PROTECTED"}})
                            st.success("✅ 更新成功！新しいPINでログインできます。")
                        else:
                            st.error("氏名または合言葉が間違っているか、新しいPINが入力されていません。")

            with st.expander("🆘 合言葉も忘れたので、管理者に依頼する"):
                st.write("管理者のSlackへ通知を送り、PINのリセットを依頼します。")
                req_name = st.text_input("あなたのお名前", key="req_pin_name")
                if st.button("🚀 管理者にリセット依頼を送る", use_container_width=True):
                    if not req_name:
                        st.warning("名前を入力してください。")
                    else:
                        backup_to_gas_async("request_pin_reset", {"payload": {"name": req_name}})
                        st.success(f"✅ {req_name}さん、管理者に通知を送りました。")


# ==========================================
# ナビゲーション＆共通ヘッダー
# ==========================================
def _do_logout():
    st.session_state.auth = None
    st.session_state.manual_logout = True
    st.session_state.pending_auth_clear = True
    st.session_state.auth_op_id = f"c_{time.time()}"
    st.session_state.target_ev_id = ""
    st.session_state.current_menu = "dashboard"
    st.rerun()


def render_top_navigation(user, unanswered_events):
    """メイン画面の上部を広く使えるよう、左サイドバーへメニューを集約し、折りたたみ時は左上「メニュー」ピルを強調表示する"""
    role = user.get("role", "guest")
    active_groups = [str(user.get(f"group_{i}", "")).strip() for i in range(1, 5)]
    active_groups = [g for g in active_groups if g]
    group_txt = " / ".join(active_groups) if active_groups else "未所属"
    role_emoji = {"top_admin": "👑", "admin": "🛠️", "user": "📝", "guest": "👤"}.get(role, "👤")

    u_cnt = len(unanswered_events)
    menu_pill_txt = f"メニュー 🔴{u_cnt}" if u_cnt > 0 else "メニュー"
    st.markdown(
        f"<style>:root {{ --sss-menu-label: {json.dumps(menu_pill_txt, ensure_ascii=False)}; }}</style>",
        unsafe_allow_html=True,
    )

    dash_lbl = f"📅 日程調整・一覧 (🔴未回答 {u_cnt})" if u_cnt > 0 else "📅 日程調整・一覧"
    nav_items = [
        ("dashboard", dash_lbl),
        ("timetable", "⏰ 時間割の登録"),
    ]
    if role in ["user", "admin", "top_admin"]:
        nav_items.append(("create", "➕ イベント新規作成"))
    nav_items.extend([
        ("profile", "👤 プロフィール設定"),
        ("guide", "📖 使い方ガイド"),
    ])
    if role in ["admin", "top_admin"]:
        nav_items.append(("admin", "⚙️ 管理者メニュー"))

    if st.session_state.get("current_menu") not in [k for k, _ in nav_items]:
        st.session_state.current_menu = "dashboard"
    cur_menu = st.session_state.current_menu

    with st.sidebar:
        st.markdown(_compact_html(f"""
        <div style="font-size:18px; font-weight:900; color:#064e3b; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
            <span>📅 SSScheduler</span>
        </div>
        <div class="sb-user-card">
            <div style="font-size:14.5px; font-weight:800; color:#0f172a;">{role_emoji} {html_lib.escape(user.get("name", ""))} さん</div>
            <div style="font-size:11.5px; color:#475569; margin-top:3px;">{html_lib.escape(group_txt)}</div>
            <div style="margin-top:6px;">
                <span style="font-size:11px; background:#e2e8f0; color:#334155; padding:2px 8px; border-radius:999px; font-weight:700;">ID: {html_lib.escape(str(user.get("user_id", "")))}</span>
            </div>
        </div>
        """), unsafe_allow_html=True)

        st.caption("🧭 メニュー切り替え")
        for m_key, m_lbl in nav_items:
            b_type = "primary" if cur_menu == m_key else "secondary"
            if st.button(m_lbl, key=f"sb_nav_{m_key}", use_container_width=True, type=b_type):
                if m_key == "dashboard" and cur_menu == "dashboard":
                    st.session_state.target_ev_id = ""
                st.session_state.current_menu = m_key
                st.rerun()

        st.markdown("---")
        if st.button("🚪 ログアウト", key="sb_nav_logout", use_container_width=True):
            _do_logout()


# ==========================================
# プロフィール・時間割設定・ガイド・新規作成・管理者画面
# ==========================================
def render_profile_view(user):
    st.title("👤 プロフィール設定")
    st.write("登録情報や所属グループの更新を行います。（未所属にする場合は選択を解除してください）")

    def_g1 = [x for x in user.get("group_1", "").split(", ") if x]
    old_to_new_g2 = {
        "通信": "通信系", "熱": "熱系", "構造 (衛星)": "構造系", "構造（衛星）": "構造系",
        "ミッション": "ミッション系", "姿勢": "姿勢系", "電源": "電源系", "C＆DH": "C＆DH系",
        "電装": "COLOURS電装系", "構造 (ロケット)": "COLOURS構造系", "構造（ロケット）": "COLOURS構造系",
        "推進": "COLOURS推進系", "燃焼": "COLOURS燃焼系",
    }
    raw_def_g2 = [x.strip() for x in user.get("group_2", "").split(",") if x.strip()]
    def_g2 = [old_to_new_g2.get(x, x) for x in raw_def_g2]
    def_g3 = [x for x in user.get("group_3", "").split(", ") if x]
    def_g4 = [x for x in user.get("group_4", "").split(", ") if x]

    st.markdown("##### 📛 基本情報")
    upd_name = st.text_input("氏名（※ログインIDとしても使用されます）", value=user.get("name", ""))

    upd_g1 = st.multiselect("🚀 プロジェクト", ["衛星", "ロケット", "BizSat"], default=def_g1, key="upd_g1")
    upd_g2_opts, upd_g4_opts = [], []
    if "衛星" in upd_g1:
        upd_g2_opts.extend(["ミッション系", "電源系", "構造系", "通信系", "姿勢系", "熱系", "C＆DH系"])
        upd_g4_opts.extend(["ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ", "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ", "PMs (衛星)"])
    if "ロケット" in upd_g1:
        upd_g2_opts.extend(["COLOURS燃焼系", "COLOURS推進系", "COLOURS構造系", "COLOURS電装系", "COLOURSエンジン系"])
        upd_g4_opts.extend(["燃焼系長", "推進系長", "構造系長", "電装系長", "PMs (ロケット)", "エンジン系長"])

    upd_g2_opts = list(dict.fromkeys(upd_g2_opts))
    upd_g4_opts = list(dict.fromkeys(upd_g4_opts))
    safe_def_g2 = [x for x in def_g2 if x in upd_g2_opts]
    safe_def_g4 = [x for x in def_g4 if x in upd_g4_opts]
    safe_def_g3 = [x for x in def_g3 if x in ["執行部", "新入生教育", "広報", "イベント", "会計"]]

    upd_g2 = st.multiselect("🔧 系", upd_g2_opts, default=safe_def_g2, key="upd_g2")
    upd_g3 = st.multiselect("🏢 委員会", ["執行部", "新入生教育", "広報", "イベント", "会計"], default=safe_def_g3, key="upd_g3")
    upd_g4 = st.multiselect("👑 役職", upd_g4_opts, default=safe_def_g4, key="upd_g4")

    st.markdown("---")
    st.markdown("##### 📅 外部カレンダー連携 (任意)")
    st.write("GoogleカレンダーやiPhoneの「非公開URL（iCal形式 / .ics）」を設定しておくと、日程調整の際に自分の予定を自動でグレーアウトできます。")
    upd_cal_url = st.text_input(
        "カレンダーの非公開URL",
        value=user.get("calendar_url", ""),
        placeholder="https://calendar.google.com/calendar/ical/.../basic.ics",
    )

    if st.button("💾 プロフィールを更新", use_container_width=True, type="primary"):
        clean_name = upd_name.replace(" ", "").replace("　", "")
        if not clean_name:
            st.error("氏名は空にできません。")
        else:
            if clean_name != user.get("name"):
                existing = list(db.collection("users").where("name", "==", clean_name).stream())
                if existing:
                    st.error(f"エラー: '{clean_name}' という名前は既に使われています。別の名前を指定してください。")
                    st.stop()

            payload = {
                "user_id": user["user_id"],
                "name": clean_name,
                "group_1": ", ".join(upd_g1),
                "group_2": ", ".join(upd_g2),
                "group_3": ", ".join(upd_g3),
                "group_4": ", ".join(upd_g4),
                "calendar_url": upd_cal_url,
            }
            gas_payload = payload.copy()
            gas_payload["calendar_url"] = "LINKED" if upd_cal_url else ""

            try:
                db.collection("users").document(str(user["user_id"])).update(payload)
                invalidate_cache("users")
                backup_to_gas_async("update_user", {"payload": gas_payload})
                st.session_state.auth = {**user, **payload}
                st.success("✅ プロフィールを保存しました！")
                time.sleep(0.8)
                st.rerun()
            except Exception as e:
                st.error(f"更新に失敗しました: {e}")

    st.markdown("---")
    st.markdown("##### 🔐 セキュリティ設定 (PIN・合言葉の変更)")
    with st.expander("PINや合言葉を変更する"):
        st.write("本人確認のため、現在のPINを入力してから新しい情報を設定してください。")
        with st.form("security_update_form"):
            current_p = st.text_input("現在のPIN (必須)", type="password")
            new_p = st.text_input("新しいPIN (変更しない場合は空欄)", type="password")
            new_s = st.text_input("新しい秘密の合言葉 (変更しない場合は空欄)")

            if st.form_submit_button("更新する", use_container_width=True, type="primary"):
                if not current_p:
                    st.error("エラー: 現在のPINを入力してください。")
                elif hash_pin(current_p) != user.get("pin") and current_p != user.get("pin"):
                    st.error("エラー: 現在のPINが間違っています。")
                elif not new_p and not new_s:
                    st.warning("変更する新しいPINまたは合言葉を入力してください。")
                else:
                    updates = {}
                    if new_p:
                        updates["pin"] = hash_pin(new_p)
                    if new_s:
                        updates["secret_word"] = hash_pin(new_s)
                    try:
                        db.collection("users").document(str(user["user_id"])).update(updates)
                        invalidate_cache("users")
                        gas_payload = {"user_id": user["user_id"]}
                        if new_p:
                            gas_payload["pin"] = "PROTECTED"
                        if new_s:
                            gas_payload["secret_word"] = "PROTECTED"
                        backup_to_gas_async("update_user", {"payload": gas_payload})
                        updated_u = {**user, **updates}
                        st.session_state.auth = updated_u
                        if new_p:
                            _trigger_auto_login_save(updated_u, True)
                        st.success("✅ セキュリティ情報を更新しました！")
                        time.sleep(0.8)
                        st.rerun()
                    except Exception as e:
                        st.error(f"更新に失敗しました: {e}")

    st.markdown("---")
    st.markdown("##### ⚠️ アカウントの削除（退会）")
    with st.expander("退会手続きを開く"):
        st.warning("退会すると、これまでの回答データや時間割がすべて削除され、元に戻すことはできません。")
        if st.button("💥 本当に退会する", type="primary"):
            uid = str(user["user_id"])
            db.collection("users").document(uid).delete()
            res_docs = db.collection("responses").where("user_id", "==", uid).stream()
            for d in res_docs:
                db.collection("responses").document(d.id).delete()
            invalidate_cache("all")
            backup_to_gas_async("delete_user", {"payload": {"user_id": uid}})
            _do_logout()


def render_timetable_settings_view(user):
    st.title("⏰ 時間割設定")
    st.info("※ここでチェックした授業・予定は、日程調整画面で「授 / 不可」として一括反映できます。")

    fixed_sched = user.get("fixed_schedule", {})
    ui_state = {str(i): {} for i in range(5)}
    days_jp = ["月", "火", "水", "木", "金"]
    col_ratios = [1.2, 1, 1, 1, 1, 1]

    st.markdown('<div class="sss-tt-row-marker"></div>', unsafe_allow_html=True)
    cols = st.columns(col_ratios)
    cols[0].markdown("<div style='padding:8px;'></div>", unsafe_allow_html=True)
    for i, d in enumerate(days_jp):
        cols[i + 1].markdown(f"<div class='tt-day-header'>{d}</div>", unsafe_allow_html=True)
    st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)

    for p_name, p_time, s_idx, e_idx, p_key in PERIODS_MASTER:
        st.markdown('<div class="sss-tt-row-marker"></div>', unsafe_allow_html=True)
        cols = st.columns(col_ratios)
        cols[0].markdown(f"<div class='tt-time-cell'>{p_name}<br><span class='tt-time-sub'>{p_time}</span></div>", unsafe_allow_html=True)
        for i in range(5):
            day_bin = fixed_sched.get(str(i), "0" * 96)
            val = day_bin[s_idx:e_idx] == "1" * (e_idx - s_idx)
            checked = cols[i + 1].checkbox(" ", value=val, key=f"{p_key}_{i}", label_visibility="collapsed")
            ui_state[str(i)][p_key] = checked
            if checked:
                cols[i + 1].markdown("<div class='status-on'>✔︎ あり</div>", unsafe_allow_html=True)
            else:
                cols[i + 1].markdown("<div class='status-off'>-</div>", unsafe_allow_html=True)
        st.markdown("<hr style='margin: 4px 0; border: none; border-bottom: 1px dashed #ddd;'>", unsafe_allow_html=True)

    st.markdown('<div class="sss-tt-row-marker"></div>', unsafe_allow_html=True)
    cols = st.columns(col_ratios)
    cols[0].markdown("<div class='tt-time-cell' style='border-left-color:#FF9800;'>放課後<br><span class='tt-time-sub'>18:30〜</span></div>", unsafe_allow_html=True)
    for i in range(5):
        day_bin = fixed_sched.get(str(i), "0" * 96)
        val = "1" in day_bin[74:]
        checked = cols[i + 1].checkbox(" ", value=val, key=f"af_{i}", label_visibility="collapsed")
        ui_state[str(i)]["af"] = checked
        if checked:
            cols[i + 1].markdown("<div class='af-status-on'>🌙 予定</div>", unsafe_allow_html=True)
        else:
            cols[i + 1].markdown("<div class='status-off'>-</div>", unsafe_allow_html=True)
    st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)

    st.markdown('<div class="sss-tt-row-marker"></div>', unsafe_allow_html=True)
    cols = st.columns(col_ratios)
    cols[0].markdown("<div style='text-align:center; font-size:10px; color:#666; padding-top:10px;'>終了時刻</div>", unsafe_allow_html=True)
    for i in range(5):
        if ui_state[str(i)]["af"]:
            day_bin = fixed_sched.get(str(i), "0" * 96)
            af_bin = day_bin[74:]
            af_end_val = "21:00"
            if "1" in af_bin:
                last_idx = 74 + af_bin.rfind("1")
                af_end_val = time_master[last_idx + 1] if (last_idx + 1 < len(time_master)) else "23:45"
            af_opts = [idx_to_time(idx) for idx in range(76, 96)]
            af_idx = af_opts.index(af_end_val) if af_end_val in af_opts else 8
            ui_state[str(i)]["af_end"] = cols[i + 1].selectbox("終了時間", af_opts, index=af_idx, key=f"afe_{i}", label_visibility="collapsed")
        else:
            cols[i + 1].markdown("<div style='text-align:center; color:#ccc; padding-top:10px; font-size:12px;'>-</div>", unsafe_allow_html=True)
            ui_state[str(i)]["af_end"] = "21:00"

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("💾 時間割を保存する", use_container_width=True, type="primary"):
        new_fixed_sched = {}
        for i in range(5):
            wd_str = str(i)
            new_bin = ["0"] * 96
            for _, _, p_start, p_end, p_key in PERIODS_MASTER:
                if ui_state[wd_str][p_key]:
                    new_bin[p_start:p_end] = ["1"] * (p_end - p_start)
            if ui_state[wd_str]["af"]:
                end_idx = time_master.index(ui_state[wd_str]["af_end"])
                new_bin[74:end_idx] = ["1"] * (end_idx - 74)
            new_fixed_sched[wd_str] = "".join(new_bin)

        payload = {"user_id": user["user_id"], "fixed_schedule": new_fixed_sched}
        try:
            db.collection("users").document(str(user["user_id"])).update(payload)
            invalidate_cache("users")
            backup_to_gas_async("update_user", {"payload": payload})
            st.session_state.auth = {**user, **payload}
            st.toast("✅ 時間割を保存しました！")
            st.rerun()
        except Exception as e:
            st.error(f"更新に失敗しました: {e}")


def render_guide_view():
    st.markdown(_compact_html("""
<style>
.g-hero {
    background: linear-gradient(135deg, #ecfdf5, #eff6ff);
    border: 1px solid #cbd5e1; border-radius: 16px;
    padding: 16px 18px; margin-bottom: 14px;
}
.g-hero h2 { margin: 0 0 6px 0; font-size: 21px; color: #0f172a; }
.g-hero p { margin: 0; font-size: 13.5px; color: #475569; line-height: 1.6; }
.g-grid {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 14px;
}
@media (max-width: 720px) { .g-grid { grid-template-columns: 1fr; } }
.g-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px;
    padding: 15px 16px; box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}
.g-step {
    display: inline-block; font-size: 11px; font-weight: 800; color: #047857;
    background: #dcfce7; padding: 2px 9px; border-radius: 999px; margin-bottom: 6px;
}
.g-title { font-size: 15.5px; font-weight: 800; color: #0f172a; margin-bottom: 8px; }
.g-text { font-size: 13px; color: #334155; line-height: 1.65; margin: 0; }
.g-demo-box {
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 10px; margin: 10px 0;
}
.g-pill-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.g-pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 800;
}
.g-switch {
    display: flex; gap: 6px; background: #e2e8f0; padding: 4px; border-radius: 10px;
}
.g-switch-btn {
    flex: 1; text-align: center; padding: 7px 6px; border-radius: 8px; font-size: 12px; font-weight: 800;
}
.g-kbd {
    display: inline-block; background: #f1f5f9; border: 1px solid #cbd5e1;
    border-radius: 5px; padding: 1px 6px; font-size: 11.5px; font-weight: 700; color: #1e293b;
}
.g-fp-mock {
    display: inline-flex; align-items: center; gap: 5px;
    background: #0f172a; color: #fff; border-radius: 999px;
    padding: 5px 10px; font-size: 12px; font-weight: 800; margin-top: 8px;
}
.g-fp-dot {
    width: 22px; height: 22px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 900;
}
</style>
<div class="g-hero">
    <h2>📖 SSScheduler かんたん使い方ガイド</h2>
    <p>はじめて使う方でも <b>30秒で迷わず入力・確認</b> できるよう、画面イメージ付きで基本操作と便利機能をまとめました。他のページへ移動するときは左上の <b>「メニュー」</b> ボタン（PCは左サイドバー）を開いてください。</p>
</div>
<div class="g-grid">
    <div class="g-card">
        <span class="g-step">STEP 1・画面の見方</span>
        <div class="g-title">🔄 「入力」と「みんなの集計」を切り替える</div>
        <p class="g-text">イベントを開くとすぐ上に切り替えボタンがあります。自分の予定を提出すると、<b>自動で「みんなの集計」へ移動</b>します。</p>
        <div class="g-demo-box">
            <div class="g-switch">
                <div class="g-switch-btn" style="background:#ef4444; color:#fff;">✏️ 予定を入力する</div>
                <div class="g-switch-btn" style="background:#fff; color:#334155;">📊 みんなの集計 (12名)</div>
            </div>
        </div>
        <p class="g-text">提出後も「✏️ 回答を修正」からいつでも何度でも書き直せます。</p>
    </div>
    <div class="g-card">
        <span class="g-step">STEP 2・色の意味とパレット</span>
        <div class="g-title">🎨 ペンを選んでカレンダーをなぞるだけ</div>
        <p class="g-text">参加できる時間帯をペンで塗って、下の赤い <b>「✅ 回答を保存して提出する」</b> を押せば完了です。</p>
        <div class="g-demo-box">
            <div class="g-pill-row">
                <span class="g-pill" style="background:#4CAF50; color:#fff;">🟢 ◯ 可（参加OK）</span>
                <span class="g-pill" style="background:#FFEB3B; color:#333;">🟡 △ 未定（微妙）</span>
                <span class="g-pill" style="background:#fff; color:#475569; border:1px solid #cbd5e1;">⚪ × 不可（消す）</span>
                <span class="g-pill" style="background:#e2e8f0; color:#475569;">授 授業等</span>
                <span class="g-pill" style="background:#e0f2fe; color:#0369a1;">💬 メモ付き</span>
            </div>
            <div>
                <span class="g-fp-mock">
                    <span style="color:#94a3b8;">⠿</span>
                    <span class="g-fp-dot" style="background:#4CAF50; color:#fff;">◯</span>
                    <span class="g-fp-dot" style="background:#FFEB3B; color:#1e293b;">△</span>
                    <span class="g-fp-dot" style="background:#f8fafc; color:#0f172a;">×</span>
                    <span style="font-size:11px; color:#cbd5e1;">← 指で好きな位置へ動かせるパレット</span>
                </span>
            </div>
        </div>
        <p class="g-text">スマホでは画面上に浮かぶ黒いペンパレットを指でドラッグして手元に置けるため、上下に戻る手間がありません。</p>
    </div>
    <div class="g-card">
        <span class="g-step">STEP 3・操作のコツ</span>
        <div class="g-title">📱 スマホ ＆ 💻 PC 快適操作チートシート</div>
        <div class="g-demo-box">
            <div style="font-size:12.5px; font-weight:800; color:#0369a1; margin-bottom:4px;">📱 スマートフォン</div>
            <div class="g-text" style="font-size:12.5px;">
                ・<b>1本指でなぞる</b> → マスを連続で塗る<br>
                ・<b>2本指で動かす</b> → 塗らずに上下左右スクロール<br>
                ・<b>🔍− / ＋ ボタン</b> → 予定表を縮小・拡大して全体を見渡す<br>
                ・<b>マスを長押し（または 💬 ペン）</b> → 「遅刻します」などの時間メモ入力
            </div>
            <hr style="margin:8px 0; border:0; border-top:1px dashed #cbd5e1;">
            <div style="font-size:12.5px; font-weight:800; color:#047857; margin-bottom:4px;">💻 パソコン</div>
            <div class="g-text" style="font-size:12.5px;">
                ・<span class="g-kbd">左ドラッグ</span> 塗る ／ <span class="g-kbd">右クリック・右ドラッグ</span> すぐ消す<br>
                ・<span class="g-kbd">ダブルクリック</span> その時間枠に詳細メモを追加<br>
                ・<span class="g-kbd">🔍− / ＋</span> で見やすいサイズに縮小・拡大
            </div>
        </div>
    </div>
    <div class="g-card">
        <span class="g-step">STEP 4・集計と決定</span>
        <div class="g-title">🏆 集計の見方 ＆ ワンタップでカレンダー登録</div>
        <p class="g-text">集計画面では <b>「🏆 おすすめ候補」</b> が自動で上位表示されます。緑が濃いマスほど参加できる人が多い時間帯です。</p>
        <div class="g-demo-box">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; font-size:12px; font-weight:700;">
                <span>少</span>
                <div style="flex:1; height:10px; border-radius:999px; background:linear-gradient(90deg, #f0faf2, #1b5e20);"></div>
                <span>多</span>
            </div>
            <div style="font-size:12px; color:#334155;">
                👆 <b>マスをタップ／クリック</b>すると、その時間の <b>◯ 参加可 / △ 未定 / × 不可</b> のメンバーとメモがポップアップ表示されます。集計表も <b>🔍− / ＋ ボタン</b>で縮小・拡大できます。
            </div>
        </div>
        <p class="g-text">絞り込みや必須メンバー指定は <b>「⚙️ 表示設定・絞り込み」</b> から開けます。</p>
    </div>
</div>
<div class="g-card">
    <span class="g-step">⚡ 時短テクニック</span>
    <div class="g-title">🚀 毎回手入力しなくてOK！自動入力＆カレンダー連携</div>
    <div class="g-grid" style="margin-bottom:0; margin-top:8px;">
        <div class="g-demo-box" style="margin:0;">
            <div style="font-weight:800; font-size:13px; color:#0f172a; margin-bottom:4px;">⏰ 1. 自分の時間割を登録しておく</div>
            <p class="g-text" style="font-size:12.5px;">左メニューの <b>「⏰ 時間割の登録」</b> で授業を一度登録しておくと、入力画面の <b>「⚙️ 便利機能」→「時間割反映」</b> から1タップで授業コマを自動ブロックできます。</p>
        </div>
        <div class="g-demo-box" style="margin:0;">
            <div style="font-weight:800; font-size:13px; color:#0f172a; margin-bottom:4px;">📌 2. 開催日時が決まったら1タップ登録</div>
            <p class="g-text" style="font-size:12.5px;">主催者が日時を確定するとイベント上部に緑の決定カードが表示されます。<b>「📅 Googleカレンダー追加」</b> や <b>「📥 .ics保存」</b> で自分の予定表へすぐ登録できます。</p>
        </div>
    </div>
</div>
"""), unsafe_allow_html=True)


def render_create_event_view(user):
    st.title("➕ イベント新規作成")
    st.caption("作成したい日程調整のタイプを下のカードからタップして選んでください。")

    if "create_ev_type" not in st.session_state:
        st.session_state.create_ev_type = "time"

    picked_type = type_picker(selected=st.session_state.create_ev_type, key="create_ev_type_picker")
    if picked_type in ["time", "timetable", "date_timetable", "options"]:
        st.session_state.create_ev_type = picked_type
    ev_type = st.session_state.create_ev_type

    ev_title = st.text_input("イベント名", placeholder="例: 定例MTG / 新歓日程調整")

    with st.container(border=True):
        st.markdown("##### ⏳ 回答期限の設定")
        col_d1, col_d2 = st.columns([1, 1])
        with col_d1:
            deadline_date = st.date_input("回答期限 (日付)", value=datetime.today() + timedelta(days=7))
        with col_d2:
            deadline_time = st.time_input("回答期限 (時刻)", value=datetime.strptime("23:59", "%H:%M").time())
        auto_close = st.checkbox("✅ 期限が過ぎたら自動で締め切る (回答不可にする)", value=True)
        auto_archive = st.checkbox("✅ 締切後、7日経過したら自動でアーカイブする", value=True)

    ev_start, ev_end, t_start, t_end = None, None, None, None
    opts_list = []

    if ev_type == "time":
        with st.container(border=True):
            st.markdown("##### 📅 1. カレンダーに表示する【期間】")
            col1, col_m1, col2 = st.columns([10, 1, 10])
            with col1:
                ev_start = st.date_input("開始日", label_visibility="collapsed")
            with col_m1:
                st.markdown("<div style='text-align:center; font-weight:bold; font-size:18px;'>〜</div>", unsafe_allow_html=True)
            with col2:
                ev_end = st.date_input("終了日", label_visibility="collapsed")

        with st.container(border=True):
            st.markdown("##### ⏰ 2. 1日あたりの対象【時間帯】")
            col3, col_m2, col4 = st.columns([10, 1, 10])
            with col3:
                t_start = st.selectbox("開始時刻", time_master, index=36, label_visibility="collapsed")
            with col_m2:
                st.markdown("<div style='text-align:center; font-weight:bold; font-size:18px;'>〜</div>", unsafe_allow_html=True)
            with col4:
                t_end = st.selectbox("終了時刻", time_master, index=72, label_visibility="collapsed")

    elif ev_type == "timetable":
        pass

    elif ev_type == "date_timetable":
        with st.container(border=True):
            st.markdown("##### 📅 対象となる【期間】")
            col1, col_m1, col2 = st.columns([10, 1, 10])
            with col1:
                ev_start = st.date_input("開始日", label_visibility="collapsed")
            with col_m1:
                st.markdown("<div style='text-align:center; font-weight:bold; font-size:18px;'>〜</div>", unsafe_allow_html=True)
            with col2:
                ev_end = st.date_input("終了日", label_visibility="collapsed")
    else:
        ev_type = "options"
        if "opt_count" not in st.session_state:
            st.session_state.opt_count = 3
        with st.container(border=True):
            st.markdown("##### 📅 候補リストを作成")
            for i in range(st.session_state.opt_count):
                val = st.text_input(f"候補 {i + 1}", key=f"new_opt_{i}", placeholder="例: 4/1 19:00〜 新歓")
                opts_list.append(val)
            if st.button("➕ 候補を追加する", use_container_width=True):
                st.session_state.opt_count += 1
                st.rerun()

    with st.container(border=True):
        st.markdown("##### 👥 参加メンバーの指定")
        is_all_members = st.checkbox("✅ 全員に公開する（デフォルト）", value=True, key="create_all_members")
        target_scope_json = ""
        t_g1, t_g2, t_g3, t_g4 = [], [], [], []

        if not is_all_members:
            all_u = _fetch_all_users_cached()
            all_g1 = sort_groups(list({g.strip() for u in all_u for g in str(u.get("group_1", "")).split(",") if g.strip()}), MASTER_G1)
            all_g2 = sort_groups(list({g.strip() for u in all_u for g in str(u.get("group_2", "")).split(",") if g.strip()}), MASTER_G2)
            all_g3 = sort_groups(list({g.strip() for u in all_u for g in str(u.get("group_3", "")).split(",") if g.strip()}), MASTER_G3)

            st.markdown("<span style='font-size:13px; color:#555;'>※ここで指定したグループや個人のみにイベントが表示されます。</span>", unsafe_allow_html=True)
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                t_g1 = st.multiselect("🚀 プロジェクト", all_g1, key="tgt_g1")
                t_g3 = st.multiselect("🏢 委員会", all_g3, key="tgt_g3")
                t_g4 = st.multiselect("👑 役職", MASTER_G4_OPTS, key="tgt_g4")
            with col_t2:
                t_g2 = st.multiselect("🔧 系", all_g2, key="tgt_g2")
                t_users = st.multiselect(
                    "👤 特定の個人",
                    sorted(all_u, key=lambda x: x.get("name", "")),
                    format_func=lambda x: f"{x.get('name')} (ID: {x.get('user_id')})",
                    key="tgt_users",
                )

            expanded_g4 = []
            for g in t_g4:
                if g == "シスマネ":
                    expanded_g4.extend(["ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ", "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ", "シスマネ"])
                elif g == "系長":
                    expanded_g4.extend(["燃焼系長", "推進系長", "構造系長", "電装系長", "エンジン系長", "系長"])
                else:
                    expanded_g4.append(g)

            target_scope_json = json.dumps({
                "groups": t_g1 + t_g2 + t_g3 + expanded_g4,
                "users": [u["user_id"] for u in t_users],
            })

        preview_mentions = []
        if is_all_members:
            preview_mentions.append("@channel")
        else:
            if "衛星" in t_g1: preview_mentions.append("@cubesat")
            if "ロケット" in t_g1: preview_mentions.append("@rocket")
            if "BizSat" in t_g1: preview_mentions.append("@biz-sat")
            if "通信系" in t_g2 or "通信" in t_g2: preview_mentions.append("@com")
            if "熱系" in t_g2 or "熱" in t_g2: preview_mentions.append("@heat")
            if "構造系" in t_g2 or "構造 (衛星)" in t_g2: preview_mentions.append("@str")
            if "ミッション系" in t_g2 or "ミッション" in t_g2: preview_mentions.append("@mission")
            if "姿勢系" in t_g2 or "姿勢" in t_g2: preview_mentions.append("@shisei")
            if "電源系" in t_g2 or "電源" in t_g2: preview_mentions.append("@eps")
            if "C＆DH系" in t_g2 or "C＆DH" in t_g2: preview_mentions.append("@cdh")
            if "COLOURS電装系" in t_g2 or "電装" in t_g2: preview_mentions.append("@avionics")
            if "COLOURS構造系" in t_g2 or "構造 (ロケット)" in t_g2: preview_mentions.append("@structure")
            if "COLOURS推進系" in t_g2 or "推進" in t_g2: preview_mentions.append("@simu")
            if "COLOURS燃焼系" in t_g2 or "燃焼" in t_g2: preview_mentions.append("@combustion")
            if "PMs (衛星)" in t_g4: preview_mentions.append("@pms")
            if "シスマネ" in t_g4: preview_mentions.append("@managers")
            if "新入生教育" in t_g3: preview_mentions.append("@sssup")
            if "執行部" in t_g3: preview_mentions.append("@executives")
            if "広報" in t_g3: preview_mentions.append("@kouhou")
            if "イベント" in t_g3: preview_mentions.append("@event")
            if "会計" in t_g3: preview_mentions.append("@kaikei")
            preview_mentions = list(dict.fromkeys(preview_mentions))

        st.markdown("---")
        st.markdown("##### 📣 Slackメンションのプレビュー")
        st.warning("⚠️ **注意:** 「プロジェクト」と「系」を両方選択すると、それぞれのグループ全体にメンションが飛びます。")
        if preview_mentions:
            st.code(" ".join(preview_mentions), language="text")
        else:
            st.write("※メンションは設定されていません（個別のユーザー指定のみ、または通知なし）")

    with st.container(border=True):
        st.markdown("##### 🔒 プライバシー・通知設定")
        is_private = st.checkbox("🤫 プライベート調整にする（回答者の名前を他の参加者に隠す）", key="create_private")
        skip_slack = st.checkbox("🔕 Slackに通知を送らない（ひっそり作成してURLで直接招待する）", value=False, key="skip_slack")

    st.markdown("##### 📝 イベントの説明・備考")
    ev_desc_raw = rt_editor(key="desc_editor")
    ev_desc = ev_desc_raw if ev_desc_raw else ""

    if st.button("🚀 イベントを作成", use_container_width=True, type="primary"):
        if not ev_title:
            st.warning("イベント名を入力してください。")
        elif ev_type in ["time", "date_timetable"] and (not ev_start or not ev_end):
            st.error("開始日と終了日を正しく入力してください。")
        elif ev_type in ["time", "date_timetable"] and ev_start > ev_end:
            st.error("終了日は開始日以降に設定してください。")
        elif ev_type == "time" and time_master.index(t_start) >= time_master.index(t_end):
            st.error("終了時刻は開始時刻より後に設定してください。")
        elif ev_type == "options" and not any(o.strip() for o in opts_list):
            st.error("最低1つの候補を入力してください。")
        elif not is_all_members and target_scope_json == '{"groups": [], "users": []}':
            st.error("対象メンバーを指定するか、「全員に公開する」にチェックを入れてください。")
        else:
            mention_text = " ".join(preview_mentions).replace("@channel", " < !channel > ").replace(" ", "")
            deadline_str = f"{deadline_date.strftime('%Y-%m-%d')} {deadline_time.strftime('%H:%M')}"
            created_event_id = f"EV-{datetime.now().strftime('%m%d-%H%M%S')}-{random.randint(1000, 9999)}"

            payload = {
                "event_id": created_event_id,
                "title": ev_title,
                "description": ev_desc,
                "start_date": ev_start.strftime("%Y-%m-%d") if ev_type in ["time", "date_timetable"] else "",
                "end_date": ev_end.strftime("%Y-%m-%d") if ev_type in ["time", "date_timetable"] else "",
                "start_idx": time_master.index(t_start) if ev_type == "time" else 0,
                "end_idx": time_master.index(t_end) if ev_type == "time" else 0,
                "status": "open",
                "event_type": ev_type,
                "event_options": json.dumps([o.strip() for o in opts_list if o.strip()]) if ev_type == "options" else "",
                "deadline": deadline_str,
                "auto_close": auto_close,
                "auto_archive": auto_archive,
                "target_scope": target_scope_json,
                "is_private": is_private,
                "skip_slack": skip_slack,
                "mention_text": mention_text,
                "created_by": str(user.get("user_id", "")),
            }

            try:
                db.collection("events").document(created_event_id).set(payload)
                invalidate_cache("events")
                backup_to_gas_async("create_event", {"payload": payload})
                st.session_state.last_created_ev = {"id": created_event_id, "title": ev_title}
                if "opt_count" in st.session_state:
                    del st.session_state.opt_count
            except Exception as e:
                st.error(f"❌ イベントの作成に失敗しました: {e}")

    if st.session_state.get("last_created_ev"):
        created = st.session_state.last_created_ev
        share_url = f"{APP_BASE_URL}?event={created['id']}"
        st.success(f"「{created['title']}」を作成しました！")
        c_cp, c_go = st.columns([2, 1])
        with c_cp:
            render_copy_button(
                share_url,
                btn_label="🔗 招待リンクをコピー",
                share_title=created["title"],
                share_url=share_url,
                key_suffix=f"created_{created['id']}",
                full_width=True,
            )
        with c_go:
            if st.button("📝 このイベントを開く", key="open_newly_created", use_container_width=True, type="primary"):
                st.session_state.target_ev_id = created["id"]
                st.session_state.current_menu = "dashboard"
                st.session_state.last_created_ev = None
                st.rerun()
        st.code(share_url, language="text")


def render_admin_view(user):
    st.title("⚙️ 管理者ダッシュボード")
    tab_manage, tab_users = st.tabs(["📝 イベント・アーカイブ管理", "👥 ユーザー管理"])

    with tab_manage:
        all_users_admin = _fetch_all_users_cached()
        user_map = {u.get("user_id"): u.get("name") for u in all_users_admin}
        all_g1 = sort_groups(list({g.strip() for u in all_users_admin for g in str(u.get("group_1", "")).split(",") if g.strip()}), MASTER_G1)
        all_g2 = sort_groups(list({g.strip() for u in all_users_admin for g in str(u.get("group_2", "")).split(",") if g.strip()}), MASTER_G2)
        all_g3 = sort_groups(list({g.strip() for u in all_users_admin for g in str(u.get("group_3", "")).split(",") if g.strip()}), MASTER_G3)

        all_events = [normalize_event_dict(d) for d in _fetch_all_events_cached()]

        if all_events:
            df_ev = pd.DataFrame(all_events)
            for col_name, default_val in [
                ("event_type", "time"), ("deadline", ""), ("target_scope", ""),
                ("is_private", False), ("start_idx", 0), ("end_idx", 0),
            ]:
                if col_name not in df_ev.columns:
                    df_ev[col_name] = default_val
            df_ev["種類"] = df_ev["event_type"].replace({
                "time": "🕒 時間", "timetable": "🏫 時間割",
                "date_timetable": "📅 日付コマ", "options": "📅 予定候補",
            })
            df_ev["期限"] = df_ev["deadline"].apply(format_deadline_jp)
            df_ev["公開範囲"] = df_ev["target_scope"].apply(lambda x: format_target_scope(x, user_map))
            df_ev["URL"] = df_ev["event_id"].apply(lambda eid: f"{APP_BASE_URL}?event={eid}")

            st.subheader("📋 全イベント一覧（行をクリックで選択）")
            df_ev_active = df_ev[df_ev["status"] != "archived"].reset_index(drop=True)
            prev_selected = st.session_state.get("manage_target_ev_id", None)

            event_selection = st.dataframe(
                df_ev_active[["title", "種類", "期限", "公開範囲", "status", "URL"]],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="multi-row",
                key="event_table",
                column_config={"URL": st.column_config.TextColumn("URL（コピー用）")},
            )

            selected_rows = event_selection.selection.rows
            just_selected = False
            selected_event_ids = []
            if selected_rows:
                valid_rows = [r for r in selected_rows if r < len(df_ev_active)]
                if valid_rows:
                    selected_event_ids = [df_ev_active.iloc[r]["event_id"] for r in valid_rows]
                    selected_event_id = selected_event_ids[0]
                    if selected_event_id != prev_selected:
                        just_selected = True
                        st.session_state["manage_target_ev_id"] = selected_event_id
                        row_data = df_ev_active.iloc[valid_rows[0]]
                        target_label = f"{row_data['title']} ({row_data['status']})"
                        st.session_state["manage_target_ev"] = target_label
                        st.session_state["chk_unanswered"] = target_label

            if len(selected_rows) > 0:
                st.markdown(f"**✅ {len(selected_rows)} 件のイベントが選択されています**")
                if st.button(f"📦 選択した {len(selected_rows)} 件を一括アーカイブする", type="primary"):
                    for eid in selected_event_ids:
                        db.collection("events").document(eid).update({"status": "archived"})
                        backup_to_gas_async("update_event_status", {"payload": {"event_id": eid, "status": "archived"}})
                    invalidate_cache("events")
                    st.toast(f"✅ {len(selected_rows)}件のイベントをアーカイブしました！")
                    time.sleep(0.8)
                    st.rerun()

            st.markdown("---")
            st.markdown('<div id="manage-section"></div>', unsafe_allow_html=True)
            st.subheader("⚙️ イベントの編集・ステータス管理・削除")

            if just_selected:
                components.html(
                    """<script>
                    setTimeout(function() {
                        const target = window.parent.document.getElementById('manage-section');
                        if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
                    }, 150);
                    </script>""",
                    height=0,
                )

            active_events = [ev for ev in all_events if ev.get("status") in ["open", "closed"]]
            if active_events:
                ev_options = {f"{ev.get('title')} ({ev.get('status')})": ev for ev in active_events}
                selected_label = st.selectbox(
                    "管理するイベントを検索・選択（↑表の行クリックでも選択可）",
                    options=list(ev_options.keys()),
                    key="manage_target_ev",
                )
                target_ev = ev_options[selected_label]

                tab_edit, tab_status, tab_delete = st.tabs(["✏️ 情報編集", "⚙️ ステータス変更", "🗑️ 削除"])
                with tab_edit:
                    with st.form("edit_event_form"):
                        st.info("💡 タイトル、説明文、回答期限、および参加メンバー（公開範囲）を編集できます。")
                        new_title = st.text_input("タイトル", value=target_ev.get("title", ""))
                        new_desc = st.text_area("説明文・備考", value=target_ev.get("description", ""), height=150)
                        new_auto_archive = st.checkbox("✅ 締切後、7日経過したら自動でアーカイブする", value=target_ev.get("auto_archive", True))

                        orig_deadline = target_ev.get("deadline") or target_ev.get("close_time", "")
                        try:
                            dt = pd.to_datetime(orig_deadline)
                            d_val, t_val = dt.date(), dt.time()
                        except Exception:
                            d_val, t_val = datetime.today().date(), datetime.strptime("23:59", "%H:%M").time()

                        col_d1, col_d2 = st.columns([1, 1])
                        with col_d1:
                            new_dl_date = st.date_input("回答期限 (日付)", value=d_val, key="edit_dl_d")
                        with col_d2:
                            new_dl_time = st.time_input("回答期限 (時刻)", value=t_val, key="edit_dl_t")

                        st.markdown("---")
                        st.markdown("##### 👥 参加メンバーの再設定")
                        scope_str = target_ev.get("target_scope", "")
                        is_all_members_def = True
                        t_g1_def, t_g2_def, t_g3_def, t_g4_def, t_users_def = [], [], [], [], []
                        if scope_str and scope_str.startswith("{"):
                            try:
                                scope = json.loads(scope_str)
                                tg, tu = scope.get("groups", []), scope.get("users", [])
                                if tg or tu:
                                    is_all_members_def = False
                                    t_g1_def = [g for g in tg if g in all_g1]
                                    t_g2_def = [g for g in tg if g in all_g2]
                                    t_g3_def = [g for g in tg if g in all_g3]
                                    t_g4_def = [g for g in tg if g in MASTER_G4_OPTS]
                                    t_users_def = [u for u in all_users_admin if u["user_id"] in tu]
                            except Exception:
                                pass

                        edit_is_all = st.checkbox("✅ 全員に公開する", value=is_all_members_def, key="edit_all_members")
                        col_t1, col_t2 = st.columns(2)
                        with col_t1:
                            edit_g1 = st.multiselect("🚀 プロジェクト", all_g1, default=t_g1_def, key="edit_g1")
                            edit_g3 = st.multiselect("🏢 委員会", all_g3, default=t_g3_def, key="edit_g3")
                            edit_g4 = st.multiselect("👑 役職", MASTER_G4_OPTS, default=t_g4_def, key="edit_g4")
                        with col_t2:
                            edit_g2 = st.multiselect("🔧 系", all_g2, default=t_g2_def, key="edit_g2")
                            edit_users = st.multiselect(
                                "👤 特定の個人",
                                sorted(all_users_admin, key=lambda x: x.get("name", "")),
                                default=t_users_def,
                                format_func=lambda x: f"{x.get('name')} (ID: {x.get('user_id')})",
                                key="edit_users",
                            )

                        if st.form_submit_button("💾 変更を保存", type="primary"):
                            if not new_title:
                                st.error("タイトルは必須です。")
                            else:
                                new_dl_str = f"{new_dl_date.strftime('%Y-%m-%d')} {new_dl_time.strftime('%H:%M')}"
                                new_scope_json = ""
                                if not edit_is_all:
                                    expanded_g4 = []
                                    for g in edit_g4:
                                        if g == "シスマネ":
                                            expanded_g4.extend(["ミッションシスマネ", "電源シスマネ", "構造シスマネ", "通信シスマネ", "姿勢シスマネ", "熱シスマネ", "C＆DHシスマネ", "シスマネ"])
                                        elif g == "系長":
                                            expanded_g4.extend(["燃焼系長", "推進系長", "構造系長", "電装系長", "エンジン系長", "系長"])
                                        else:
                                            expanded_g4.append(g)
                                    new_scope_json = json.dumps({"groups": edit_g1 + edit_g2 + edit_g3 + expanded_g4, "users": [u["user_id"] for u in edit_users]})

                                updates = {
                                    "title": new_title,
                                    "description": new_desc,
                                    "deadline": new_dl_str,
                                    "auto_archive": new_auto_archive,
                                    "target_scope": new_scope_json,
                                }
                                db.collection("events").document(target_ev["event_id"]).update(updates)
                                invalidate_cache("events")
                                backup_to_gas_async("update_event", {"payload": {"event_id": target_ev["event_id"], **updates}})
                                st.toast("✅ イベント情報を更新しました")
                                time.sleep(0.8)
                                st.rerun()

                with tab_status:
                    with st.form("update_status_form"):
                        current_status = target_ev.get("status", "open")
                        status_opts = ["open", "closed", "archived"]
                        idx = status_opts.index(current_status) if current_status in status_opts else 0
                        new_status = st.selectbox("ステータス", status_opts, index=idx)
                        if st.form_submit_button("更新する"):
                            db.collection("events").document(target_ev["event_id"]).update({"status": new_status})
                            invalidate_cache("events")
                            backup_to_gas_async("update_event_status", {"payload": {"event_id": target_ev["event_id"], "status": new_status}})
                            st.toast("✅ ステータスを更新しました")
                            time.sleep(0.8)
                            st.rerun()

                with tab_delete:
                    st.warning("⚠️ **イベントの削除**\n\n削除すると元に戻せません。回答データもすべて削除されます。")
                    ans_docs = list(db.collection("responses").where("event_id", "==", target_ev["event_id"]).stream())
                    ans_count = len(ans_docs)
                    if ans_count > 0:
                        st.error(f"🚨 **すでに {ans_count} 件の回答があります！**")
                    else:
                        st.info("回答はまだありません。")

                    ev_id_str = target_ev["event_id"]
                    last_4 = ev_id_str[-4:] if len(ev_id_str) >= 4 else ev_id_str
                    with st.form("delete_event_form"):
                        st.write(f"誤操作を防ぐため、イベントIDの下4桁「**{last_4}**」を入力してください。")
                        confirm_str = st.text_input("イベントIDの下4桁", key="del_confirm")
                        if st.form_submit_button("🗑️ イベントを完全に削除する"):
                            if confirm_str == last_4:
                                db.collection("events").document(ev_id_str).delete()
                                for d in ans_docs:
                                    db.collection("responses").document(d.id).delete()
                                invalidate_cache("all")
                                backup_to_gas_async("delete_event", {"payload": {"event_id": ev_id_str}})
                                st.toast("🗑️ イベントを削除しました")
                                time.sleep(0.8)
                                st.rerun()
                            else:
                                st.error("入力された確認コードが一致しません。")
            else:
                st.info("💡 現在、編集・管理できるイベント（open または closed）はありません。")

            st.markdown("---")
            st.subheader("👀 未回答者の抽出")
            if active_events:
                selected_chk_label = st.selectbox(
                    "確認するイベントを選択（↑表の行クリックでも選択可）",
                    options=list(ev_options.keys()),
                    key="chk_unanswered",
                )
                check_ev = ev_options[selected_chk_label]
                if st.button("未回答者を抽出する", type="primary"):
                    with st.spinner("データを照合中..."):
                        ans_docs = db.collection("responses").where("event_id", "==", check_ev["event_id"]).stream()
                        answered_uids = {str(d.to_dict().get("user_id")) for d in ans_docs}
                        target_users = []
                        scope_str = check_ev.get("target_scope", "")
                        for u in all_users_admin:
                            uid = str(u.get("user_id"))
                            if uid in answered_uids:
                                continue
                            if is_in_scope(expand_user_groups(u), uid, scope_str):
                                target_users.append(u.get("name", ""))
                        st.session_state["last_unanswered_result"] = {
                            "ev_id": check_ev["event_id"],
                            "users": sorted(target_users),
                        }

                res_un = st.session_state.get("last_unanswered_result")
                if res_un and res_un.get("ev_id") == check_ev["event_id"]:
                    t_users_res = res_un["users"]
                    if t_users_res:
                        st.warning(f"⚠️ 対象者のうち、未回答の人が {len(t_users_res)} 名います。")
                        txt_list = "\n".join(t_users_res)
                        render_copy_button(
                            txt_list,
                            btn_label="📋 未回答者リストをコピー",
                            key_suffix=f"unans_{check_ev['event_id']}",
                        )
                        st.code(txt_list, language="text")
                    else:
                        st.success("🎉 対象者は全員回答済みです！")

            st.markdown("---")
            st.subheader("📦 アーカイブ済み")
            archived_events = [ev for ev in all_events if ev.get("status") == "archived"]
            if archived_events:
                df_ev_archived = df_ev[df_ev["status"] == "archived"].reset_index(drop=True)
                ev_options_arch = {ev.get("title"): ev for ev in archived_events}
                prev_arch_selected = st.session_state.get("manage_arch_ev_id", None)

                st.markdown("##### 📋 アーカイブ一覧（行をクリックで選択）")
                arch_selection = st.dataframe(
                    df_ev_archived[["title", "種類", "期限", "公開範囲", "status"]],
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="arch_table",
                )
                if arch_selection.selection.rows:
                    valid_arch_rows = [r for r in arch_selection.selection.rows if r < len(df_ev_archived)]
                    if valid_arch_rows:
                        sel_id = df_ev_archived.iloc[valid_arch_rows[0]]["event_id"]
                        if sel_id != prev_arch_selected:
                            st.session_state["manage_arch_ev_id"] = sel_id
                            st.session_state["manage_restore_ev"] = df_ev_archived.iloc[valid_arch_rows[0]]["title"]

                with st.form("restore_event_form"):
                    selected_restore_label = st.selectbox(
                        "復元するイベントを選択（↑表の行クリックでも選択可）",
                        options=list(ev_options_arch.keys()),
                        key="manage_restore_ev",
                    )
                    restore_ev = ev_options_arch[selected_restore_label]
                    if st.form_submit_button("🔄 選択したイベントを復元 (openにする)"):
                        db.collection("events").document(restore_ev["event_id"]).update({"status": "open", "auto_archive": False})
                        invalidate_cache("events")
                        backup_to_gas_async("update_event_status", {"payload": {"event_id": restore_ev["event_id"], "status": "open", "auto_archive": False}})
                        st.toast("✅ イベントを復元しました（自動アーカイブはオフになりました）")
                        time.sleep(0.8)
                        st.rerun()
            else:
                st.info("アーカイブされたイベントはありません。")

    with tab_users:
        st.subheader("👥 ユーザー一覧と権限管理")
        if st.button("🔄 ユーザー一覧を最新に更新"):
            invalidate_cache("users")
            st.rerun()

        all_users = _fetch_all_users_cached()
        if all_users:
            df_u = pd.DataFrame(all_users).rename(columns={
                "user_id": "ユーザーID", "name": "氏名", "role": "権限",
                "group_1": "プロジェクト", "group_2": "系", "group_3": "委員会", "group_4": "役職",
            })
            df_u["権限"] = df_u["権限"].replace({"top_admin": "👑 最高管理者", "admin": "🛠️ 管理者", "user": "📝 ユーザー", "guest": "👤 ゲスト"})
            display_cols = [c for c in ["ユーザーID", "氏名", "権限", "プロジェクト", "系", "委員会", "役職"] if c in df_u.columns]
            html_table = df_u[display_cols].to_html(index=False, border=0, classes="custom-tbl")
            table_html = (
                "<style>.custom-tbl { width: 100%; border-collapse: collapse; font-size: 14px; text-align: left; } "
                ".custom-tbl th { background-color: #f0f2f6; padding: 10px; border-bottom: 2px solid #4CAF50; white-space: nowrap; color: #333; } "
                ".custom-tbl td { padding: 10px; border-bottom: 1px solid #eee; color: #333; word-break: break-all; } "
                ".custom-tbl tr:hover { background-color: #f8f9fa; }</style>"
                f'<div style="overflow-x: auto; border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 20px;">{html_table}</div>'
            )
            st.markdown(table_html, unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("🚨 ユーザー情報の更新 (ID・氏名・PINリセット等)")
            tgt_user = st.selectbox("対象ユーザー", all_users, format_func=lambda x: f"{x.get('name')} (ID: {x.get('user_id')})")

            with st.form("admin_user_update"):
                new_u_pin = st.text_input("新しいPIN (リセットする場合のみ入力)", type="password", autocomplete="new-password")
                if user.get("role") == "top_admin":
                    st.info("👑 最高管理者メニュー: ユーザーIDと氏名の変更が可能です。")
                    new_u_id = st.text_input("ユーザーID", value=tgt_user.get("user_id"))
                    new_u_name = st.text_input("氏名", value=tgt_user.get("name"))
                    role_opts = ["guest", "user", "admin"]
                    if tgt_user.get("role") == "top_admin":
                        st.info("※最高管理者の権限はここで変更できません。下の譲渡メニューを使用してください。")
                        new_u_role = "top_admin"
                    else:
                        current_role = tgt_user.get("role") if tgt_user.get("role") in role_opts else "guest"
                        new_u_role = st.selectbox("権限の変更", role_opts, index=role_opts.index(current_role))
                else:
                    st.info("※権限（Role）やユーザーIDの変更は top_admin のみ可能です。")
                    new_u_id = tgt_user.get("user_id")
                    new_u_name = tgt_user.get("name")
                    new_u_role = tgt_user.get("role")

                del_check = st.checkbox("💥 このユーザーを完全に削除する (復旧不可)")

                if st.form_submit_button("更新/削除 実行", type="primary"):
                    if del_check:
                        if tgt_user.get("role") == "top_admin":
                            st.error("最高管理者は削除できません。先に譲渡してください。")
                        else:
                            uid = str(tgt_user["user_id"])
                            db.collection("users").document(uid).delete()
                            res_docs = db.collection("responses").where("user_id", "==", uid).stream()
                            for d in res_docs:
                                db.collection("responses").document(d.id).delete()
                            invalidate_cache("all")
                            backup_to_gas_async("delete_user", {"payload": {"user_id": uid}})
                            st.toast(f"ユーザー {uid} を削除しました", icon="✅")
                            st.rerun()
                    else:
                        if tgt_user.get("role") == "top_admin" and new_u_role != "top_admin":
                            st.error("最高管理者の権限は変更できません。")
                        else:
                            old_uid = str(tgt_user["user_id"])
                            new_uid = new_u_id.strip() if new_u_id else old_uid
                            new_name = new_u_name.strip() if new_u_name else tgt_user.get("name")
                            updates = {"role": new_u_role, "name": new_name}
                            gas_payload = {"user_id": old_uid, "role": new_u_role, "name": new_name}
                            if new_uid != old_uid:
                                updates["user_id"] = new_uid
                                gas_payload["new_user_id"] = new_uid
                            if new_u_pin:
                                updates["pin"] = hash_pin(new_u_pin)
                                gas_payload["new_pin"] = "PROTECTED"

                            try:
                                if new_uid != old_uid:
                                    existing = db.collection("users").document(new_uid).get()
                                    if existing.exists:
                                        st.error(f"エラー: ユーザーID '{new_uid}' は既に存在します。")
                                        st.stop()
                                    new_user_data = {**tgt_user, **updates}
                                    db.collection("users").document(new_uid).set(new_user_data)
                                    db.collection("users").document(old_uid).delete()
                                    res_docs = db.collection("responses").where("user_id", "==", old_uid).stream()
                                    for r_doc in res_docs:
                                        r_data = r_doc.to_dict()
                                        r_event_id = r_data.get("event_id")
                                        r_data["user_id"] = new_uid
                                        db.collection("responses").document(f"{r_event_id}_{new_uid}").set(r_data)
                                        db.collection("responses").document(r_doc.id).delete()
                                else:
                                    db.collection("users").document(old_uid).update(updates)
                                invalidate_cache("all")
                                backup_to_gas_async("admin_update_user", {"payload": gas_payload})
                                st.toast("ユーザー情報を更新しました", icon="✅")
                                st.rerun()
                            except Exception as e:
                                st.error(f"更新中にエラーが発生しました: {e}")

            if user.get("role") == "top_admin":
                st.markdown("---")
                st.subheader("👑 最高管理者 (top_admin) の譲渡")
                st.warning("⚠️ この操作を実行すると、あなたは `admin` に降格し、元に戻すことはできません。")
                candidates = [u for u in all_users if u.get("user_id") != user.get("user_id")]
                new_top = st.selectbox("譲渡先ユーザー", candidates, format_func=lambda x: f"{x.get('name')} (ID: {x.get('user_id')})")
                st.markdown(
                    "<span style='font-size:13px; color:#555;'>PINリセットなどのSOSを受け取るための、新しい管理者の<b>SlackメンバーID（Uから始まる英数字）</b>を入力してください。</span>",
                    unsafe_allow_html=True,
                )
                new_slack_id = st.text_input("SlackメンバーID (例: U06CEMZJ7DE)")

                if st.button("🔔 テスト通知を送信"):
                    if new_slack_id:
                        clean_id = new_slack_id.strip().replace("@", "").replace("<", "").replace(">", "")
                        res = call_gas("test_slack_mention", {"payload": {"slack_id": f"<@{clean_id}>"}}, method="POST")
                        if res.get("status") == "success":
                            st.success("Slackにテスト通知を送信しました！通知が来ているか確認してください。")
                        else:
                            st.error("テスト通知の送信に失敗しました。")
                    else:
                        st.warning("SlackメンバーIDを入力してください。")

                if st.checkbox("✅ Slackでテスト通知が届いたことを確認しました"):
                    if st.button("🚀 top_adminを譲渡する", type="primary"):
                        clean_id = new_slack_id.strip().replace("@", "").replace("<", "").replace(">", "")
                        mention_str = f"<@{clean_id}>" if clean_id else ""
                        db.collection("users").document(str(user["user_id"])).update({"role": "admin"})
                        updates_top = {"role": "top_admin"}
                        if mention_str:
                            updates_top["slack_id"] = mention_str
                        db.collection("users").document(str(new_top["user_id"])).update(updates_top)
                        invalidate_cache("users")
                        backup_to_gas_async("transfer_top_admin", {"payload": {
                            "caller_id": user["user_id"], "target_id": new_top["user_id"], "slack_id": mention_str,
                        }})
                        _do_logout()


# ==========================================
# ダッシュボード・個別イベント・集計UI
# ==========================================
def _render_event_card(ev, mode_btn_prefix, btn_label):
    ev_type = ev.get("event_type") or ev.get("type", "time")
    type_badge = EVENT_TYPE_LABELS.get(ev_type, "📅 日程調整")
    dl_text = format_deadline_jp(ev.get("deadline") or ev.get("close_time", ""))
    confirmed = parse_confirmed_info(ev.get("confirmed_info"))
    is_closed = ev.get("status") == "closed"

    badges_html = f"<span class='sss-badge sss-badge-type'>{html_lib.escape(type_badge)}</span>"
    if is_closed:
        badges_html += "<span class='sss-badge sss-badge-closed'>🔒 締切</span>"
    if confirmed:
        badges_html += f"<span class='sss-badge sss-badge-confirmed'>🎉 決定: {html_lib.escape(confirmed.get('label', ''))}</span>"

    with st.container(border=True):
        st.markdown(f"**{html_lib.escape(ev.get('title', ''))}**", unsafe_allow_html=False)
        st.markdown(badges_html, unsafe_allow_html=True)
        dl_color = "#64748b" if (ev.get("is_answered") or is_closed) else "#E91E63"
        st.markdown(f"<span style='color:{dl_color}; font-size:12px; font-weight:600;'>⏳ 締切: {html_lib.escape(dl_text)}</span>", unsafe_allow_html=True)
        if st.button(btn_label, key=f"{mode_btn_prefix}_{ev['event_id']}", use_container_width=True):
            st.session_state.target_ev_id = ev["event_id"]
            st.rerun()


def render_dashboard_view(events):
    unanswered_open = []
    closed_unanswered = []
    seen_ids = set()
    for ev in events:
        eid = ev.get("event_id")
        if eid in seen_ids:
            continue
        seen_ids.add(eid)
        if not ev.get("is_answered"):
            if ev.get("status") == "open":
                unanswered_open.append(ev)
            else:
                closed_unanswered.append(ev)

    answered_events = [ev for ev in events if ev.get("is_answered")]
    confirmed_cnt = sum(1 for ev in events if parse_confirmed_info(ev.get("confirmed_info")))

    st.subheader("📋 イベント一覧")
    st.markdown(
        _compact_html(f"""
        <div class="dash-stats">
            <span class="dash-stat-pill" style="background:#fef2f2; color:#b91c1c; border-color:#fecaca;">🔴 未回答 {len(unanswered_open)}件</span>
            <span class="dash-stat-pill" style="background:#ecfdf5; color:#047857; border-color:#a7f3d0;">✅ 回答済 {len(answered_events)}件</span>
            <span class="dash-stat-pill" style="background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe;">🎉 開催決定 {confirmed_cnt}件</span>
            <span class="menu-hint-banner">👈 左上「メニュー」から時間割・新規作成・ガイドへ</span>
        </div>
        """),
        unsafe_allow_html=True,
    )

    c_left, c_right = st.columns(2)
    with c_left:
        st.markdown("#### 🔴 未回答のイベント")
        if unanswered_open:
            for ev in unanswered_open:
                _render_event_card(ev, "btn_u", "📝 このイベントに回答する")
        else:
            st.success("未回答のイベントはありません！🎉")

    with c_right:
        st.markdown("#### ✅ 回答済みのイベント")
        if answered_events:
            for ev in answered_events:
                _render_event_card(ev, "btn_a", "📊 回答・集計を見る")
        else:
            st.info("回答済みのイベントはありません。")

    if closed_unanswered:
        with st.expander(f"🔒 締切済みのイベント（未回答・集計閲覧のみ: {len(closed_unanswered)}件）", expanded=False):
            for ev in closed_unanswered:
                _render_event_card(ev, "btn_c", "📊 集計結果を見る")


def _save_confirmed_info(event_id, info_dict, notify_slack=False):
    """確定日時をFirestoreへ保存し、GASへも非同期バックアップする（空なら削除）"""
    if info_dict is None:
        db.collection("events").document(event_id).update({"confirmed_info": firestore.DELETE_FIELD})
    else:
        db.collection("events").document(event_id).update({"confirmed_info": info_dict})
    invalidate_cache("events")

    confirmed_str = json.dumps(info_dict, ensure_ascii=False) if info_dict else ""
    backup_to_gas_async("update_event", {
        "payload": {
            "event_id": event_id,
            "confirmed_info": confirmed_str,
            "notify_confirm_slack": bool(notify_slack and info_dict),
        }
    })


def render_confirmed_banner(event, share_url, can_confirm=False):
    confirmed = parse_confirmed_info(event.get("confirmed_info"))
    if not confirmed:
        return

    event_id = event.get("event_id")
    loc_html = f"<br>📍 <b>場所/URL:</b> {html_lib.escape(confirmed['location'])}" if confirmed.get("location") else ""
    note_html = f"<br>📝 <b>連絡:</b> {html_lib.escape(confirmed['note'])}" if confirmed.get("note") else ""

    start_dt = confirmed.get("start_dt", "")
    end_dt = confirmed.get("end_dt", "")
    details_txt = f"{confirmed.get('note', '')}\n詳細: {share_url}".strip()
    announce_txt = format_confirmed_announce_text(event, confirmed, share_url)

    gcal_url = build_gcal_url(
        event.get("title", "SSScheduler予定"),
        start_dt,
        end_dt,
        location=confirmed.get("location", ""),
        details=details_txt,
    )
    ics_data = build_ics_content(
        event.get("title", "SSScheduler予定"),
        start_dt,
        end_dt,
        location=confirmed.get("location", ""),
        details=details_txt,
        uid_prefix=event_id or "ssscheduler",
    )

    # 決定表示・カレンダー登録・決定連絡コピー・取り消しをすべて1つの区画（カード）内に集約
    with st.container(border=True):
        st.markdown('<div class="sss-confirmed-box-marker"></div>', unsafe_allow_html=True)
        st.markdown(
            _compact_html(f"""
            <div class="confirmed-banner-title">🎉 開催日時が決定しました</div>
            <div class="confirmed-banner-dt">📅 {html_lib.escape(confirmed.get('label', ''))}</div>
            <div class="confirmed-banner-meta">{loc_html}{note_html}</div>
            """),
            unsafe_allow_html=True,
        )

        if gcal_url and ics_data:
            b1, b2, b3 = st.columns([1.2, 1.1, 1.2])
            with b1:
                st.link_button("📅 Googleカレンダー追加", gcal_url, use_container_width=True, type="primary")
            with b2:
                st.download_button(
                    "📥 .ics 保存",
                    data=ics_data.encode("utf-8"),
                    file_name=f"{event_id or 'event'}.ics",
                    mime="text/calendar",
                    use_container_width=True,
                )
            with b3:
                render_copy_button(
                    announce_txt,
                    btn_label="📋 決定連絡コピー",
                    key_suffix=f"conf_cp_{event_id}",
                    full_width=True,
                )
        else:
            render_copy_button(
                announce_txt,
                btn_label="📋 決定連絡をコピー",
                key_suffix=f"conf_cp_{event_id}",
                full_width=True,
            )

        if can_confirm:
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
            if st.button("🗑️ この開催日時の決定を取り消す（主催者 / 管理者）", key=f"banner_unconfirm_{event_id}", use_container_width=True):
                _save_confirmed_info(event_id, None)
                st.toast("開催日時の決定を取り消しました。")
                st.rerun()


def render_ranking_cards(event, user, best_slots, share_url, can_confirm, key_prefix):
    """おすすめ候補日時をスマホでも見やすく2段ピル構成で表示（上位3件＋4〜5位展開）"""
    event_id = event.get("event_id")
    existing_conf = parse_confirmed_info(event.get("confirmed_info")) or {}

    if not best_slots:
        st.info("条件を満たすおすすめ候補がまだありません。")
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    rank_classes = ["rank-card rank-card-1", "rank-card rank-card-2", "rank-card rank-card-3", "rank-card", "rank-card"]

    def _draw_slot(i, slot):
        medal = medals[i] if i < len(medals) else f"{i + 1}."
        card_cls = rank_classes[i] if i < len(rank_classes) else "rank-card"
        card_html = (
            f"<div class='{card_cls}'>"
            f"<div class='rank-dt'>{medal} {html_lib.escape(slot['label'])}</div>"
            f"<div class='rank-chips'>"
            f"<span class='r-chip r-chip-score'>目安 {slot['score']:g}名</span>"
            f"<span class='r-chip r-chip-yes'>◯ {slot['yes']}</span>"
            f"<span class='r-chip r-chip-maybe'>△ {slot['maybe']}</span>"
            f"<span class='r-chip r-chip-no'>× {slot['no']}</span>"
            f"</div></div>"
        )
        if can_confirm:
            with st.container():
                st.markdown('<div class="sss-rank-row-marker"></div>', unsafe_allow_html=True)
                c_card, c_act = st.columns([4.4, 1])
                with c_card:
                    st.markdown(card_html, unsafe_allow_html=True)
                with c_act:
                    if st.button("📌 確定", key=f"{key_prefix}_pin_{i}_{event_id}", use_container_width=True):
                        new_conf = {
                            "label": slot["label"],
                            "start_dt": slot.get("start_dt", ""),
                            "end_dt": slot.get("end_dt", ""),
                            "location": existing_conf.get("location", ""),
                            "note": existing_conf.get("note", ""),
                            "confirmed_by": user.get("name", ""),
                            "confirmed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        }
                        _save_confirmed_info(event_id, new_conf)
                        st.toast(f"📌 「{slot['label']}」で確定しました！")
                        st.rerun()
        else:
            st.markdown(card_html, unsafe_allow_html=True)

    for i, slot in enumerate(best_slots[:3]):
        _draw_slot(i, slot)

    if len(best_slots) > 3:
        with st.expander(f"➕ 4〜{len(best_slots)}位の候補を見る", expanded=False):
            for i, slot in enumerate(best_slots[3:], start=3):
                _draw_slot(i, slot)

    slack_txt = format_slack_ranking_text(event, best_slots, share_url)
    render_copy_button(
        slack_txt,
        btn_label="📋 Slack用ランキングをコピー",
        key_suffix=f"{key_prefix}_slack_{event_id}",
    )


def render_confirm_editor_expander(event, user, best_slots, can_confirm, key_prefix):
    """主催者・管理者向けの開催日時 確定・編集・取消フォーム（画面下部に収納）"""
    if not can_confirm:
        return
    event_id = event.get("event_id")
    existing_conf = parse_confirmed_info(event.get("confirmed_info")) or {}

    with st.expander("📌 開催日時の確定・編集・取消（主催者 / 管理者用）", expanded=False):
        with st.form(f"confirm_edit_form_{key_prefix}_{event_id}"):
            def_label = existing_conf.get("label") or (best_slots[0]["label"] if best_slots else "")
            def_start = existing_conf.get("start_dt") or (best_slots[0].get("start_dt", "") if best_slots else "")
            def_end = existing_conf.get("end_dt") or (best_slots[0].get("end_dt", "") if best_slots else "")

            inp_label = st.text_input("決定日時（表示ラベル）", value=def_label, placeholder="例: 04/15(水) 13:00〜14:00")
            col_dt1, col_dt2 = st.columns(2)
            with col_dt1:
                inp_start = st.text_input("開始日時 (GCal連携用: YYYY-MM-DD HH:MM)", value=def_start, placeholder="2026-04-15 13:00")
            with col_dt2:
                inp_end = st.text_input("終了日時 (GCal連携用: YYYY-MM-DD HH:MM)", value=def_end, placeholder="2026-04-15 14:00")
            inp_loc = st.text_input("場所 / 会議URL (任意)", value=existing_conf.get("location", ""), placeholder="例: B4棟 201 / Zoom URL")
            inp_note = st.text_input("参加者への一言メモ (任意)", value=existing_conf.get("note", ""), placeholder="例: PC持参でお願いします")
            notify_slack = st.checkbox("📣 確定と同時にSlackへ決定通知を送る", value=False)

            c_sv, c_rm = st.columns([2, 1])
            with c_sv:
                save_btn = st.form_submit_button("💾 この内容で確定・更新", type="primary", use_container_width=True)
            with c_rm:
                clear_btn = st.form_submit_button("🗑️ 確定を取り消す", use_container_width=True)

            if save_btn:
                if not inp_label.strip():
                    st.error("決定日時（表示ラベル）を入力してください。")
                else:
                    _save_confirmed_info(event_id, {
                        "label": inp_label.strip(),
                        "start_dt": inp_start.strip(),
                        "end_dt": inp_end.strip(),
                        "location": inp_loc.strip(),
                        "note": inp_note.strip(),
                        "confirmed_by": user.get("name", ""),
                        "confirmed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }, notify_slack=notify_slack)
                    st.toast("🎉 開催日時を確定しました！")
                    st.rerun()
            elif clear_btn:
                _save_confirmed_info(event_id, None)
                st.toast("確定日時を取り消しました。")
                st.rerun()


def render_grid_event_view(event, user, can_view_details, can_confirm, is_closed, share_url):
    event_id = event.get("event_id")
    event_type = event.get("event_type") or event.get("type", "time")
    fixed_sched = user.get("fixed_schedule", {})
    unavail_col_rows = {}
    s_idx = 0

    if event_type == "time":
        s_idx = int(event.get("start_time_idx") or event.get("start_idx", 0))
        e_idx = int(event.get("end_time_idx") or event.get("end_idx", 0))
        if e_idx <= s_idx:
            e_idx = s_idx + 1
        date_objs, date_strs, clean_date_labels, week_breaks, day_kinds, legacy_col_map = compute_date_grid(
            event.get("start_date", ""), event.get("end_date", "")
        )
        time_labels = [idx_to_time(i) for i in range(s_idx, e_idx + 1)]
        for c, date_obj in enumerate(date_objs):
            wd = str(date_obj.weekday())
            if wd in fixed_sched:
                day_bin = fixed_sched[wd]
                rows_u = [gi - s_idx for gi, bit in enumerate(day_bin) if bit == "1" and s_idx <= gi <= e_idx]
                if rows_u:
                    unavail_col_rows[str(c)] = rows_u

    elif event_type == "timetable":
        date_objs = []
        date_strs = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        clean_date_labels = ["月曜", "火曜", "水曜", "木曜", "金曜"]
        week_breaks = [False] * 5
        day_kinds = ["weekday"] * 5
        legacy_col_map = {ds: i for i, ds in enumerate(date_strs)}
        time_labels = TIMETABLE_LABELS
        for c, wd in enumerate(["0", "1", "2", "3", "4"]):
            if wd in fixed_sched:
                day_bin = fixed_sched[wd]
                u_rows = []
                for r_idx, (_, _, p_s, p_e, _) in enumerate(PERIODS_MASTER):
                    if "1" in day_bin[p_s:p_e]:
                        u_rows.append(r_idx)
                if "1" in day_bin[74:]:
                    u_rows.append(len(PERIODS_MASTER))
                if u_rows:
                    unavail_col_rows[str(c)] = u_rows

    else:  # date_timetable
        date_objs, date_strs, clean_date_labels, week_breaks, day_kinds, legacy_col_map = compute_date_grid(
            event.get("start_date", ""), event.get("end_date", "")
        )
        time_labels = [p[0] for p in PERIODS_MASTER] + ["放課後"]
        for c, date_obj in enumerate(date_objs):
            wd = str(date_obj.weekday())
            if wd in fixed_sched:
                day_bin = fixed_sched[wd]
                u_rows = []
                for r_idx, (_, _, p_s, p_e, _) in enumerate(PERIODS_MASTER):
                    if "1" in day_bin[p_s:p_e]:
                        u_rows.append(r_idx)
                if "1" in day_bin[74:]:
                    u_rows.append(len(PERIODS_MASTER))
                if u_rows:
                    unavail_col_rows[str(c)] = u_rows

    if (
        "df_input" not in st.session_state
        or st.session_state.get("last_build_ev_id") != event_id
    ):
        df_init, my_comment, raw_my_cd = decode_binary_to_matrix(
            st.session_state.event_responses,
            user.get("user_id"),
            date_strs,
            time_labels,
            event_type,
            s_idx=s_idx,
        )
        st.session_state.df_input = df_init
        st.session_state.my_comment = my_comment
        st.session_state.my_cell_details = normalize_cell_details_for_editor(
            raw_my_cd, date_strs, legacy_col_map, len(time_labels), event_type=event_type
        )
        st.session_state.last_build_ev_id = event_id

    active_view = st.session_state.get("event_view_tab", "input")

    if active_view == "input":
        matrix_list = st.session_state.df_input[date_strs].values.tolist()
        raw = grid_editor(
            eventId=event_id,
            eventType=event_type,
            isTimeMode=(event_type == "time"),
            dateStrs=date_strs,
            cleanLabels=clean_date_labels,
            weekBreaks=week_breaks,
            dayKinds=day_kinds,
            timeLabels=time_labels,
            matrix=matrix_list,
            cellDetails=st.session_state.get("my_cell_details", {}),
            unavailColRows=unavail_col_rows,
            myComment=st.session_state.get("my_comment", ""),
            isClosed=is_closed,
            saveTs=st.session_state.get("last_saved_ts", 0),
            importTs=st.session_state.get("cal_import_ts", 0),
            defaultCellH=(34 if event_type == "time" else 48),
            key=f"editor_v18_{event_id}",
        )

        if raw and isinstance(raw, dict) and "data" in raw:
            if raw.get("trigger_save") and st.session_state.get("last_saved_ts") != raw.get("ts"):
                st.session_state.last_saved_ts = raw.get("ts")
                st.session_state.df_input = pd.DataFrame(raw["data"], index=time_labels, columns=date_strs)
                st.session_state.my_comment = raw.get("comment", "")
                cell_details_json = raw.get("cell_details", {}) or {}
                st.session_state.my_cell_details = cell_details_json
                cell_details_str = json.dumps(cell_details_json, separators=(",", ":")) if cell_details_json else "{}"
                all_res = encode_matrix_to_responses(
                    st.session_state.df_input, date_strs, time_labels, event_type, s_idx=s_idx
                )
                payload = {
                    "event_id": event_id,
                    "user_id": user.get("user_id"),
                    "comment": st.session_state.my_comment,
                    "cell_details": cell_details_str,
                    "responses": all_res,
                }
                if save_response_hybrid(payload):
                    st.session_state.save_success_msg = "回答を保存しました！みんなの集計を確認しましょう👀"
                    st.session_state.event_view_tab = "graph"
                    st.rerun()

        if event_type == "time" and not is_closed:
            with st.expander("📅 Googleカレンダー連携（外部予定を自動反映）", expanded=False):
                c_imp1, c_imp2 = st.columns([3, 1])
                with c_imp1:
                    st.write("プロフィールに設定したカレンダーの予定を読み込んで、自動で「授業等(グレー)」として反映します。")
                with c_imp2:
                    if st.button("🔄 カレンダーから取得", use_container_width=True):
                        user_cal_url = user.get("calendar_url", "")
                        if not user_cal_url or "http" not in user_cal_url:
                            st.warning("プロフィール画面でカレンダーの非公開URLを設定してください。")
                        else:
                            with st.spinner("予定を取得中..."):
                                res = call_gas(
                                    "import_google_calendar",
                                    {"payload": {
                                        "start_date": event.get("start_date"),
                                        "end_date": event.get("end_date"),
                                        "ical_url": user_cal_url,
                                    }},
                                    method="POST",
                                )
                                if res.get("status") == "success":
                                    busy_data = res.get("data", {}).get("busy_slots", {})
                                    if not busy_data:
                                        st.info("指定期間に予定は見つかりませんでした。")
                                    else:
                                        e_idx_lim = s_idx + len(time_labels) - 1
                                        for d_str, slots in busy_data.items():
                                            if d_str in st.session_state.df_input.columns:
                                                for t_idx in slots:
                                                    if s_idx <= t_idx <= e_idx_lim:
                                                        t_lbl = time_master[t_idx]
                                                        if t_lbl in st.session_state.df_input.index:
                                                            st.session_state.df_input.loc[t_lbl, d_str] = 3
                                        st.session_state.cal_import_ts = int(time.time() * 1000)
                                        st.success("カレンダーの予定を反映しました！内容を確認して「提出」を押してください。")
                                        time.sleep(0.7)
                                        st.rerun()
                                else:
                                    st.error("取得に失敗しました。GAS側の権限承認が済んでいるか確認してください。")

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        if st.button("📊 みんなの集計を見る →", key=f"bottom_to_graph_{event_id}", use_container_width=True):
            st.session_state.event_view_tab = "graph"
            st.rerun()
        return

    # ========================================
    # 📊 みんなの集計ビュー（結果ファースト・設定は折りたたみに収納）
    # ========================================
    all_res_data = st.session_state.event_responses
    all_names = sorted({r.get("user_name", "不明") for r in all_res_data})

    all_g1, all_g2, all_g3 = set(), set(), set()
    for r in all_res_data:
        for g in str(r.get("group_1", "")).split(","):
            if g.strip(): all_g1.add(g.strip())
        for g in str(r.get("group_2", "")).split(","):
            if g.strip(): all_g2.add(g.strip())
        for g in str(r.get("group_3", "")).split(","):
            if g.strip(): all_g3.add(g.strip())

    all_g1_sorted = sort_groups(list(all_g1), MASTER_G1)
    all_g2_sorted = sort_groups(list(all_g2), MASTER_G2)
    all_g3_sorted = sort_groups(list(all_g3), MASTER_G3)

    req_user_ids = set()
    req_names = []
    allow_maybe_req = True
    duration_slots = 1
    sel_dur_label = ""

    # 設定・絞り込みはスマホでも縦長にならないよう全幅1行の折りたたみ＋内部2タブに整理
    with st.expander("⚙️ 表示設定・絞り込み", expanded=False):
        st_tab_disp, st_tab_flt = st.tabs(["🎛️ 表示・必須メンバー", "🔍 グループ・日時で絞る"])
        with st_tab_disp:
            policy = st.radio(
                "「未定(△)」の計算",
                [0.5, 1.0, 0.0],
                format_func=lambda x: f"{x}人",
                horizontal=True,
                key=f"policy_{event_id}",
            )
            show_my_overlay = st.checkbox("🙋 自分の回答をヒートマップに重ねる", value=False, key=f"overlay_{event_id}")

            if event_type == "time":
                all_dur_opts = [("15分", 1), ("30分", 2), ("45分", 3), ("60分", 4), ("90分", 6), ("120分", 8)]
                valid_dur_opts = [opt for opt in all_dur_opts if opt[1] <= len(time_labels)] or [("15分", 1)]
                def_dur_idx = next((idx for idx, opt in enumerate(valid_dur_opts) if opt[1] == 4), len(valid_dur_opts) - 1)
                sel_dur = st.selectbox(
                    "⏱️ おすすめ候補の所要時間",
                    options=valid_dur_opts,
                    index=def_dur_idx,
                    format_func=lambda x: x[0],
                    key=f"dur_sel_{event_id}",
                )
                duration_slots = sel_dur[1]
                sel_dur_label = sel_dur[0]

            if can_view_details and all_res_data:
                uid_to_name = {str(r.get("user_id")): r.get("user_name", "不明") for r in all_res_data}
                name_to_uid = {}
                for uid, uname in uid_to_name.items():
                    name_to_uid.setdefault(uname, []).append(uid)
                req_names = st.multiselect(
                    "⭐ 必須メンバー指定（全員参加できる枠のみ強調）",
                    options=all_names,
                    key=f"req_members_{event_id}",
                )
                for rn in req_names:
                    req_user_ids.update(name_to_uid.get(rn, []))
                if req_names:
                    allow_maybe_req = st.checkbox("必須メンバーの「△(未定)」も許容する", value=True, key=f"req_maybe_{event_id}")

        with st_tab_flt:
            with st.form("filter_form"):
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    f_g1 = st.multiselect("🚀 プロジェクト", all_g1_sorted)
                    f_g3 = st.multiselect("🏢 委員会", all_g3_sorted)
                    f_g4 = st.multiselect("👑 役職", MASTER_G4_OPTS)
                with f_col2:
                    f_g2 = st.multiselect("🔧 系", all_g2_sorted)
                    f_names = st.multiselect("👤 特定の個人", all_names)

                f_time = st.select_slider("⏰ 表示する時間帯", options=time_labels, value=(time_labels[0], time_labels[-1]))
                if event_type in ["time", "date_timetable"] and len(date_objs) > 1:
                    f_d_col1, f_d_col2 = st.columns(2)
                    with f_d_col1:
                        f_dates = st.date_input("📅 表示する期間", value=(date_objs[0], date_objs[-1]), min_value=date_objs[0], max_value=date_objs[-1])
                    with f_d_col2:
                        f_wdays = st.multiselect("📆 表示する曜日", ["月", "火", "水", "木", "金", "土", "日"], default=["月", "火", "水", "木", "金", "土", "日"])
                else:
                    f_dates = None
                    f_wdays = ["月", "火", "水", "木", "金", "土", "日"]

                st.form_submit_button("✅ 絞り込みを適用", type="primary", use_container_width=True)

        if st.button("🔄 最新の回答を取得する", use_container_width=True, key=f"refresh_grid_{event_id}"):
            invalidate_cache("responses")
            invalidate_cache("events")
            st.rerun()

    filtered_data = filter_responses(all_res_data, f_names, f_g1, f_g2, f_g3, f_g4)
    t_start_idx = time_labels.index(f_time[0])
    t_end_idx = time_labels.index(f_time[1])
    disp_time_labels = time_labels[t_start_idx : t_end_idx + 1]

    disp_date_strs, disp_clean_date_labels, disp_week_breaks, disp_day_kinds = [], [], [], []
    if event_type in ["time", "date_timetable"]:
        d_start = f_dates[0] if isinstance(f_dates, tuple) and len(f_dates) > 0 else date_objs[0]
        d_end = f_dates[1] if isinstance(f_dates, tuple) and len(f_dates) > 1 else date_objs[-1]
        for c, d_obj in enumerate(date_objs):
            wd_str = ["月", "火", "水", "木", "金", "土", "日"][d_obj.weekday()]
            if d_start <= d_obj <= d_end and wd_str in f_wdays:
                disp_date_strs.append(date_strs[c])
                disp_clean_date_labels.append(clean_date_labels[c])
                disp_day_kinds.append(day_kinds[c])
                disp_week_breaks.append(len(disp_date_strs) > 1 and d_obj.weekday() == 0)
    else:
        disp_date_strs = date_strs
        disp_clean_date_labels = clean_date_labels
        disp_week_breaks = week_breaks
        disp_day_kinds = day_kinds

    # アクティブなフィルターがあれば1行チップで分かりやすく通知
    unique_all = len({r.get("user_id") for r in all_res_data})
    unique_filtered = len({r.get("user_id") for r in filtered_data})
    active_tags = []
    if unique_all != unique_filtered:
        active_tags.append(f"回答者 {unique_filtered}/{unique_all}名")
    if req_names:
        active_tags.append(f"⭐ 必須: {', '.join(req_names)}")
    if show_my_overlay:
        active_tags.append("🙋 自分の回答表示中")
    if policy != 0.5:
        active_tags.append(f"△={policy:g}人")
    if active_tags:
        st.markdown(
            f"<div class='active-filter-pill'>🔍 適用中: {' ／ '.join(html_lib.escape(t) for t in active_tags)}</div>",
            unsafe_allow_html=True,
        )

    if not disp_date_strs or not disp_time_labels:
        st.warning("⚠️ 指定された条件に合う日付または時間帯がありません。「⚙️ 表示設定・絞り込み」から条件を広げてください。")
        return

    # ユーザーごとの回答マトリクスとセル詳細を構築
    user_meta = {}
    user_grid = {}
    user_notes = {}
    comments_list = []

    for r in filtered_data:
        uid = str(r.get("user_id"))
        u_groups = [x.strip() for gk in ["group_1", "group_2", "group_3", "group_4"] for x in str(r.get(gk, "")).split(",") if x.strip()]
        is_target = is_in_scope(u_groups, uid, event.get("target_scope", ""))
        badge = "" if is_target else " 💡対象外"
        disp_name = f"{r.get('user_name', '')}{badge}"

        if uid not in user_meta:
            user_meta[uid] = {"disp_name": disp_name, "raw_name": r.get("user_name", "不明")}
            user_grid[uid] = {}
            user_notes[uid] = {}

        if can_view_details and r.get("comment") and r.get("comment").strip():
            entry = {"user": disp_name, "comment": r.get("comment")}
            if entry not in comments_list:
                comments_list.append(entry)

        d_str = r.get("date")
        if d_str not in disp_date_strs:
            continue

        cd = {}
        if r.get("cell_details") and str(r.get("cell_details")).strip() not in ["", "{}"]:
            try:
                cd = json.loads(r["cell_details"])
            except Exception:
                cd = {}

        b = str(r.get("binary_data") or r.get("binary", "")).replace("'", "").zfill(96)
        leg_col = legacy_col_map.get(d_str)

        for disp_r, t_str in enumerate(disp_time_labels):
            orig_r_idx = time_labels.index(t_str)
            if event_type == "time":
                v = int(b[s_idx + orig_r_idx]) if (s_idx + orig_r_idx) < 96 else 0
            elif event_type == "date_timetable":
                if orig_r_idx < len(PERIODS_MASTER):
                    p_start = PERIODS_MASTER[orig_r_idx][2]
                    v = int(b[p_start]) if p_start < 96 else 0
                else:
                    v = int(b[74]) if 74 < 96 else 0
            else:
                bit_pos = TIMETABLE_BIT_MAP.get(orig_r_idx, orig_r_idx)
                v = int(b[bit_pos]) if bit_pos < 96 else 0

            user_grid[uid][(d_str, disp_r)] = v
            c_note = get_cell_note(cd, orig_r_idx, d_str, legacy_col_idx=leg_col, event_type=event_type)
            if c_note:
                user_notes[uid][(d_str, disp_r)] = c_note

    # 自分の回答重ね合わせ用マップ
    my_overlay_grid = {}
    if show_my_overlay and "df_input" in st.session_state:
        df_my = st.session_state.df_input
        for c_idx, d_str in enumerate(disp_date_strs):
            if d_str in df_my.columns:
                for disp_r, t_str in enumerate(disp_time_labels):
                    if t_str in df_my.index:
                        my_overlay_grid[(disp_r, c_idx)] = int(df_my.loc[t_str, d_str])

    effective_dur = min(duration_slots, len(disp_time_labels))
    best_slots = compute_best_slots_grid(
        user_grid=user_grid,
        user_meta=user_meta,
        disp_date_strs=disp_date_strs,
        disp_clean_date_labels=disp_clean_date_labels,
        disp_time_labels=disp_time_labels,
        time_labels=time_labels,
        event_type=event_type,
        policy=policy,
        required_user_ids=req_user_ids,
        allow_maybe_for_required=allow_maybe_req,
        duration_slots=effective_dur,
        top_n=5,
    )

    dur_suffix = f"（{sel_dur_label}枠）" if sel_dur_label else ""
    st.markdown(f"#### 🏆 おすすめ候補{dur_suffix}")
    render_ranking_cards(event, user, best_slots, share_url, can_confirm, key_prefix="grid")

    st.markdown("#### 🟩 時間帯別ヒートマップ")

    z = np.zeros((len(disp_time_labels), len(disp_date_strs)))
    cell_info = {}

    for disp_r in range(len(disp_time_labels)):
        for c_idx, d_str in enumerate(disp_date_strs):
            score = 0.0
            yes_list, maybe_list, no_list, req_fails = [], [], [], []
            for uid, uinfo in user_meta.items():
                v = user_grid[uid].get((d_str, disp_r), 0)
                c_note = user_notes[uid].get((d_str, disp_r), "")
                note_suffix = f" [{c_note}]" if c_note else ""
                name_label = f"{uinfo['disp_name']}{note_suffix}"

                eff_v = 0 if v == 3 else v
                if eff_v == 1:
                    score += 1.0
                    if can_view_details:
                        yes_list.append(name_label)
                elif eff_v == 2:
                    score += policy
                    if can_view_details:
                        maybe_list.append(name_label)
                else:
                    if can_view_details:
                        if v == 3 and not c_note:
                            no_list.append(f"{uinfo['disp_name']} (授業等)")
                        else:
                            no_list.append(name_label)

                if uid in req_user_ids:
                    if eff_v == 0 or (eff_v == 2 and not allow_maybe_req):
                        req_fails.append(uinfo["raw_name"])

            z[disp_r, c_idx] = score
            cell_info[f"{disp_r}_{c_idx}"] = {
                "scoreText": f"{score:g}",
                "yes": yes_list,
                "maybe": maybe_list,
                "no": no_list,
                "isReqBlocked": len(req_fails) > 0,
                "reqFailNames": req_fails,
                "myVal": my_overlay_grid.get((disp_r, c_idx), 0),
            }

    max_z = float(np.max(z)) if np.max(z) > 0 else 1.0
    agg_viewer(
        eventType=event_type,
        isTimeMode=(event_type == "time"),
        dateStrs=disp_date_strs,
        cleanLabels=disp_clean_date_labels,
        weekBreaks=disp_week_breaks,
        dayKinds=disp_day_kinds,
        timeLabels=disp_time_labels,
        z=z.tolist(),
        maxZ=max_z,
        cellInfo=cell_info,
        showMyOverlay=show_my_overlay,
        hasRequiredFilter=bool(req_user_ids),
        canViewDetails=can_view_details,
        defaultCellH=(34 if event_type == "time" else 46),
        key=f"agg_v4_{event_id}",
    )

    if can_view_details:
        with st.expander(f"🙋 回答済みのメンバー ({len(all_names)}名)", expanded=False):
            st.write(", ".join(all_names) if all_names else "まだ回答がありません。")

    if comments_list and can_view_details:
        st.markdown("##### 💬 参加者からのコメント")
        for c in comments_list:
            st.info(f"**{c['user']}**: {c['comment']}")

    render_confirm_editor_expander(event, user, best_slots, can_confirm, key_prefix="grid")

    if not is_closed:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        if st.button("← ✏️ 自分の回答を入力・修正する", key=f"bottom_to_in_{event_id}", use_container_width=True):
            st.session_state.event_view_tab = "input"
            st.rerun()


def render_options_event_view(event, user, can_view_details, can_confirm, is_closed, share_url):
    event_id = event.get("event_id")
    opts = json.loads(event.get("event_options") or event.get("options_name", "[]"))
    active_view = st.session_state.get("event_view_tab", "input")

    if active_view == "input":
        my_ans_row = next((r for r in st.session_state.event_responses if str(r.get("user_id")) == str(user.get("user_id"))), None)
        b_data_val = (my_ans_row.get("binary_data") or my_ans_row.get("binary", "")) if my_ans_row else ""
        my_ans_bin = b_data_val.replace("'", "").zfill(96) if b_data_val else "0" * 96
        my_comment = my_ans_row.get("comment", "") if my_ans_row else ""

        st.markdown("##### 📌 各候補の参加可否を選んでください")
        raw = options_editor(
            options=opts,
            myAnsBin=my_ans_bin,
            myComment=my_comment,
            eventId=event_id,
            isClosed=is_closed,
            saveTs=st.session_state.get("last_saved_ts", 0),
            key=f"opt_editor_v2_{event_id}",
        )

        if raw and isinstance(raw, dict) and raw.get("trigger_save") and st.session_state.get("last_saved_ts") != raw.get("ts"):
            st.session_state.last_saved_ts = raw.get("ts")
            b_str = raw.get("binary", "0" * 96).ljust(96, "0")[:96]
            payload = {
                "event_id": event_id,
                "user_id": user.get("user_id"),
                "comment": raw.get("comment", ""),
                "responses": [{"date": "options", "binary_data": b_str}],
            }
            if save_response_hybrid(payload):
                st.session_state.save_success_msg = "回答を保存しました！みんなの集計を確認しましょう👀"
                st.session_state.event_view_tab = "graph"
                st.rerun()

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("📊 みんなの集計を見る →", key=f"opt_bottom_to_graph_{event_id}", use_container_width=True):
            st.session_state.event_view_tab = "graph"
            st.rerun()
        return

    # ========================================
    # 📊 予定候補 集計ビュー（結果ファースト・設定は折りたたみに収納）
    # ========================================
    all_res_data = st.session_state.event_responses
    all_names = sorted({r.get("user_name", "不明") for r in all_res_data})

    all_g1, all_g2, all_g3 = set(), set(), set()
    for r in all_res_data:
        for g in str(r.get("group_1", "")).split(","):
            if g.strip(): all_g1.add(g.strip())
        for g in str(r.get("group_2", "")).split(","):
            if g.strip(): all_g2.add(g.strip())
        for g in str(r.get("group_3", "")).split(","):
            if g.strip(): all_g3.add(g.strip())

    all_g1_sorted = sort_groups(list(all_g1), MASTER_G1)
    all_g2_sorted = sort_groups(list(all_g2), MASTER_G2)
    all_g3_sorted = sort_groups(list(all_g3), MASTER_G3)

    req_user_ids = set()
    req_names = []
    allow_maybe_req = True

    with st.expander("⚙️ 表示設定・絞り込み", expanded=False):
        st_opt_disp, st_opt_flt = st.tabs(["🎛️ 表示・必須メンバー", "🔍 グループで絞る"])
        with st_opt_disp:
            policy = st.radio(
                "「未定(△)」の計算",
                [0.5, 1.0, 0.0],
                format_func=lambda x: f"{x}人",
                horizontal=True,
                key=f"opt_policy_{event_id}",
            )
            if can_view_details and all_res_data:
                uid_to_name = {str(r.get("user_id")): r.get("user_name", "不明") for r in all_res_data}
                name_to_uid = {}
                for uid, uname in uid_to_name.items():
                    name_to_uid.setdefault(uname, []).append(uid)
                req_names = st.multiselect("⭐ 必須メンバー指定", options=all_names, key=f"opt_req_{event_id}")
                for rn in req_names:
                    req_user_ids.update(name_to_uid.get(rn, []))
                if req_names:
                    allow_maybe_req = st.checkbox("必須メンバーの「△(未定)」も許容する", value=True, key=f"opt_req_maybe_{event_id}")

        with st_opt_flt:
            with st.form("opt_filter_form"):
                f_col1, f_col2 = st.columns(2)
                with f_col1:
                    f_g1 = st.multiselect("🚀 プロジェクト", all_g1_sorted, key="f2_g1")
                    f_g3 = st.multiselect("🏢 委員会", all_g3_sorted, key="f2_g3")
                    f_g4 = st.multiselect("👑 役職", MASTER_G4_OPTS, key="f2_g4")
                with f_col2:
                    f_g2 = st.multiselect("🔧 系", all_g2_sorted, key="f2_g2")
                    f_names = st.multiselect("👤 特定の個人", all_names, key="f2_names")
                st.form_submit_button("✅ 絞り込みを適用", type="primary", use_container_width=True)

        if st.button("🔄 最新の回答を取得する", use_container_width=True, key=f"opt_refresh_{event_id}"):
            invalidate_cache("responses")
            invalidate_cache("events")
            st.rerun()

    filtered_data = filter_responses(all_res_data, f_names, f_g1, f_g2, f_g3, f_g4)
    unique_all = len({r.get("user_id") for r in all_res_data})
    unique_filtered = len({r.get("user_id") for r in filtered_data})
    active_tags = []
    if unique_all != unique_filtered:
        active_tags.append(f"回答者 {unique_filtered}/{unique_all}名")
    if req_names:
        active_tags.append(f"⭐ 必須: {', '.join(req_names)}")
    if policy != 0.5:
        active_tags.append(f"△={policy:g}人")
    if active_tags:
        st.markdown(
            f"<div class='active-filter-pill'>🔍 適用中: {' ／ '.join(html_lib.escape(t) for t in active_tags)}</div>",
            unsafe_allow_html=True,
        )

    best_slots = compute_best_slots_options(
        opts=opts,
        filtered_data=filtered_data,
        policy=policy,
        required_user_ids=req_user_ids,
        allow_maybe_for_required=allow_maybe_req,
        top_n=5,
    )
    st.markdown("#### 🏆 おすすめ候補")
    render_ranking_cards(event, user, best_slots, share_url, can_confirm, key_prefix="opt")

    st.markdown("#### 📊 各候補の詳細集計")

    my_ans_row = next((r for r in all_res_data if str(r.get("user_id")) == str(user.get("user_id"))), None)
    my_bin = ((my_ans_row.get("binary_data") or my_ans_row.get("binary", "")) if my_ans_row else "").replace("'", "").zfill(96)

    counts = [0.0] * len(opts)
    details = [{"yes": [], "maybe": [], "no": [], "req_ng": False} for _ in range(len(opts))]
    comments_list = []

    for r in filtered_data:
        uid = str(r.get("user_id"))
        u_groups = [x.strip() for gk in ["group_1", "group_2", "group_3", "group_4"] for x in str(r.get(gk, "")).split(",") if x.strip()]
        is_target = is_in_scope(u_groups, uid, event.get("target_scope", ""))
        badge = "" if is_target else " 💡対象外"
        disp_name = f"{r.get('user_name', '')}{badge}"

        if can_view_details and r.get("comment") and r.get("comment").strip():
            entry = {"user": disp_name, "comment": r.get("comment")}
            if entry not in comments_list:
                comments_list.append(entry)

        b = str(r.get("binary_data") or r.get("binary", "")).replace("'", "").zfill(96)
        for i in range(len(opts)):
            v = int(b[i]) if i < len(b) else 0
            if v == 1:
                counts[i] += 1.0
                if can_view_details:
                    details[i]["yes"].append(disp_name)
            elif v == 2:
                counts[i] += policy
                if can_view_details:
                    details[i]["maybe"].append(disp_name)
            else:
                if can_view_details:
                    details[i]["no"].append(disp_name)
            if uid in req_user_ids and (v == 0 or (v == 2 and not allow_maybe_req)):
                details[i]["req_ng"] = True

    max_c = max(counts) if counts and max(counts) > 0 else 1
    for i, opt in enumerate(opts):
        count = counts[i]
        ratio = count / max_c if max_c > 0 else 0
        bar_width = f"{ratio * 100}%"
        my_v = int(my_bin[i]) if (my_ans_row and i < len(my_bin)) else 0
        my_tag = " <span style='font-size:11px; background:#e3f2fd; color:#1565c0; padding:2px 6px; border-radius:999px;'>自分:◯</span>" if my_v == 1 else (
            " <span style='font-size:11px; background:#fff8e1; color:#92400e; padding:2px 6px; border-radius:999px;'>自分:△</span>" if my_v == 2 else ""
        )
        req_tag = " <span style='font-size:11px; background:#fef2f2; color:#b91c1c; padding:2px 6px; border-radius:999px;'>必須NG</span>" if details[i]["req_ng"] else ""
        card_opacity = "opacity:0.65;" if details[i]["req_ng"] else ""

        st.markdown(_compact_html(f"""
        <div style="background:#fff; border:1px solid #e2e8f0; border-radius:12px; padding:13px 14px; margin-bottom:5px; box-shadow:0 2px 6px rgba(15,23,42,0.04); {card_opacity}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
                <div style="font-size:15px; font-weight:bold; color:#0f172a;">📅 {html_lib.escape(opt)}{my_tag}{req_tag}</div>
                <div style="font-size:14px; font-weight:bold; color:#047857;">参加目安: {count:g} 人</div>
            </div>
            <div style="width:100%; background:#f1f5f9; border-radius:8px; height:12px; overflow:hidden;">
                <div style="width:{bar_width}; background:linear-gradient(90deg, #34d399, #10b981); height:100%; border-radius:8px;"></div>
            </div>
        </div>
        """), unsafe_allow_html=True)

        if can_view_details:
            with st.expander("👥 参加者内訳を見る"):
                c_yes, c_maybe, c_no = st.columns(3)
                with c_yes:
                    st.markdown("<span style='color:#166534; font-weight:bold;'>◯ 参加可能</span>", unsafe_allow_html=True)
                    if details[i]["yes"]:
                        st.code("\n".join(details[i]["yes"]), language="text")
                    else:
                        st.write("なし")
                with c_maybe:
                    st.markdown("<span style='color:#d97706; font-weight:bold;'>△ 未定</span>", unsafe_allow_html=True)
                    st.markdown("<br>".join([f"△ {html_lib.escape(n)}" for n in details[i]["maybe"]]) if details[i]["maybe"] else "なし", unsafe_allow_html=True)
                with c_no:
                    st.markdown("<span style='color:#64748b; font-weight:bold;'>× 不可</span>", unsafe_allow_html=True)
                    st.markdown("<br>".join([f"× {html_lib.escape(n)}" for n in details[i]["no"]]) if details[i]["no"] else "なし", unsafe_allow_html=True)

    if can_view_details:
        with st.expander(f"🙋 回答済みのメンバー ({len(all_names)}名)", expanded=False):
            st.write(", ".join(all_names) if all_names else "まだ回答がありません。")

    if comments_list and can_view_details:
        st.markdown("##### 💬 参加者からのコメント")
        for c in comments_list:
            st.info(f"**{c['user']}**: {c['comment']}")

    render_confirm_editor_expander(event, user, best_slots, can_confirm, key_prefix="opt")

    if not is_closed:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        if st.button("← ✏️ 自分の回答を入力・修正する", key=f"opt_bottom_to_in_{event_id}", use_container_width=True):
            st.session_state.event_view_tab = "input"
            st.rerun()


def render_event_detail_view(user, events, user_map_fs, current_ev_id):
    event = next((ev for ev in events if ev["event_id"] == current_ev_id), None)
    if not event:
        st.error("指定されたイベントが見つかりません。")
        if st.button("🏠 ダッシュボードに戻る"):
            st.session_state.target_ev_id = ""
            st.rerun()
        return

    st.session_state.event_responses = fetch_responses_for_event(current_ev_id, user_map_fs)
    share_url = f"{APP_BASE_URL}?event={current_ev_id}"

    st.markdown('<div class="sss-top-action-marker"></div>', unsafe_allow_html=True)
    c_top1, c_top2 = st.columns([1, 1.8])
    with c_top1:
        if st.button("🔙 戻る", type="secondary", use_container_width=True):
            st.session_state.target_ev_id = ""
            st.rerun()
    with c_top2:
        render_copy_button(
            share_url,
            btn_label="🔗 URLコピー",
            share_title=event.get("title", "SSScheduler"),
            share_url=share_url,
            key_suffix=f"ev_share_{current_ev_id}",
            full_width=True,
        )

    is_closed = event.get("status") == "closed"
    is_private_event = event.get("is_private", False)
    can_view_details = not (is_private_event and user.get("role") not in ["admin", "top_admin"])
    can_confirm = (
        user.get("role") in ["admin", "top_admin"]
        or str(event.get("created_by", "")) == str(user.get("user_id", ""))
    )

    # タイトル＋ステータスを1枚のすっきりしたヒーローカードに集約
    ev_close_time = event.get("deadline") or event.get("close_time", "")
    pills = []
    if event.get("is_answered"):
        pills.append("<span class='hero-pill pill-answered'>✅ 回答済（修正可）</span>")
    elif not is_closed:
        pills.append("<span class='hero-pill pill-unanswered'>📝 未回答</span>")
    if is_closed:
        pills.append("<span class='hero-pill pill-closed'>🔒 締切済</span>")
    elif ev_close_time:
        pills.append(f"<span class='hero-pill pill-deadline'>⏳ 締切 {html_lib.escape(format_deadline_jp(ev_close_time))}</span>")
    if is_private_event:
        pills.append("<span class='hero-pill pill-private'>🤫 プライベート</span>")
    if event.get("is_out_of_scope"):
        pills.append("<span class='hero-pill pill-outscope'>⚠️ 対象外イベント（有志参加）</span>")

    st.markdown(
        _compact_html(f"""
        <div class="event-hero">
            <div class="event-hero-title">{html_lib.escape(event.get('title', ''))}</div>
            <div class="event-hero-pills">{''.join(pills)}</div>
        </div>
        """),
        unsafe_allow_html=True,
    )

    # 開催日時確定バナー（主催者・管理者用の取り消しメニュー付き）
    render_confirmed_banner(event, share_url, can_confirm=can_confirm)

    if event.get("description"):
        desc_html = event["description"].replace("\n", "<br>")
        st.markdown(f"<div class='event-desc'>{desc_html}</div>", unsafe_allow_html=True)

    # イベント開いた直後の初期タブ設定
    if st.session_state.get("last_opened_ev_id") != current_ev_id:
        st.session_state.last_opened_ev_id = current_ev_id
        st.session_state.event_view_tab = "graph" if is_closed else "input"

    respondent_count = len({r.get("user_id") for r in st.session_state.event_responses})
    cur_tab = st.session_state.get("event_view_tab", "input")

    # 大きく分かりやすいセグメントスイッチャー（入力 ⇔ 集計）
    st.markdown('<div class="sss-tab-switcher-marker"></div>', unsafe_allow_html=True)
    sw_col1, sw_col2 = st.columns(2)
    in_label = "✏️ 回答を修正 (済✓)" if event.get("is_answered") else "✏️ 予定を入力する"
    if is_closed:
        in_label = "🔒 自分の回答を見る"
    gr_label = f"📊 みんなの集計 ({respondent_count}名)"

    with sw_col1:
        if st.button(in_label, key=f"sw_in_{current_ev_id}", use_container_width=True, type=("primary" if cur_tab == "input" else "secondary")):
            st.session_state.event_view_tab = "input"
            st.rerun()
    with sw_col2:
        if st.button(gr_label, key=f"sw_gr_{current_ev_id}", use_container_width=True, type=("primary" if cur_tab == "graph" else "secondary")):
            st.session_state.event_view_tab = "graph"
            st.rerun()

    event_type = event.get("event_type") or event.get("type", "time")
    if event_type in ["time", "timetable", "date_timetable"]:
        render_grid_event_view(event, user, can_view_details, can_confirm, is_closed, share_url)
    elif event_type == "options":
        render_options_event_view(event, user, can_view_details, can_confirm, is_closed, share_url)


# ==========================================
# メインエントリーポイント
# ==========================================
def main():
    if "app_initialized" not in st.session_state:
        st.session_state.app_initialized = True
    if "auth" not in st.session_state:
        st.session_state.auth = None
    if "current_menu" not in st.session_state:
        st.session_state.current_menu = "dashboard"

    if st.session_state.get("save_success_msg"):
        st.toast(st.session_state.save_success_msg, icon="✅")
        st.session_state.save_success_msg = None

    if "event" in st.query_params:
        st.session_state.jump_to_event = st.query_params["event"]
        st.query_params.clear()

    # ペンディング中のlocalStorage書き込み/クリアを処理（非表示iframe）
    if st.session_state.get("pending_auth_clear"):
        auth_storage(mode="clear", opId=st.session_state.get("auth_op_id", "clr"), key="auth_storage_write")
        st.session_state.pending_auth_clear = False
    elif st.session_state.get("pending_auth_save"):
        auth_storage(
            mode="write",
            payload=st.session_state.pending_auth_save,
            opId=st.session_state.get("auth_op_id", "sav"),
            key="auth_storage_write",
        )
        st.session_state.pending_auth_save = None

    if not st.session_state.auth:
        render_login_view()
        return

    user = st.session_state.auth
    if "jump_to_event" in st.session_state:
        st.session_state.target_ev_id = st.session_state.jump_to_event
        st.session_state.current_menu = "dashboard"
        del st.session_state.jump_to_event

    current_ev_id = st.session_state.get("target_ev_id", "")
    _, events, user_map_fs = get_app_data_from_firestore(user, target_ev_id=current_ev_id)

    unanswered_events = []
    seen_ids = set()
    for ev in events:
        eid = ev.get("event_id")
        if not ev.get("is_answered") and ev.get("status") == "open" and eid not in seen_ids:
            unanswered_events.append(ev)
            seen_ids.add(eid)

    render_top_navigation(user, unanswered_events)

    cur_menu = st.session_state.get("current_menu", "dashboard")
    if cur_menu == "profile":
        render_profile_view(user)
    elif cur_menu == "timetable":
        render_timetable_settings_view(user)
    elif cur_menu == "guide":
        render_guide_view()
    elif cur_menu == "create" and user.get("role") in ["user", "admin", "top_admin"]:
        render_create_event_view(user)
    elif cur_menu == "admin" and user.get("role") in ["admin", "top_admin"]:
        render_admin_view(user)
    else:
        if not events:
            st.info("現在表示できるイベントはありません。")
            return
        if not current_ev_id:
            render_dashboard_view(events)
        else:
            render_event_detail_view(user, events, user_map_fs, current_ev_id)


if __name__ == "__main__":
    main()
