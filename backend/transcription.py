import os
import time

from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI

from backend.langfuse_service import (
    get_langfuse_client,
    safe_langfuse_metadata,
    should_capture_clinical_data,
)


load_dotenv()


# ============================================================
# ENVIRONMENT
# ============================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY",
    "",
).strip()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "",
).strip()


if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is missing from .env"
    )


groq_client = Groq(
    api_key=GROQ_API_KEY
)


# OpenAI is optional.
# It is used ONLY if both Groq transcription
# models fail.

openai_client = None

if OPENAI_API_KEY:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY
    )


# ============================================================
# MODELS
# ============================================================

PRIMARY_TRANSCRIPTION_MODEL = (
    "whisper-large-v3"
)

FALLBACK_TRANSCRIPTION_MODEL = (
    "whisper-large-v3-turbo"
)

OPENAI_TRANSCRIPTION_MODEL = (
    "gpt-transcribe"
)

FORMATTER_MODEL = (
    "openai/gpt-oss-20b"
)


# ============================================================
# CURRENT GROQ PRICING
# ============================================================

WHISPER_PRICE_PER_HOUR = {
    "whisper-large-v3": 0.111,
    "whisper-large-v3-turbo": 0.04,
}


FORMATTER_INPUT_PRICE_PER_MILLION = (
    0.075
)

FORMATTER_OUTPUT_PRICE_PER_MILLION = (
    0.30
)


# ============================================================
# LANGFUSE HELPERS
# ============================================================

def start_generation(
    *,
    name,
    model,
    metadata,
):

    try:

        langfuse = get_langfuse_client()

        if not langfuse:
            return None

        return langfuse.start_observation(
            name=name,
            as_type="generation",
            model=model,
            metadata=metadata,
        )

    except Exception as error:

        print(
            "Langfuse observation unavailable:",
            type(error).__name__,
        )

        return None


def end_generation(
    generation,
    *,
    output=None,
    metadata=None,
    usage_details=None,
    cost_details=None,
    error=None,
):

    if not generation:
        return

    try:

        update_data = {}

        if output is not None:
            update_data["output"] = output

        if metadata is not None:
            update_data["metadata"] = metadata

        if usage_details is not None:
            update_data[
                "usage_details"
            ] = usage_details

        if cost_details is not None:
            update_data[
                "cost_details"
            ] = cost_details

        if error is not None:

            update_data["level"] = "ERROR"

            update_data[
                "status_message"
            ] = type(error).__name__

        generation.update(
            **update_data
        )

        generation.end()

    except Exception as error:

        print(
            "Langfuse observation update failed:",
            type(error).__name__,
        )


# ============================================================
# TOKEN HELPER
# ============================================================

def get_token_usage(response):

    usage = getattr(
        response,
        "usage",
        None,
    )

    if not usage:
        return {
            "input": 0,
            "output": 0,
            "total": 0,
        }

    input_tokens = getattr(
        usage,
        "prompt_tokens",
        0,
    ) or 0

    output_tokens = getattr(
        usage,
        "completion_tokens",
        0,
    ) or 0

    total_tokens = getattr(
        usage,
        "total_tokens",
        input_tokens + output_tokens,
    ) or (
        input_tokens
        + output_tokens
    )

    return {
        "input": int(input_tokens),
        "output": int(output_tokens),
        "total": int(total_tokens),
    }


# ============================================================
# FORMATTER COST
# ============================================================

def calculate_formatter_cost(
    token_usage,
):

    input_tokens = token_usage[
        "input"
    ]

    output_tokens = token_usage[
        "output"
    ]

    input_cost = (
        input_tokens
        / 1_000_000
    ) * FORMATTER_INPUT_PRICE_PER_MILLION

    output_cost = (
        output_tokens
        / 1_000_000
    ) * FORMATTER_OUTPUT_PRICE_PER_MILLION

    total_cost = (
        input_cost
        + output_cost
    )

    return {
        "input": round(
            input_cost,
            8,
        ),
        "output": round(
            output_cost,
            8,
        ),
        "total": round(
            total_cost,
            8,
        ),
    }


