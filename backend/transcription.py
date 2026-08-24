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
# MODELS
# ============================================================

TRANSCRIPTION_MODEL = (
    "whisper-large-v3"
)

FORMATTER_MODEL = (
    "openai/gpt-oss-20b"
)


# ============================================================
# DOCTOR / PATIENT TRANSCRIPT FORMATTER
# ============================================================

def format_doctor_patient_transcript(
    transcript: str,
) -> str:
    """
    Convert raw transcription into a clean
    Doctor/Patient dialogue format.

    The formatter must not invent or remove
    clinical information.
    """

    if not transcript:
        return transcript


    prompt = f"""
You are formatting a medical consultation transcript.

Convert the raw transcript into a clean conversation
between a Doctor and a Patient.

Use exactly these speaker labels:

Doctor:
Patient:

IMPORTANT RULES:

1. Do not summarize the conversation.

2. Do not remove any information from the transcript.

3. Do not add or invent any medical information.

4. Preserve all important clinical information exactly,
including:

- Patient name
- Patient age
- Date
- Consultation time
- Symptoms
- Symptom duration
- Blood pressure
- Heart rate
- Temperature
- Oxygen saturation
- ECG information
- Diagnosis
- Medicine names
- Medicine dosage
- Medicine frequency
- Medicine duration
- Tests
- Doctor instructions
- Follow-up instructions

5. Correct only obvious punctuation,
capitalization and formatting problems.

6. Identify Doctor and Patient based on
the context of the conversation.

7. Every time the speaker changes,
start a new line.

8. Add one blank line between speakers.

9. Do not use any labels other than:

Doctor:
Patient:

10. If a sentence clearly contains the doctor
checking vitals, giving diagnosis, prescribing
medicine, recommending tests or giving instructions,
label it as Doctor.

11. If a sentence contains the patient's symptoms,
questions, personal information or response to
the doctor, label it as Patient.

12. Do not change medical facts.

13. Return only the formatted transcript.
Do not provide explanations or notes.


RAW TRANSCRIPT:

{transcript}
"""


    try:

        response = (
            client.chat.completions.create(
                model=FORMATTER_MODEL,

                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a medical transcript "
                            "formatter. Your job is only to "
                            "separate doctor and patient speech "
                            "without changing clinical meaning."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],

                temperature=0.0,
            )
        )


        formatted_transcript = (
            response
            .choices[0]
            .message
            .content
            or ""
        ).strip()


        if not formatted_transcript:
            return transcript


        return formatted_transcript


    except Exception as error:

        print(
            "Transcript formatting failed. "
            "Using original transcript instead."
        )

        print(
            f"Formatter error: {str(error)}"
        )

        return transcript


# ============================================================
# TRANSCRIPTION FUNCTION
# ============================================================

def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
) -> str:
    """
    Convert doctor-patient audio into text,
    format it as Doctor/Patient dialogue,
    and trace transcription in Langfuse.
    """


    # ========================================================
    # VALIDATE AUDIO
    # ========================================================

    if not audio_bytes:
        raise ValueError(
            "Audio file is empty."
        )


    # ========================================================
    # LANGFUSE CLIENT
    # ========================================================

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

        # ====================================================
        # LANGFUSE GENERATION TRACE
        # ====================================================

        with langfuse.start_as_current_observation(
            as_type="generation",

            name="consultation-transcription",

            model=TRANSCRIPTION_MODEL,

            input=trace_input,
        ) as generation:


            # =================================================
            # PREPARE AUDIO FILE
            # =================================================

            audio_file = BytesIO(
                audio_bytes
            )


            audio_file.name = (
                filename
            )


            # =================================================
            # GROQ WHISPER TRANSCRIPTION
            # =================================================

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


            # =================================================
            # RAW TRANSCRIPT
            # =================================================

            raw_transcript = (
                transcription.text
                or ""
            ).strip()


            # =================================================
            # CHECK SPEECH
            # =================================================

            if not raw_transcript:

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
            # FORMAT AS DOCTOR / PATIENT
            # =================================================

            transcript = (
                format_doctor_patient_transcript(
                    raw_transcript
                )
            )


            # =================================================
            # PRIVACY-AWARE LANGFUSE OUTPUT
            # =================================================

            if should_capture_clinical_data():

                generation.update(
                    output={
                        "raw_transcript": (
                            raw_transcript
                        ),

                        "formatted_transcript": (
                            transcript
                        ),
                    }
                )


            else:

                generation.update(
                    output={
                        "transcription_successful": True,

                        "raw_transcript_characters": len(
                            raw_transcript
                        ),

                        "formatted_transcript_characters": len(
                            transcript
                        ),

                        "clinical_content_logged": False,
                    }
                )


            # =================================================
            # RETURN FORMATTED TRANSCRIPT
            # =================================================

            return transcript


    except ValueError:

        raise


    except Exception as error:

        raise RuntimeError(
            "Audio transcription failed: "
            f"{str(error)}"
        ) from error