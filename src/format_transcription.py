import ast
from dotenv import load_dotenv
import os
load_dotenv()

formatted_transcript_path = os.getenv("FORMATTED_TRANSCRIPT_PATH")

def merge_segments(transcript, max_pause=0.8):
    merged = []
    prev_speaker, prev_start, prev_end, prev_text = None, None, None, ""
    print(transcript,type(transcript))
    for tuple_item in transcript:
        start, end, speaker, text = ast.literal_eval(tuple_item)

        if speaker == prev_speaker and start - prev_end <= max_pause:
            prev_end = end
            prev_text += " " + text
        else:
            if prev_speaker is not None:
                merged.append((prev_start, prev_end, prev_speaker, prev_text.strip()))
            prev_speaker, prev_start, prev_end, prev_text = speaker, start, end, text

    if prev_speaker is not None:
        merged.append((prev_start, prev_end, prev_speaker, prev_text.strip()))

    return merged



def format_transcript(metadata,raw_transcript_filepath):
    file_name_metadata=metadata["patient_name"]+'_'+metadata["doctor_name"]+'_'+metadata["visit_date"]

    raw_transcript = []
    with open(raw_transcript_filepath, "r") as f:
        for line in f:
            raw_transcript.append(line.strip())
    # Merge consecutive segments by same speaker
    merged_transcript = merge_segments(raw_transcript)

    # Print transcript
    transcript_lines = []

    for start, end, speaker, text in merged_transcript:
        line = f"[{start:.1f} - {end:.1f}] {speaker}: {text}"
        transcript_lines.append(line)



    formatted_trans_path=formatted_transcript_path+file_name_metadata+".txt"
    with open(formatted_trans_path, "w") as f:
        for s in transcript_lines:
            f.write(str(s) +"\n")
    return formatted_trans_path
