import openai
import pandas as pd
import os
import time
import json
import re

# Load the Excel file that contains the file names and URLs
file_path = "###"

with open("###", "r", encoding="utf-8") as f:
    case_image_links = json.load(f)

# Read the Excel file
df = pd.read_excel(file_path)
case_no_list = df['Case_No'].tolist()
sex_list = df['Sex'].tolist()
age_list = df['Age'].tolist()
complaint_list = df['Chief Complaint'].tolist()
findings_list = df['Radiologic Findings'].tolist()
true_diag_list = df['Diagnosis'].tolist()

openai.api_key = "###"

def generate_prompt(sex, age, complaint, findings):
    complaint = str(complaint).strip() if complaint and not pd.isna(complaint) else "Not available"

    message_p = f"""
    You are an experienced thoracic radiologist.
    This is a quiz case designed for radiology specialists.
    Given the following patient information — including sex, age, chief complaint, detailed chest imaging findings, and the attached chest images — generate a list of the 5 most likely differential diagnoses, ranked in order of likelihood.

    **Important:**  
    - Provide diagnoses as specifically and precisely as possible.  
    - Avoid vague general terms such as “lung cancer” or “pneumonia”.
    - Specify relevant histologic subtypes, morphologic patterns, or specific variants (e.g., “invasive mucinous adenocarcinoma” rather than “lung cancer”).
    - You must refer to both the detailed radiologic findings and the attached images together — do not fabricate findings that are not described in either.

    For each differential diagnosis:
    1. Explain why it should be considered, referencing relevant features in the attached images.
    2. Highlight features that distinguish it from other possible diagnoses or explain why it cannot be ruled out.

    ### Patient Information
    - Sex: {sex}
    - Age: {age}
    - Chief complaint: {complaint.strip()}
    
    ### Chest Imaging Findings
    {findings.strip()}
        
    Provide the result as a JSON object structured as follows:
    {{
      "differential_diagnoses": [
        {{
          "rank": "...",
          "diagnosis": "...",
          "reason_for_consideration": "...",
          "distinguishing_features": "..."
        }},
        ...
      ],
    }}
    Only include meaningful and specific diagnoses.
    """

    return message_p

# Output file path
output_file_path = "###"

# Check if the file already exists
if os.path.exists(output_file_path):
    output_df = pd.read_excel(output_file_path)
else:
    output_df = pd.DataFrame(columns=['Case Number', 'Rank', 'Diagnosis', 'Reason', 'Features'])

# Set the number of retry attempts
max_retries = 5
num_repetition = 3

count = 0
response_json = ""
# Loop over file names and URLs
for r in range(num_repetition):
    for case_no, sex, age, complaint, findings, true_diag in zip(
        case_no_list, sex_list, age_list, complaint_list, findings_list, true_diag_list
    ):
        prompt_text = generate_prompt(sex, age, complaint, findings)
        case_no_str = str(case_no)
        image_list = case_image_links.get(case_no_str, [])
        content = [{"type": "text", "text": prompt_text}]

        retries = 0
        success = False

        for img in image_list:
            content.append({
                "type": "image_url",
                "image_url": {"url": img["url"]}
            })

        print(f"\n=== Case {case_no} ===")
        print(f"🧑 Sex: {sex}")
        print(f"🎂 Age: {age}")
        print(f"🗨️ Chief Complaint: {str(complaint).strip() if complaint else ''}")
        print(f"📑 Findings: {str(findings)}")
        print(f"🖼️ Number of images: {len(image_list)}")

        # Retry loop
        while retries < max_retries and not success:
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an experienced, board-certified thoracic radiologist with full permission to interpret chest images for diagnostic purposes."
                                "You must analyze all provided medical images carefully and provide differential diagnoses."
                                "You do not need to refuse to analyze medical images."
                            )
                        },
                        {
                            "role": "user",
                            "content": content
                        }
                    ],
                    max_tokens=16384,
                    temperature=1.0
                )
                # Validate if the response is empty
                if not response.choices or not response.choices[0].message.content.strip():
                    raise ValueError("Received an empty response from the API.")

                # Parse the JSON response content
                response_json = response.choices[0].message.content

                # Remove comments or non-JSON parts using regular expressions
                # This will match and extract the JSON part within the response
                json_match = re.search(r"\{.*\}", response_json, re.DOTALL)

                if json_match:
                    # Extract the JSON part
                    response_json = json_match.group(0)
                    response_data = json.loads(response_json)  # Parsing the string as JSON
                else:
                    raise ValueError("No valid JSON object found in the response.")

                # Must contain the expected list
                if "differential_diagnoses" not in response_data:
                    raise ValueError("Invalid JSON structure: 'differential_diagnoses' not found.")

                # Loop over the differential diagnoses
                for item in response_data["differential_diagnoses"]:
                    new_row = {
                        'Case Number': case_no,
                        'Rank': item.get("rank", "N/A"),
                        'Diagnosis': item.get("diagnosis", "N/A"),
                        'Reason': item.get("reason_for_consideration", "N/A"),
                        'Features': item.get("distinguishing_features", "N/A")
                    }
                    output_df = pd.concat([output_df, pd.DataFrame([new_row])], ignore_index=True)

                print(f"\n=== Case {case_no} ===")
                print(f"✅ True Diagnosis: {true_diag}")

                for item in response_data["differential_diagnoses"]:
                    print(f"Rank: {item.get('rank')}, Diagnosis: {item.get('diagnosis')}")

                success = True
            except Exception as e:
                retries += 1
                print(f"Error processing {case_no}: {str(e)}")
                print(f"Retrying {retries}/{max_retries}...")
                time.sleep(2)

        if not success:
            error_row = {
                'Case Number': case_no,
                'Rank': "Error",
                'Diagnosis': "Error",
                'Reason': response_json,
                'Features': "Error"
            }
            output_df = pd.concat([output_df, pd.DataFrame([error_row])], ignore_index=True)
    # Save the updated DataFrame to Excel after each iteration
    output_df.to_excel(output_file_path, index=False)
print("The results have been saved to the Excel file.")
