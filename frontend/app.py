import os
from datetime import datetime, timezone
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
    page_title="Medical Scribe AI",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="collapsed",
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

        for key in list(
            st.session_state.keys()
        ):

            del st.session_state[key]

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
# AUDIT HISTORY VIEW
# ============================================================

def show_audit_history(record_id):

    try:

        response = requests.get(
            f"{FASTAPI_URL}/records/{record_id}/audit-history",
            headers=api_headers(),
            timeout=10,
        )

        if response.status_code != 200:

            show_api_error(response)
            return

        data = response.json()

        history = data.get(
            "history",
            [],
        )

        if not history:

            st.info(
                "No edit or delete history found."
            )
            return

        st.markdown(
            f"### Audit History ? Record #{record_id}"
        )

        for item in history:

            action = item.get(
                "action",
                "UNKNOWN",
            )

            username = item.get(
                "username",
                "Unknown",
            )

            timestamp = item.get(
                "timestamp",
                "",
            )

            changed_fields = item.get(
                "changed_fields",
                [],
            )

            old_values = item.get(
                "old_values",
            ) or {}

            new_values = item.get(
                "new_values",
            ) or {}

            with st.expander(
                f"{action} | {timestamp} | {username}"
            ):

                st.write(
                    f"**Doctor/User:** {username}"
                )

                st.write(
                    f"**Action:** {action}"
                )

                st.write(
                    f"**Time:** {timestamp}"
                )

                if action == "EDIT":

                    if not changed_fields:

                        st.write(
                            "No changed fields recorded."
                        )

                    for field in changed_fields:

                        st.markdown(
                            f"**{field}**"
                        )

                        col1, col2 = st.columns(
                            2
                        )

                        with col1:

                            st.caption(
                                "Old Value"
                            )

                            st.write(
                                old_values.get(
                                    field
                                )
                            )

                        with col2:

                            st.caption(
                                "New Value"
                            )

                            st.write(
                                new_values.get(
                                    field
                                )
                            )

                if item.get(
                    "details"
                ):

                    st.caption(
                        item.get(
                            "details"
                        )
                    )

    except requests.exceptions.Timeout:

        st.error(
            "Audit history request timed out."
        )

    except Exception as error:

        st.error(
            "Unable to load audit history."
        )

        print(
            "Audit history frontend error:",
            type(error).__name__,
        )


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


