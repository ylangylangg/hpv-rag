"""
role: coordinator
DOES NOT COMMUNICATE DIRECTLY W FRONTEND!
log the query → rag.search → llm → validate → log outcome → build citations.

input: user qn and relevant convo context

classify intent, do routing:
1) route booking requests to defined responses (provide vaccination/booking links)
    note: in the future, may become 'escalation' also - like provide contact number to call the school to speak to a human?
2) route information requests to RAG
3) handle clarification and out-of-scope requests

output: a validated response object
"""

import json
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from . import llm, rag
from .schemas import AskRequest, AskResponse, Answer, Citation


NO_ANSWER = "I couldn't find enough information in the available sources to answer that."

def insufficient(limitation: str) -> Answer:
    return Answer(answer=NO_ANSWER, key_points=[], sufficient_evidence=False,
                  evidence_ids=[], limitations=[limitation])


def validate_answer(raw: str | None, evidence: list[dict]) -> Answer:
    result = Answer.model_validate_json(raw)
    known = {row["evidence_id"] for row in evidence}
    ids = result.evidence_ids
    if not set(ids) <= known or len(set(ids)) != len(ids):
        raise ValueError("Invalid evidence IDs")
    if result.sufficient_evidence and not ids:
        raise ValueError("Answer without evidence")
    text = " ". join([result.answer, *result.key_points, *result.limitations])
    if re.search(r"https?://|www\.", text, re.I):
        raise ValueError("Model-generated URLs are not accepted")
    return result


def answer(question: str, input_type: str = "text") -> AskResponse:
    question = AskRequest(question=question).question
    request_id = "web-" + str(uuid4())
    started = time.perf_counter()
    evidence, usage, error = [], {}, None
    with rag.connect() as db:
        db.execute("""INSERT INTO query_logs
            (request_id,timestamp,input_type,claim,generation_model,embedding_model,status)
            VALUES (?,?,?,?,?,?,'processing')""",
            (request_id, datetime.now(timezone.utc).isoformat(), input_type, question,
                llm.GENERATION_MODEL, llm.EMBEDDING_MODEL))
    try:
        evidence, usage["query_embedding"] = rag.search(question)
        if not evidence:
            result = insufficient("No usable passages were retrieved from the curated collection.")
        else:
            raw, usage["answer"] = llm.generate_answer(question, evidence)
            try:
                result = validate_answer(raw, evidence)
            except (ValueError, TypeError):
                error = "invalid_answer"
                result = insufficient("The model response failed validation; no conclusion or citations were accepted.")
    except Exception as exc:
        # SDK exception messages may contain credentials; record only the class name.
        error = type(exc).__name__
        result = insufficient("Evidence processing is temporarily unavailable. Please try a new message later.")

    outcome = "answered" if result.sufficient_evidence else "insufficient"
    with rag.connect() as db:
        db.execute("""UPDATE query_logs SET retrieved=?, verdict=?, cited_ids=?, token_usage=?,
            duration_ms=?, error_status=?, status=? WHERE request_id=?""",
            (json.dumps([{"chunk_id": row["id"], "score": row["score"]} for row in evidence]),
            outcome, json.dumps(result.evidence_ids), json.dumps(usage),
                (time.perf_counter() - started) * 1000, error, "error" if error else "done", request_id))
        
    by_id = {row["evidence_id"]: row for row in evidence}
    citations = [Citation(**{field: by_id[evidence_id][field] for field in Citation.model_fields})
                    for evidence_id in result.evidence_ids]
    return AskResponse(
        request_id=request_id, question=question, answer=result.answer,
        key_points=result.key_points, citations=citations,
        limitations=result.limitations, error=error,
    )



def check(claim: str, input_type: str = "text") -> AskResponse:
    """Preserve the claim and expose only citations validated against retrieved evidence."""
    