# ============================================================
# WHISPER COST
# ============================================================

def calculate_whisper_cost(
    *,
    model,
    duration_seconds,
):

    price_per_hour = (
        WHISPER_PRICE_PER_HOUR.get(
            model
        )
    )

    if price_per_hour is None:
        return None

    billed_seconds = max(
        float(duration_seconds),
        10.0,
    )

    total_cost = (
        billed_seconds
        / 3600
    ) * price_per_hour

    return {
        "audio": round(
            total_cost,
            8,
        ),
        "total": round(
            total_cost,
            8,
        ),
    }


# ============================================================
# AUDIO DURATION
# ============================================================

def get_audio_duration(
    transcription,
):

    duration = getattr(
        transcription,
        "duration",
        None,
    )

    if duration is not None:

        try:
            return float(
                duration
            )

        except (
            TypeError,
            ValueError,
        ):
            pass

    segments = getattr(
        transcription,
        "segments",
        None,
    )

    if segments:

        try:

            last_segment = (
                segments[-1]
            )

            end_time = getattr(
                last_segment,
                "end",
                None,
            )

            if end_time is not None:
                return float(
                    end_time
                )

        except Exception:
            pass

    return None


# ============================================================
# TRANSCRIPT FORMATTER
# ============================================================

def format_transcript(
    raw_transcript: str,
    session_id: str | None = None,
):

    if not raw_transcript:
        return ""

    start_time = (
        time.perf_counter()
    )

    generation = start_generation(
        name="transcript-formatting",
        model=FORMATTER_MODEL,
        metadata=safe_langfuse_metadata(
            component="transcript_formatting",
            provider="groq",
            model=FORMATTER_MODEL,
            status="started",
            session_id=session_id,
            transcript_length=len(
                raw_transcript
            ),
            fallback_used=False,
        ),
    )

    formatter_prompt = """
You are formatting a medical consultation transcript.

Convert the transcript into a clear dialogue.

Use only these labels:

Doctor:
Patient:

Rules:
- Do not add medical information.
- Do not invent missing words.
- Do not diagnose anything.
- Preserve the meaning of the conversation.
- Only organize the existing transcript.
"""

    try:

        response = (
            groq_client
            .chat
            .completions
            .create(
                model=FORMATTER_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": formatter_prompt,
                    },
                    {
                        "role": "user",
                        "content": raw_transcript,
                    },
                ],
                temperature=0.1,
                max_tokens=2500,
            )
        )

        formatted_transcript = (
            response
            .choices[0]
            .message
            .content
            .strip()
        )

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        token_usage = (
            get_token_usage(
                response
            )
        )

        cost_details = (
            calculate_formatter_cost(
                token_usage
            )
        )

        langfuse_output = None

        if should_capture_clinical_data():
            langfuse_output = (
                formatted_transcript
            )

        metadata = (
            safe_langfuse_metadata(
                component="transcript_formatting",
                provider="groq",
                model=FORMATTER_MODEL,
                status="success",
                session_id=session_id,
                transcript_length=len(
                    formatted_transcript
                ),
                latency_ms=latency_ms,
                fallback_used=False,
            )
        )

        metadata[
            "latency_seconds"
        ] = round(
            latency_ms / 1000,
            3,
        )

        metadata[
            "input_tokens"
        ] = token_usage["input"]

        metadata[
            "output_tokens"
        ] = token_usage["output"]

        metadata[
            "total_tokens"
        ] = token_usage["total"]

        metadata[
            "estimated_cost_usd"
        ] = cost_details["total"]

        end_generation(
            generation,
            output=langfuse_output,
            metadata=metadata,
            usage_details={
                "input": token_usage["input"],
                "output": token_usage["output"],
                "total": token_usage["total"],
            },
            cost_details=cost_details,
        )

        print(
            "Transcript formatting:",
            f"{latency_ms / 1000:.3f}s",
            "| tokens:",
            token_usage["total"],
            "| cost: $",
            cost_details["total"],
        )

        return formatted_transcript

    except Exception as error:

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        end_generation(
            generation,
            metadata=safe_langfuse_metadata(
                component="transcript_formatting",
                provider="groq",
                model=FORMATTER_MODEL,
                status="failed",
                session_id=session_id,
                latency_ms=latency_ms,
                fallback_used=False,
                error_type=type(
                    error
                ).__name__,
            ),
            error=error,
        )

        print(
            "Transcript formatter failed:",
            type(error).__name__,
        )

        return raw_transcript


