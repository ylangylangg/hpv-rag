# download source html into data/raw and update data/sources.json

import datetime
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2] # go up 3 parentlevels


SOURCE = {
    "id": "s01",
    "title": "Preventing HPV Infection: HPV Vaccination",
    "publisher": "HealthHub",
    "url": "https://www.healthhub.sg/health-conditions/faqs-on-hpv-and-hpv-immunisation",
}


def fetch():
    raw_folder = ROOT / "data" / "raw"
    raw_folder.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        SOURCE["url"],
        headers={"User-Agent": "Mozilla/5.0"},
    )

    print("Downloading source...")

    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()

    raw_path = raw_folder / f"{SOURCE['id']}.html"
    raw_path.write_bytes(raw)

    record = {
        **SOURCE,
        "captured_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
    }

    manifest = {"sources": [record]}

    manifest_path = ROOT / "data" / "sources.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("Saved HTML:", raw_path)
    print("Saved metadata:", manifest_path)


if __name__ == "__main__":
    fetch()