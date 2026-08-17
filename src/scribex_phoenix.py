"""
scribex_phoenix.py
------------------
Single script: transcript → SOAP note → guardrails → Phoenix tracing + evals

Generation model : medllama2     (via Ollama)
Judge model      : llama3.1:8b  (via Ollama)

All calls — generation AND judge — appear as spans in Phoenix UI.

HOW TO RUN:
    pip install arize-phoenix openinference-instrumentation-openai opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

    # Pull models (one time)
    ollama pull medllama2
    ollama pull llama3.1:8b

    # Generate one note + see trace in Phoenix
    python scribex_phoenix.py --mode run --transcript_file data/CAR0001.txt

    # Run evals on all gold-standard files
    python scribex_phoenix.py --mode eval --data_dir ./data

    # Open http://localhost:6006 to see all traces
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ── Model config ──────────────────────────────────────────────────────────────
GENERATION_MODEL = "phi3:3.8b"
JUDGE_MODEL      = "llama3.1:8b"
OLLAMA_BASE_URL  = "http://localhost:11434/v1"


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: START PHOENIX
# ──────────────────────────────────────────────────────────────────────────────

# Module-level tracer — used by both generation and judge spans
tracer = None


def start_phoenix():
    global tracer

    import phoenix as px
    from phoenix.otel import register
    from opentelemetry import trace
    from openinference.instrumentation.openai import OpenAIInstrumentor

    # Fixed local folder — avoids Windows temp file permission errors
    os.makedirs("./phoenix_data", exist_ok=True)
    os.environ["PHOENIX_WORKING_DIR"] = os.path.abspath("./phoenix_data")

    px.launch_app(use_temp_dir=False)

    tracer_provider = register(
        project_name="scribex",
        endpoint="http://localhost:6006/v1/traces",
    )

    # Instrument OpenAI client class — patches ALL instances including Ollama clients
    # because Ollama uses the same OpenAI SDK
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)

    # Get a tracer for manual spans (judge calls)
    tracer = trace.get_tracer("scribex", tracer_provider=tracer_provider)

    print("✅ Phoenix running → http://localhost:6006")
    print(f"   Generation model : {GENERATION_MODEL}")
    print(f"   Judge model      : {JUDGE_MODEL}\n")
    return tracer_provider


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: GENERATE SOAP NOTE  (medllama2 via Ollama)
# ──────────────────────────────────────────────────────────────────────────────

GENERATION_PROMPT = """You are a clinical documentation assistant.
Convert the diarized medical transcript into a SOAP note.

Write the note using exactly these headings:

SUBJECTIVE:
[What the patient reported: chief complaint, onset, location, quality, severity 1-10,
timing, what makes it better or worse, associated symptoms, medications, allergies,
social history, family history. Write at least 3-4 sentences.]

OBJECTIVE:
Vital signs: Not documented. Physical examination: Not performed during this encounter.

ASSESSMENT:
[Primary diagnosis with reasoning, then 2-3 differentials.]

PLAN:
1. [First step]
2. [Second step]
3. [Third step]

