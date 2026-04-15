import base64
import os
import subprocess
import time

import requests
from tenacity import retry, stop_after_delay, wait_fixed


PROJECT = "kov_e2e"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", "docker-compose.e2e.yml"]
API_URL = "http://localhost:18000"


SAMPLE_PDF_B64 = (
    "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4K"
    "ZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4K"
    "ZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAg"
    "MCA2MTIgNzkyXQogICAvQ29udGVudHMgNCAwIFIKICAgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAv"
    "RjEgNSAwIFIgPj4gPj4KPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA1NSA+PgpzdHJlYW0K"
    "QlQKL0YxIDI0IFRmCjAgNzAwIFRkCihIZWxsbyB3b3JsZCkgVGoKRVQKZW5kc3RyZWFtCmVuZG9i"
    "ago1IDAgb2JqCjw8IC9UeXBlIC9Gb250IC9TdWJ0eXBlIC9UeXBlMSAvQmFzZUZvbnQgL0hlbHZl"
    "dGljYSA+PgplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDE1IDAw"
    "MDAwIG4gCjAwMDAwMDAwNjIgMDAwMDAgbiAKMDAwMDAwMDEyNCAwMDAwMCBuIAowMDAwMDAwMjcx"
    "IDAwMDAwIG4gCjAwMDAwMDA0MDkgMDAwMDAgbiAKdHJhaWxlcgo8PCAvU2l6ZSA2IC9Sb290IDEg"
    "MCBSID4+CnN0YXJ0eHJlZgo0OTkKJSVFT0YK"
)


@retry(stop=stop_after_delay(120), wait=wait_fixed(2))
def wait_health():
    r = requests.get(API_URL + "/health", timeout=2)
    assert r.status_code == 200


def setup_module():
    subprocess.run(COMPOSE + ["up", "-d", "--build"], check=True)
    wait_health()


def teardown_module():
    subprocess.run(COMPOSE + ["down", "-v"], check=False)


def test_scan_and_search_roundtrip():
    pdf_bytes = base64.b64decode(SAMPLE_PDF_B64)
    files = {"file": ("sample.pdf", pdf_bytes, "application/pdf")}
    r = requests.post(API_URL + "/rag/scan/upload", files=files, timeout=60)
    assert r.status_code == 200
    doc_id = r.json()["document_id"]

    r = requests.get(API_URL + f"/rag/scan/documents/{doc_id}", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    r = requests.post(
        API_URL + "/rag/search",
        json={"user_query": "мне тревожно", "scenario_id": "dialog", "language": "ru", "search_profile": "quick_advice"},
        timeout=60,
    )
    assert r.status_code == 200
    data = r.json()
    parts = data["telegram_messages"]
    assert 1 <= len(parts) <= 3
    assert all(len(p["text"]) <= 600 for p in parts)
