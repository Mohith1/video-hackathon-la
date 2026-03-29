"""
SegmentIQ — Bedrock bearer token connectivity test.
Run from backend/ after setting AWS_BEARER_TOKEN_BEDROCK in .env:
    python test_bedrock.py
"""
import os, json, base64
import httpx
from dotenv import load_dotenv

load_dotenv()

BEARER  = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
REGION  = os.getenv("AWS_REGION", "us-east-1")
ACCOUNT = os.getenv("AWS_ACCOUNT_ID", "719573866669")
BUCKET  = os.getenv("S3_BUCKET", "")

# Correct inference profile model IDs (us. prefix for us-east-1)
MARENGO = "us.twelvelabs.marengo-embed-3-0-v1:0"
PEGASUS = "us.twelvelabs.pegasus-1-2-v1:0"

BASE = f"https://bedrock-runtime.{REGION}.amazonaws.com"
HEADERS = {
    "Authorization": f"Bearer {BEARER}",
    "Content-Type":  "application/json",
    "Accept":        "application/json",
}

if not BEARER:
    print("ERROR: AWS_BEARER_TOKEN_BEDROCK not set in .env")
    exit(1)

print(f"=== SegmentIQ Bedrock test ===")
print(f"Region  : {REGION}")
print(f"Account : {ACCOUNT}")
print(f"Token   : {BEARER[:16]}...{BEARER[-8:]}")


def call(model_id, body, label):
    url = f"{BASE}/model/{model_id}/invoke"
    print(f"\n[{label}]  {model_id}")
    print(f"  body keys: {list(body.keys())}")
    try:
        r = httpx.post(url, json=body, headers=HEADERS, timeout=60.0)
        print(f"  status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"  response keys: {list(data.keys())}")
            print(f"  PASS")
            return data
        else:
            print(f"  body: {r.text[:300]}")
            print(f"  FAIL")
            return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


# 1. Marengo text embedding
r = call(MARENGO, {
    "inputType": "text",
    "text": {"inputText": "sports broadcast timeout moment"},
}, "Marengo text")
if r:
    data = r.get("data", [])
    emb = data[0].get("embedding", []) if data and isinstance(data[0], dict) else (data[0] if data else [])
    print(f"  embedding dim={len(emb)}  first3={emb[:3]}")


# 2. Marengo image embedding — base64 tiny JPEG (no S3 needed)
tiny_jpeg_b64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
    "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAARCAABAAEDASIA"
    "AhEBAxEB/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAU"
    "AQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8A"
    "LIAAB//Z"
)
r = call(MARENGO, {
    "inputType": "image",
    "image": {"mediaSource": {"base64String": tiny_jpeg_b64}},
}, "Marengo image (base64)")
if r:
    data = r.get("data", [])
    emb = data[0].get("embedding", []) if data and isinstance(data[0], dict) else (data[0] if data else [])
    print(f"  embedding dim={len(emb)}  first3={emb[:3]}")


# 3. Pegasus (only if S3_BUCKET and VIDEO_FILE are set)
VIDEO_FILE = os.getenv("VIDEO_FILE", "")
if BUCKET and VIDEO_FILE:
    video_uri = f"s3://{BUCKET}/{VIDEO_FILE}"
    r = call(PEGASUS, {
        "inputPrompt": 'Describe this video briefly. Return JSON: {"summary": "..."}',
        "mediaSource": {"s3Location": {"uri": video_uri, "bucketOwner": ACCOUNT}},
        "temperature": 0.2,
    }, "Pegasus video")
    if r:
        print(f"  message: {str(r.get('message',''))[:300]}")
        print(f"  finishReason: {r.get('finishReason')}")
else:
    print(f"\n[Pegasus] skipped — set S3_BUCKET and VIDEO_FILE in .env to test")

print("\n=== Done ===")
