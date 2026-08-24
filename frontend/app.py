import os
from io import BytesIO

import requests
import streamlit as st

from dotenv import load_dotenv
from handsfree_recorder import render_handsfree_recorder


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# BACKEND URL
# ============================================================

def get_fastapi_url():

    environment_url = os.getenv(
        "FASTAPI_URL",
        "",
    ).strip()

    if environment_url:

        return (
            environment_url
            .rstrip("/")
        )

    try:

        secret_url = (
            st.secrets.get(
                "FASTAPI_URL",
                ""
            )
        )

        if secret_url:

            return (
                str(secret_url)
                .strip()
                .rstrip("/")
            )

    except Exception:

        pass

    return (
        "http://127.0.0.1:8000"
    )


FASTAPI_URL = (
    get_fastapi_url()
)


# ============================================================
# STREAMLIT PAGE
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

DEFAULTS = {
    "record_id": None,
    "patient_name": "",
    "patient_id": "",
    "session_id": "",
    "transcript": "",
    "clinical_data": {},
    "consultation_date": "",
    "consultation_time": "",
    "input_version": 0,
    "pending_handsfree_audio": None,
}


for key, value in DEFAULTS.items():

    if key not in st.session_state:

        st.session_state[
            key
        ] = value


# ============================================================
# RESET
# ============================================================

def reset_consultation():

    st.session_state.record_id = None
    st.session_state.patient_name = ""
    st.session_state.patient_id = ""
    st.session_state.session_id = ""
    st.session_state.transcript = ""
    st.session_state.clinical_data = {}
    st.session_state.consultation_date = ""
    st.session_state.consultation_time = ""
    st.session_state.input_version += 1
    st.session_state.pending_handsfree_audio = None


# ============================================================
# LOAD OLD RECORD
# ============================================================

def load_record(
    record: dict
):

    st.session_state.record_id = (
        record.get("id")
    )

    st.session_state.patient_name = (
        record.get(
            "patient_name"
        )
        or "Not in audio"
    )

    st.session_state.patient_id = (
        record.get(
            "patient_id"
        )
        or ""
    )

    st.session_state.transcript = (
        record.get(
            "transcript"
        )
        or ""
    )

    st.session_state.consultation_date = (
        record.get(
            "consultation_date"
        )
        or ""
    )

    st.session_state.consultation_time = (
        record.get(
            "consultation_time"
        )
        or ""
    )

    st.session_state.clinical_data = {

        "patient_name": (
            record.get(
                "patient_name"
            )
            or "Not in audio"
        ),

        "chief_complaint": (
            record.get(
                "chief_complaint"
            )
        ),

        "diagnosis": (
            record.get(
                "diagnosis"
            )
        ),

        "vitals": (
            record.get(
                "vitals"
            )
            or {}
        ),

        "symptoms": (
            record.get(
                "symptoms"
            )
            or []
        ),

        "medications": (
            record.get(
                "medications"
            )
            or []
        ),

        "recommended_tests": (
            record.get(
                "recommended_tests"
            )
            or []
        ),

        "doctor_instructions": (
            record.get(
                "doctor_instructions"
            )
            or []
        ),

        "follow_up": (
            record.get(
                "follow_up"
            )
        ),
    }


# ============================================================
# RESPONSIVE CSS
# ============================================================

