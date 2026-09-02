import os
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from textwrap import dedent

import requests
import streamlit as st
from dotenv import load_dotenv

try:
    from frontend.handsfree_recorder import render_handsfree_recorder
except ModuleNotFoundError as error:
    if error.name != "frontend":
        raise
    from handsfree_recorder import render_handsfree_recorder


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# FASTAPI CONFIG
# ============================================================

def get_fastapi_url():

    env_url = os.getenv(
        "FASTAPI_URL",
        "",
    ).strip()

    if env_url:
        return env_url.rstrip("/")

    try:

        secret_url = st.secrets.get(
            "FASTAPI_URL",
            "",
        )

        if secret_url:
            return str(secret_url).rstrip("/")

    except Exception:
        pass

    return "http://127.0.0.1:8000"


FASTAPI_URL = get_fastapi_url()


MEDICAL_SCRIBE_API_KEY = os.getenv(
    "MEDICAL_SCRIBE_API_KEY",
    "",
).strip()


ADMIN_API_KEY = os.getenv(
    "ADMIN_API_KEY",
    "",
).strip()


def api_headers():

    access_token = st.session_state.get(
        "access_token"
    )

    if not access_token:
        return {}

    return {
        "Authorization": (
            f"Bearer {access_token}"
        )
    }


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="MediNote",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

SESSION_DEFAULTS = {

    "authenticated": False,

    "access_token": None,

    "username": None,

    "user_role": None,

    "record_id": None,

    "patient_name": None,

    "patient_id": None,

    "session_id": None,

    "transcript": "",

    "clinical_data": {},

    "date": None,

    "time": None,

    "pending_handsfree_audio": None,

    "last_audio_name": None,

    "edit_mode": False,

    "last_activity_time": None,

    "workspace_view": "consultation",
}


for key, value in SESSION_DEFAULTS.items():

    if key not in st.session_state:

        st.session_state[key] = value


# ============================================================
# SESSION INACTIVITY SECURITY
# ============================================================

SESSION_TIMEOUT_MINUTES = 30


def current_utc_timestamp():

    return datetime.now(
        timezone.utc
    ).timestamp()


def update_activity_time():

    st.session_state[
        "last_activity_time"
    ] = current_utc_timestamp()


def check_inactivity_timeout():

    if not st.session_state.get(
        "authenticated"
    ):
        return

    last_activity_time = (
        st.session_state.get(
            "last_activity_time"
        )
    )

    if last_activity_time is None:

        update_activity_time()
        return

    elapsed_seconds = (
        current_utc_timestamp()
        - last_activity_time
    )

    timeout_seconds = (
        SESSION_TIMEOUT_MINUTES
        * 60
    )

    if elapsed_seconds >= timeout_seconds:

        clear_auth_session()
        st.session_state["last_activity_time"] = None

        st.warning(
            "Session ended due to inactivity. "
            "Please login again."
        )

        st.rerun()


# ============================================================
# RESET CONSULTATION
# ============================================================

def reset_consultation():

    auth_keys = {
        "authenticated",
        "access_token",
        "username",
        "user_role",
    }

    for key, value in SESSION_DEFAULTS.items():

        if key not in auth_keys:

            st.session_state[key] = value


# ============================================================
# RECORD LOADER
# ============================================================

def load_record(record):

    st.session_state.record_id = record.get(
        "id"
    )

    st.session_state.patient_name = record.get(
        "patient_name"
    )

    st.session_state.patient_id = record.get(
        "patient_id"
    )

    st.session_state.transcript = record.get(
        "transcript",
        "",
    )

    st.session_state.date = record.get(
        "date"
    )

    st.session_state.time = record.get(
        "time"
    )

    st.session_state.clinical_data = {

        "patient_name": record.get(
            "patient_name"
        ),

        "chief_complaint": record.get(
            "chief_complaint"
        ),

        "symptoms": record.get(
            "symptoms",
            [],
        ),

        "vitals": record.get(
            "vitals",
            {},
        ),

        "diagnosis": record.get(
            "diagnosis"
        ),

        "medications": record.get(
            "medications",
            [],
        ),

        "recommended_tests": record.get(
            "recommended_tests",
            [],
        ),

        "doctor_instructions": record.get(
            "doctor_instructions",
            [],
        ),

        "follow_up": record.get(
            "follow_up"
        ),
    }



# ============================================================
# DOCTOR CORRECTION HELPERS
# ============================================================

def list_to_lines(values):

    if not values:
        return ""

    return "\n".join(
        str(value)
        for value in values
        if value
    )


def lines_to_list(value):

    return [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]


def medications_to_lines(
    medications,
):

    lines = []

    for medicine in medications or []:

        if isinstance(
            medicine,
            dict,
        ):

            line = " | ".join(
                [
                    str(
                        medicine.get(
                            "name"
                        )
                        or ""
                    ),
                    str(
                        medicine.get(
                            "dosage"
                        )
                        or ""
                    ),
                    str(
                        medicine.get(
                            "frequency"
                        )
                        or ""
                    ),
                    str(
                        medicine.get(
                            "duration"
                        )
                        or ""
                    ),
                    str(
                        medicine.get(
                            "route"
                        )
                        or ""
                    ),
                ]
            )

            lines.append(
                line
            )

        elif medicine:

            lines.append(
                str(medicine)
            )

    return "\n".join(
        lines
    )


def lines_to_medications(
    value,
):

    medications = []

    for line in value.splitlines():

        line = line.strip()

        if not line:
            continue

        parts = [
            part.strip()
            for part in line.split(
                "|"
            )
        ]

        while len(parts) < 5:
            parts.append("")

        medications.append(
            {
                "name": parts[0],
                "dosage": parts[1],
                "frequency": parts[2],
                "duration": parts[3],
                "route": parts[4],
            }
        )

    return medications


# ============================================================
# BACKEND HEALTH CHECK
# ============================================================

def get_backend_health():

    try:

        response = requests.get(
            f"{FASTAPI_URL}/health",
            timeout=4,
        )

        if response.status_code == 200:

            return response.json()

    except Exception:
        pass

    return None


# ============================================================
# API ERROR
# ============================================================

def clear_auth_session():

    st.session_state[
        "authenticated"
    ] = False

    st.session_state[
        "access_token"
    ] = None

    st.session_state[
        "username"
    ] = None

    st.session_state[
        "user_role"
    ] = None


def show_api_error(response):

    if response.status_code == 401:

        clear_auth_session()

        st.error(
            "Session expired. Please login again."
        )

        st.rerun()

    try:

        data = response.json()

        detail = data.get(
            "detail",
            "Request failed.",
        )

    except Exception:

        detail = (
            "Backend request failed."
        )

    st.error(detail)




# ============================================================
# STYLING
# ============================================================

