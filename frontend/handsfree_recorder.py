import io
import os
import re
import threading
import time
import wave

import numpy as np
import streamlit as st

from dotenv import load_dotenv
from groq import Groq
from streamlit_webrtc import (
    WebRtcMode,
    webrtc_streamer,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

WAKE_PHRASES = (
    "start recording",
    "start the recording",
    "start record",
    "begin recording",
)

SILENCE_SECONDS = 5.0

WAKE_WINDOW_SECONDS = 5.0

WAKE_CHECK_INTERVAL_SECONDS = 1.0

MIN_RECORDING_SECONDS = 2.0


SILENCE_RMS = float(
    os.getenv(
        "HANDS_FREE_SILENCE_RMS",
        "0.006",
    )
)


# ============================================================
# GROQ
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    "",
).strip()


WAKE_TRANSCRIPTION_MODEL = os.getenv(
    "WAKE_TRANSCRIPTION_MODEL",
    "whisper-large-v3-turbo",
).strip()


groq_client = None


if GROQ_API_KEY:

    groq_client = Groq(
        api_key=GROQ_API_KEY
    )


# ============================================================
# PCM → WAV
# ============================================================

def pcm_to_wav(
    pcm_bytes: bytes,
    sample_rate: int,
) -> bytes:

    output = io.BytesIO()

    with wave.open(
        output,
        "wb",
    ) as wav_file:

        wav_file.setnchannels(
            1
        )

        wav_file.setsampwidth(
            2
        )

        wav_file.setframerate(
            sample_rate
        )

        wav_file.writeframes(
            pcm_bytes
        )

    wav_bytes = (
        output.getvalue()
    )

    output.close()

    return wav_bytes


# ============================================================
# AUDIO FRAME → MONO PCM16
# ============================================================

def frame_to_mono_pcm16(
    frame,
):

    audio_array = (
        frame.to_ndarray()
    )


    if audio_array.ndim == 2:

        audio_array = (
            audio_array
            .astype(
                np.float32
            )
            .mean(
                axis=0
            )
        )


    audio_array = np.asarray(
        audio_array
    )


    if np.issubdtype(
        audio_array.dtype,
        np.floating,
    ):

        audio_array = np.clip(
            audio_array,
            -1.0,
            1.0,
        )


        audio_array = (
            audio_array
            * 32767.0
        ).astype(
            np.int16
        )

    else:

        audio_array = (
            audio_array
            .astype(
                np.int16,
                copy=False,
            )
        )


    return (
        audio_array.tobytes(),
        int(
            frame.sample_rate
        ),
    )


# ============================================================
# AUDIO VOLUME
# ============================================================

def calculate_rms(
    pcm_bytes: bytes,
) -> float:

    if not pcm_bytes:

        return 0.0


    samples = np.frombuffer(
        pcm_bytes,
        dtype=np.int16,
    )


    if samples.size == 0:

        return 0.0


    values = (
        samples.astype(
            np.float32
        )
        / 32768.0
    )


    rms = np.sqrt(
        np.mean(
            values * values
        )
    )


    return float(
        rms
    )


# ============================================================
# HANDS FREE STATE
# ============================================================