st.markdown(
    """
    <style>

    /* ======================================================
       DESKTOP / GLOBAL
       ====================================================== */

    .stApp {
        background:
            radial-gradient(
                circle at top left,
                #e0f2fe 0%,
                transparent 28%
            ),
            radial-gradient(
                circle at top right,
                #dcfce7 0%,
                transparent 24%
            ),
            linear-gradient(
                180deg,
                #f8fafc 0%,
                #f1f5f9 100%
            );
    }


    .block-container {
        max-width: 1450px;
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }


    #MainMenu {
        visibility: hidden;
    }


    footer {
        visibility: hidden;
    }


    header {
        visibility: hidden;
    }


    /* ======================================================
       CARDS
       ====================================================== */

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 20px;
        background:
            rgba(
                255,
                255,
                255,
                0.82
            );
    }


    /* ======================================================
       METRICS
       ====================================================== */

    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 18px;
        width: 100%;
    }


    /* ======================================================
       FILE UPLOADER
       ====================================================== */

    [data-testid="stFileUploader"] {
        background: white;
        border: 1px dashed #94a3b8;
        border-radius: 18px;
        padding: 10px;
        width: 100%;
    }


    /* ======================================================
       TEXT AREA
       ====================================================== */

    [data-testid="stTextArea"] textarea {
        border-radius: 16px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        line-height: 1.6;
        width: 100%;
    }


    /* ======================================================
       BUTTONS
       ====================================================== */

    .stButton > button {
        min-height: 46px;
        border-radius: 14px;
        font-weight: 700;
        width: 100%;
    }


    /* ======================================================
       ALERTS
       ====================================================== */

    [data-testid="stAlert"] {
        border-radius: 16px;
    }


    /* ======================================================
       AUDIO
       ====================================================== */

    audio {
        width: 100% !important;
        max-width: 100% !important;
    }


    /* ======================================================
       WEBRTC
       ====================================================== */

    iframe {
        max-width: 100% !important;
    }


    /* ======================================================
       TABS
       ====================================================== */

    [data-baseweb="tab-list"] {
        gap: 8px;
        overflow-x: auto;
        scrollbar-width: thin;
    }


    [data-baseweb="tab"] {
        white-space: nowrap;
    }


    /* ======================================================
       MOBILE
       ====================================================== */

    @media screen and (max-width: 768px) {

        .block-container {
            padding-top: 0.8rem !important;
            padding-bottom: 1.5rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }


        h1 {
            font-size: 1.8rem !important;
            line-height: 1.2 !important;
        }


        h2 {
            font-size: 1.35rem !important;
        }


        h3 {
            font-size: 1.15rem !important;
        }


        /* ==================================================
           STACK STREAMLIT COLUMNS
           ================================================== */

        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.75rem !important;
        }


        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }


        /* ==================================================
           CARDS
           ================================================== */

        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px !important;
        }


        /* ==================================================
           METRICS
           ================================================== */

        [data-testid="stMetric"] {
            padding: 12px !important;
            border-radius: 14px !important;
        }


        [data-testid="stMetricLabel"] {
            font-size: 0.8rem !important;
        }


        [data-testid="stMetricValue"] {
            font-size: 1.2rem !important;
        }


        /* ==================================================
           BUTTONS
           ================================================== */

        .stButton > button {
            width: 100% !important;
            min-height: 48px !important;
            font-size: 0.95rem !important;
        }


        /* ==================================================
           INPUTS
           ================================================== */

        input,
        textarea {
            font-size: 16px !important;
        }


        /* ==================================================
           TRANSCRIPT
           ================================================== */

        [data-testid="stTextArea"] textarea {
            min-height: 240px !important;
        }


        /* ==================================================
           TABS
           ================================================== */

        [data-baseweb="tab-list"] {
            overflow-x: auto !important;
            display: flex !important;
            flex-wrap: nowrap !important;
        }


        [data-baseweb="tab"] {
            min-width: max-content !important;
            padding-left: 12px !important;
            padding-right: 12px !important;
        }


        /* ==================================================
           FILE UPLOAD
           ================================================== */

        [data-testid="stFileUploader"] {
            padding: 8px !important;
        }


        /* ==================================================
           EXPANDERS
           ================================================== */

        [data-testid="stExpander"] {
            width: 100% !important;
        }


        /* ==================================================
           WEBRTC
           ================================================== */

        iframe {
            width: 100% !important;
            max-width: 100% !important;
        }

    }


    /* ======================================================
       SMALL PHONES
       ====================================================== */

    @media screen and (max-width: 480px) {

        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }


        h1 {
            font-size: 1.55rem !important;
        }


        p {
            font-size: 0.92rem !important;
        }


        [data-testid="stMetric"] {
            padding: 10px !important;
        }

    }

    </style>
    """,

    unsafe_allow_html=True,
)


# ============================================================
# HEADER
# ============================================================

header_left, header_right = (
    st.columns(
        [5, 1.3]
    )
)


with header_left:

    st.title(
        "🩺 Medical Scribe AI"
    )

    st.caption(
        "Doctor–Patient Conversation "
        "Intelligence Platform"
    )


with header_right:

    st.success(
        "● System Online"
    )

    if st.button(
        "＋ New Consultation",
        use_container_width=True,
    ):

        reset_consultation()

        st.rerun()


# ============================================================
# HERO
# ============================================================