st.markdown(
    dedent("""
    <style>

    .stApp {
        background:
            linear-gradient(
                180deg,
                #f8fafc 0%,
                #f1f5f9 100%
            );
    }

    .block-container {
        max-width: 1500px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }

    .main-header {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 20px 24px;
        margin-bottom: 18px;
        box-shadow:
            0 4px 18px rgba(
                15,
                23,
                42,
                0.05
            );
    }

    .hero-card {
        background:
            linear-gradient(
                135deg,
                #ffffff,
                #f8fafc
            );
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 24px;
        margin-bottom: 18px;
    }

    .medical-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 15px;
        box-shadow:
            0 2px 12px rgba(
                15,
                23,
                42,
                0.04
            );
    }

    .status-online {
        display: inline-block;
        padding: 7px 13px;
        border-radius: 999px;
        background: #dcfce7;
        color: #166534;
        font-weight: 600;
        font-size: 13px;
    }

    .status-offline {
        display: inline-block;
        padding: 7px 13px;
        border-radius: 999px;
        background: #fee2e2;
        color: #991b1b;
        font-weight: 600;
        font-size: 13px;
    }

    .section-title {
        font-size: 18px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 8px;
    }

    .small-muted {
        color: #64748b;
        font-size: 13px;
    }

    .result-label {
        color: #64748b;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: .04em;
    }

    .result-value {
        color: #0f172a;
        font-size: 15px;
        margin-top: 4px;
    }

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #e2e8f0;
        padding: 12px;
        border-radius: 12px;
    }

    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
    }

    textarea {
        border-radius: 10px !important;
    }

    
/* Analyze & Save Consultation primary button */
div.stButton > button[kind="primary"] {
    background-color: #2563EB !important;
    color: #FFFFFF !important;
    border: 1px solid #2563EB !important;
    font-weight: 700 !important;
}

div.stButton > button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
    color: #FFFFFF !important;
    border-color: #1D4ED8 !important;
}

div.stButton > button[kind="primary"]:disabled {
    background-color: #94A3B8 !important;
    color: #FFFFFF !important;
    opacity: 0.85 !important;
}

</style>
    """),
    unsafe_allow_html=True,
)


