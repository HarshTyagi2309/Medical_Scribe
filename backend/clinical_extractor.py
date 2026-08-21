import json
import os

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
        "GROQ_API_KEY not found in .env"
    )


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=GROQ_API_KEY
)


CLINICAL_MODEL = (
    "openai/gpt-oss-20b"
)


# ============================================================
# EXTRACTION PROMPT
# ============================================================

EXTRACTION_PROMPT = """
You are a clinical information extraction system.

Extract information ONLY from the supplied doctor-patient
consultation transcript.

DO NOT provide medical advice.

============================================================
CRITICAL SAFETY RULES
============================================================

1. Never invent information.

2. Never guess the patient's name.

3. Only return the patient's name when it is explicitly spoken
   in the conversation.

4. If the patient's name is not explicitly spoken, return:

   "patient_name": "Not in audio"

5. Never infer a disease or diagnosis from symptoms.

6. Only populate "diagnosis" if a diagnosis/disease is explicitly
   stated in the consultation.

7. Never invent:
   - medicines
   - doses
   - frequency
   - duration
   - route
   - tests
   - vitals
   - instructions
   - follow-up

8. Missing information must be null or an empty list.

9. The transcript may contain Hindi, English, or Hinglish.

============================================================
MEDICATION RULES
============================================================

For EACH medicine, carefully extract separately:

- medicine name
- dosage
- frequency
- duration
- route

Examples:

"Paracetamol 500 mg din mein do baar teen din ke liye"

must produce approximately:

{
  "name": "Paracetamol",
  "dosage": "500 mg",
  "frequency": "twice daily",
  "duration": "3 days",
  "route": null
}

"Amlodipine 5 mg once daily"

must produce:

{
  "name": "Amlodipine",
  "dosage": "5 mg",
  "frequency": "once daily",
  "duration": null,
  "route": null
}

Do not drop dosage, frequency, or duration when they are clearly
present in the transcript.

"medications" MUST ALWAYS be an array.

============================================================
VITAL RULES
============================================================

Extract when explicitly stated:

- blood_pressure
- heart_rate
- temperature
- oxygen_saturation

Preserve units when possible.

Examples:

"BP 140 by 90"
→ "140/90"

"heart rate 96 beats per minute"
→ "96 bpm"

"temperature 101 degrees Fahrenheit"
→ "101 F"

"oxygen saturation 97 percent"
→ "97%"

============================================================
FOLLOW-UP RULE
============================================================

Statements such as:

- follow up after 3 days
- come back next week
- visit after the reports
- review after 5 days

must be placed in "follow_up".

They may ALSO remain in doctor_instructions if appropriate.

============================================================
OUTPUT FORMAT
============================================================

Return ONLY valid JSON.

Do not use markdown.
Do not use ```json fences.
Do not add explanations.

Use exactly this structure:

{
  "patient_name": "Not in audio",
  "chief_complaint": null,
  "symptoms": [],
  "vitals": {
    "blood_pressure": null,
    "heart_rate": null,
    "temperature": null,
    "oxygen_saturation": null
  },
  "diagnosis": null,
  "medications": [],
  "recommended_tests": [],
  "doctor_instructions": [],
  "follow_up": null
}

Every medication must use:

{
  "name": "",
  "dosage": null,
  "frequency": null,
  "duration": null,
  "route": null
}

CONSULTATION TRANSCRIPT:

"""


# ============================================================
# NORMALIZATION HELPERS
# ============================================================

def as_list(value):

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def normalize_text(value):

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def normalize_text_list(value):

    result = []

    for item in as_list(value):

        text = normalize_text(
            item
        )

        if text:
            result.append(
                text
            )

    return result


def normalize_patient_name(value):

    value = normalize_text(
        value
    )

    if not value:
        return "Not in audio"

    invalid_values = {
        "unknown",
        "none",
        "null",
        "not mentioned",
        "not available",
        "n/a",
        "not in transcript",
    }

    if value.lower() in invalid_values:
        return "Not in audio"

    return value


def normalize_vitals(value):

    if not isinstance(
        value,
        dict,
    ):
        value = {}

    return {
        "blood_pressure": normalize_text(
            value.get(
                "blood_pressure"
            )
        ),

        "heart_rate": normalize_text(
            value.get(
                "heart_rate"
            )
        ),

        "temperature": normalize_text(
            value.get(
                "temperature"
            )
        ),

        "oxygen_saturation": normalize_text(
            value.get(
                "oxygen_saturation"
            )
        ),
    }