with st.container(
    border=True
):

    st.subheader(
        "AI Clinical Consultation Assistant"
    )

    st.write(
        "Record or upload a doctor-patient conversation. "
        "Medical Scribe AI will transcribe, extract "
        "structured clinical information and securely "
        "store the consultation."
    )


    h1, h2, h3, h4, h5 = (
        st.columns(5)
    )


    with h1:

        st.caption(
            "🎙️ Record"
        )


    with h2:

        st.caption(
            "📝 Transcribe"
        )


    with h3:

        st.caption(
            "🧠 Extract"
        )


    with h4:

        st.caption(
            "💾 Store"
        )


    with h5:

        st.caption(
            "📊 Observe"
        )


st.write("")


# ============================================================
# MAIN
# ============================================================

left_col, right_col = (
    st.columns(
        [1, 1.25],
        gap="large",
    )
)


# ============================================================
# LEFT COLUMN
# ============================================================

with left_col:

    # ========================================================
    # NEW CONSULTATION
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "🎙️ New Consultation"
        )

        st.caption(
            "Patient name is extracted automatically "
            "when explicitly spoken."
        )


        # ====================================================
        # INPUT TABS
        # ====================================================

        handsfree_tab, record_tab, upload_tab = (
            st.tabs(
                [
                    "🗣️ Hands-Free",
                    "🎙️ Manual Record",
                    "📁 Upload Audio",
                ]
            )
        )


        recorded_audio = None
        uploaded_audio = None


        # ====================================================
        # HANDS FREE
        # ====================================================

        with handsfree_tab:

            render_handsfree_recorder()


        # ====================================================
        # MANUAL RECORD
        # ====================================================

        with record_tab:

            recorded_audio = (
                st.audio_input(

                    "Record doctor-patient consultation",

                    sample_rate=16000,

                    key=(
                        "recorder_"
                        f"{st.session_state.input_version}"
                    ),
                )
            )


            if recorded_audio:

                st.audio(
                    recorded_audio
                )


        # ====================================================
        # UPLOAD
        # ====================================================

        with upload_tab:

            uploaded_audio = (
                st.file_uploader(

                    "Upload consultation audio",

                    type=[
                        "wav",
                        "mp3",
                        "m4a",
                        "ogg",
                        "webm",
                    ],

                    key=(
                        "uploader_"
                        f"{st.session_state.input_version}"
                    ),
                )
            )


            if uploaded_audio:

                st.audio(
                    uploaded_audio
                )


        # ====================================================
        # AUDIO SOURCE
        # ====================================================

        audio_source = None
        audio_name = None
        audio_type = None
        auto_analyze = False


        pending_handsfree_audio = (
            st.session_state.get(
                "pending_handsfree_audio"
            )
        )


        # ====================================================
        # HANDS FREE AUDIO
        # ====================================================

        if pending_handsfree_audio:

            audio_source = (
                BytesIO(
                    pending_handsfree_audio
                )
            )


            audio_name = (
                "handsfree_consultation.wav"
            )


            audio_type = (
                "audio/wav"
            )


            auto_analyze = True


        # ====================================================
        # MANUAL AUDIO
        # ====================================================

        elif recorded_audio:

            audio_source = (
                recorded_audio
            )


            audio_name = (
                "recorded_consultation.wav"
            )


            audio_type = (
                "audio/wav"
            )


        # ====================================================
        # UPLOADED AUDIO
        # ====================================================

        elif uploaded_audio:

            audio_source = (
                uploaded_audio
            )


            audio_name = (
                uploaded_audio.name
            )


            audio_type = (
                uploaded_audio.type
                or "audio/wav"
            )


        # ====================================================
        # ANALYZE BUTTON
        # ====================================================

        manual_analyze = (
            st.button(
                "✨ Analyze & Save Consultation",
                type="primary",
                use_container_width=True,
            )
        )


        analyze = (
            manual_analyze
            or auto_analyze
        )


        # ====================================================
        # PROCESS
        # ====================================================

        if analyze:

            if audio_source is None:

                st.warning(
                    "Please record or upload "
                    "consultation audio first."
                )


            else:

                try:

                    with st.spinner(
                        "Transcribing, analyzing "
                        "and saving consultation..."
                    ):


                        files = {

                            "audio": (

                                audio_name,

                                audio_source.getvalue(),

                                audio_type,
                            )
                        }


                        response = (
                            requests.post(

                                (
                                    f"{FASTAPI_URL}"
                                    "/process-consultation"
                                ),

                                files=files,

                                timeout=240,
                            )
                        )


                    # ========================================
                    # SUCCESS
                    # ========================================

                    if (
                        response.status_code
                        == 200
                    ):

                        result = (
                            response.json()
                        )


                        # ====================================
                        # DUPLICATE
                        # ====================================

                        if result.get(
                            "duplicate"
                        ):

                            st.warning(
                                "This consultation audio "
                                "has already been processed."
                            )


                            st.info(
                                "Existing Record ID: "
                                f"{result.get('record_id')}"
                            )


                        # ====================================
                        # NEW RECORD
                        # ====================================

                        else:

                            st.session_state.record_id = (
                                result.get(
                                    "record_id"
                                )
                            )


                            st.session_state.patient_name = (
                                result.get(
                                    "patient_name",
                                    "Not in audio",
                                )
                            )


                            st.session_state.patient_id = (
                                result.get(
                                    "patient_id",
                                    "",
                                )
                            )


                            st.session_state.session_id = (
                                result.get(
                                    "session_id",
                                    "",
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
                                    "clinical_data",
                                    {},
                                )
                            )


                            st.session_state.consultation_date = (
                                result.get(
                                    "consultation_date",
                                    "",
                                )
                            )


                            st.session_state.consultation_time = (
                                result.get(
                                    "consultation_time",
                                    "",
                                )
                            )


                            st.success(
                                "Consultation analyzed "
                                "and saved successfully."
                            )


                    # ========================================
                    # ERROR
                    # ========================================

                    else:

                        print(
                            "Consultation processing failed:",
                            response.status_code,
                            response.text,
                        )


                        st.error(
                            "Please try again after some time."
                        )


                except Exception as error:

                    print(
                        "Consultation processing error:",
                        repr(
                            error
                        ),
                    )


                    st.error(
                        "Please try again after some time."
                    )


                finally:

                    if auto_analyze:

                        st.session_state[
                            "pending_handsfree_audio"
                        ] = None


    # ========================================================
    # PATIENT INFORMATION
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "👤 Patient & Consultation"
        )


        p1, p2 = (
            st.columns(
                2
            )
        )


        with p1:

            st.metric(
                "Patient Name",

                (
                    st.session_state.patient_name
                    or "—"
                ),
            )


        with p2:

            st.metric(
                "Patient ID",

                (
                    st.session_state.patient_id
                    or "—"
                ),
            )


        r1, r2, r3 = (
            st.columns(
                3
            )
        )


        with r1:

            st.metric(
                "Record ID",

                (
                    st.session_state.record_id
                    or "—"
                ),
            )


        with r2:

            st.metric(
                "Date",

                (
                    st.session_state
                    .consultation_date
                    or "—"
                ),
            )


        with r3:

            st.metric(
                "Time",

                (
                    st.session_state
                    .consultation_time
                    or "—"
                ),
            )


    # ========================================================
    # TRANSCRIPT
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "📝 Conversation Transcript"
        )


        if st.session_state.transcript:

            st.text_area(

                "Transcript",

                value=(
                    st.session_state
                    .transcript
                ),

                height=350,

                label_visibility="collapsed",
            )


        else:

            st.info(
                "No consultation processed yet."
            )