# Production clinical workspace theme.
st.markdown(
    dedent("""
    <style>
    :root {
        --mn-bg:#f3f6f9; --mn-surface:#ffffff; --mn-soft:#f8fafb;
        --mn-ink:#142536; --mn-muted:#687b8e; --mn-border:#dfe7ec;
        --mn-teal:#13877f; --mn-teal-dark:#0c6e68; --mn-teal-soft:#e8f6f4;
        --mn-danger:#c94d58; --mn-shadow:0 8px 24px rgba(25,49,72,.055);
    }
    .stApp { color:var(--mn-ink); background:var(--mn-bg); }
    .block-container { max-width:1400px; padding:1.65rem 2.25rem 2.5rem; }
    header[data-testid="stHeader"] { background:rgba(243,246,249,.88); backdrop-filter:blur(12px); }
    #MainMenu, footer { visibility:hidden; }

    section[data-testid="stSidebar"] {
        width:292px!important; background:#0b1f33;
        border-right:1px solid rgba(255,255,255,.08);
    }
    section[data-testid="stSidebar"] > div:first-child { padding:1.15rem .85rem 1rem; }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        background:linear-gradient(145deg,rgba(18,166,153,.12),transparent 38%),#0b1f33;
    }
    .mn-brand { display:flex; align-items:center; gap:12px; padding:6px 8px 18px;
        border-bottom:1px solid rgba(255,255,255,.09); margin-bottom:18px; }
    .mn-logo { display:grid; place-items:center; width:42px; height:42px; flex:0 0 42px;
        border-radius:10px; background:#19a79b; color:#fff; font-size:24px; font-weight:700;
        box-shadow:0 8px 20px rgba(25,167,155,.22); }
    .mn-brand-name { color:#fff; font-size:1.18rem; line-height:1.2; font-weight:750; }
    .mn-brand-tag { color:#91a6bc; font-size:.76rem; margin-top:3px; }
    .mn-nav-label { color:#7089a1; font-size:.68rem; font-weight:700; letter-spacing:.08em;
        padding:5px 11px 7px; }
    .mn-profile { display:flex; align-items:center; gap:11px; padding:12px; margin:18px 3px 10px;
        border:1px solid rgba(255,255,255,.09); border-radius:8px; background:rgba(255,255,255,.045); }
    .mn-avatar { display:grid; place-items:center; width:36px; height:36px; flex:0 0 36px;
        border-radius:50%; background:#e9f7f5; color:#087f75; font-size:.76rem; font-weight:800; }
    .mn-profile-name { color:#f7fbff; font-size:.86rem; font-weight:650; line-height:1.2; }
    .mn-profile-role { color:#8298ae; font-size:.71rem; margin-top:3px; text-transform:capitalize; }
    .mn-health { display:flex; align-items:center; gap:8px; color:#8fa5b9; font-size:.73rem;
        padding:4px 10px 10px; }
    .mn-health-dot { width:7px; height:7px; border-radius:50%; background:#35c98f;
        box-shadow:0 0 0 3px rgba(53,201,143,.12); }
    .mn-health-dot.offline { background:#df6670; box-shadow:0 0 0 3px rgba(223,102,112,.12); }
    section[data-testid="stSidebar"] .stButton button { width:100%; min-height:43px; justify-content:flex-start;
        padding:.5rem .75rem; border:1px solid transparent; border-radius:8px; background:transparent;
        color:#b9c8d7; font-size:.86rem; font-weight:550; }
    section[data-testid="stSidebar"] .stButton button:hover { color:#fff; background:rgba(255,255,255,.065);
        border-color:rgba(255,255,255,.05); transform:none; box-shadow:none; }
    section[data-testid="stSidebar"] .stButton button[kind="primary"] { color:#fff; background:#147f79;
        border-color:#27968f; box-shadow:0 5px 14px rgba(0,0,0,.16); }
    section[data-testid="stSidebar"] div[data-testid="stButton"] { margin-bottom:2px; }
    .mn-sidebar-link { display:flex; align-items:center; min-height:43px; padding:11px 12px; margin-bottom:2px;
        border:1px solid transparent; border-radius:8px; color:#b9c8d7!important; font-size:.86rem;
        font-weight:550; text-decoration:none!important; }
    .mn-sidebar-link:hover { color:#fff!important; background:rgba(255,255,255,.065); }

    .mn-page-header { display:flex; align-items:flex-start; justify-content:space-between; gap:24px;
        padding:2px 0 20px; margin-bottom:20px; border-bottom:1px solid var(--mn-border); }
    .mn-eyebrow { color:var(--mn-teal-dark); font-size:.7rem; font-weight:800; letter-spacing:.08em;
        text-transform:uppercase; margin-bottom:6px; }
    .mn-title { color:var(--mn-ink); font-size:1.72rem; line-height:1.2; font-weight:760; }
    .mn-subtitle { max-width:690px; color:var(--mn-muted); font-size:.88rem; margin-top:5px; }
    .mn-status { display:inline-flex; align-items:center; gap:7px; flex:0 0 auto; padding:7px 10px;
        border:1px solid #c7ead7; border-radius:999px; color:#176b50; background:#eaf7f0;
        font-size:.72rem; font-weight:700; }
    .mn-status.offline { color:#a33c46; background:#fcedee; border-color:#f0cbd0; }
    .mn-status i { width:7px; height:7px; border-radius:50%; background:#27a96f; }
    .mn-status.offline i { background:#d85d68; }
    .mn-record-state { display:flex; align-items:center; gap:11px; min-height:52px; padding:10px 13px;
        margin:10px 0 12px; border:1px solid #d7e5e4; border-radius:8px; background:#f5faf9; }
    .mn-record-dot { width:11px; height:11px; flex:0 0 11px; border-radius:50%; background:#79909f;
        box-shadow:0 0 0 4px rgba(121,144,159,.12); }
    .mn-record-state.recording { color:#9f2f3a; border-color:#efc8cd; background:#fff4f5; }
    .mn-record-state.recording .mn-record-dot { background:#db4654;
        box-shadow:0 0 0 5px rgba(219,70,84,.14); animation:mn-pulse 1.25s ease-out infinite; }
    .mn-record-state.ready { color:#176b50; border-color:#c7ead7; background:#eef9f3; }
    .mn-record-state.ready .mn-record-dot { background:#27a96f; box-shadow:0 0 0 4px rgba(39,169,111,.13); }
    .mn-record-copy { min-width:0; }
    .mn-record-label { color:inherit; font-size:.76rem; line-height:1.15; font-weight:800; text-transform:uppercase; }
    .mn-record-detail { color:var(--mn-muted); font-size:.72rem; margin-top:3px; }
    @keyframes mn-pulse { 0% { box-shadow:0 0 0 0 rgba(219,70,84,.38); }
        70% { box-shadow:0 0 0 10px rgba(219,70,84,0); } 100% { box-shadow:0 0 0 0 rgba(219,70,84,0); } }
    div[data-testid="stAudioInput"] { padding:14px; border:1px solid var(--mn-border); border-radius:8px;
        background:var(--mn-soft); }
    .main-header { display:none; }
    .hero-card { display:none; }

    .section-title { color:var(--mn-ink)!important; font-size:1rem; font-weight:720;
        margin:4px 0 12px; }
    h1,h2,h3,h4,p,label,span { letter-spacing:0; }
    h2 { color:var(--mn-ink); font-size:1.4rem!important; }
    h3 { color:var(--mn-ink); font-size:1.03rem!important; font-weight:720!important; }
    h4 { color:var(--mn-ink); font-size:.94rem!important; }
    div[data-testid="stCaptionContainer"] { color:var(--mn-muted); }
    hr { border-color:var(--mn-border)!important; margin:1.4rem 0!important; }

    div[data-testid="stVerticalBlockBorderWrapper"] { background:var(--mn-surface); border:1px solid var(--mn-border);
        border-radius:8px; box-shadow:var(--mn-shadow); }
    div[data-testid="stMetric"] { min-height:100px; padding:16px 17px; border:1px solid var(--mn-border);
        border-radius:8px; background:var(--mn-surface); box-shadow:var(--mn-shadow); }
    div[data-testid="stMetricLabel"] { color:var(--mn-muted); font-size:.76rem; font-weight:650; }
    div[data-testid="stMetricValue"] { color:var(--mn-ink); font-size:1.18rem; font-weight:750; }

    .stButton>button, .stFormSubmitButton>button { min-height:42px; border-radius:8px; border-color:#ccd8df;
        color:#294052; background:#fff; font-weight:650; transition:transform 120ms ease,box-shadow 120ms ease; }
    .stButton>button:hover, .stFormSubmitButton>button:hover { color:var(--mn-teal-dark); border-color:#8dbab6;
        box-shadow:0 5px 14px rgba(25,49,72,.08); transform:translateY(-1px); }
    .stButton>button[kind="primary"], .stFormSubmitButton>button[kind="primary"] { color:#fff!important;
        border-color:var(--mn-teal-dark)!important; background:var(--mn-teal)!important;
        box-shadow:0 5px 14px rgba(19,135,127,.18); }
    .stButton>button[kind="primary"]:hover, .stFormSubmitButton>button[kind="primary"]:hover {
        color:#fff!important; background:var(--mn-teal-dark)!important; }

    div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:4px; padding:4px; border:1px solid var(--mn-border);
        border-radius:8px; background:#eaf0f3; overflow-x:auto; }
    div[data-testid="stTabs"] button { min-height:38px; padding:7px 13px; border-radius:6px; white-space:nowrap; }
    div[data-testid="stTabs"] button[aria-selected="true"] { color:var(--mn-teal-dark); background:#fff;
        box-shadow:0 2px 7px rgba(25,49,72,.08); }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display:none; }
    div[data-testid="stFileUploaderDropzone"] { min-height:126px; padding:1.15rem; border:1px dashed #a9c7c4;
        border-radius:8px!important; background:#f6fbfa; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"]>div {
        border-radius:8px!important; border-color:#ccd8df; background:#fff; }
    .stTextInput input { min-height:44px; }
    div[data-testid="stExpander"] { border:1px solid var(--mn-border); border-radius:8px!important;
        background:var(--mn-surface); box-shadow:0 4px 14px rgba(25,49,72,.035); }
    div[data-testid="stForm"] { padding:1.35rem; border:1px solid var(--mn-border); border-radius:8px;
        background:var(--mn-surface); box-shadow:var(--mn-shadow); }
    div[data-testid="stAlert"] { border-radius:8px; border-width:1px; }
    audio { width:100%; }

    .mn-login { max-width:520px; margin:46px auto 22px; text-align:center; }
    .mn-login-mark { display:grid; place-items:center; width:48px; height:48px; margin:0 auto 14px;
        border-radius:10px; color:#fff; background:var(--mn-teal); font-size:26px; font-weight:750;
        box-shadow:0 9px 22px rgba(19,135,127,.2); }
    .mn-login-title { color:var(--mn-ink); font-size:1.7rem; font-weight:760; }
    .mn-login-copy { color:var(--mn-muted); font-size:.88rem; margin-top:5px; }

    .mn-footer { display:flex; flex-wrap:wrap; gap:8px 18px; padding:20px 2px 2px; margin-top:25px;
        border-top:1px solid var(--mn-border); color:#7a8c9c; font-size:.71rem; }
    .mn-footer span:before { content:""; display:inline-block; width:6px; height:6px; margin-right:7px;
        border-radius:50%; background:#35ad78; vertical-align:1px; }
    @media (max-width:768px) {
        .block-container { padding:1rem .85rem 2rem; }
        .mn-page-header { gap:12px; }
        .mn-title { font-size:1.45rem; }
        .mn-status { padding:6px 8px; }
        div[data-testid="stHorizontalBlock"] { gap:.75rem; }
        div[data-testid="column"] { min-width:0!important; }
        div[data-testid="stMetric"] { min-height:86px; padding:12px; }
    }
    </style>
    """),
    unsafe_allow_html=True,
)


