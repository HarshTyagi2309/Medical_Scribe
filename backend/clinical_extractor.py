import json
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


openai_client = (
    OpenAI(
        api_key=OPENAI_API_KEY
    )
    if OPENAI_API_KEY
    else None
)


# ============================================================
# MODELS
# ============================================================

PRIMARY_EXTRACTION_MODEL = (
    "openai/gpt-oss-20b"
)

FALLBACK_EXTRACTION_MODEL = (
    "qwen/qwen3.6-27b"
)

OPENAI_EMERGENCY_EXTRACTION_MODEL = (
    "gpt-4.1-mini"
)


# ============================================================
# MODEL PRICING PER 1 MILLION TOKENS
# ============================================================

MODEL_PRICING = {
    "openai/gpt-oss-20b": {
        "input": 0.075,
        "output": 0.30,
    },
    "qwen/qwen3.6-27b": {
        "input": 0.60,
        "output": 3.00,
    },
}


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
            "Langfuse extraction observation unavailable:",
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

            update_data[
                "level"
            ] = "ERROR"

            update_data[
                "status_message"
            ] = type(error).__name__

        generation.update(
            **update_data
        )

        generation.end()

    except Exception as error:

        print(
            "Langfuse extraction update failed:",
            type(error).__name__,
        )


# ============================================================
# TOKEN USAGE
# ============================================================

def get_token_usage(
    response,
):

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
        input_tokens
        + output_tokens,
    ) or (
        input_tokens
        + output_tokens
    )

    return {
        "input": int(
            input_tokens
        ),
        "output": int(
            output_tokens
        ),
        "total": int(
            total_tokens
        ),
    }


# ============================================================
# COST CALCULATION
# ============================================================

def calculate_model_cost(
    *,
    model,
    token_usage,
):

    pricing = MODEL_PRICING.get(
        model
    )

    if not pricing:
        return None

    input_cost = (
        token_usage["input"]
        / 1_000_000
    ) * pricing["input"]

    output_cost = (
        token_usage["output"]
        / 1_000_000
    ) * pricing["output"]

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
# DEFAULT CLINICAL DATA
# ============================================================

def empty_clinical_data():

    return {
        "patient_name": None,
        "chief_complaint": None,
        "symptoms": [],
        "vitals": {
            "blood_pressure": None,
            "heart_rate": None,
            "temperature": None,
            "oxygen_saturation": None,
        },
        "diagnosis": None,
        "medications": [],
        "recommended_tests": [],
        "doctor_instructions": [],
        "follow_up": None,
    }


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_clinical_data(
    data,
):

    result = (
        empty_clinical_data()
    )

    if not isinstance(
        data,
        dict,
    ):
        return result

    result[
        "patient_name"
    ] = data.get(
        "patient_name"
    )

    result[
        "chief_complaint"
    ] = data.get(
        "chief_complaint"
    )

    if isinstance(
        data.get(
            "symptoms"
        ),
        list,
    ):
        result[
            "symptoms"
        ] = data[
            "symptoms"
        ]

    vitals = data.get(
        "vitals"
    )

    if isinstance(
        vitals,
        dict,
    ):

        result[
            "vitals"
        ] = {
            "blood_pressure": vitals.get(
                "blood_pressure"
            ),
            "heart_rate": vitals.get(
                "heart_rate"
            ),
            "temperature": vitals.get(
                "temperature"
            ),
            "oxygen_saturation": vitals.get(
                "oxygen_saturation"
            ),
        }

    result[
        "diagnosis"
    ] = data.get(
        "diagnosis"
    )

    for key in [
        "medications",
        "recommended_tests",
        "doctor_instructions",
    ]:

        value = data.get(
            key
        )

        if isinstance(
            value,
            list,
        ):
            result[
                key
            ] = value

    result[
        "follow_up"
    ] = data.get(
        "follow_up"
    )

    return result


# ============================================================
# EXTRACTION PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a medical documentation extraction assistant.

Extract ONLY information explicitly stated in the consultation.

STRICT RULES:

1. Never invent information.
2. Never infer a diagnosis.
3. Diagnosis must only be included if explicitly stated by the doctor.
4. Never infer a patient name.
5. If information is missing, return null or [].
6. Do not add medical advice.
7. Do not guess unclear words.
8. Preserve medications exactly as stated.

Return ONLY valid JSON.

Structure:

