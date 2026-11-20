"""
step 1:
downloads html into data/raw and updates metadata in data/sources.json
append new sources to SOURCES!
running this scraper creates a html file per source scraped, or overwrites it if already exists
"""

import datetime
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2] # go up 3 parent levels


SOURCES = [
    {
        "source_id": "s01",
        "title": "Preventing HPV Infection: HPV Vaccination",
        "publisher": "HealthHub",
        "url": "https://www.healthhub.sg/health-conditions/faqs-on-hpv-and-hpv-immunisation",
    },
    # can add on
    # {
    # "source_id": "s02",
    # "title":
    # "publisher":
    # "url":
    # }
]


def fetch():
    raw_folder = ROOT / "data" / "raw"
    raw_folder.mkdir(parents=True, exist_ok=True)

    records = []

    for source in SOURCES:
        request = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0"},
        )

        print(f"Downloading {source['source_id']} - {source['title']}")

        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()

        raw_path = raw_folder / f"{source['source_id']}.html"
        raw_path.write_bytes(raw)

        record = {
            **source, # dictionary unpacking
            "raw_path": f"data/raw/{source['source_id']}.html",
            "captured_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
        }

        records.append(record)

        print("Saved HTML: ", raw_path)
    
    manifest_path = ROOT / "data" / "sources.json"

    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        existing = {"sources": []}

    # update existing records or append new ones instead of overwriting
    source_map = {
        item["source_id"]: item
        for item in existing["sources"]
    }

    for record in records:
        source_map[record["source_id"]] = record

    manifest = {"sources": list(source_map.values())}

   
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("Saved metadata:", manifest_path)


if __name__ == "__main__":
    fetch()