# HPV Information Assistant
IN PROGRESS! Stuff not linked properly yet

## Motivation

Finding specific information about Human Papillomavirus (HPV) can be difficult, requiring navigating multiple webpages and official sources. Information can also change over time as national guidance is updated. For example, MOH's press release on *2 October 2026* announced the introduction of HPV9 (Gardasil 9) into the National Childhood and Adult Immunisation Schedules from January 2027. Such updates may not yet be reflected across existing webpages and tools, making it harder for users to find the latest recommendations in one place.

This project aims to make Singapore-specific HPV information easier to access through a single chat interface, retrieving relevant information from manually reviewed sources and providing citations for users to verify.

## Overview

A Singapore-focused healthcare information chatbot about HPV. Users can ask questions about HPV types, transmission, vaccine types, eligibility, subsidies, and updated schedules.

The application uses a Retrieval-Augmented Generation (RAG) pipeline to find relevant passages from its knowledge base and generate responses using an LLM. Built with Streamlit for the chat interface and FastAPI for backend request handling, it provides source citations alongside generated answers.


Explore key information about HPV, including how it spreads, different HPV types, available vaccinations, screening, and cervical cancer prevention with reliable answers supported by Singapore healthcare resources.

```text
hpv-rag/
|-- src/
|   |-- -- ingestion
|       |-- __init__.py
|       |-- scrape.py
|       |-- clean.py
|       `-- ingest.py
|   |-- __init__.py
|   |-- main.py
|   |-- schemas.py
|   |-- rag.py
|   |-- answerer.py
|   |-- llm.py
|   `-- stt.py  # speech to text
|-- data/
|   |-- raw/
|   |-- clean/
|   |-- processed/
|   `-- sources.json
|-- app.py # streamlit frontend
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