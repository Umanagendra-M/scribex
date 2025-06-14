
import ollama

from dotenv import load_dotenv
import os
load_dotenv()


def llm_workflow(metadata,formatted_trans_path):
    def prepare_prompt(metadata, transcript_lines):
        patient = metadata.get("patient_name", "N/A")
        age = metadata.get("patient_age", "N/A")
        sex = metadata.get("patient_sex", "N/A")
        visit_date = metadata.get("visit_date", "N/A")
        doctor = metadata.get("doctor_name", "N/A")
        role = metadata.get("doctor_role", "N/A")

        header = f"""Patient Info:
        Name: {patient}
        Age: {age}
        Sex: {sex}
        Date: {visit_date}

        Doctor Info:
        Name: {doctor}
        Role: {role}

        Conversation Transcript:"""


        body = "\\n".join(transcript_lines)
        footer = """\\n"You are a clinical documentation assistant. Use the conversation below to generate a SOAP (Subjective, Objective, Assessment, Plan) note.

    Do NOT add any information that is not present in the transcript. If details are missing, leave that section concise or empty"""

        return header + body + footer


    transcript_lines=[]
    with open(formatted_trans_path, "r") as f:
        for line in f:
            transcript_lines.append(line.strip())

    prompt_text = prepare_prompt(metadata, transcript_lines)



    SOAP_NOTES_PATH = os.getenv("SOAP_NOTES_PATH")
    

    response = ollama.generate(model="llama3.2:latest", prompt=prompt_text)
    #print("response",response)
    file_name_metadata=metadata["patient_name"]+'_'+metadata["doctor_name"]+'_'+metadata["visit_date"]+'.txt'
    print(SOAP_NOTES_PATH,file_name_metadata)
    soap_note_path=SOAP_NOTES_PATH+file_name_metadata
    with open(soap_note_path,'w') as f:
        f.write(response["response"])
        
    return soap_note_path