# ============================================================
# RIGHT COLUMN
# ============================================================

with right_col:

    clinical = (
        st.session_state.clinical_data
    )


    vitals = (
        clinical.get(
            "vitals",
            {},
        )
    )


    # ========================================================
    # VITALS
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "❤️ Patient Vitals"
        )


        v1, v2 = (
            st.columns(
                2
            )
        )


        with v1:

            st.metric(
                "🩸 Blood Pressure",

                (
                    vitals.get(
                        "blood_pressure"
                    )
                    or "—"
                ),
            )


        with v2:

            st.metric(
                "❤️ Heart Rate",

                (
                    vitals.get(
                        "heart_rate"
                    )
                    or "—"
                ),
            )


        v3, v4 = (
            st.columns(
                2
            )
        )


        with v3:

            st.metric(
                "🌡️ Temperature",

                (
                    vitals.get(
                        "temperature"
                    )
                    or "—"
                ),
            )


        with v4:

            st.metric(
                "🫁 SpO₂",

                (
                    vitals.get(
                        "oxygen_saturation"
                    )
                    or "—"
                ),
            )


    # ========================================================
    # DIAGNOSIS
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "🩺 Disease / Diagnosis"
        )


        diagnosis = (
            clinical.get(
                "diagnosis"
            )
        )


        if diagnosis:

            st.success(
                diagnosis
            )


        else:

            st.info(
                "No diagnosis explicitly mentioned."
            )


    # ========================================================
    # CHIEF COMPLAINT
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "🗣️ Chief Complaint"
        )


        st.write(
            clinical.get(
                "chief_complaint"
            )
            or "Not mentioned"
        )


    # ========================================================
    # SYMPTOMS
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "🤒 Symptoms"
        )


        symptoms = (
            clinical.get(
                "symptoms",
                [],
            )
        )


        if symptoms:

            for symptom in symptoms:

                st.write(
                    f"• {symptom}"
                )


        else:

            st.info(
                "No symptoms extracted."
            )


    # ========================================================
    # MEDICINES
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "💊 Medicines"
        )


        medications = (
            clinical.get(
                "medications",
                [],
            )
        )


        if medications:

            for index, medicine in enumerate(
                medications,
                1,
            ):


                st.markdown(
                    f"**{index}. "
                    f"{medicine.get('name')}**"
                )


                m1, m2 = (
                    st.columns(
                        2
                    )
                )


                with m1:

                    st.caption(
                        "Dosage"
                    )


                    st.write(
                        medicine.get(
                            "dosage"
                        )
                        or "—"
                    )


                    st.caption(
                        "Frequency"
                    )


                    st.write(
                        medicine.get(
                            "frequency"
                        )
                        or "—"
                    )


                with m2:

                    st.caption(
                        "Duration"
                    )


                    st.write(
                        medicine.get(
                            "duration"
                        )
                        or "—"
                    )


                    st.caption(
                        "Route"
                    )


                    st.write(
                        medicine.get(
                            "route"
                        )
                        or "—"
                    )


                if (
                    index
                    < len(
                        medications
                    )
                ):

                    st.divider()


        else:

            st.info(
                "No medicines extracted."
            )


    # ========================================================
    # TESTS
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "🧪 Recommended Tests"
        )


        tests = (
            clinical.get(
                "recommended_tests",
                [],
            )
        )


        if tests:

            for test in tests:

                st.write(
                    f"• {test}"
                )


        else:

            st.info(
                "No tests mentioned."
            )


    # ========================================================
    # DOCTOR INSTRUCTIONS
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "📌 Doctor Instructions"
        )


        instructions = (
            clinical.get(
                "doctor_instructions",
                [],
            )
        )


        if instructions:

            for instruction in instructions:

                st.write(
                    f"• {instruction}"
                )


        else:

            st.info(
                "No instructions extracted."
            )


    # ========================================================
    # FOLLOW UP
    # ========================================================

    with st.container(
        border=True
    ):

        st.subheader(
            "📅 Follow-up"
        )


        st.write(
            clinical.get(
                "follow_up"
            )
            or "Not mentioned"
        )