# ============================================================
# GROQ TRANSCRIPTION ATTEMPT
# ============================================================

def transcribe_with_model(
    *,
    audio_bytes: bytes,
    filename: str,
    model: str,
    session_id: str | None,
    fallback_used: bool,
):

    start_time = (
        time.perf_counter()
    )

    observation_name = (
        "audio-transcription-fallback"
        if fallback_used
        else "audio-transcription-primary"
    )

    generation = start_generation(
        name=observation_name,
        model=model,
        metadata=safe_langfuse_metadata(
            component="audio_transcription",
            provider="groq",
            model=model,
            status="started",
            session_id=session_id,
            audio_size=len(
                audio_bytes
            ),
            fallback_used=fallback_used,
        ),
    )

    try:

        transcription = (
            groq_client
            .audio
            .transcriptions
            .create(
                file=(
                    filename,
                    audio_bytes,
                ),
                model=model,
                response_format="verbose_json",
                timestamp_granularities=[
                    "segment"
                ],
            )
        )

        raw_transcript = (
            getattr(
                transcription,
                "text",
                "",
            )
            or ""
        ).strip()

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        duration_seconds = (
            get_audio_duration(
                transcription
            )
        )

        cost_details = None

        if duration_seconds is not None:

            cost_details = (
                calculate_whisper_cost(
                    model=model,
                    duration_seconds=duration_seconds,
                )
            )

        metadata = safe_langfuse_metadata(
            component="audio_transcription",
            provider="groq",
            model=model,
            status="success",
            session_id=session_id,
            audio_size=len(
                audio_bytes
            ),
            transcript_length=len(
                raw_transcript
            ),
            latency_ms=latency_ms,
            fallback_used=fallback_used,
        )

        metadata[
            "latency_seconds"
        ] = round(
            latency_ms / 1000,
            3,
        )

        if duration_seconds is not None:

            metadata[
                "audio_duration_seconds"
            ] = round(
                duration_seconds,
                3,
            )

        if cost_details:

            metadata[
                "estimated_cost_usd"
            ] = cost_details["total"]

        langfuse_output = None

        if should_capture_clinical_data():
            langfuse_output = raw_transcript

        end_generation(
            generation,
            output=langfuse_output,
            metadata=metadata,
            cost_details=cost_details,
        )

        print(
            observation_name,
            "| provider: groq",
            "| model:",
            model,
            "| time:",
            f"{latency_ms / 1000:.3f}s",
        )

        return raw_transcript

    except Exception as error:

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        end_generation(
            generation,
            metadata=safe_langfuse_metadata(
                component="audio_transcription",
                provider="groq",
                model=model,
                status="failed",
                session_id=session_id,
                audio_size=len(
                    audio_bytes
                ),
                latency_ms=latency_ms,
                fallback_used=fallback_used,
                error_type=type(
                    error
                ).__name__,
            ),
            error=error,
        )

        raise


# ============================================================
# OPENAI PROVIDER FALLBACK
# ============================================================

