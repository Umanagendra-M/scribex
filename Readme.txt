ScribeX

An AI scribe that converts doctor-patient conversations into SOAP notes. Built from a real clinical problem — starting simple, learning what breaks, evolving toward a multi-agent architecture.

The Problem That Started This

A pediatrician sees 20 patients a day. Each visit is 30 minutes. After the visit, the doctor spends another 20-30 minutes writing clinical notes — transcribing what was said, structuring it into SOAP format, and uploading it to the EHR.

That's 400-600 minutes of documentation per day. For a single doctor.

The problem isn't lack of tools — it's that existing tools either require a cloud connection (PHI can't leave the clinic), don't understand medical jargon, or produce notes that need so much editing they save no time.

The requirement that shaped everything: the entire system must run offline, on local hardware, with no patient data leaving the machine.

What I Learned Before Writing Any Code

Before building, I spent time understanding the actual clinical workflow by working through a structured requirements discovery process. The questions that turned out to matter most:

Who speaks in a pediatric visit? Not two people — three or more. Doctor, patient (child), and parent(s). Sometimes siblings. A transcription that can't identify who said what produces a useless SOAP note — you can't attribute subjective symptoms (what the parent reports) vs objective findings (what the doctor observes) without knowing who said what.

What does "real-time" actually mean here? The doctor wants to see the note being built during the visit — not wait 5 minutes after. But they also want to review and approve before anything is finalized. So it's real-time transcription + async approval.

What makes a SOAP note "good"? I asked: what accuracy threshold is acceptable? 95% for transcription. What defines a good summary? It should be easily understandable. How will success be measured? Doctor and patient satisfaction — not a precision metric.

That last answer changed how I thought about evaluation. The ground truth isn't a labeled dataset — it's a doctor clicking "approve."

What sections can a patient edit? History of the issue — yes. Medications — no. Assessment — no. This asymmetry matters architecturally: the system needs role-based write permissions per SOAP section, not just per document.

The full requirements discovery is documented in Readme.txt in this repository — the raw Q&A that defined what to build before a line of code was written.

Version 1 — Single Agent (This Repository)

The first version is intentionally simple. One agent, one pipeline, one happy path.

Audio input (WAV file or microphone)
    ↓
Whisper ASR → raw transcript
    ↓
Single LLM call → SOAP note generation
    ↓
Doctor review UI → approve or edit
    ↓
PDF export + database storage

What this version does:

Takes a recorded audio file (WAV), transcribes it using Whisper, sends the transcript to an LLM with a SOAP prompt, and presents the structured note for doctor review. On approval, generates a PDF and saves to local SQLite.

What this version does not do:

Real-time transcription. Speaker diarization. ICD-10 code suggestions. FHIR formatting. EPIC integration. Multilingual support. Role-based section editing.

Those are not oversights — they're decisions. Version 1 answers one question: can a local LLM pipeline produce a SOAP note that a doctor would recognize as useful? Before adding complexity, that question needed an answer.

Tech Stack — v1
Speech Recognition:   OpenAI Whisper (local, offline)
SOAP Generation:      LLM via Ollama (local inference)
Storage:              SQLite
UI:                   Streamlit
Language:             Python 3.11
OS:                   Windows (primary)
Hardware target:      16GB RAM, no GPU required
Getting Started
bash
git clone https://github.com/Umanagendra-M/scribex.git
cd scribex

pip install -r requirements.txt

# Copy env template and configure
cp .env.example .env

# Run
streamlit run src/app.py

Place a WAV audio file in data/ or connect a microphone. The system will transcribe, generate a SOAP note, and present it for review.

Project Structure
scribex/
├── src/
│   ├── transcription.py    # Whisper ASR
│   ├── soap_generator.py   # LLM SOAP note generation
│   ├── review.py           # Doctor approval flow
│   ├── export.py           # PDF generation
│   ├── database.py         # SQLite storage
│   └── app.py              # Streamlit UI
├── data/
│   └── sample_audio/
├── output.wav              # Sample output
├── requirements.txt
└── .env
What This Version Taught Me

Building v1 surfaced three problems that a single-agent architecture can't solve cleanly:

Problem 1 — The pipeline is brittle end to end. If transcription produces a noisy output, the SOAP generator receives garbage and produces garbage. There's no checkpoint, no validation, no way to retry just one stage. A multi-stage pipeline needs each stage to be independently testable and retryable.

Problem 2 — Speaker diarization can't be an afterthought. In testing with real pediatric visit audio, the LLM frequently confused who said what — attributing parent-reported symptoms to the doctor's objective findings. Diarization isn't a feature to add later — it's a prerequisite for accurate SOAP generation. It needs to be its own stage with its own model.

Problem 3 — A single LLM call can't do everything. Asking one LLM call to transcribe context, extract medical entities, suggest ICD-10 codes, format SOAP sections, and handle role-based permissions produces mediocre output across all tasks. Specialized models per task — a transcription model, an extraction model, a generation model — produce better results than one general model asked to do everything.

These three observations drove the architecture of the next version.

Evolution — Where This Leads

The limitations of v1 directly shaped the design of ScribeXAgent — a multi-agent version built with LangGraph where each concern is a specialized agent:

scribex (v1)                    ScribeXAgent (v2)
────────────────────            ────────────────────────────
Single LLM call                 Specialized agents per task
No diarization                  DiarizationAgent (pyannote)
Sequential, brittle             LangGraph state machine
No FHIR output                  FHIR R4 + EPIC integration
WAV file only                   Real-time + file input
English only                    English, Spanish, French
SQLite                          PostgreSQL with audit trail

The single-agent version is not a prototype to discard — it's a validated proof of concept that answered whether the core pipeline works before adding coordination complexity. That sequencing is intentional.

Clinical Data Model

Each patient visit stores:

patient_id                  UUID
patient_name                text
provider_name               text
doctor_name                 text
time_of_visit               timestamp
hospital_name               text
audio_file                  path (WAV)
created_transcript          text (auto-generated by Whisper)
doctor_approved_transcript  text (post-review)
patient_edited_transcript   text (patient-editable sections)
soap_note                   JSON
pdf_path                    path
created_at                  timestamp
Scale Parameters
Target clinic size:     Single pediatric practice
Patients per day:       20
Audio per visit:        ~30 minutes WAV
Notes per day:          20 SOAP notes (~10MB each)
Offline:                Yes — no internet required
Hardware:               16GB RAM, Windows
Author

Umanagendra M — ML/AI Engineer with 8 years of experience in production NLP and GenAI systems. Previously built clinical NLP pipelines at Carelon/Elevance Health including a 76-label BERT fine-tuning pipeline for clinical entity extraction.

GitHub | ScribeXAgent →

License

MIT License