# ============================================================
# HISTORY
# ============================================================

st.write("")


with st.container(
    border=True
):

    st.subheader(
        "📚 Patient Consultation History"
    )


    search_col, refresh_col = (
        st.columns(
            [5, 1]
        )
    )


    with search_col:

        search_term = (
            st.text_input(

                "Search records",

                placeholder=(
                    "Search by patient name, patient ID, "
                    "complaint or diagnosis..."
                ),

                label_visibility="collapsed",
            )
        )


    with refresh_col:

        if st.button(
            "🔄 Refresh",
            use_container_width=True,
        ):

            st.rerun()


    try:

        params = {}


        if search_term.strip():

            params[
                "q"
            ] = (
                search_term.strip()
            )


        history_response = (
            requests.get(

                (
                    f"{FASTAPI_URL}"
                    "/records"
                ),

                params=params,

                timeout=20,
            )
        )


        # ====================================================
        # HISTORY SUCCESS
        # ====================================================

        if (
            history_response.status_code
            == 200
        ):

            records = (
                history_response
                .json()
                .get(
                    "records",
                    [],
                )
            )


            st.caption(
                f"Records found: {len(records)}"
            )


            if not records:

                st.info(
                    "No matching consultation records."
                )


            # =================================================
            # RECORD LOOP
            # =================================================

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
                    or "No ID"
                )


                title = (
                    f"{patient_name}"
                    f" • {patient_id}"
                    f" • Record #{record['id']}"
                    f" • {record['consultation_date']}"
                )


                with st.expander(
                    title
                ):


                    # =========================================
                    # OPEN CONSULTATION
                    # =========================================

                    if st.button(

                        "📂 Open Consultation",

                        key=(
                            "open_record_"
                            f"{record['id']}"
                        ),

                        use_container_width=True,
                    ):

                        try:

                            detail_response = (
                                requests.get(

                                    (
                                        f"{FASTAPI_URL}"
                                        f"/records/"
                                        f"{record['id']}"
                                    ),

                                    timeout=20,
                                )
                            )


                            if (
                                detail_response.status_code
                                == 200
                            ):

                                selected = (
                                    detail_response
                                    .json()
                                    .get(
                                        "record",
                                        {},
                                    )
                                )


                                load_record(
                                    selected
                                )


                                st.rerun()


                            else:

                                print(
                                    "Consultation detail "
                                    "request failed:",

                                    detail_response.status_code,

                                    detail_response.text,
                                )


                                st.error(
                                    "Please try again "
                                    "after some time."
                                )


                        except Exception as error:

                            print(
                                "Consultation detail "
                                "loading error:",

                                repr(
                                    error
                                ),
                            )


                            st.error(
                                "Please try again "
                                "after some time."
                            )


                    st.divider()


                    # =========================================
                    # BASIC INFORMATION
                    # =========================================

                    c1, c2, c3 = (
                        st.columns(
                            3
                        )
                    )


                    with c1:

                        st.write(
                            "**Patient Name**"
                        )


                        st.write(
                            patient_name
                        )


                    with c2:

                        st.write(
                            "**Patient ID**"
                        )


                        st.write(
                            patient_id
                        )


                    with c3:

                        st.write(
                            "**Consultation**"
                        )


                        st.write(
                            (
                                f"{record['consultation_date']} "
                                f"{record['consultation_time']}"
                            )
                        )


                    # =========================================
                    # DIAGNOSIS
                    # =========================================

                    st.write(
                        "**Diagnosis**"
                    )


                    st.write(
                        record.get(
                            "diagnosis"
                        )
                        or "Not mentioned"
                    )


                    # =========================================
                    # CHIEF COMPLAINT
                    # =========================================

                    st.write(
                        "**Chief Complaint**"
                    )


                    st.write(
                        record.get(
                            "chief_complaint"
                        )
                        or "Not mentioned"
                    )


                    # =========================================
                    # SYMPTOMS
                    # =========================================

                    st.write(
                        "**Symptoms**"
                    )


                    history_symptoms = (
                        record.get(
                            "symptoms",
                            [],
                        )
                    )


                    if history_symptoms:

                        for symptom in history_symptoms:

                            st.write(
                                f"• {symptom}"
                            )


                    else:

                        st.write(
                            "Not mentioned"
                        )


                    # =========================================
                    # MEDICINES
                    # =========================================

                    st.write(
                        "**Medicines**"
                    )


                    history_medicines = (
                        record.get(
                            "medications",
                            [],
                        )
                    )


                    if history_medicines:

                        for medicine in history_medicines:

                            medicine_text = (
                                f"• "
                                f"{medicine.get('name')}"
                            )


                            if medicine.get(
                                "dosage"
                            ):

                                medicine_text += (
                                    " — "
                                    f"{medicine.get('dosage')}"
                                )


                            if medicine.get(
                                "frequency"
                            ):

                                medicine_text += (
                                    " — "
                                    f"{medicine.get('frequency')}"
                                )


                            if medicine.get(
                                "duration"
                            ):

                                medicine_text += (
                                    " — "
                                    f"{medicine.get('duration')}"
                                )


                            st.write(
                                medicine_text
                            )


                    else:

                        st.write(
                            "No medicines"
                        )


                    # =========================================
                    # TRANSCRIPT
                    # =========================================

                    st.write(
                        "**Transcript**"
                    )


                    st.text_area(

                        "Previous transcript",

                        value=(
                            record.get(
                                "transcript",
                                "",
                            )
                        ),

                        height=180,

                        key=(
                            "history_transcript_"
                            f"{record['id']}"
                        ),

                        label_visibility="collapsed",
                    )


        # ====================================================
        # HISTORY ERROR
        # ====================================================

        else:

            print(
                "History request failed:",
                history_response.status_code,
                history_response.text,
            )


            st.warning(
                "Please try again after some time."
            )


    except Exception as error:

        print(
            "History loading error:",
            repr(
                error
            ),
        )


        st.warning(
            "Please try again after some time."
        )


# ============================================================
# DISCLAIMER
# ============================================================

st.write("")


st.warning(
    "⚠️ AI-generated clinical information "
    "must be reviewed and verified by an "
    "authorized healthcare professional "
    "before clinical use."
)


st.divider()


st.caption(
    "Medical Scribe AI"
    " • FastAPI"
    " • Streamlit"
    " • Groq"
    " • SQLite"
    " • Langfuse"
)