{
  "patient_name": null,
  "chief_complaint": null,
  "symptoms": [],
  "vitals": {
    "blood_pressure": null,
    "heart_rate": null,
    "temperature": null,
    "oxygen_saturation": null
  },
  "diagnosis": null,
  "medications": [
    {
      "name": null,
      "dosage": null,
      "frequency": null,
      "duration": null,
      "route": null
    }
  ],
  "recommended_tests": [],
  "doctor_instructions": [],
  "follow_up": null
}
"""


# ============================================================
# GROQ EXTRACTION
# ============================================================

def extract_with_model(
    *,
    transcript,
    model,
    session_id,
    fallback_used,
):

    start_time = (
        time.perf_counter()
    )

    observation_name = (
        "clinical-extraction-fallback"
        if fallback_used
        else "clinical-extraction-primary"
    )

    generation = start_generation(
        name=observation_name,
        model=model,
        metadata=safe_langfuse_metadata(
            component="clinical_extraction",
            provider="groq",
            model=model,
            status="started",
            session_id=session_id,
            transcript_length=len(
                transcript
            ),
            fallback_used=fallback_used,
        ),
    )

    try:

        response = (
            groq_client
            .chat
            .completions
            .create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": transcript,
                    },
                ],
                response_format={
                    "type": "json_object"
                },
                temperature=0.1,
                max_tokens=2500,
            )
        )

        raw_result = (
            response
            .choices[0]
            .message
            .content
        )

        parsed_result = json.loads(
            raw_result
        )

        clinical_data = (
            normalize_clinical_data(
                parsed_result
            )
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
            calculate_model_cost(
                model=model,
                token_usage=token_usage,
            )
        )

        metadata = (
            safe_langfuse_metadata(
                component="clinical_extraction",
                provider="groq",
                model=model,
                status="success",
                session_id=session_id,
                transcript_length=len(
                    transcript
                ),
                latency_ms=latency_ms,
                fallback_used=fallback_used,
            )
        )

        metadata.update(
            {
                "latency_seconds": round(
                    latency_ms
                    / 1000,
                    3,
                ),
                "input_tokens": token_usage[
                    "input"
                ],
                "output_tokens": token_usage[
                    "output"
                ],
                "total_tokens": token_usage[
                    "total"
                ],
                "symptom_count": len(
                    clinical_data[
                        "symptoms"
                    ]
                ),
                "medication_count": len(
                    clinical_data[
                        "medications"
                    ]
                ),
                "recommended_test_count": len(
                    clinical_data[
                        "recommended_tests"
                    ]
                ),
                "instruction_count": len(
                    clinical_data[
                        "doctor_instructions"
                    ]
                ),
                "diagnosis_present": bool(
                    clinical_data[
                        "diagnosis"
                    ]
                ),
                "patient_name_present": bool(
                    clinical_data[
                        "patient_name"
                    ]
                ),
            }
        )

        if cost_details:

            metadata[
                "estimated_cost_usd"
            ] = cost_details[
                "total"
            ]

        langfuse_output = None

        if (
            should_capture_clinical_data()
        ):
            langfuse_output = (
                clinical_data
            )

        end_generation(
            generation,
            output=langfuse_output,
            metadata=metadata,
            usage_details={
                "input": token_usage[
                    "input"
                ],
                "output": token_usage[
                    "output"
                ],
                "total": token_usage[
                    "total"
                ],
            },
            cost_details=cost_details,
        )

        print(
            observation_name,
            "| provider: groq",
            "| model:",
            model,
            "| time:",
            f"{latency_ms / 1000:.3f}s",
            "| tokens:",
            token_usage[
                "total"
            ],
            "| cost:",
            (
                f"${cost_details['total']}"
                if cost_details
                else "unknown"
            ),
        )

        return clinical_data

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
            metadata=(
                safe_langfuse_metadata(
                    component="clinical_extraction",
                    provider="groq",
                    model=model,
                    status="failed",
                    session_id=session_id,
                    transcript_length=len(
                        transcript
                    ),
                    latency_ms=latency_ms,
                    fallback_used=fallback_used,
                    error_type=(
                        type(
                            error
                        ).__name__
                    ),
                )
            ),
            error=error,
        )

        raise


# ============================================================
# OPENAI EMERGENCY EXTRACTION
# ============================================================

def extract_with_openai(
    *,
    transcript,
    session_id,
):

    if not openai_client:

        raise RuntimeError(
            "OPENAI_API_KEY is not configured."
        )

    start_time = (
        time.perf_counter()
    )

    generation = start_generation(
        name=(
            "clinical-extraction-openai-emergency"
        ),
        model=(
            OPENAI_EMERGENCY_EXTRACTION_MODEL
        ),
        metadata=safe_langfuse_metadata(
            component="clinical_extraction",
            provider="openai",
            model=(
                OPENAI_EMERGENCY_EXTRACTION_MODEL
            ),
            status="started",
            session_id=session_id,
            transcript_length=len(
                transcript
            ),
            fallback_used=True,
        ),
    )

    try:

        response = (
            openai_client
            .chat
            .completions
            .create(
                model=(
                    OPENAI_EMERGENCY_EXTRACTION_MODEL
                ),
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": transcript,
                    },
                ],
                response_format={
                    "type": "json_object"
                },
                temperature=0.1,
                max_tokens=2500,
            )
        )

        raw_result = (
            response
            .choices[0]
            .message
            .content
        )

        if not raw_result:

            raise ValueError(
                "OpenAI returned an empty extraction response."
            )

        parsed_result = json.loads(
            raw_result
        )

        clinical_data = (
            normalize_clinical_data(
                parsed_result
            )
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

        metadata = (
            safe_langfuse_metadata(
                component="clinical_extraction",
                provider="openai",
                model=(
                    OPENAI_EMERGENCY_EXTRACTION_MODEL
                ),
                status="success",
                session_id=session_id,
                transcript_length=len(
                    transcript
                ),
                latency_ms=latency_ms,
                fallback_used=True,
            )
        )

        metadata.update(
            {
                "latency_seconds": round(
                    latency_ms
                    / 1000,
                    3,
                ),
                "input_tokens": token_usage[
                    "input"
                ],
                "output_tokens": token_usage[
                    "output"
                ],
                "total_tokens": token_usage[
                    "total"
                ],
                "symptom_count": len(
                    clinical_data[
                        "symptoms"
                    ]
                ),
                "medication_count": len(
                    clinical_data[
                        "medications"
                    ]
                ),
                "recommended_test_count": len(
                    clinical_data[
                        "recommended_tests"
                    ]
                ),
                "instruction_count": len(
                    clinical_data[
                        "doctor_instructions"
                    ]
                ),
                "diagnosis_present": bool(
                    clinical_data[
                        "diagnosis"
                    ]
                ),
                "patient_name_present": bool(
                    clinical_data[
                        "patient_name"
                    ]
                ),
            }
        )

        langfuse_output = None

        if (
            should_capture_clinical_data()
        ):
            langfuse_output = (
                clinical_data
            )

        end_generation(
            generation,
            output=langfuse_output,
            metadata=metadata,
            usage_details={
                "input": token_usage[
                    "input"
                ],
                "output": token_usage[
                    "output"
                ],
                "total": token_usage[
                    "total"
                ],
            },
        )

        print(
            "clinical-extraction-openai-emergency",
            "| provider: openai",
            "| model:",
            OPENAI_EMERGENCY_EXTRACTION_MODEL,
            "| time:",
            f"{latency_ms / 1000:.3f}s",
            "| tokens:",
            token_usage[
                "total"
            ],
        )

        return clinical_data

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
            metadata=(
                safe_langfuse_metadata(
                    component="clinical_extraction",
                    provider="openai",
                    model=(
                        OPENAI_EMERGENCY_EXTRACTION_MODEL
                    ),
                    status="failed",
                    session_id=session_id,
                    transcript_length=len(
                        transcript
                    ),
                    latency_ms=latency_ms,
                    fallback_used=True,
                    error_type=(
                        type(
                            error
                        ).__name__
                    ),
                )
            ),
            error=error,
        )

        raise


# ============================================================
# EXTRACTION WITH AUTOMATIC FALLBACK
# ============================================================

def extract_clinical_data(
    transcript: str,
    session_id: str | None = None,
):

    if not transcript:

        return (
            empty_clinical_data()
        )

    # ========================================================
    # 1. GROQ PRIMARY
    # ========================================================

    try:

        result = extract_with_model(
            transcript=transcript,
            model=PRIMARY_EXTRACTION_MODEL,
            session_id=session_id,
            fallback_used=False,
        )

        print(
            "Primary extraction model used:",
            PRIMARY_EXTRACTION_MODEL,
        )

        return result

    except Exception as primary_error:

        print(
            "Primary clinical extraction failed:",
            type(
                primary_error
            ).__name__,
        )

    # ========================================================
    # 2. GROQ FALLBACK
    # ========================================================

    print(
        "Switching to Groq extraction fallback:",
        FALLBACK_EXTRACTION_MODEL,
    )

    try:

        result = extract_with_model(
            transcript=transcript,
            model=FALLBACK_EXTRACTION_MODEL,
            session_id=session_id,
            fallback_used=True,
        )

        print(
            "Groq fallback clinical extraction succeeded:",
            FALLBACK_EXTRACTION_MODEL,
        )

        return result

    except Exception as fallback_error:

        print(
            "Groq fallback clinical extraction failed:",
            type(
                fallback_error
            ).__name__,
        )

    # ========================================================
    # 3. OPENAI EMERGENCY FALLBACK
    # ========================================================

    print(
        "Switching to OpenAI emergency extraction:",
        OPENAI_EMERGENCY_EXTRACTION_MODEL,
    )

    try:

        result = extract_with_openai(
            transcript=transcript,
            session_id=session_id,
        )

        print(
            "OpenAI emergency clinical extraction succeeded:",
            OPENAI_EMERGENCY_EXTRACTION_MODEL,
        )

        return result

    except Exception as openai_error:

        print(
            "OpenAI emergency clinical extraction failed:",
            type(
                openai_error
            ).__name__,
        )

        raise RuntimeError(
            "All clinical extraction providers failed."
        ) from openai_error