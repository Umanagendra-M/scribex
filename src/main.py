from record_mic import record_audio
from audio_transcribe import  extract_transcript
from format_transcription import format_transcript
from llm_call import llm_workflow
metadata = {
    "doctor_name": "Dr. John Smith",
    "doctor_role": "Primary Care Physician",
    "patient_name": "Jane Doe",
    "patient_age": 45,
    "patient_sex": "Female",
    "visit_date": "2025-05-28",
    "reason_for_visit": "Follow-up for hypertension"
    }

def SOAP_Note_gen():
    audio_filepath=record_audio(metadata)
    raw_transcript_filename=extract_transcript(metadata,audio_filepath)
    formatted_transcript_path=format_transcript(metadata,raw_transcript_filename)
    SOAP_path=llm_workflow(metadata,formatted_transcript_path)
    print("The SOAP note is generated at ",SOAP_path)
    

if __name__=='__main__':
    SOAP_Note_gen()