RULES:
- SUBJECTIVE: Only what the patient said. Never invent information.
- OBJECTIVE: Copy the line above exactly. Never invent vitals or exam findings.
- ASSESSMENT: Based only on what is in the transcript.
- PLAN: If patient mentioned a drug allergy, do NOT recommend that drug class."""


def ollama_client():
    """Returns an OpenAI client pointed at local Ollama."""
    from openai import OpenAI
    return OpenAI(api_key="ollama", base_url=OLLAMA_BASE_URL)


def normalize_soap(soap: dict) -> dict:
    """Normalize all SOAP values to plain strings."""
    result = {}
    for key in ["subjective", "objective", "assessment", "plan"]:
        val = soap.get(key, "")
        if isinstance(val, list):
            val = "\n".join(str(item) for item in val)
        elif isinstance(val, dict):
            val = json.dumps(val)
        elif not isinstance(val, str):
            val = str(val)
        result[key] = val.strip()
    return result


def parse_plain_text_soap(text: str) -> dict:
    """Extract SOAP sections from plain text using heading markers."""
    soap = {"subjective": "", "objective": "", "assessment": "", "plan": ""}
    pattern = re.compile(
        r"(SUBJECTIVE|OBJECTIVE|ASSESSMENT|PLAN)\s*:\s*",
        re.IGNORECASE,
    )
    parts = pattern.split(text)
    i = 1
    while i < len(parts) - 1:
        heading = parts[i].strip().lower()
        content = parts[i + 1].strip()
        content = pattern.split(content)[0].strip()
        if heading in soap:
            soap[heading] = content
        i += 2
    return soap


def generate_soap(transcript: str) -> dict:
    """
    Generate a SOAP note from a diarized transcript using medllama2.
    This call is auto-traced by Phoenix via OpenAIInstrumentor.
    """
    client = ollama_client()

    response = client.chat.completions.create(
        model=GENERATION_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": GENERATION_PROMPT},
            {"role": "user",   "content": f"Transcript:\n\n{transcript}"},
        ],
    )
    raw = response.choices[0].message.content

    # Try 1: JSON (in case model returns it)
    raw_stripped = re.sub(r"```json|```", "", raw).strip()
    json_match = re.search(r"\{.*\}", raw_stripped, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return normalize_soap(json.loads(json_str))
        except json.JSONDecodeError:
            pass
        try:
            json_clean = re.sub(r'(?<!\\)\n', ' ', json_str)
            json_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', json_clean)
            return normalize_soap(json.loads(json_clean))
        except json.JSONDecodeError:
            pass

    # Try 2: Plain text section parsing
    soap = parse_plain_text_soap(raw)

    # Try 3: Last resort
    if not any(soap.values()):
        soap["subjective"] = raw.strip()
        soap["objective"]  = "Vital signs: Not documented. Physical examination: Not performed during this encounter."
        soap["assessment"] = "Could not parse — review raw output in subjective field."
        soap["plan"]       = "Manual review required."

    return normalize_soap(soap)


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: GUARDRAILS  (rule-based, no LLM calls)
# ──────────────────────────────────────────────────────────────────────────────

FABRICATED_PATTERNS = re.compile(
    r"vital signs (are |were )?(within )?normal( limits)?"
    r"|heart (rate|sounds) (are |were |is )?(normal|regular|\d+)"
    r"|blood pressure:?\s*\d+"
    r"|o2 sat\w*:?\s*\d+"
    r"|respiratory rate:?\s*\d+"
    r"|no (acute )?distress"
    r"|lungs (are |were )?clear"
    r"|(abdomen|belly) (is |was )?(soft|non-tender)"
    r"|bowel sounds (are |were )?(normal|present)",
    re.IGNORECASE,
)

SAFE_OBJECTIVE = (
    "Vital signs: Not documented. "
    "Physical examination: Not performed during this encounter."
)

ALLERGY_DRUG_MAP = {
    "penicillin":      ["penicillin", "amoxicillin", "ampicillin", "augmentin"],
    "sulfa":           ["sulfamethoxazole", "bactrim", "tmp-smx", "sulfa"],
    "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "fluoroquinolone"],
    "nsaid":           ["ibuprofen", "naproxen", "diclofenac", "nsaid"],
}

ALLERGY_CONTEXT_RE = re.compile(r"allerg[^.;\n]{0,100}", re.IGNORECASE)
KNOWN_DRUG_RE = re.compile(
    r"\b(penicillin|amoxicillin|ampicillin|augmentin|"
    r"sulfamethoxazole|sulfa|bactrim|"
    r"ciprofloxacin|levofloxacin|fluoroquinolone|"
    r"ibuprofen|naproxen|nsaid)\b",
    re.IGNORECASE,
)


def run_guardrails(soap: dict, transcript: str) -> tuple[dict, list[str]]:
    soap = normalize_soap(soap)
    warnings = []

    # Guardrail 1: Fabricated vitals
    objective = soap.get("objective", "")
    if "not documented" not in objective.lower() and FABRICATED_PATTERNS.search(objective):
        warnings.append("🚫 FABRICATED VITALS: Objective had invented findings. Auto-replaced.")
        soap["objective"] = SAFE_OBJECTIVE

    # Guardrail 2: Empty objective
    if len(soap.get("objective", "").strip()) < 20:
        warnings.append("⚠️  EMPTY OBJECTIVE: Replaced with safe default.")
        soap["objective"] = SAFE_OBJECTIVE

    # Guardrail 3: Allergy conflict
    search_text = transcript + "\n" + soap.get("subjective", "")
    allergens = []
    for ctx in ALLERGY_CONTEXT_RE.findall(search_text):
        for m in KNOWN_DRUG_RE.finditer(ctx):
            allergens.append(m.group(0).lower())

    plan = soap.get("plan", "").lower()
    for allergen in set(allergens):
        drug_class = next(
            (cls for cls, drugs in ALLERGY_DRUG_MAP.items() if allergen in drugs), None
        )
        if not drug_class:
            continue
        for drug in ALLERGY_DRUG_MAP[drug_class]:
            if drug in plan:
                warnings.append(
                    f"🚫 ALLERGY CONFLICT: Plan has '{drug}' but patient allergic to {allergen}."
                )

    return soap, warnings


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4: LLM-AS-JUDGE EVALS  (llama3.1:8b via Ollama)
# All judge calls are wrapped in OpenTelemetry spans so they appear in Phoenix
# ──────────────────────────────────────────────────────────────────────────────

HALLUCINATION_JUDGE_PROMPT = """You are a medical documentation reviewer.