class HandsFreeState:

    def __init__(
        self,
    ):

        self.lock = (
            threading.Lock()
        )


        self.mode = (
            "waiting"
        )


        self.status = (
            'Listening for "start recording"...'
        )


        self.sample_rate = (
            48000
        )


        self.wake_buffer = (
            bytearray()
        )


        self.recording_buffer = (
            bytearray()
        )


        self.last_wake_check = (
            0.0
        )


        self.wake_check_running = (
            False
        )


        self.recording_started_at = (
            None
        )


        self.last_speech_at = (
            None
        )


        self.completed_wav = (
            None
        )


        self.completed_id = (
            0
        )


    # ========================================================
    # RESET
    # ========================================================

    def reset_waiting(
        self,
    ):

        with self.lock:

            self.mode = (
                "waiting"
            )


            self.status = (
                'Listening for "start recording"...'
            )


            self.wake_buffer.clear()


            self.recording_buffer.clear()


            self.recording_started_at = (
                None
            )


            self.last_speech_at = (
                None
            )


            self.completed_wav = (
                None
            )


            self.last_wake_check = (
                0.0
            )


            self.wake_check_running = (
                False
            )


    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(
        self,
    ):

        with self.lock:

            return {

                "mode": (
                    self.mode
                ),

                "status": (
                    self.status
                ),

                "completed_id": (
                    self.completed_id
                ),

                "has_completed_audio": (
                    self.completed_wav
                    is not None
                ),
            }


    # ========================================================
    # GET COMPLETED AUDIO
    # ========================================================

    def pop_completed_audio(
        self,
    ):

        with self.lock:

            audio = (
                self.completed_wav
            )


            self.completed_wav = (
                None
            )


            self.wake_buffer.clear()


            self.recording_buffer.clear()


            self.recording_started_at = (
                None
            )


            self.last_speech_at = (
                None
            )


            return audio


# ============================================================
# SESSION STATE
# ============================================================

def get_handsfree_state():

    if (
        "handsfree_audio_state"
        not in st.session_state
    ):

        st.session_state[
            "handsfree_audio_state"
        ] = HandsFreeState()


    return st.session_state[
        "handsfree_audio_state"
    ]


# ============================================================
# WAKE PHRASE DETECTION
# ============================================================

def detect_wake_phrase(
    state: HandsFreeState,
    pcm_snapshot: bytes,
    sample_rate: int,
):
    """
    Transcribe the rolling microphone buffer and detect the
    configured wake phrase.

    This function runs in a background thread so the WebRTC
    audio callback never blocks on the transcription API.
    """

    try:
        if groq_client is None:
            print(
                "[HANDS-FREE] GROQ_API_KEY is not configured."
            )

            with state.lock:
                state.status = (
                    "Wake phrase service is unavailable."
                )

            return

        if not pcm_snapshot:
            return

        wav_bytes = pcm_to_wav(
            pcm_snapshot,
            sample_rate,
        )

        print(
            "[HANDS-FREE] Checking microphone audio for wake phrase..."
        )

        response = (
            groq_client
            .audio
            .transcriptions
            .create(
                file=(
                    "wake_command.wav",
                    wav_bytes,
                ),
                model=WAKE_TRANSCRIPTION_MODEL,
                response_format="json",
                temperature=0.0,
                language="en",
                prompt=(
                    "Listen carefully for the command "
                    "'start recording'. "
                    "The speaker may also say "
                    "'start the recording', "
                    "'start record', or "
                    "'begin recording'."
                ),
            )
        )

        # Support both SDK object and dict responses.
        if isinstance(response, dict):
            detected_text = (
                response.get("text", "")
                or ""
            )
        else:
            detected_text = (
                getattr(
                    response,
                    "text",
                    "",
                )
                or ""
            )

        detected_text = str(
            detected_text
        ).strip()

        normalized_text = (
            detected_text
            .lower()
            .replace(".", " ")
            .replace(",", " ")
            .replace("!", " ")
            .replace("?", " ")
            .replace("-", " ")
        )

        normalized_text = " ".join(
            normalized_text.split()
        )

        print(
            "[HANDS-FREE] Heard:",
            repr(detected_text),
        )

        print(
            "[HANDS-FREE] Normalized:",
            repr(normalized_text),
        )

        # Exact + tolerant matching.
        wake_detected = any(
            phrase in normalized_text
            for phrase in WAKE_PHRASES
        )

        # Whisper can occasionally return small variations.
        words = set(
            normalized_text.split()
        )

        if (
            "start" in words
            and (
                "recording" in words
                or "record" in words
            )
        ):
            wake_detected = True

        if (
            "begin" in words
            and "recording" in words
        ):
            wake_detected = True

        if not wake_detected:
            return

        with state.lock:
            if state.mode != "waiting":
                return

            now = time.monotonic()

            state.mode = "recording"

            state.status = (
                "?? Recording consultation. "
                "Recording will automatically stop "
                "after 5 seconds of silence."
            )

            state.recording_buffer.clear()

            # Keep the last short part of microphone audio so
            # speech immediately following the wake phrase is
            # less likely to be lost.
            bytes_per_second = (
                sample_rate * 2
            )

            keep_bytes = int(
                0.35 * bytes_per_second
            )

            if len(pcm_snapshot) > keep_bytes:
                state.recording_buffer.extend(
                    pcm_snapshot[-keep_bytes:]
                )

            state.wake_buffer.clear()

            state.recording_started_at = now
            state.last_speech_at = now

        print(
            "[HANDS-FREE] WAKE PHRASE DETECTED -> RECORDING STARTED"
        )

    except Exception as error:
        print(
            "[HANDS-FREE] Wake detection error:",
            type(error).__name__,
            str(error),
        )

        with state.lock:
            if state.mode == "waiting":
                state.status = (
                    "Listening for "
                    '"start recording"...'
                )

    finally:
        with state.lock:
            state.wake_check_running = False