def normalize_medications(value):

    result = []

    for medicine in as_list(
        value
    ):

        if not isinstance(
            medicine,
            dict,
        ):
            continue

        name = normalize_text(
            medicine.get(
                "name"
            )
        )

        if not name:
            continue

        result.append(
            {
                "name": name,

                "dosage": normalize_text(
                    medicine.get(
                        "dosage"
                    )
                ),

                "frequency": normalize_text(
                    medicine.get(
                        "frequency"
                    )
                ),

                "duration": normalize_text(
                    medicine.get(
                        "duration"
                    )
                ),

                "route": normalize_text(
                    medicine.get(
                        "route"
                    )
                ),
            }
        )

    return result


def normalize_clinical_data(data):

    if not isinstance(
        data,
        dict,
    ):

        raise ValueError(
            "Clinical AI response must be a JSON object."
        )

    return {
        "patient_name": (
            normalize_patient_name(
                data.get(
                    "patient_name"
                )
            )
        ),

        "chief_complaint": (
            normalize_text(
                data.get(
                    "chief_complaint"
                )
            )
        ),

        "symptoms": (
            normalize_text_list(
                data.get(
                    "symptoms"
                )
            )
        ),

        "vitals": (
            normalize_vitals(
                data.get(
                    "vitals"
                )
            )
        ),

        "diagnosis": (
            normalize_text(
                data.get(
                    "diagnosis"
                )
            )
        ),

        "medications": (
            normalize_medications(
                data.get(
                    "medications"
                )
            )
        ),

        "recommended_tests": (
            normalize_text_list(
                data.get(
                    "recommended_tests"
                )
            )
        ),

        "doctor_instructions": (
            normalize_text_list(
                data.get(
                    "doctor_instructions"
                )
            )
        ),

        "follow_up": (
            normalize_text(
                data.get(
                    "follow_up"
                )
            )
        ),
    }


# ============================================================
# CLINICAL EXTRACTION
# ============================================================

def extract_clinical_data(
    transcript: str
) -> dict:

    if not transcript or not transcript.strip():

        raise ValueError(
            "Transcript cannot be empty."
        )


    langfuse = (
        get_langfuse_client()
    )


    if should_capture_clinical_data():

        langfuse_input = {
            "transcript": transcript
        }

    else:

        langfuse_input = {
            "transcript_characters": (
                len(transcript)
            ),

            "clinical_content_logged": False,
        }


    try:

        with langfuse.start_as_current_observation(

            as_type="generation",

            name="clinical-extraction",

            model=CLINICAL_MODEL,

            input=langfuse_input,

        ) as generation:


            response = (
                client.chat.completions.create(

                    model=CLINICAL_MODEL,

                    messages=[
                        {
                            "role": "user",

                            "content": (
                                EXTRACTION_PROMPT
                                + transcript
                            ),
                        }
                    ],

                    response_format={
                        "type": "json_object"
                    },

                    include_reasoning=False,

                    reasoning_effort="low",

                    temperature=0.1,

                    max_completion_tokens=2500,
                )
            )


            content = (
                response
                .choices[0]
                .message
                .content
            )


            if not content:

                generation.update(
                    level="ERROR",

                    status_message=(
                        "Clinical model returned empty output."
                    ),
                )

                raise RuntimeError(
                    "Clinical AI returned empty output."
                )


            raw_data = (
                json.loads(
                    content
                )
            )


            clinical_data = (
                normalize_clinical_data(
                    raw_data
                )
            )


            usage = getattr(
                response,
                "usage",
                None,
            )


            if (
                should_capture_clinical_data()
            ):

                trace_output = (
                    clinical_data
                )

            else:

                trace_output = {
                    "extraction_successful": True,

                    "patient_name_present": (
                        clinical_data[
                            "patient_name"
                        ]
                        != "Not in audio"
                    ),

                    "symptoms_count": len(
                        clinical_data[
                            "symptoms"
                        ]
                    ),

                    "medications_count": len(
                        clinical_data[
                            "medications"
                        ]
                    ),

                    "tests_count": len(
                        clinical_data[
                            "recommended_tests"
                        ]
                    ),

                    "clinical_content_logged": False,
                }


            update_data = {
                "output": trace_output
            }


            if usage:

                update_data[
                    "usage_details"
                ] = {
                    "input": getattr(
                        usage,
                        "prompt_tokens",
                        0,
                    ),

                    "output": getattr(
                        usage,
                        "completion_tokens",
                        0,
                    ),
                }


            generation.update(
                **update_data
            )


            return clinical_data


    except json.JSONDecodeError as error:

        raise RuntimeError(
            "Clinical AI returned invalid JSON."
        ) from error


    except Exception as error:

        raise RuntimeError(
            "Clinical extraction failed: "
            f"{str(error)}"
        ) from error