Your job: check if the SOAP note contains facts NOT found in the transcript.

TRANSCRIPT:
{transcript}

SOAP NOTE TO CHECK:
SUBJECTIVE: {subjective}
OBJECTIVE: {objective}
ASSESSMENT: {assessment}
PLAN: {plan}

Check specifically for:
- Invented vital signs (blood pressure, heart rate, oxygen saturation)
- Fabricated physical exam findings (heart sounds, lung sounds, abdomen)
- Lab values or imaging results not mentioned in the transcript
- Diagnoses not supported by anything the patient said

Respond with ONLY this JSON, nothing else:
{{"label": "grounded", "score": 0.9, "reason": "No invented facts found"}}

Use label "hallucination" and score below 0.5 if you find invented facts.
Use label "grounded" and score above 0.7 if the note sticks to the transcript."""

COMPLETENESS_JUDGE_PROMPT = """You are a medical documentation reviewer.

Your job: check if the generated SOAP note captures the key clinical content.

REFERENCE NOTE (expert-written):
SUBJECTIVE: {reference_subjective}
ASSESSMENT: {reference_assessment}
PLAN: {reference_plan}

GENERATED NOTE:
SUBJECTIVE: {subjective}
ASSESSMENT: {assessment}
PLAN: {plan}

Check if the generated note:
- Identified the correct primary diagnosis
- Captured the main symptoms and risk factors
- Included appropriate next steps in the plan

Respond with ONLY this JSON, nothing else:
{{"label": "complete", "score": 0.8, "reason": "Captured main diagnosis and plan"}}

