"""
API entry point, connects backend to frontend
Run: python -m uvicorn backend.main:app --reload.
"""
import tempfile
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile, Form
from pydantic import ValidationError

from . import answerer, rag, stt
from .schemas import AskRequest, AskResponse, ClarificationNeeded, HealthResponse, VoiceAskResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    rag.init_database()
    yield


app = FastAPI(title="HPV Vaccine RAG", version="0.1.0", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
# checks for: liveness (application running) and readiness (if application can serve requests)
def health() -> HealthResponse:
    try:
        with rag.connect() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        raise HTTPException(503, "Storage unavailable.") from None
    return HealthResponse()


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    # Synchronous handlers run in FastAPI's thread pool, including model/SQLite work.
    try:
        return answerer.answer(payload.question)
    except ClarificationNeeded as exc:
        raise 
    except Exception:
        raise HTTPException(503, "Answer generation is temporarily unavailable.") from None

# probably should be more like that now
# @app.post("/ask")
# def ask(request: AskRequest):
#     question = request.question

#     evidence = retrieve(question)

#     result = generate_answer(question, evidence)

#     return result


@app.post("/ask/voice", response_model=VoiceAskResponse)
def ask_voice(
    audio: Annotated[UploadFile, File(description="Microphone recording.")],
    history: Annotated[str, Form()] = "[]",
) -> VoiceAskResponse:
    try:
        history_list = json.loads(history)

        with tempfile.NamedTemporaryFile(suffix=".wav") as temp:
            temp.write(audio.file.read())
            temp.flush()
            transcript = stt.transcribe(Path(temp.name))

        payload = AskRequest(question=transcript, history=history_list)
        result = answerer.answer(payload.question, payload.history)

        return VoiceAskResponse(
            **result.model_dump(),
            transcript=transcript,
        )

    except ClarificationNeeded as exc:
        raise HTTPException(422, str(exc)) from None
    except ValidationError(json.JSONDecodeError, ValidationError):
        raise HTTPException(
            422,
            "The transcript must contain a question of 1 to 100 characters."
        ) from None
    except Exception:
        raise HTTPException(
            503, "Audio processing is temporarily unavailable."
        ) from None
    finally:
        audio.file.close()