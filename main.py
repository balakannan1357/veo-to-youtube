import datetime
import os
import time
import requests
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from openai import AzureOpenAI

load_dotenv()
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
AGENT1_DEPLOYMENT = os.getenv("AGENT1_DEPLOYMENT")
YOUTUBE_CLIENT_SECRET_FILE = os.getenv("YOUTUBE_CLIENT_SECRET_FILE")
PROJECT_ID = os.getenv("PROJECT_ID")
BUCKET_NAME = os.getenv("BUCKET_NAME")
VEO_MODEL_ID = os.getenv("VEO_MODEL_ID")
LOCATION = os.getenv("LOCATION")

client = AzureOpenAI(
    api_version=AZURE_OPENAI_API_VERSION,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
)

def get_access_token():
    gcloud_path = r"C:\Users\balak\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    return os.popen(f'"{gcloud_path}" auth print-access-token').read().strip()

def request_gpt() -> str:
    completion = client.chat.completions.create(
        model=AGENT1_DEPLOYMENT,
        messages=[
            {
                "role": "user",
                "content": "Give me a short creative visual prompt for a 30-second satisfying video.",
            },
        ],
    )
    prompt = completion.choices[0].message.content
    today = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"prompt_{today}.txt"
    with open(filename, "w") as f:
        f.write(prompt)
    print(f"Prompt saved to {filename}: {prompt}")
    return prompt

def generate_video_with_veo(prompt):
    print("Sending request to Veo API...")
    url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{VEO_MODEL_ID}:predictLongRunning"
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "durationSeconds": 8,
            "aspectRatio": "16:9",
            "generateAudio": True,
            "storageUri": f"gs://{BUCKET_NAME}/"
        }
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"Veo request failed: {response.text}")
    operation_name = response.json()["name"]
    print("Operation started:", operation_name)
    return operation_name

def poll_video_generation(operation_name):
    operation_url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{VEO_MODEL_ID}:fetchPredictOperation"
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "operationName": operation_name
    }
    while True:
        result = requests.post(operation_url, headers=headers, json=data)
        result_json = result.json()
        if result_json.get("done"):
            break
        print("Waiting for video generation...")
        time.sleep(15)

    videos = result_json["response"]["videos"]
    gcs_uri = videos[0]["gcsUri"]
    local_path = "output/video.mp4"
    os.makedirs("output", exist_ok=True)
    gcloud_path = r"C:\Users\balak\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    os.popen(f'"{gcloud_path}" storage cp {gcs_uri} {local_path}')
    print(f"Downloaded video to {local_path}")
    return local_path

def upload_to_youtube(video_path, title, description):
    print("Authenticating and uploading to YouTube...")
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRET_FILE, scopes)
    credentials = flow.run_local_server()
    youtube = build("youtube", "v3", credentials=credentials)

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["AI", "satisfying", "generated", "shorts"]
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4")
    response = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    ).execute()

    print(f"✅ Video uploaded: https://www.youtube.com/watch?v={response['id']}")

def main():
    prompt = request_gpt()
    operation_name = generate_video_with_veo(prompt)
    video_file = poll_video_generation(operation_name)
    title = f"Satisfying AI Video - {datetime.date.today().strftime('%B %d, %Y')}"
    upload_to_youtube(video_file, title, prompt)

if __name__ == "__main__":
    main()