# Responsive visual system. Colors follow the device light/dark preference.
st.markdown(
    dedent("""
    <style>
    :root {
        --ms-bg:#f4f7fb; --ms-surface:rgba(255,255,255,.94);
        --ms-text:#10233f; --ms-muted:#60708a; --ms-border:#dce5ef;
        --ms-brand:#087f8c; --ms-brand-strong:#066975;
        --ms-shadow:0 16px 38px rgba(25,55,90,.09);
    }
    @media (prefers-color-scheme:dark) {
        :root {
            --ms-bg:#09131f; --ms-surface:rgba(18,32,48,.95);
            --ms-text:#edf6ff; --ms-muted:#a8b8ca; --ms-border:#294057;
            --ms-brand:#2bc4c9; --ms-brand-strong:#159ba2;
            --ms-shadow:0 18px 44px rgba(0,0,0,.28);
        }
    }
    .stApp {
        color:var(--ms-text);
        background:radial-gradient(circle at 8% 0%,rgba(19,165,174,.13),transparent 28rem),
                   radial-gradient(circle at 92% 8%,rgba(72,118,255,.10),transparent 24rem),
                   var(--ms-bg);
    }
    .block-container { max-width:1380px; padding:1.4rem 2rem 3rem; }
    .main-header,.hero-card {
        background:var(--ms-surface); border:1px solid var(--ms-border);
        box-shadow:var(--ms-shadow); backdrop-filter:blur(12px);
    }
    .main-header { border-radius:22px; padding:22px 26px; margin-bottom:18px; }
    .main-header h2,.hero-card h3,.section-title,.result-value { color:var(--ms-text)!important; }
    .main-header p,.hero-card p,.small-muted,.result-label { color:var(--ms-muted)!important; }
    .hero-card { position:relative; overflow:hidden; border-radius:22px; padding:26px; margin-bottom:22px; }
    .hero-card::after { content:""; position:absolute; width:180px; height:180px; right:-65px; top:-90px; border-radius:50%; background:rgba(20,184,166,.12); }
    .small-muted { color:var(--ms-brand)!important; font-weight:700; }
    .status-online,.status-offline { display:inline-flex; align-items:center; padding:8px 13px; border-radius:999px; font-weight:700; font-size:12px; }
    .status-online { background:rgba(34,197,94,.13); color:#16803b; border:1px solid rgba(34,197,94,.22); }
    .status-offline { background:rgba(239,68,68,.12); color:#c42b2b; border:1px solid rgba(239,68,68,.22); }
    .section-title { font-size:1.15rem; margin-bottom:10px; }
    div[data-testid="stMetric"] { min-height:96px; background:var(--ms-surface); border:1px solid var(--ms-border); padding:15px; border-radius:16px; box-shadow:0 7px 22px rgba(15,23,42,.05); }
    div[data-testid="stMetricLabel"] { color:var(--ms-muted); }
    div[data-testid="stMetricValue"] { color:var(--ms-text); font-size:1.18rem; }
    div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:8px; overflow-x:auto; }
    div[data-testid="stTabs"] button { border-radius:12px 12px 0 0; white-space:nowrap; }
    div[data-testid="stExpander"],div[data-testid="stFileUploaderDropzone"],textarea { border-color:var(--ms-border)!important; border-radius:14px!important; }
    .stButton>button { min-height:2.75rem; border-radius:12px; font-weight:700; }
    .stButton>button[kind="primary"] { border:0; background:linear-gradient(135deg,var(--ms-brand),var(--ms-brand-strong)); }
    hr { border-color:var(--ms-border)!important; }
    @media (max-width:768px) {
        .block-container { padding:.8rem .85rem 2rem; }
        .main-header,.hero-card { border-radius:17px; padding:18px; }
        .main-header p { font-size:.9rem; }
        .hero-card::after { display:none; }
        div[data-testid="stHorizontalBlock"] { gap:.75rem; }
        div[data-testid="column"] { min-width:0!important; }
        div[data-testid="stMetric"] { min-height:84px; padding:12px; }
    }
    </style>
    """),
    unsafe_allow_html=True,
)


# ============================================================
# LOGIN
# ============================================================

