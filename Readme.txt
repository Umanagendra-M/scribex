Functional requirements:
user should start the process 
The system transcribes in the backend
The SOAP format appears for approval
The SOAP output is taken and a pdf is generated.
and send to epic for integration.
The entire transaction should be saved and retrieved when needed from data base.
20 patients per day
20*30 minute audio - wav format

20* 30 summaries - each of size 10 mb

patient id patient name provider name doctor name time of visit hospital name audio  created transcript doctor approved transcript patient edited transcript 




non functional requirements:
-should be automatic updated

mic sends the data to transcription service.
dilarization is needed to understand who said what.
when the data arrives the soap template is updated 
SOAP note template is filled from transcription service
The formatted file is given to the docx file for creation the doctor checks it in the FHIR ahd FH7 format.
upon clicking ok the data gets updated to the patient copy which has all the medical related sections locked and it is logged in the backend.


🧍‍♀️ 1. User & Use Case Profile
Question	                                                                            Answer
Who are the intended users? (e.g., doctors, nurses)	                                  doctors are going to do the final review
What types of clinical encounters will this support?	                              inpatient visit
What is the typical duration of conversations?	                                      30 minutes
Will the tool be used during the visit or after (real-time vs post-processing)?	      real time vs post processing
Will the user interact with the output (edit, annotate)?	                          patient should be able to edit the few sections like the history of the issue 
                                                                                      but not medication section and assessment.

🎙️ 2. Audio Input & Environment
Question	                                                                          Answer
How is audio captured? (mic, phone, uploaded file)	                                  mic/phone/uploaded file 
Will the audio quality vary (background noise, accents)?	                          background noise is expected
Are there multiple speakers per recording?	                                          patient and doctor will be there will be kids as well sometimes.
Is speaker diarization (identifying who is speaking) required?	                      yes since this is for pediatrician
Are there specific non-English languages or regional accents to support?	          yes spanish mostly and french sometimes

🧠 3. AI Capabilities
📢 Speech Recognition (ASR)
Question	                                                                                Answer
Is real-time transcription required?	                                               yes
Should the model support medical jargon and drug names?	                               yes
Should the system learn from user corrections over time?	                           yes   

📝 Summarization
Question	Answer
What kind of output is expected? (SOAP notes, bullet points, narrative)	              SOAP notes
Should the summary format change based on medical specialty?	                      yes 
Is summarization automatic, user-assisted, or both?	                                  semi automatic, doctor has to agree and the sheet is finalized after that.

🧬 Medical NLP
Question	                                                                                 Answer
What entities should be extracted? (symptoms, diagnoses, meds)	                      symptoms,diagnosis.meds
Should the system suggest ICD-10 or CPT codes?	                                      yes if possible
Do we need integration with medical ontologies (SNOMED, UMLS)?	                      not needed now

🖥️ 4. System Requirements
Question	Answer
Should the app run on Windows, Mac, Linux — or all?	                                   first on windows then will check
Is local (offline) processing mandatory?	                                           yes it is going to be standalone.
What are the expected hardware specs of the target user?	                           16gb ram 
Should the app support GPU acceleration if available?	                               not mandatory

🔐 5. Privacy, Security & Compliance
Question	Answer
Should the tool be HIPAA-compliant or meet similar standards?	                       It is offline here
Can any data leave the local machine?	                                               nope
Is encryption of data-at-rest and in-transit required?	                               nope        
Should access control / login functionality be built in?	                           yes
Should logs or audit trails be kept?	                                               yes 

📤 6. Output Format & Integration
Question	                                                                        Answer
What output formats are needed? (PDF, text, HL7, FHIR)	                             FHIR
Should users be able to export/share summaries easily?                               yes     	
Is integration with an EHR system required? If so, which one(s)?	                 EPIC
Will the user need a UI to view, search, or edit notes?	                             yes   

📏 7. Evaluation & Success Criteria
Question	                                                                          Answer
What accuracy threshold is acceptable for transcription?	                          95 percent
What defines a "good" summary in the user’s view?	                                  it should be easily understandable
Will end users review and rate output quality?	                                      yes
How will success be measured (e.g., time saved, error rate, satisfaction)?	          satifaction on doctor and patient side

🔧 8. Dev & Maintenance Preferences
Question	Answer
Will the system be self-managed or maintained by a team?                                 self managed	
Should it be modular and open to third-party plugins?	                                 yes
Is containerization (Docker) preferred for deployment?	                                 yes  
Should the system support auto-updating or manual updates only?                          auto updating/manual




