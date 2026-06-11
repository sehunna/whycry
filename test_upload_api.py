import os
import requests
import json
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
boundary = "boundary_string_why_cry_demo"

metadata = {
    "file": {
        "displayName": "19981.mp4"
    }
}

# Read file data
with open("19981.mp4", "rb") as f:
    file_data = f.read()

# Build payload
part1 = f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: video/mp4\r\n\r\n".encode("utf-8")
part2 = file_data
part3 = f"\r\n--{boundary}--\r\n".encode("utf-8")

payload = part1 + part2 + part3

headers = {
    "X-Goog-Upload-Protocol": "multipart",
    "Content-Type": f"multipart/related; boundary={boundary}"
}

response = requests.post(url, headers=headers, data=payload)
print("Status:", response.status_code)
print("Response:", response.text)
