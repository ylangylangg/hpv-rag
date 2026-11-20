"""OpenAI embeddings and structured assessments, called only when evidence is needed."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .schemas import Assessment, IntentResult


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
GENERATION_MODEL = os.getenv("OPENAI_GENERATION_MODEL", "")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = int(os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "1536"))
if not 1 <= EMBEDDING_DIMENSIONS <= 3072:
    raise ValueError("OPENAI_EMBEDDING_DIMENSIONS must be 1 to 3072")

ASSESSMENT_RULES = """You are an evidence-grounded question-answering assistant.

Answer the user's question using the provided
retrieved evidence.

Instructions:
1. Answer the question directly.
2. Synthesise relevant information from multiple sources.
3. Cite the sources supporting your answer.
4. Do not introduce unsupported factual claims.
5. If the evidence is insufficient, clearly state this.
6. If sources contradict each other, explain the discrepancy.
7. Distinguish current guidance from outdated information.
8. Do not invent citations or source details.
9. List in evidence_ids only the passages you actually used. Set sufficient_evidence=false if they don't answer the question.
10. Give general information only, not personal medical advice; suggest a clinician for individual circumstances."""


def embed(texts: list[str]) -> tuple[list[list[float]], dict]:
    # A scoped client needs no application factory, shared state, or shutdown hook.
    with OpenAI(timeout=30, max_retries=2) as client:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL, dimensions=EMBEDDING_DIMENSIONS, input=texts)
    data = sorted(response.data, key=lambda item: item.index)
    if [item.index for item in data] != list(range(len(texts))):
        raise ValueError("Invalid embedding response mapping")
    return [item.embedding for item in data], response.usage.model_dump() if response.usage else {}

# new: in this file, classify intent first - add separate INTENT_CLASSIFICATION_PROMPT and classify_intent()
# Add intent routing to answerer.py, before retrieval or answer generation.
def classify_intent(message: str) -> IntentResult:
    # Send message to LLM with classification instructions.
    # Require structured output matching IntentResult.
    # Return validated result.
    ...


def generate_answer(question: str, evidence: list[dict]) -> tuple[str | None, dict]:
    if not GENERATION_MODEL.strip():
        raise ValueError("Set OPENAI_GENERATION_MODEL in .env to a model available to your project")
    # Citation titles and URLs in the response come from SQLite, never model output.
    passages = [{key: row[key] for key in
                 ("evidence_id", "content", "title", "publisher", "published_date", "retrieved_date")}
                for row in evidence]
    messages = [
        {"role": "system", "content": ASSESSMENT_RULES},
        {"role": "user", "content": json.dumps({"question": question,
            "assessment_date": datetime.now(timezone.utc).date().isoformat(),
            "evidence": passages}, ensure_ascii=False)},
    ]
    options = {"reasoning_effort": "low"} if GENERATION_MODEL.startswith(("gpt-5", "gpt-6")) else {}
    with OpenAI(timeout=30, max_retries=2) as client:
        response = client.chat.completions.create(
            model=GENERATION_MODEL, messages=messages, max_completion_tokens=4096,
            response_format={"type": "json_schema", "json_schema": {
                "name": "assessment", "strict": True, "schema": Assessment.model_json_schema()}}, **options)
    usage = response.usage.model_dump() if response.usage else {}
    if not response.choices:
        return None, usage
    choice = response.choices[0]
    if choice.finish_reason != "stop" or choice.message.refusal:
        return None, usage
    return choice.message.content, usage