if not st.session_state.get(
    "authenticated"
):

    st.markdown(
        """
        <div style="
            max-width:520px;
            margin:50px auto 20px auto;
            text-align:center;
        ">
            <h1> Medical Scribe AI</h1>
            <p>
                Secure clinical documentation assistant
            </p>
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
# LOGOUT
# ============================================================

logout_col1, logout_col2 = st.columns(
    [5, 1]
)

with logout_col1:

    st.caption(
        "Signed in as "
        f"{st.session_state.get('username')} "
        f"({st.session_state.get('user_role')})"
    )


with logout_col2:

    if st.button(
        "Logout",
        use_container_width=True,
    ):

        for key in list(
            st.session_state.keys()
        ):

            del st.session_state[key]

        st.rerun()


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
# HEADER
# ============================================================

header_left, header_right = st.columns(
    [5, 1.5]
)


with header_left:

    st.markdown(
        dedent("""
        <div class="main-header">
            <h2 style="
                margin:0;
                color:#0f172a;
            ">
                🩺 Medical Scribe AI
            </h2>
            <p style="
                margin:6px 0 0 0;
                color:#64748b;
            ">
                AI-assisted clinical consultation
                transcription and structured documentation
            </p>
        </div>
        """),
        unsafe_allow_html=True,
    )


with header_right:

    st.write("")

    if backend_online:

        st.markdown(
            dedent("""
            <div class="status-online">
                ● Backend Online
            </div>
            """),
            unsafe_allow_html=True,
        )

    else:

        st.markdown(
            dedent("""
            <div class="status-offline">
                ● Backend Offline
            </div>
            """),
            unsafe_allow_html=True,
        )

    st.write("")

    if st.button(
        "+ New Consultation",
        use_container_width=True,
    ):

        reset_consultation()

        st.rerun()


# ============================================================
# HERO
# ============================================================

st.markdown(
    dedent("""
    <div class="hero-card">
        <h3 style="
            margin-top:0;
            color:#0f172a;
        ">
            Clinical Consultation Assistant
        </h3>
        <p style="
            color:#475569;
            margin-bottom:12px;
        ">
            Record or upload a doctor-patient consultation.
            The system transcribes the conversation,
            extracts structured clinical information,
            and stores the consultation using encrypted
            local storage.
        </p>
        <div class="small-muted">
            Record → Transcribe → Extract → Encrypt → Store → Observe
        </div>
    </div>
    """),
    unsafe_allow_html=True,
)


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
                "mp3",
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


    elif uploaded_audio is not None:

        selected_audio_bytes = (
            uploaded_audio.getvalue()
        )

        selected_audio_name = (
            uploaded_audio.name
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
                "SpOâ''",
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
                        "SpOâ''",
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

st.divider()

st.markdown(
    "## Consultation History"
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

                            audit_button = st.button(
                                "Audit History",
                                key=(
                                    f"audit_record_"
                                    f"{record.get('id')}"
                                ),
                                type="secondary",
                            )

                            if audit_button:

                                show_audit_history(
                                    record.get(
                                        "id"
                                    )
                                )


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

st.divider()

st.caption(
    "Medical Scribe AI is an AI-assisted documentation tool. "
    "Clinical information generated by the system must be "
    "reviewed and verified by an authorized healthcare "
    "professional before clinical use."
)


st.caption(
    "FastAPI • Streamlit • Groq • SQLite • Langfuse"
)



# ============================================================
# GLOBAL AUDIT HISTORY
# ============================================================

st.divider()

st.markdown(
    "## Audit History"
)

st.caption(
    "Permanent doctor edit/delete activity, including deleted records."
)

if st.button(
    "View Full Audit History",
    key="global_audit_history_button",
):

    try:

        response = requests.get(
            f"{FASTAPI_URL}/audit-history",
            headers=api_headers(),
            timeout=10,
        )

        if response.status_code != 200:

            show_api_error(
                response
            )

        else:

            data = response.json()

            history = data.get(
                "history",
                [],
            )

            if not history:

                st.info(
                    "No audit history found."
                )

            else:

                st.success(
                    f"{len(history)} audit event(s) found."
                )

                for item in history:

                    record_id = item.get(
                        "record_id"
                    )

                    action = item.get(
                        "action",
                        "UNKNOWN",
                    )

                    username = item.get(
                        "username",
                        "Unknown",
                    )

                    timestamp = item.get(
                        "timestamp",
                        "",
                    )

                    with st.expander(
                        f"Record #{record_id} | "
                        f"{action} | "
                        f"{timestamp}"
                    ):

                        st.write(
                            f"**Record ID:** {record_id}"
                        )

                        st.write(
                            f"**Doctor/User:** {username}"
                        )

                        st.write(
                            f"**Role:** "
                            f"{item.get('role', '')}"
                        )

                        st.write(
                            f"**Action:** {action}"
                        )

                        st.write(
                            f"**Time:** {timestamp}"
                        )

                        if action == "EDIT":

                            changed_fields = (
                                item.get(
                                    "changed_fields",
                                    [],
                                )
                            )

                            old_values = (
                                item.get(
                                    "old_values",
                                )
                                or {}
                            )

                            new_values = (
                                item.get(
                                    "new_values",
                                )
                                or {}
                            )

                            for field in changed_fields:

                                st.markdown(
                                    f"### {field}"
                                )

                                old_col, new_col = (
                                    st.columns(2)
                                )

                                with old_col:

                                    st.caption(
                                        "Old Value"
                                    )

                                    st.write(
                                        old_values.get(
                                            field
                                        )
                                    )

                                with new_col:

                                    st.caption(
                                        "New Value"
                                    )

                                    st.write(
                                        new_values.get(
                                            field
                                        )
                                    )

                        details = item.get(
                            "details"
                        )

                        if details:

                            st.caption(
                                details
                            )

    except requests.exceptions.Timeout:

        st.error(
            "Audit history request timed out."
        )

    except Exception as error:

        st.error(
            "Unable to load global audit history."
        )

        print(
            "Global audit history error:",
            type(error).__name__,
        )

