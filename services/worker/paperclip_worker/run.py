from __future__ import annotations
import os, json
from pathlib import Path
import requests
from paperclip_schemas import ServerParsed

API = os.environ.get("PAPERCLIP_API", "http://127.0.0.1:8000/api")
OUT = Path(__file__).resolve().parents[2] / "data" / "analysis"
OUT.mkdir(parents=True, exist_ok=True)

def iter_captures():
    url = f"{API}/captures/?page_size=200"
    while url:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        for c in data.get("results", data):
            yield c
        url = data.get("next")

def main():
    docs: list[ServerParsed] = []
    for cap in iter_captures():
        detail = requests.get(f"{API}/captures/{cap['id']}/", timeout=30).json()
        if detail.get("server_parsed"):
            sp = ServerParsed.model_validate(detail["server_parsed"])
            docs.append(sp)

    (OUT / "latest.json").write_text(
        json.dumps({"count": len(docs), "ids": [d.id for d in docs]}, indent=2),
        "utf-8"
    )

if __name__ == "__main__":
    main()