# ============================================================
# AUDIO CALLBACK
# ============================================================

def build_audio_callback(
    state: HandsFreeState,
):

    def audio_frame_callback(
        frame,
    ):

        try:

            (
                pcm_bytes,
                sample_rate,
            ) = frame_to_mono_pcm16(
                frame
            )


            current_time = (
                time.monotonic()
            )


            rms = calculate_rms(
                pcm_bytes
            )


            speech_detected = (
                rms
                >= SILENCE_RMS
            )


            wake_job = None


            with state.lock:

                state.sample_rate = (
                    sample_rate
                )


                # ============================================
                # WAITING FOR "START RECORDING"
                # ============================================

                if (
                    state.mode
                    == "waiting"
                ):

                    state.wake_buffer.extend(
                        pcm_bytes
                    )


                    bytes_per_second = (
                        sample_rate
                        * 2
                    )


                    max_wake_bytes = int(
                        WAKE_WINDOW_SECONDS
                        * bytes_per_second
                    )


                    if (
                        len(
                            state.wake_buffer
                        )
                        > max_wake_bytes
                    ):

                        del state.wake_buffer[
                            :-max_wake_bytes
                        ]


                    enough_audio = (

                        len(
                            state.wake_buffer
                        )

                        >= int(
                            1.5
                            * bytes_per_second
                        )
                    )


                    wake_interval_ready = (

                        current_time
                        - state.last_wake_check

                        >= WAKE_CHECK_INTERVAL_SECONDS
                    )


                    # IMPORTANT:
                    # Wake phrase detection does NOT depend
                    # on RMS/speech_detected anymore.

                    if (
                        enough_audio
                        and wake_interval_ready
                        and not state.wake_check_running
                    ):

                        state.last_wake_check = (
                            current_time
                        )


                        state.wake_check_running = (
                            True
                        )


                        wake_job = (

                            bytes(
                                state.wake_buffer
                            ),

                            sample_rate,
                        )


                # ============================================
                # ACTIVE RECORDING
                # ============================================

                elif (
                    state.mode
                    == "recording"
                ):

                    state.recording_buffer.extend(
                        pcm_bytes
                    )


                    if speech_detected:

                        state.last_speech_at = (
                            current_time
                        )


                    started_at = (

                        state.recording_started_at
                        or current_time
                    )


                    last_speech = (

                        state.last_speech_at
                        or started_at
                    )


                    recording_duration = (

                        current_time
                        - started_at
                    )


                    silence_duration = (

                        current_time
                        - last_speech
                    )


                    # ========================================
                    # 5 SECOND SILENCE
                    # ========================================

                    if (
                        recording_duration
                        >= MIN_RECORDING_SECONDS

                        and silence_duration
                        >= SILENCE_SECONDS
                    ):

                        state.mode = (
                            "processing"
                        )


                        state.status = (
                            "⏳ Silence detected. "
                            "Processing consultation..."
                        )


                        recording_pcm = bytes(
                            state.recording_buffer
                        )


                        state.completed_wav = (
                            pcm_to_wav(
                                recording_pcm,
                                sample_rate,
                            )
                        )


                        recording_pcm = None


                        state.completed_id += (
                            1
                        )


                        state.recording_buffer.clear()


                        state.wake_buffer.clear()


                        state.recording_started_at = (
                            None
                        )


                        state.last_speech_at = (
                            None
                        )


            # ================================================
            # WAKE WORD API CALL IN THREAD
            # ================================================

            if wake_job is not None:

                (
                    pcm_snapshot,
                    rate,
                ) = wake_job


                thread = threading.Thread(

                    target=(
                        detect_wake_phrase
                    ),

                    args=(
                        state,
                        pcm_snapshot,
                        rate,
                    ),

                    daemon=True,
                )


                thread.start()


                pcm_snapshot = None


        except Exception as error:

            print(
                "Hands-free audio error:",
                repr(
                    error
                ),
            )


        finally:

            pcm_bytes = None


        return frame


    return audio_frame_callback