def transcribe_with_openai(
    *,
    audio_bytes: bytes,
    filename: str,
    session_id: str | None,
):

    if openai_client is None:

        raise RuntimeError(
            "OpenAI emergency fallback is not configured."
        )

    start_time = (
        time.perf_counter()
    )

    generation = start_generation(
        name="audio-transcription-provider-fallback",
        model=OPENAI_TRANSCRIPTION_MODEL,
        metadata=safe_langfuse_metadata(
            component="audio_transcription",
            provider="openai",
            model=OPENAI_TRANSCRIPTION_MODEL,
            status="started",
            session_id=session_id,
            audio_size=len(
                audio_bytes
            ),
            fallback_used=True,
        ),
    )

    try:

        transcription = (
            openai_client
            .audio
            .transcriptions
            .create(
                model=OPENAI_TRANSCRIPTION_MODEL,
                file=(
                    filename,
                    audio_bytes,
                ),
            )
        )

        raw_transcript = (
            getattr(
                transcription,
                "text",
                "",
            )
            or ""
        ).strip()

        if not raw_transcript:

            raise RuntimeError(
                "OpenAI returned an empty transcription."
            )

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        metadata = safe_langfuse_metadata(
            component="audio_transcription",
            provider="openai",
            model=OPENAI_TRANSCRIPTION_MODEL,
            status="success",
            session_id=session_id,
            audio_size=len(
                audio_bytes
            ),
            transcript_length=len(
                raw_transcript
            ),
            latency_ms=latency_ms,
            fallback_used=True,
        )

        metadata[
            "latency_seconds"
        ] = round(
            latency_ms / 1000,
            3,
        )

        langfuse_output = None

        if should_capture_clinical_data():
            langfuse_output = raw_transcript

        end_generation(
            generation,
            output=langfuse_output,
            metadata=metadata,
        )

        print(
            "Emergency provider fallback succeeded",
            "| provider: openai",
            "| model:",
            OPENAI_TRANSCRIPTION_MODEL,
            "| time:",
            f"{latency_ms / 1000:.3f}s",
        )

        return raw_transcript

    except Exception as error:

        latency_ms = round(
            (
                time.perf_counter()
                - start_time
            )
            * 1000,
            2,
        )

        end_generation(
            generation,
            metadata=safe_langfuse_metadata(
                component="audio_transcription",
                provider="openai",
                model=OPENAI_TRANSCRIPTION_MODEL,
                status="failed",
                session_id=session_id,
                audio_size=len(
                    audio_bytes
                ),
                latency_ms=latency_ms,
                fallback_used=True,
                error_type=type(
                    error
                ).__name__,
            ),
            error=error,
        )

        raise


# ============================================================
# AUDIO TRANSCRIPTION WITH PROVIDER FALLBACK
# ============================================================

def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "consultation.wav",
    session_id: str | None = None,
):

    if not audio_bytes:

        raise ValueError(
            "Audio file is empty."
        )

    try:

        raw_transcript = (
            transcribe_with_model(
                audio_bytes=audio_bytes,
                filename=filename,
                model=PRIMARY_TRANSCRIPTION_MODEL,
                session_id=session_id,
                fallback_used=False,
            )
        )

        print(
            "Primary transcription model used:",
            PRIMARY_TRANSCRIPTION_MODEL,
        )

    except Exception as primary_error:

        print(
            "Primary transcription failed:",
            type(
                primary_error
            ).__name__,
        )

        print(
            "Switching to Groq fallback:",
            FALLBACK_TRANSCRIPTION_MODEL,
        )

        try:

            raw_transcript = (
                transcribe_with_model(
                    audio_bytes=audio_bytes,
                    filename=filename,
                    model=FALLBACK_TRANSCRIPTION_MODEL,
                    session_id=session_id,
                    fallback_used=True,
                )
            )

            print(
                "Groq fallback transcription succeeded:",
                FALLBACK_TRANSCRIPTION_MODEL,
            )

        except Exception as groq_fallback_error:

            print(
                "Groq fallback transcription failed:",
                type(
                    groq_fallback_error
                ).__name__,
            )

            print(
                "Switching to emergency OpenAI provider fallback."
            )

            try:

                raw_transcript = (
                    transcribe_with_openai(
                        audio_bytes=audio_bytes,
                        filename=filename,
                        session_id=session_id,
                    )
                )

            except Exception as openai_error:

                print(
                    "OpenAI provider fallback failed:",
                    type(
                        openai_error
                    ).__name__,
                )

                raise RuntimeError(
                    "All transcription providers failed."
                ) from openai_error

    formatted_transcript = (
        format_transcript(
            raw_transcript,
            session_id=session_id,
        )
    )

    return formatted_transcript