def render_history_view(backend_online):
    """Render the backend-connected consultation history workspace."""

    st.markdown(
        """
        <div class="mn-page-header">
            <div>
                <div class="mn-eyebrow">Patient records</div>
                <div class="mn-title">Consultation history</div>
                <div class="mn-subtitle">
                    Search, review and manage saved clinical consultations.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    search_col, refresh_col = st.columns([4, 1])

    with search_col:
        search_query = st.text_input(
            "Search consultations",
            placeholder="Search by patient ID or patient name",
            label_visibility="collapsed",
        )

    with refresh_col:
        st.button(
            "Refresh",
            key="history_view_refresh",
            use_container_width=True,
        )

    if not backend_online:
        st.warning("Start the FastAPI backend to access consultation history.")
        return

    try:
        params = {}
        if search_query.strip():
            params["q"] = search_query.strip()

        response = requests.get(
            f"{FASTAPI_URL}/records",
            params=params,
            headers=api_headers(),
            timeout=20,
        )

        if response.status_code != 200:
            show_api_error(response)
            return

        records = response.json()
        if not records:
            st.info("No consultation records found.")
            return

        st.caption(f"{len(records)} consultation(s) found")

        for record in records:
            patient_name = record.get("patient_name") or "Not in audio"
            patient_id = record.get("patient_id") or "N/A"
            date = record.get("date") or ""
            time = record.get("time") or ""
            record_id = record.get("id")

            with st.expander(
                f"{patient_name}  |  {patient_id}  |  {date} {time}"
            ):
                detail_col, action_col = st.columns([3, 1])

                with detail_col:
                    st.markdown("**Chief complaint**")
                    st.write(record.get("chief_complaint") or "Not available")
                    st.markdown("**Diagnosis**")
                    st.write(record.get("diagnosis") or "Not stated")

                with action_col:
                    if st.button(
                        "Open consultation",
                        key=f"history_view_open_{record_id}",
                        type="primary",
                        use_container_width=True,
                    ):
                        record_response = requests.get(
                            f"{FASTAPI_URL}/records/{record_id}",
                            headers=api_headers(),
                            timeout=20,
                        )
                        if record_response.status_code == 200:
                            load_record(record_response.json())
                            st.session_state.workspace_view = "consultation"
                            st.rerun()
                        else:
                            show_api_error(record_response)

                    if st.session_state.get("user_role") == "doctor":
                        if st.button(
                            "Delete",
                            key=f"history_view_delete_{record_id}",
                            use_container_width=True,
                        ):
                            delete_response = requests.delete(
                                f"{FASTAPI_URL}/records/{record_id}",
                                headers=api_headers(),
                                timeout=30,
                            )
                            if delete_response.status_code == 200:
                                if st.session_state.get("record_id") == record_id:
                                    reset_consultation()
                                    st.session_state.workspace_view = "history"
                                st.success("Consultation and saved audio deleted.")
                                st.rerun()
                            else:
                                show_api_error(delete_response)

    except requests.exceptions.ConnectionError:
        st.warning("Consultation history is unavailable because the backend is offline.")
    except requests.exceptions.Timeout:
        st.warning("Consultation history request timed out.")
    except Exception as error:
        st.warning("Unable to load consultation history.")
        print("History view error:", type(error).__name__)


# ============================================================
# LOGIN
# ============================================================

with st.sidebar:
    st.markdown(
        """
        <div class="mn-brand">
            <div class="mn-logo">+</div>
            <div>
                <div class="mn-brand-name">MediNote</div>
                <div class="mn-brand-tag">AI Clinical Scribe</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if not st.session_state.get(
    "authenticated"
):

    st.markdown(
        """
        <div class="mn-login">
            <div class="mn-login-mark">+</div>
            <div class="mn-login-title">Welcome to MediNote</div>
            <div class="mn-login-copy">Secure clinical documentation workspace</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    login_left, login_center, login_right = (
        st.columns([1, 1.2, 1])
    )

    with login_center:

        with st.form(
            "login_form"
        ):

            st.markdown(
                "### Sign in as Doctor and Admin"
            )

            username = st.text_input(
                "Username"
            )

            password = st.text_input(
                "Password",
                type="password",
            )

            login_button = (
                st.form_submit_button(
                    "Login",
                    type="primary",
                    use_container_width=True,
                )
            )


        if login_button:

            if (
                not username.strip()
                or not password
            ):

                st.warning(
                    "Enter username and password."
                )

            else:

                try:

                    with st.spinner(
                        "Signing in..."
                    ):

                        response = requests.post(
                            f"{FASTAPI_URL}/auth/login",
                            json={
                                "username": username.strip(),
                                "password": password,
                            },
                            timeout=15,
                        )


                    if response.status_code == 200:

                        result = response.json()

                        st.session_state[
                            "authenticated"
                        ] = True

                        st.session_state[
                            "access_token"
                        ] = result.get(
                            "access_token"
                        )

                        st.session_state[
                            "username"
                        ] = result.get(
                            "username"
                        )

                        st.session_state[
                            "user_role"
                        ] = result.get(
                            "role"
                        )

                        update_activity_time()

                        st.rerun()

                    else:

                        st.error(
                            "Invalid username or password."
                        )


                except requests.exceptions.ConnectionError:

                    st.error(
                        "Cannot connect to Medical Scribe server."
                    )


                except requests.exceptions.Timeout:

                    st.error(
                        "Login request timed out."
                    )


                except Exception as error:

                    st.error(
                        "Unable to sign in."
                    )

                    print(
                        "Login error:",
                        type(error).__name__,
                    )


    st.stop()


# ============================================================
# SESSION TIMEOUT CHECK
# ============================================================

check_inactivity_timeout()



# ============================================================
# HEALTH
# ============================================================

health = get_backend_health()

backend_online = (
    health is not None
    and health.get("status")
    == "healthy"
)


# ============================================================
# SIDEBAR WORKSPACE
# ============================================================

with st.sidebar:

    st.markdown(
        '<div class="mn-nav-label">WORKSPACE</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        "＋  Consultation",
        type=(
            "primary"
            if st.session_state.workspace_view == "consultation"
            else "secondary"
        ),
        use_container_width=True,
    ):
        st.session_state.workspace_view = "consultation"
        st.rerun()

    if st.button(
        "📋  Consultation History",
        type=(
            "primary"
            if st.session_state.workspace_view == "history"
            else "secondary"
        ),
        use_container_width=True,
    ):
        st.session_state.workspace_view = "history"
        st.rerun()

    username = (
        st.session_state.get("username")
        or "Authorized user"
    )
    user_role = (
        st.session_state.get("user_role")
        or "clinical account"
    )
    initials = "".join(
        part[0].upper()
        for part in username.split()[:2]
        if part
    ) or "AU"
    username_display = escape(str(username))
    role_display = escape(str(user_role))
    health_class = "" if backend_online else " offline"
    health_label = "Backend online" if backend_online else "Backend offline"

    st.markdown(
        f"""
        <div class="mn-profile">
            <div class="mn-avatar">{initials}</div>
            <div>
                <div class="mn-profile-name">{username_display}</div>
                <div class="mn-profile-role">{role_display} account</div>
            </div>
        </div>
        <div class="mn-health">
            <span class="mn-health-dot{health_class}"></span>
            {health_label}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(
        "↪  Sign out",
        use_container_width=True,
    ):
        clear_auth_session()
        st.session_state["last_activity_time"] = None
        st.rerun()


if st.session_state.workspace_view == "history":
    render_history_view(backend_online)
    st.markdown(
        """
        <div class="mn-footer">
            <span>Encrypted clinical storage</span>
            <span>Authenticated access</span>
            <span>Role-based records</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


# ============================================================
# HEADER
# ============================================================

status_class = "" if backend_online else " offline"
status_text = "System ready" if backend_online else "Backend unavailable"

header_main, header_actions = st.columns([5, 1.35])

with header_main:
    st.markdown(
        dedent("""
        <div>
            <div class="mn-eyebrow">Clinical workspace</div>
            <div class="mn-title">New consultation</div>
            <div class="mn-subtitle">
                Capture a consultation, generate a transcript and review
                structured clinical documentation before use.
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )

with header_actions:
    st.markdown(
        f'<div class="mn-status{status_class}"><i></i>{status_text}</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        "＋  New Consultation",
        key="header_new_consultation",
        use_container_width=True,
    ):
        reset_consultation()
        st.session_state.workspace_view = "consultation"
        st.rerun()

st.divider()


# ============================================================
# MAIN COLUMNS
# ============================================================

left_column, right_column = st.columns(
    [1.05, 1],
    gap="large",
)


# ============================================================
# LEFT COLUMN
# ============================================================

with left_column:

    st.markdown(
        '<div class="section-title">New Consultation</div>',
        unsafe_allow_html=True,
    )

    input_tabs = st.tabs(
        [
            "🎙️ Hands-Free",
            "🎤 Manual Record",
            "📁 Upload Audio",
        ]
    )


    # ========================================================
    # HANDS FREE
    # ========================================================

    with input_tabs[0]:

        st.caption(
            "Hands-Free mode listens for the configured "
            "wake phrase and automatically stops after silence."
        )

        try:

            render_handsfree_recorder()

        except Exception:

            st.warning(
                "Hands-Free recorder is currently unavailable. "
                "Use Manual Record or Upload Audio."
            )


    # ========================================================
    # MANUAL RECORD
    # ========================================================

    with input_tabs[1]:

        st.caption(
            "Record the consultation directly "
            "from your microphone."
        )

        manual_audio = st.audio_input(
            "Record consultation",
            sample_rate=16000,
        )


    # ========================================================
    # UPLOAD AUDIO
    # ========================================================

    with input_tabs[2]:

        st.caption(
            "Upload an existing consultation audio file."
        )

        uploaded_audio = st.file_uploader(
            "Choose audio file",
            type=[
                "wav",
                "m4a",
                "ogg",
                "webm",
            ],
        )


    # ========================================================
    # SELECT AUDIO SOURCE
    # ========================================================

    selected_audio_bytes = None
    selected_audio_name = None
    auto_analyze = False


    pending_handsfree_audio = (
        st.session_state.get(
            "pending_handsfree_audio"
        )
    )


    if pending_handsfree_audio:

        selected_audio_bytes = (
            pending_handsfree_audio
        )

        selected_audio_name = (
            "handsfree_consultation.wav"
        )

        auto_analyze = True


    elif manual_audio is not None:

        selected_audio_bytes = (
            manual_audio.getvalue()
        )

        selected_audio_name = (
            "manual_consultation.wav"
        )

        st.markdown(
            """
            <div class="mn-record-state ready">
                <span class="mn-record-dot"></span>
                <div class="mn-record-copy">
                    <div class="mn-record-label">Audio captured</div>
                    <div class="mn-record-detail">Manual recording is ready to process.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


    elif uploaded_audio is not None:

        selected_audio_bytes = (
            uploaded_audio.getvalue()
        )

        selected_audio_name = (
            uploaded_audio.name
        )

        st.markdown(
            """
            <div class="mn-record-state ready">
                <span class="mn-record-dot"></span>
                <div class="mn-record-copy">
                    <div class="mn-record-label">Audio selected</div>
                    <div class="mn-record-detail">Uploaded audio is ready to process.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


    # ========================================================
    # AUDIO PREVIEW
    # ========================================================

    if selected_audio_bytes:

        st.audio(
            selected_audio_bytes
        )

        st.caption(
            f"Selected audio: {selected_audio_name}"
        )


    # ========================================================
    # PROCESS FUNCTION
    # ========================================================

    def process_consultation():

        if not backend_online:

            st.error(
                "Backend is offline. Start FastAPI first."
            )

            return


        if not MEDICAL_SCRIBE_API_KEY:

            st.error(
                "MEDICAL_SCRIBE_API_KEY is missing from .env"
            )

            return


        if not selected_audio_bytes:

            st.warning(
                "Record or upload an audio file first."
            )

            return


        files = {

            "audio": (
                selected_audio_name,
                BytesIO(
                    selected_audio_bytes
                ),
            )
        }


        try:

            with st.spinner(
                "Processing consultation..."
            ):

                response = requests.post(

                    f"{FASTAPI_URL}/process-consultation",

                    files=files,

                    headers=api_headers(),

                    timeout=240,
                )


            if response.status_code != 200:

                show_api_error(
                    response
                )

                return


            result = response.json()


            # =================================================
            # DUPLICATE
            # =================================================

            if result.get(
                "duplicate"
            ):

                st.warning(
                    "This audio has already been processed."
                )

                record_id = result.get(
                    "record_id"
                )

                if record_id:

                    record_response = requests.get(

                        f"{FASTAPI_URL}/records/{record_id}",

                        headers=api_headers(),

                        timeout=20,
                    )


                    if record_response.status_code == 200:

                        load_record(
                            record_response.json()
                        )

                st.session_state[
                    "pending_handsfree_audio"
                ] = None

                st.rerun()

                return


            # =================================================
            # NEW RESULT
            # =================================================

            st.session_state.record_id = (
                result.get(
                    "record_id"
                )
            )

            st.session_state.patient_name = (
                result.get(
                    "patient_name"
                )
            )

            st.session_state.patient_id = (
                result.get(
                    "patient_id"
                )
            )

            st.session_state.session_id = (
                result.get(
                    "session_id"
                )
            )

            timestamp = (
                result.get(
                    "timestamp"
                )
                or {}
            )

            st.session_state.date = (
                timestamp.get(
                    "date"
                )
            )

            st.session_state.time = (
                timestamp.get(
                    "time"
                )
            )

            st.session_state.transcript = (
                result.get(
                    "transcript",
                    "",
                )
            )

            st.session_state.clinical_data = (
                result.get(
                    "clinical_data"
                )
                or {}
            )

            st.session_state[
                "pending_handsfree_audio"
            ] = None


            st.success(
                "Consultation processed and saved successfully."
            )

            st.rerun()


        except requests.exceptions.Timeout:

            st.error(
                "Processing timed out. "
                "Please try again."
            )


        except requests.exceptions.ConnectionError:

            st.error(
                "Cannot connect to FastAPI backend."
            )


        except Exception as error:

            st.error(
                "Unexpected frontend error."
            )

            print(
                "Frontend processing error:",
                type(error).__name__,
            )


    # ========================================================
    # PROCESS BUTTON
    # ========================================================

    analyze_button = st.button(
        "✨ Analyze & Save Consultation",
        type="primary",
        use_container_width=True,
        disabled=(
            selected_audio_bytes
            is None
        ),
    )


    if analyze_button:

        process_consultation()


    if auto_analyze:

        st.session_state[
            "pending_handsfree_audio"
        ] = None

        process_consultation()


    # ========================================================
    # PATIENT INFO
    # ========================================================

    if st.session_state.record_id:

        st.divider()

        st.markdown(
            '<div class="section-title">Patient Information</div>',
            unsafe_allow_html=True,
        )

        patient_col1, patient_col2 = st.columns(
            2
        )


        with patient_col1:

            st.metric(
                "Patient Name",
                st.session_state.patient_name
                or "Not in audio",
            )


        with patient_col2:

            st.metric(
                "Patient ID",
                st.session_state.patient_id
                or "N/A",
            )


        date_col, time_col = st.columns(
            2
        )


        with date_col:

            st.metric(
                "Date",
                st.session_state.date
                or "N/A",
            )


        with time_col:

            st.metric(
                "Time",
                st.session_state.time
                or "N/A",
            )


    # ========================================================
    # TRANSCRIPT
    # ========================================================

    st.divider()

    st.markdown(
        '<div class="section-title">Consultation Transcript</div>',
        unsafe_allow_html=True,
    )


    transcript_display = st.session_state.get(
        "transcript",
        "",
    )


    if transcript_display:

        st.text_area(
            "Transcript",
            value=transcript_display,
            height=300,
            disabled=True,
            label_visibility="collapsed",
        )

    else:

        st.info(
            "Transcript will appear here after processing."
        )


# ============================================================
# RIGHT COLUMN
# ============================================================

with right_column:

    st.markdown(
        '<div class="section-title">Clinical Summary</div>',
        unsafe_allow_html=True,
    )


    clinical_data = (
        st.session_state.get(
            "clinical_data"
        )
        or {}
    )


    if not clinical_data:

        st.info(
            "Structured clinical information "
            "will appear here after processing."
        )


    else:

        vitals = (
            clinical_data.get(
                "vitals"
            )
            or {}
        )


        # ====================================================
        # VITALS
        # ====================================================

        st.markdown(
            "#### Vitals"
        )

        vital_col1, vital_col2 = st.columns(
            2
        )

        vital_col3, vital_col4 = st.columns(
            2
        )


        with vital_col1:

            st.metric(
                "Blood Pressure",
                vitals.get(
                    "blood_pressure"
                )
                or "Not recorded",
            )


        with vital_col2:

            st.metric(
                "Heart Rate",
                vitals.get(
                    "heart_rate"
                )
                or "Not recorded",
            )


        with vital_col3:

            st.metric(
                "Temperature",
                vitals.get(
                    "temperature"
                )
                or "Not recorded",
            )


        with vital_col4:

            st.metric(
                "SpO2",
                vitals.get(
                    "oxygen_saturation"
                )
                or "Not recorded",
            )


        st.divider()


        # ====================================================
        # DIAGNOSIS
        # ====================================================

        st.markdown(
            "#### Diagnosis"
        )

        diagnosis = clinical_data.get(
            "diagnosis"
        )

        if diagnosis:

            st.success(
                diagnosis
            )

        else:

            st.caption(
                "No explicit diagnosis stated in audio."
            )


        # ====================================================
        # CHIEF COMPLAINT
        # ====================================================

        st.markdown(
            "#### Chief Complaint"
        )

        chief_complaint = (
            clinical_data.get(
                "chief_complaint"
            )
        )

        if chief_complaint:

            st.write(
                chief_complaint
            )

        else:

            st.caption(
                "Not available"
            )


        # ====================================================
        # SYMPTOMS
        # ====================================================

        st.markdown(
            "#### Symptoms"
        )

        symptoms = (
            clinical_data.get(
                "symptoms"
            )
            or []
        )

        if symptoms:

            for symptom in symptoms:

                st.write(
                    f"• {symptom}"
                )

        else:

            st.caption(
                "No symptoms extracted."
            )


        # ====================================================
        # MEDICATIONS
        # ====================================================

        st.markdown(
            "#### Medications"
        )

        medications = (
            clinical_data.get(
                "medications"
            )
            or []
        )


        if medications:

            for index, medicine in enumerate(
                medications,
                start=1,
            ):

                if isinstance(
                    medicine,
                    dict,
                ):

                    medicine_name = (
                        medicine.get(
                            "name"
                        )
                        or "Medication"
                    )

                    with st.expander(
                        f"{index}. {medicine_name}"
                    ):

                        st.write(
                            "**Dosage:**",
                            medicine.get(
                                "dosage"
                            )
                            or "Not stated",
                        )

                        st.write(
                            "**Frequency:**",
                            medicine.get(
                                "frequency"
                            )
                            or "Not stated",
                        )

                        st.write(
                            "**Duration:**",
                            medicine.get(
                                "duration"
                            )
                            or "Not stated",
                        )

                        st.write(
                            "**Route:**",
                            medicine.get(
                                "route"
                            )
                            or "Not stated",
                        )

                else:

                    st.write(
                        f"• {medicine}"
                    )

        else:

            st.caption(
                "No medications extracted."
            )


        # ====================================================
        # TESTS
        # ====================================================

        st.markdown(
            "#### Recommended Tests"
        )

        recommended_tests = (
            clinical_data.get(
                "recommended_tests"
            )
            or []
        )


        if recommended_tests:

            for test in recommended_tests:

                st.write(
                    f"• {test}"
                )

        else:

            st.caption(
                "No tests recommended."
            )


        # ====================================================
        # DOCTOR INSTRUCTIONS
        # ====================================================

        st.markdown(
            "#### Doctor Instructions"
        )

        doctor_instructions = (
            clinical_data.get(
                "doctor_instructions"
            )
            or []
        )


        if doctor_instructions:

            for instruction in doctor_instructions:

                st.write(
                    f"• {instruction}"
                )

        else:

            st.caption(
                "No instructions extracted."
            )


        # ====================================================
        # FOLLOW UP
        # ====================================================

        st.markdown(
            "#### Follow Up"
        )

        follow_up = (
            clinical_data.get(
                "follow_up"
            )
        )


        if follow_up:

            st.write(
                follow_up
            )

        else:

            st.caption(
                "No follow-up information stated."
            )



# ============================================================
# DOCTOR CORRECTION
# ============================================================

if (
    st.session_state.record_id
    and st.session_state.clinical_data
):

    st.divider()

    st.markdown(
        "## ✏️ Doctor Correction"
    )

    st.caption(
        "The consultation was already saved automatically. "
        "Use this section only if a healthcare professional "
        "needs to correct the saved AI-generated record."
    )


    if not st.session_state.edit_mode:

        if st.button(
            "✏️ Edit Saved Record",
            use_container_width=True,
        ):

            st.session_state.edit_mode = True

            st.rerun()


    else:

        current_data = (
            st.session_state.clinical_data
            or {}
        )

        current_vitals = (
            current_data.get(
                "vitals"
            )
            or {}
        )


        with st.form(
            "doctor_correction_form"
        ):

            st.markdown(
                "### Patient & Clinical Information"
            )


            edit_patient_name = (
                st.text_input(
                    "Patient Name",
                    value=(
                        st.session_state.patient_name
                        or ""
                    ),
                )
            )


            edit_chief_complaint = (
                st.text_area(
                    "Chief Complaint",
                    value=(
                        current_data.get(
                            "chief_complaint"
                        )
                        or ""
                    ),
                    height=90,
                )
            )


            edit_diagnosis = (
                st.text_area(
                    "Diagnosis",
                    value=(
                        current_data.get(
                            "diagnosis"
                        )
                        or ""
                    ),
                    height=90,
                )
            )


            st.markdown(
                "### Vitals"
            )

            vital_1, vital_2 = (
                st.columns(2)
            )

            vital_3, vital_4 = (
                st.columns(2)
            )


            with vital_1:

                edit_bp = (
                    st.text_input(
                        "Blood Pressure",
                        value=(
                            current_vitals.get(
                                "blood_pressure"
                            )
                            or ""
                        ),
                    )
                )


            with vital_2:

                edit_hr = (
                    st.text_input(
                        "Heart Rate",
                        value=(
                            current_vitals.get(
                                "heart_rate"
                            )
                            or ""
                        ),
                    )
                )


            with vital_3:

                edit_temp = (
                    st.text_input(
                        "Temperature",
                        value=(
                            current_vitals.get(
                                "temperature"
                            )
                            or ""
                        ),
                    )
                )


            with vital_4:

                edit_spo2 = (
                    st.text_input(
                        "SpO2",
                        value=(
                            current_vitals.get(
                                "oxygen_saturation"
                            )
                            or ""
                        ),
                    )
                )


            st.markdown(
                "### Symptoms"
            )

            edit_symptoms = (
                st.text_area(
                    "One symptom per line",
                    value=list_to_lines(
                        current_data.get(
                            "symptoms",
                            [],
                        )
                    ),
                    height=120,
                )
            )


            st.markdown(
                "### Medications"
            )

            st.caption(
                "One medicine per line using: "
                "Name | Dosage | Frequency | Duration | Route"
            )

            edit_medications = (
                st.text_area(
                    "Medication List",
                    value=medications_to_lines(
                        current_data.get(
                            "medications",
                            [],
                        )
                    ),
                    height=180,
                    placeholder=(
                        "Paracetamol | 500 mg | "
                        "Twice daily | 5 days | Oral"
                    ),
                )
            )


            st.markdown(
                "### Recommended Tests"
            )

            edit_tests = (
                st.text_area(
                    "One test per line",
                    value=list_to_lines(
                        current_data.get(
                            "recommended_tests",
                            [],
                        )
                    ),
                    height=100,
                )
            )


            st.markdown(
                "### Doctor Instructions"
            )

            edit_instructions = (
                st.text_area(
                    "One instruction per line",
                    value=list_to_lines(
                        current_data.get(
                            "doctor_instructions",
                            [],
                        )
                    ),
                    height=120,
                )
            )


            edit_follow_up = (
                st.text_area(
                    "Follow Up",
                    value=(
                        current_data.get(
                            "follow_up"
                        )
                        or ""
                    ),
                    height=90,
                )
            )


            st.markdown(
                "### Transcript"
            )

            edit_transcript = (
                st.text_area(
                    "Correct Transcript",
                    value=(
                        st.session_state.transcript
                        or ""
                    ),
                    height=250,
                )
            )


            save_col, cancel_col = (
                st.columns(2)
            )


            with save_col:

                save_correction = (
                    st.form_submit_button(
                        "💾 Save Correction",
                        type="primary",
                        use_container_width=True,
                    )
                )


            with cancel_col:

                cancel_correction = (
                    st.form_submit_button(
                        "Cancel",
                        use_container_width=True,
                    )
                )


        if cancel_correction:

            st.session_state.edit_mode = False

            st.rerun()


        if save_correction:

            payload = {

                "patient_name": (
                    edit_patient_name.strip()
                    or None
                ),

                "transcript": (
                    edit_transcript.strip()
                    or None
                ),

                "chief_complaint": (
                    edit_chief_complaint.strip()
                    or None
                ),

                "diagnosis": (
                    edit_diagnosis.strip()
                    or None
                ),

                "symptoms": (
                    lines_to_list(
                        edit_symptoms
                    )
                ),

                "medications": (
                    lines_to_medications(
                        edit_medications
                    )
                ),

                "recommended_tests": (
                    lines_to_list(
                        edit_tests
                    )
                ),

                "doctor_instructions": (
                    lines_to_list(
                        edit_instructions
                    )
                ),

                "follow_up": (
                    edit_follow_up.strip()
                    or None
                ),

                "vitals": {

                    "blood_pressure": (
                        edit_bp.strip()
                        or None
                    ),

                    "heart_rate": (
                        edit_hr.strip()
                        or None
                    ),

                    "temperature": (
                        edit_temp.strip()
                        or None
                    ),

                    "oxygen_saturation": (
                        edit_spo2.strip()
                        or None
                    ),
                },
            }


            try:

                with st.spinner(
                    "Saving doctor correction..."
                ):

                    response = requests.put(

                        (
                            f"{FASTAPI_URL}/records/"
                            f"{st.session_state.record_id}"
                        ),

                        json=payload,

                        headers=api_headers(),

                        timeout=30,
                    )


                if (
                    response.status_code
                    == 200
                ):

                    result = (
                        response.json()
                    )

                    updated_record = (
                        result.get(
                            "record"
                        )
                    )

                    if updated_record:

                        load_record(
                            updated_record
                        )

                    st.session_state.edit_mode = False

                    st.success(
                        "Doctor correction saved successfully."
                    )

                    st.rerun()


                else:

                    show_api_error(
                        response
                    )


            except requests.exceptions.ConnectionError:

                st.error(
                    "Cannot connect to FastAPI backend."
                )


            except requests.exceptions.Timeout:

                st.error(
                    "Correction request timed out."
                )


            except Exception as error:

                st.error(
                    "Unable to save doctor correction."
                )

                print(
                    "Doctor correction frontend error:",
                    type(error).__name__,
                )


# ============================================================
# HISTORY
# ============================================================

st.markdown(
    """
    <div class="mn-footer">
        <span>Encrypted clinical storage</span>
        <span>Authenticated access</span>
        <span>Audit-aware records</span>
        <span>Human review required</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "AI-generated clinical information must be reviewed and verified by an "
    "authorized healthcare professional before clinical use."
)

# History has its own sidebar-selected view above.
st.stop()

st.divider()

st.markdown(
    '<div id="consultation-history"></div><div class="section-title" '
    'style="font-size:1.28rem;">Consultation History</div>',
    unsafe_allow_html=True,
)


history_col1, history_col2 = st.columns(
    [3, 1]
)


with history_col1:

    search_query = st.text_input(
        "Search by Patient ID",
        placeholder="Example: PAT-1234ABCD",
    )


with history_col2:

    st.write("")

    st.write("")

    refresh_history = st.button(
        "🔄 Refresh",
        use_container_width=True,
    )


if backend_online and MEDICAL_SCRIBE_API_KEY:

    try:

        params = {}

        if search_query.strip():

            params["q"] = (
                search_query.strip()
            )


        history_response = requests.get(

            f"{FASTAPI_URL}/records",

            params=params,

            headers=api_headers(),

            timeout=20,
        )


        if history_response.status_code == 200:

            records = (
                history_response.json()
            )


            if not records:

                st.info(
                    "No consultation records found."
                )


            else:

                st.caption(
                    f"{len(records)} consultation(s) found"
                )


                for record in records:

                    patient_name = (
                        record.get(
                            "patient_name"
                        )
                        or "Not in audio"
                    )

                    patient_id = (
                        record.get(
                            "patient_id"
                        )
                        or "N/A"
                    )

                    date = (
                        record.get(
                            "date"
                        )
                        or ""
                    )

                    time = (
                        record.get(
                            "time"
                        )
                        or ""
                    )


                    title = (
                        f"{patient_name} • "
                        f"{patient_id} • "
                        f"{date} {time}"
                    )


                    with st.expander(
                        title
                    ):

                        diagnosis = (
                            record.get(
                                "diagnosis"
                            )
                        )

                        chief_complaint = (
                            record.get(
                                "chief_complaint"
                            )
                        )


                        st.write(
                            "**Chief Complaint:**",
                            chief_complaint
                            or "Not available",
                        )

                        st.write(
                            "**Diagnosis:**",
                            diagnosis
                            or "Not stated",
                        )


                        history_action_col1, history_action_col2 = (
                            st.columns(2)
                        )


                        with history_action_col1:

                            open_button = st.button(
                                "Open Consultation",
                                key=(
                                    f"open_record_"
                                    f"{record.get('id')}"
                                ),
                                use_container_width=True,
                            )


                        with history_action_col2:

                            delete_button = False

                            if (
                                st.session_state.get(
                                    "user_role"
                                )
                                == "doctor"
                            ):

                                delete_button = st.button(
                                    " Delete",
                                    key=(
                                        f"delete_record_"
                                        f"{record.get('id')}"
                                    ),
                                    type="secondary",
                                    use_container_width=True,
                                )


                        if delete_button:

                            try:

                                delete_response = requests.delete(

                                    (
                                        f"{FASTAPI_URL}/records/"
                                        f"{record.get('id')}"
                                    ),

                                    headers=api_headers(),

                                    timeout=30,
                                )


                                if delete_response.status_code == 200:

                                    deleted_id = record.get(
                                        "id"
                                    )

                                    if (
                                        st.session_state.get(
                                            "record_id"
                                        )
                                        == deleted_id
                                    ):

                                        reset_consultation()


                                    st.success(
                                        "Consultation and saved audio deleted."
                                    )

                                    st.rerun()


                                else:

                                    show_api_error(
                                        delete_response
                                    )


                            except requests.exceptions.ConnectionError:

                                st.error(
                                    "Cannot connect to backend."
                                )


                            except requests.exceptions.Timeout:

                                st.error(
                                    "Delete request timed out."
                                )


                            except Exception as error:

                                st.error(
                                    "Unable to delete consultation."
                                )

                                print(
                                    "Delete frontend error:",
                                    type(error).__name__,
                                )


                        if open_button:

                            record_response = (
                                requests.get(

                                    f"{FASTAPI_URL}/records/"
                                    f"{record.get('id')}",

                                    headers=api_headers(),

                                    timeout=20,
                                )
                            )


                            if (
                                record_response.status_code
                                == 200
                            ):

                                load_record(
                                    record_response.json()
                                )

                                st.rerun()

                            else:

                                show_api_error(
                                    record_response
                                )


        else:

            show_api_error(
                history_response
            )


    except requests.exceptions.ConnectionError:

        st.warning(
            "Consultation history is unavailable "
            "because the backend is offline."
        )


    except Exception as error:

        st.warning(
            "Unable to load consultation history."
        )

        print(
            "History error:",
            type(error).__name__,
        )


elif not backend_online:

    st.warning(
        "Start the FastAPI backend to access consultation history."
    )


elif not MEDICAL_SCRIBE_API_KEY:

    st.error(
        "MEDICAL_SCRIBE_API_KEY is missing from .env"
    )


# ============================================================
# DISCLAIMER
# ============================================================

st.markdown(
    """
    <div class="mn-footer">
        <span>Encrypted clinical storage</span>
        <span>Authenticated access</span>
        <span>Audit-aware records</span>
        <span>Human review required</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "AI-generated clinical information must be reviewed and verified by an "
    "authorized healthcare professional before clinical use."
)
