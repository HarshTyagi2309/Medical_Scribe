import os
from io import BytesIO

from dotenv import load_dotenv
from groq import Groq

from backend.langfuse_service import (
    get_langfuse_client,
    should_capture_clinical_data,
)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)


if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY not found. "
        "Please add it to your .env file."
    )


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=GROQ_API_KEY
)


# ============================================================
# MODEL
# ============================================================

TRANSCRIPTION_MODEL = (
    "whisper-large-v3"
)


# ============================================================
# TRANSCRIPTION FUNCTION
# ============================================================

def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
) -> str:
    """
    Convert doctor-patient audio into text
    and trace transcription in Langfuse.
    """

    if not audio_bytes:
        raise ValueError(
            "Audio file is empty."
        )

    langfuse = (
        get_langfuse_client()
    )

    trace_input = {
        "filename": filename,
        "audio_size_bytes": len(
            audio_bytes
        ),
    }


    try:

        with langfuse.start_as_current_observation(
            as_type="generation",
            name="consultation-transcription",
            model=TRANSCRIPTION_MODEL,
            input=trace_input,
        ) as generation:

            audio_file = BytesIO(
                audio_bytes
            )

            audio_file.name = (
                filename
            )


            transcription = (
                client.audio.transcriptions.create(
                    file=(
                        filename,
                        audio_file.read(),
                    ),

                    model=(
                        TRANSCRIPTION_MODEL
                    ),

                    response_format="json",

                    temperature=0.0,
                )
            )


            transcript = (
                transcription.text
                or ""
            ).strip()


            if not transcript:

                generation.update(
                    level="ERROR",

                    status_message=(
                        "No speech detected "
                        "in consultation audio."
                    ),
                )

                raise ValueError(
                    "No speech could be detected "
                    "in the uploaded audio."
                )


            # =================================================
            # PRIVACY-AWARE LANGFUSE OUTPUT
            # =================================================

            if should_capture_clinical_data():

                generation.update(
                    output={
                        "transcript": transcript
                    }
                )

            else:

                generation.update(
                    output={
                        "transcription_successful": True,

                        "transcript_characters": len(
                            transcript
                        ),

                        "clinical_content_logged": False,
                    }
                )


            return transcript


    except Exception as error:

        raise RuntimeError(
            "Audio transcription failed: "
            f"{str(error)}"
        ) from error