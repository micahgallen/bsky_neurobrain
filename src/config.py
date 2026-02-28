import os
from dotenv import load_dotenv

load_dotenv()

HOSTNAME = os.environ.get("HOSTNAME", "")
FEED_URI = os.environ.get("FEED_URI", "")
HANDLE = os.environ.get("HANDLE", "")
PASSWORD = os.environ.get("PASSWORD", "")
SERVICE_DID = os.environ.get("SERVICE_DID", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
CLASSIFIER_VERSION = os.environ.get("CLASSIFIER_VERSION", "v2")  # "v1" or "v2"
SIGNAL_FEED_URI = os.environ.get("SIGNAL_FEED_URI", "")

if not SERVICE_DID and HOSTNAME:
    SERVICE_DID = f"did:web:{HOSTNAME}"
