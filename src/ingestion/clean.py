"""
step 2:
reads source_id 
extract and clean article content from saved html, into md
preserves structural info (headings, tables, source metadata) for manual verification

note: not generalised yet, only for s01
"""

import hashlib
import json
import pathlib
import re
from bs4 import BeautifulSoup
from markdownify import markdownify


ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE_ID = "s01"
ARTICLE_SELECTOR = ".article-main-content"


def normalize(text):
    # replace repeated spaces, tabs and newlines with one space
    return re.sub(r"\s+", " ", text).strip()


def clean():
    # read the existing manifest
    manifest_path = ROOT / "data" / "sources.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    source = None

    for record in manifest["sources"]:
        if record["id"] == SOURCE_ID:
            source = record
            break

    if source is None:
        raise ValueError("s01 was not found in data/sources.json")

    # read and parse the saved html
    raw_path = ROOT / source["raw_path"]
    raw_html = raw_path.read_bytes()
    soup = BeautifulSoup(raw_html, "html.parser")

    # select article
    article = soup.select_one(ARTICLE_SELECTOR)

    if article is None:
        raise ValueError(
            "Article container not found. Inspect the saved HTML and "
            "check ARTICLE_SELECTOR before continuing."
        )

    if not article.get_text(strip=True):
        raise ValueError("The article container contains no text.")

    # convert accordion labels into section headings
    for label in article.select(".e-n-accordion-item-title-text"):
        label.name = "h3"

    # remove elements that are not article content
    for element in article.select("script, style, nav, form, iframe"):
        element.decompose()

    # remove button tags, keeping any text inside them
    for button in article.find_all("button"):
        button.unwrap()

    # keep hidden accordion bodies: their text may still be useful
    # keep images so their links/alt text can be reviewed later

    # record headings and table cells for manual comparison
    headings = []

    for heading in article.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        headings.append(normalize(heading.get_text(" ", strip=True)))

    tables = []

    for table in article.find_all("table"):
        table_rows = []

        for row in table.find_all("tr"):
            cells = []

            for cell in row.find_all(["th", "td"], recursive=False):
                cells.append(normalize(cell.get_text(" ", strip=True)))

            table_rows.append(cells)

        tables.append(table_rows)

    # convert article HTML to Markdown.
    markdown = markdownify(
        str(article),
        heading_style="ATX",
        bullets="-",
        strip=["span"],
    ).strip()

    # Reduce three or more newlines to two.
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    if not markdown:
        raise ValueError("Markdown conversion produced no content.")

    # add source title if no top-level heading is present at the start.
    if not markdown.startswith("# "):
        markdown = f"# {source['title']}\n\n{markdown}"

    # save the cleaned article and table reference
    clean_folder = ROOT / "data" / "clean"
    clean_folder.mkdir(parents=True, exist_ok=True)

    clean_path = clean_folder / f"{SOURCE_ID}.md"
    clean_path.write_text(markdown, encoding="utf-8")

    tables_path = clean_folder / f"{SOURCE_ID}.tables.json"
    tables_path.write_text(
        json.dumps(tables, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # update only the s01 record in the manifest
    source["clean_path"] = f"data/clean/{SOURCE_ID}.md"
    source["clean_sha256"] = hashlib.sha256(
        markdown.encode("utf-8")
    ).hexdigest()
    source["extraction_selector"] = ARTICLE_SELECTOR
    source["verification_status"] = "extracted_manual_review_pending"
    source["index_ready"] = False

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # save short extraction report for s01
    audit = {
        "id": SOURCE_ID,
        "status": "extracted",
        "characters": len(markdown),
        "headings": headings,
        "table_count": len(tables),
        "manual_review": (
            "Compare the saved HTML with the Markdown. Check headings, "
            "conditions, tables, links and image-only information."
        ),
    }

    audit_path = clean_folder / f"{SOURCE_ID}.audit.json"
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Saved Markdown:", clean_path)
    print("Saved table reference:", tables_path)
    print("Saved extraction report:", audit_path)
    print("Next: review the Markdown before marking it ready to index.")


if __name__ == "__main__":
    clean()

