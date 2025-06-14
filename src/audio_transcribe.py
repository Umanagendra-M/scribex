from pyannote.audio import Pipeline
import whisper
from pydub import AudioSegment
import tempfile
import os
import torchaudio

from dotenv import load_dotenv
import os
load_dotenv()

raw_transcript_path = os.getenv("RAW_TRANSCRIPT_PATH")

def extract_transcript(metadata,audio_filepath) :
    file_name_metadata=metadata["patient_name"]+'_'+metadata["doctor_name"]+'_'+metadata["visit_date"]
    transcript_filepath=raw_transcript_path+"audio_transcript_"+file_name_metadata+".txt"
    # Load diarization and ASR models
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token="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")
    asr_model = whisper.load_model("medium.en")

    # Load audio
    waveform, sample_rate = torchaudio.load(audio_filepath)
    diarization = pipeline({"waveform": waveform, "sample_rate": sample_rate})
    audio = AudioSegment.from_file(audio_filepath)

    # Transcribe segments
    raw_transcript = []

    for segment, _, speaker in diarization.itertracks(yield_label=True):
        start_ms = int(segment.start * 1000)
        end_ms = int(segment.end * 1000)
        chunk = audio[start_ms:end_ms]

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            chunk.export(tmp.name, format="wav")
            result = asr_model.transcribe(tmp.name)
            #os.remove(tmp.name)

        text = result["text"].strip()
        raw_transcript.append((segment.start, segment.end, speaker, text))

    with open(transcript_filepath, "w") as f:
        for s in raw_transcript:
            f.write(str(s) +"\n")
            
    return transcript_filepath