Use label "incomplete" and score below 0.5 if important content is missing.
Use label "complete" and score above 0.7 if key content is present."""


def parse_judge_response(raw: str) -> dict:
    """
    Parse the judge model's response into a structured dict.
    Handles: clean JSON, JSON in markdown, JSON in prose, plain text with a number.
    """
    raw_clean = re.sub(r"```json|```", "", raw).strip()

    # Try to find and parse a JSON object
    match = re.search(r"\{.*?\}", raw_clean, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(0))
            if all(k in result for k in ["label", "score", "reason"]):
                result["score"] = float(result["score"])
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: extract any float score from the text
    score_match = re.search(r'\b(0\.\d+|1\.0)\b', raw_clean)
    score = float(score_match.group(0)) if score_match else 0.5

    return {
        "label":  "unknown",
        "score":  score,
        "reason": f"Could not parse response: {raw_clean[:120]}",
    }


def call_judge(
    prompt: str,
    case_id: str,
    eval_type: str,
) -> dict:
    """
    Calls llama3.1:8b as the judge AND creates a Phoenix span for the call.

    In Phoenix UI you will see:
      scribex (root span)
        └── judge_hallucination   ← this span, with score + reason attached
        └── judge_completeness    ← this span, with score + reason attached

    Attributes visible in Phoenix for each judge span:
      - case_id       which transcript was judged
      - eval_type     hallucination or completeness
      - model         llama3.1:8b
      - input         first 500 chars of the prompt
      - output        raw model response
      - score         numeric score (0.0–1.0)
      - label         grounded/hallucination or complete/incomplete
      - reason        one-sentence explanation from the judge
    """
    with tracer.start_as_current_span(
        name=f"judge_{eval_type}",
        attributes={
            "case_id":   case_id,
            "eval_type": eval_type,
            "model":     JUDGE_MODEL,
            "input":     prompt[:500],
        },
    ) as span:
        try:
            client = ollama_client()
            response = client.chat.completions.create(
                model=JUDGE_MODEL,
                temperature=0.0,   # zero for consistent scores
                messages=[
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.choices[0].message.content
            result = parse_judge_response(raw)

        except Exception as e:
            result = {
                "label":  "error",
                "score":  0.0,
                "reason": f"Judge call failed: {str(e)}",
            }
            raw = str(e)

        # Attach everything to the span so Phoenix shows it
        span.set_attribute("output", raw[:500])
        span.set_attribute("score",  result["score"])
        span.set_attribute("label",  result["label"])
        span.set_attribute("reason", result["reason"])

        return result


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5: FULL EVAL PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def run_evals(data_dir: str):
    """
    1. Load gold-standard files
    2. Generate SOAP for each transcript  (medllama2, auto-traced)
    3. Run guardrails
    4. Judge each note with llama3.1:8b  (manual spans → visible in Phoenix)
    5. Print summary + save CSV
    """
    import pandas as pd

    # Load gold-standard files
    rows = []
    for path in sorted(Path(data_dir).glob("*.txt")):
        with open(path) as f:
            d = json.load(f)
        rows.append({
            "case_id":              path.stem,
            "transcript":           d["transcript"],
            "reference_subjective": d["subjective"],
            "reference_objective":  d["objective"],
            "reference_assessment": d["assessment"],
            "reference_plan":       d["plan"],
        })

    if not rows:
        print(f"No .txt files found in {data_dir}")
        sys.exit(1)

    print(f"Loaded {len(rows)} cases from {data_dir}\n")

    # ── Generation ────────────────────────────────────────────────────────────
    print("── Generating SOAP notes ────────────────────")
    for row in rows:
        print(f"  → {row['case_id']}")
        try:
            soap = generate_soap(row["transcript"])
            soap, warnings = run_guardrails(soap, row["transcript"])
        except Exception as e:
            print(f"    ERROR: {e}")
            soap = {k: "ERROR" for k in ["subjective", "objective", "assessment", "plan"]}
            warnings = [f"Generation failed: {e}"]

        row.update({
            "subjective":         soap["subjective"],
            "objective":          soap["objective"],
            "assessment":         soap["assessment"],
            "plan":               soap["plan"],
            "guardrail_warnings": "; ".join(warnings) if warnings else "none",
        })

    # ── Judging ───────────────────────────────────────────────────────────────
    print("\n── Running LLM judge (llama3.1:8b) ─────────")
    print("   (Each call appears as a span in Phoenix)\n")

    for row in rows:
        print(f"  → {row['case_id']}")

        # Hallucination eval
        h_result = call_judge(
            prompt=HALLUCINATION_JUDGE_PROMPT.format(
                transcript = row["transcript"][:3000],
                subjective = row["subjective"],
                objective  = row["objective"],
                assessment = row["assessment"],
                plan       = row["plan"],
            ),
            case_id   = row["case_id"],
            eval_type = "hallucination",
        )
        row["hallucination_score"]  = h_result["score"]
        row["hallucination_label"]  = h_result["label"]
        row["hallucination_reason"] = h_result["reason"]
        print(f"    hallucination : {h_result['score']:.2f} ({h_result['label']}) — {h_result['reason'][:60]}")

        # Completeness eval
        c_result = call_judge(
            prompt=COMPLETENESS_JUDGE_PROMPT.format(
                reference_subjective = row["reference_subjective"],
                reference_assessment = row["reference_assessment"],
                reference_plan       = row["reference_plan"],
                subjective           = row["subjective"],
                assessment           = row["assessment"],
                plan                 = row["plan"],
            ),
            case_id   = row["case_id"],
            eval_type = "completeness",
        )
        row["completeness_score"]  = c_result["score"]
        row["completeness_label"]  = c_result["label"]
        row["completeness_reason"] = c_result["reason"]
        print(f"    completeness  : {c_result['score']:.2f} ({c_result['label']}) — {c_result['reason'][:60]}")

    # ── Summary ───────────────────────────────────────────────────────────────
    df = pd.DataFrame(rows)

    print("\n" + "=" * 58)
    print("EVAL SUMMARY")
    print("=" * 58)
    print(f"  {'Metric':<22} {'Avg':>6}  {'Min':>6}  {'Max':>6}")
    print(f"  {'-'*22}  {'-'*6}  {'-'*6}  {'-'*6}")
    for col, label in [("hallucination_score", "hallucination"), ("completeness_score", "completeness")]:
        print(
            f"  {label:<22} {df[col].mean():>6.2f}  "
            f"{df[col].min():>6.2f}  {df[col].max():>6.2f}"
        )
    print("=" * 58)

    print("\n── Worst hallucination scores ───────────────")
    for _, r in df.nsmallest(3, "hallucination_score").iterrows():
        print(f"  {r['case_id']} ({r['hallucination_score']:.2f}): {r['hallucination_reason'][:70]}")

    print("\n── Worst completeness scores ────────────────")
    for _, r in df.nsmallest(3, "completeness_score").iterrows():
        print(f"  {r['case_id']} ({r['completeness_score']:.2f}): {r['completeness_reason'][:70]}")

    # Save CSV
    out_path = "eval_results.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved → {out_path}")
    print("All traces (generation + judge) → http://localhost:6006")

    input("\nPress Enter to exit (keeps Phoenix open)...")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ScribeX + Phoenix + Ollama")
    parser.add_argument(
        "--mode",
        choices=["run", "eval"],
        required=True,
        help="run = generate one note  |  eval = score all gold-standard files",
    )
    parser.add_argument(
        "--transcript_file",
        help="Path to a JSON file (--mode run only)",
    )
    parser.add_argument(
        "--data_dir",
        default="./data",
        help="Folder of gold-standard JSON files (--mode eval only)",
    )
    args = parser.parse_args()

    start_phoenix()

    if args.mode == "run":
        if not args.transcript_file:
            print("ERROR: --transcript_file required for --mode run")
            sys.exit(1)

        with open(args.transcript_file) as f:
            data = json.load(f)

        print(f"Generating SOAP note for {args.transcript_file}")

        soap = generate_soap(data["transcript"])
        soap, warnings = run_guardrails(soap, data["transcript"])

        print("\n── SOAP NOTE ────────────────────────────────")
        for section in ["subjective", "objective", "assessment", "plan"]:
            print(f"\n{section.upper()}:\n{soap[section]}")

        if warnings:
            print("\n── GUARDRAIL WARNINGS ───────────────────────")
            for w in warnings:
                print(w)
        else:
            print("\n✅ All guardrails passed.")

        input("\nPress Enter to exit (keeps Phoenix open)...")

    elif args.mode == "eval":
        run_evals(args.data_dir)


if __name__ == "__main__":
    main()