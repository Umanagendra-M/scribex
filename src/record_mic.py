#record a simple audio
#see if the record stops if the there is no activity for 10 seconds## this is not needed but real time processing is needed. i dont mean to detect any 10 seconds 
## gap to stop recording may be voice activated recording is needed and needed to end the record manually.
#send the recorded audio for transcription 
#use llm to create a SOAP out of the LLM 
#save it to a file 
import sounddevice as sd
import soundfile as sf
import keyboard
import numpy as np

from dotenv import load_dotenv
import os
load_dotenv()

raw_audio_path = os.getenv("RAW_AUDIO_PATH")
def record_audio(metadata): 
    file_name_metadata=metadata["patient_name"]+'_'+metadata["doctor_name"]+'_'+metadata["visit_date"]

    fs = 44100  # Sample rate
    channels = 1
    raw_audio_file_path = raw_audio_path+file_name_metadata+'.wav'
    print("Recording... Press SPACE to stop.")
    # Buffer to store recorded chunks
    recorded_frames = []
    def callback(indata, frames, time, status):
        if status:
            print(status)
        recorded_frames.append(indata.copy())
    # Start input stream in callback mode (non-blocking)
    with sd.InputStream(samplerate=fs, channels=channels, callback=callback):
        keyboard.wait('space')

    print("Stopped recording. Saving...")

    # Concatenate all recorded chunks
    audio_data = np.concatenate(recorded_frames, axis=0)

    # Save to WAV file
    sf.write(raw_audio_file_path, audio_data, fs)

    print(f"Recording saved to {raw_audio_file_path}")
    
    return raw_audio_file_path

        

