# HPV Information Assistant
IN PROGRESS! Stuff not linked properly yet

A Singapore-focused HPV information chatbot using Retrieval-Augmented Generation (RAG). Uses Streamlit for chat interface, FastAPI to handle requests, and the backend retrieves information from reviewed SG healthcare sources before answers are generated with an LLM.

Learn more about HPV, vaccination and cervical cancer prevention, with grounded answers and citations from Singapore healthcare resources.

```text
hpv-rag/
|-- frontend/
|   `-- app.py
|-- backend/
|   |-- __init__.py
|   |-- main.py
|   |-- schemas.py
|   |-- rag.py
|   |-- answerer.py
|   |-- llm.py
|   |-- stt.py  # speech to text
|   `-- ingestion
|       |-- __init__.py
|       |-- scrape.py
|       |-- clean.py
|       `-- ingest.py
|-- data/
|   |-- raw/
|   |-- clean/
|   |-- processed/
|   `-- sources.json
|-- storage/
|-- requirements.txt
|-- .env
|-- .env.example
|-- .gitignore
`-- README.md
```

## Setup

Use Python 3.12

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API key.

## Ingestion

The ingestion workflow prepares source documents for retrieval.

1. Define sources: Add source URLs and basic metadata to the `SOURCES` list in `scrape.py`
2. Download: Run `scrape.py` to download the original HTML into `data/raw/` and update `sources.json` automatically
3. Clean: Run `clean.py` to extract and structure the content into `data/clean/`
4. Review: Manually inspect the cleaned documents and save approved versions under `data/reviewed/`
5. Ingest: Run `ingest.py` to create chunks, embeddings and the retrieval index

Prioritise authoritative Singapore healthcare sources, such as MOH and HealthHub. Retain publication and retrieval dates to track changes in source information. Only reviewed documents should be included in the retrieval corpus; scraped content must be checked before ingestion.

Use the appropriate ingestion options when updating or rebuilding the corpus. Stop the backend before modifying reviewed documents or rebuilding the retrieval index.


## Running the application

Open two PowerShell terminals at the repository root.

**Terminal 1 — FastAPI backend**

```powershell
py -m uvicorn backend.main:app --reload
```

**Terminal 2 — Streamlit frontend**

```powershell
py -m streamlit run frontend/app.py
```

Open the URL printed by Streamlit