
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_ollama import ChatOllama
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("scribex")

# ---------- Config (env-driven, no hardcoded secrets/paths) ----------
AUDIO_PATH = os.getenv("AUDIO_PATH")
HF_TOKEN = os.getenv("HF_TOKEN")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./output"))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class StageTiming:
    stage: str
    seconds: float
    ok: bool
    error: str | None = None


TIMINGS: list[StageTiming] = []


def timed_stage(stage_name: str):
    """Decorator: times a stage, logs it, records success/failure without
    crashing the whole run — lets us inspect what DID complete."""

    def decorator(fn):
        def wrapper(*args, **kwargs):
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
                elapsed = time.time() - t0
                TIMINGS.append(StageTiming(stage=stage_name, seconds=elapsed, ok=True))
                log.info(f"{stage_name} completed in {elapsed:.1f}s")
                return result
            except Exception as e:
                elapsed = time.time() - t0
                TIMINGS.append(StageTiming(stage=stage_name, seconds=elapsed, ok=False, error=str(e)))
                log.error(f"{stage_name} FAILED after {elapsed:.1f}s: {e}")
                raise

        return wrapper

    return decorator


# ---------- Stage 1: Transcription ----------
@timed_stage("transcription")
def transcribe(audio_path: str, model_size: str = WHISPER_MODEL_SIZE, device: str = WHISPER_DEVICE):
    model = WhisperModel(model_size, device=device, compute_type="float16" if device == "cuda" else "int8")
    segments, info = model.transcribe(audio_path)
    result = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
    log.info(f"Detected language: {info.language} ({len(result)} segments)")
    return result, info.language


# ---------- Stage 2: Diarization ----------
@timed_stage("diarization")
def diarize(audio_path: str, hf_token: str):
    import torch

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)
    #if torch.cuda.is_available():
     #   pipeline.to(torch.device("cuda"))

    # Pass the path directly — avoids torchaudio.load()/torchcodec entirely,
    # which is what was causing the FFmpeg DLL errors. pyannote handles its
    # own audio I/O when given a path.
    diarization = pipeline(audio_path)

    turns = [
        {"start": seg.start, "end": seg.end, "speaker": speaker}
        for seg, _, speaker in diarization.itertracks(yield_label=True)
    ]
    log.info(f"Found {len(set(t['speaker'] for t in turns))} distinct speakers, {len(turns)} turns")
    return turns


# ---------- Merge (pure function, not timed as a separate "stage" — trivial cost) ----------
def merge(transcript_segments: list[dict], speaker_turns: list[dict]) -> list[dict]:
    merged = []
    for seg in transcript_segments:
        mid = (seg["start"] + seg["end"]) / 2
        speaker = "UNKNOWN"
        for turn in speaker_turns:
            if turn["start"] <= mid <= turn["end"]:
                speaker = turn["speaker"]
                break
        merged.append({"start": seg["start"], "end": seg["end"], "speaker": speaker, "text": seg["text"]})

    unknown_count = sum(1 for m in merged if m["speaker"] == "UNKNOWN")
    if unknown_count:
        log.warning(f"{unknown_count}/{len(merged)} segments had no matching speaker turn")
    return merged


# ---------- Stage 3: SOAP generation (LangChain + Ollama) ----------
_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a clinical scribe. Given a doctor-patient transcript, "
            "produce a SOAP note with Subjective, Objective, Assessment, and "
            "Plan sections. Do not invent facts not in the transcript. "
            "This is a DRAFT for physician review, not a final record.",
        ),
        ("human", "{transcript}"),
    ]
)


@timed_stage("soap_generation")
def generate_soap_note(transcript_text: str, model: str = OLLAMA_MODEL) -> str:
    llm = ChatOllama(model=model)
    chain = _PROMPT | llm | StrOutputParser()
    return chain.invoke({"transcript": transcript_text})


# ---------- Orchestration ----------
def run_pipeline(audio_path: str, hf_token: str) -> dict:
    if not audio_path or not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not hf_token:
        raise ValueError("HF_TOKEN not set — required for pyannote diarization")

    run_id = Path(audio_path).stem
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    segments, language = transcribe(audio_path)
    (run_dir / "raw_transcript.json").write_text(json.dumps(segments, indent=2))

    turns = diarize(audio_path, hf_token)
    (run_dir / "speaker_turns.json").write_text(json.dumps(turns, indent=2))

    merged = merge(segments, turns)
    transcript_text = "\n".join(f"{seg['speaker']}: {seg['text']}" for seg in merged)
    (run_dir / "diarized_transcript.txt").write_text(transcript_text)

    soap_note = generate_soap_note(transcript_text)
    (run_dir / "soap_note.txt").write_text(soap_note)

    timing_report = [asdict(t) for t in TIMINGS]
    (run_dir / "timing_report.json").write_text(json.dumps(timing_report, indent=2))

    log.info(f"Run complete. Outputs saved to {run_dir}")
    return {
        "run_id": run_id,
        "language": language,
        "soap_note": soap_note,
        "timings": timing_report,
        "output_dir": str(run_dir),
    }


if __name__ == "__main__":
    try:
        result = run_pipeline(AUDIO_PATH, HF_TOKEN)
        print("\n===== SOAP NOTE (DRAFT) =====\n")
        print(result["soap_note"])
        print(f"\nOutputs saved to: {result['output_dir']}")
    except Exception as e:
        log.error(f"Pipeline failed: {e}")
        log.info(f"Partial results (if any) are still in {OUTPUT_DIR}")
        raise