# ============================================================
# STREAMLIT COMPONENT
# ============================================================

def render_handsfree_recorder():

    state = (
        get_handsfree_state()
    )


    st.caption(
        'Enable microphone once, then say '
        '"start recording". '
        "Recording automatically stops "
        "after 5 seconds of silence."
    )


    webrtc_streamer(

        key=(
            "medical_scribe_handsfree"
        ),

        mode=(
            WebRtcMode.SENDONLY
        ),

        audio_frame_callback=(
            build_audio_callback(
                state
            )
        ),

        media_stream_constraints={
            "video": False,

            "audio": {
                "echoCancellation": True,
                "noiseSuppression": True,
                "autoGainControl": True,
            },
        },

        rtc_configuration={
            "iceServers": [
                {
                    "urls": [
                        (
                            "stun:"
                            "stun.l.google.com:19302"
                        )
                    ]
                }
            ]
        },

        media_toggle_controls=False,

        async_processing=True,
    )


    # ========================================================
    # LIVE STATUS
    # ========================================================

    @st.fragment(
        run_every=0.5
    )
    @st.fragment(run_every=0.5)
    def handsfree_status():

        snapshot = (
            state.snapshot()
        )


        if (
            snapshot["mode"]
            == "waiting"
        ):

            st.markdown(
                '<div class="mn-record-state">'
                '<span class="mn-record-dot"></span>'
                '<div class="mn-record-copy">'
                '<div class="mn-record-label">Listening</div>'
                '<div class="mn-record-detail">'
                'Say &quot;start recording&quot; to begin.'
                '</div>'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )


        elif (
            snapshot["mode"]
            == "recording"
        ):

            st.markdown(
                '<div class="mn-record-state recording">'
                '<span class="mn-record-dot"></span>'
                '<div class="mn-record-copy">'
                '<div class="mn-record-label">Recording</div>'
                '<div class="mn-record-detail">'
                'Audio capture is active. Speak normally.'
                '</div>'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )


        elif (
            snapshot["mode"]
            == "processing"
        ):

            st.markdown(
                '<div class="mn-record-state ready">'
                '<span class="mn-record-dot"></span>'
                '<div class="mn-record-copy">'
                '<div class="mn-record-label">Processing audio</div>'
                '<div class="mn-record-detail">'
                'Recording complete. Preparing the consultation.'
                '</div>'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )


        # ================================================
        # AUDIO COMPLETED
        # ================================================

        if snapshot[
            "has_completed_audio"
        ]:

            audio_bytes = (
                state
                .pop_completed_audio()
            )


            if audio_bytes:

                st.session_state[
                    "pending_handsfree_audio"
                ] = audio_bytes


                with state.lock:

                    state.mode = (
                        "waiting"
                    )


                    state.status = (
                        'Listening for '
                        '"start recording"...'
                    )


                audio_bytes = None


                st.rerun()


    handsfree_status()