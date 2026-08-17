import whisper
import numpy as np
import librosa
from sklearn.cluster import KMeans
import ollama
from pydantic import BaseModel

# 1. Define the Pydantic structural mold for a medical SOAP Note
class SoapNoteSchema(BaseModel):
    subjective: str # Chief complaints, history of illness, patient symptoms
    objective: str    # Observable parameters, vitals, exam details mentioned
    assessment: str   # Clinician's diagnostic impression/hypotheses
    plan: str         # Prescriptions, labs, referrals, lifestyle rules

def process_audio_to_soap(audio_path, approximate_speakers=2):
    # --- PHASE 1: WHISPER & VOICE CLUSTERING ---
    print("Loading Whisper model locally...")
    model = whisper.load_model("base")
    
    print("Transcribing clinical audio file...")
    result = model.transcribe(audio_path, word_timestamps=True)
    
    print("Extracting acoustic vectors for speaker separation...")
    audio_signal, sampling_rate = librosa.load(audio_path, sr=16000)
    
    segment_features = []
    valid_segments = []
    
    for segment in result['segments']:
        start_sample = int(segment['start'] * sampling_rate)
        end_sample = int(segment['end'] * sampling_rate)
        audio_slice = audio_signal[start_sample:end_sample]
        
        if len(audio_slice) > 0:
            mfccs = librosa.feature.mfcc(y=audio_slice, sr=sampling_rate, n_mfcc=13)
            segment_features.append(np.mean(mfccs.T, axis=0))
            valid_segments.append(segment)
            
    print("Grouping individual speaker identities...")
    kmeans = KMeans(n_clusters=approximate_speakers, random_state=42)
    speaker_labels = kmeans.fit_predict(segment_features)
    
    # Format individual transcript fragments into a comprehensive dialogue script
    formatted_transcript = ""
    for idx, segment in enumerate(valid_segments):
        speaker_id = f"Speaker {speaker_labels[idx]}"
        text = segment['text'].strip()
        formatted_transcript += f"{speaker_id}: {text}\n"

    print("\n--- Raw Clustered Transcript Completed ---\n")
    print(formatted_transcript)

    # --- PHASE 2: OLLAMA SOAP NOTE PROCESSING ---
    print("\nPassing transcript to Ollama for structured SOAP synthesis...")
    
    system_prompt = (
        "You are an expert clinical documentation assistant. Read the provided "
        "doctor-patient audio transcript and convert it into a highly concise, "
        "professional medical chart following the SOAP layout rule. Do not "
        "extrapolate info not present in the discussion and dont assess the patient it is doctors duty not yours."
    )

    # Use Ollama Python Client to trigger structured json formatting
    response = ollama.chat(
        model="llama3.1:8b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze this conversation:\n\n{formatted_transcript}"}
        ],
        # Forces Ollama to strictly match our Pydantic scheme constraints
        format=SoapNoteSchema.model_json_schema() 
    )

    # Validate and parse the string back into structural python object
    soap_note = SoapNoteSchema.model_validate_json(response.message.content)
    generated_soap = {"transcript":formatted_transcript,
            "subjective": soap_note.subjective,
            "objective": soap_note.objective,
            "assessment": soap_note.assessment,
            "plan": soap_note.plan
        }
    return generated_soap

if __name__ == "__main__":
    import json
    import os
    AUDIO_FILE_folder = "C:/Users/umall/Documents/playwrightapp/scribex/data/captured_audio"
    output_folder="C:/Users/umall/Documents/playwrightapp/scribex/data/eval_output"
    for _,_,files in os.walk(AUDIO_FILE_folder):
        print("files",files)
        for file_ in files:
            print("file&&&&&&&&&&&&&&&",file_)
            output_file_name=file_.replace(".mp3",".txt")  
            generated_soap=process_audio_to_soap(AUDIO_FILE_folder+"/"+file_, approximate_speakers=2)
            generated_soap["file"]=file_
            with open(output_folder+'/'+output_file_name,"w+") as f:
                json.dump(generated_soap,f,indent=4)
                

