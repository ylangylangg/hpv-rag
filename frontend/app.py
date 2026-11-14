"""
Streamlit frontend, RAG processing happens through the HTTP API.
distinction:
- messages: for complete frontend convo, including audio, results, citations and errors
- conversation_history: collect data - simple representation of previous text msgs sent to the llm
"""

import io
import os
import wave
import json
from pathlib import Path

import streamlit as st
import httpx  # to send http requests to fastapi
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[0] / ".env")
MAX_RECORDING_SECONDS = 30

DEFAULT_BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
GREETING = "Ask me about HPV vaccinations! Type your question or tap the mic to speak."

def _initial_messages() -> list[dict]:
    return[{"role": "assistant", "text": GREETING}]

# http request helper
def _request(base_url:str, method: str, path: str, **kwargs) -> dict | None:
    try:
        response = httpx.request(
            method,
            f"{base_url.rstrip('/')}{path}",
            timeout=60,
            **kwargs,
        )

        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            return None, st.error("Unexpected response from backend.")

        return payload, None

    # return (payload, error) instead of calling st.error() here, so the caller decides how to show failures
    # errors saved to session_state survive reruns
    # a st.error() shown inside this helper would be wiped by it, so this change is needed
    # previously: except...: st.error("blahblah")
    except httpx.TimeoutException:
        return None, "Backend request timed out."

    except httpx.RequestError:
        return None, "Cannot connect to backend. Check that FastAPI is running."

    except httpx.HTTPStatusError as exc:
        return None, f"Backend error: HTTP {exc.response.status_code}"

    except ValueError:
        return None, "Backend returned an invalid JSON response." 


def _wav_duration_seconds(audio_bytes: bytes) -> float | None:
    """check length of wav recording in seconds before sending to backend"""
    try:
        with wave.open(io.BytesIO(audio_bytes)) as wav:
            return wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError, ZeroDivisionError):
        return None

def _display_result(result: dict, msg_index: int) -> None:
    # display answer from backend
    st.write(result["answer"])

    key_points = result.get("key_points", [])
    if key_points:
        # displays each key point as a bullet
        for point in key_points:
            st.markdown(f"- {point}")

    limitations = result.get("limitations", [])
    if limitations:
        st.warning("Limitations")
        for item in limitations:
            st.markdown(f"- {item}")

    citations = result.get("citations", [])

    st.subheader("**Supporting sources**")

    if not citations:
        st.info("No supporting sources were retrieved.")
        return

    # citations given a sequential numbers each, starting from 1 instead of the default 0 (Source 1, ...)
    for index, citation in enumerate(citations, start=1):

        # expandable section for each citation
        with st.expander(citation.get("title") or f"Source {index}"):
            st.caption(f"Publisher: {citation.get('publisher') or 'Unknown'}")

            if citation.get("published_date"):
                st.caption(f"Published: {citation['published_date']}")

            if citation.get("content"):
                st.write(citation["content"])

            # display clickable link if url is available
            if citation.get("url"):
                st.link_button(
                    "Open original source",
                    citation["url"],

                    # create a unique key using both indexes:
                    # msg_index identifies the convo msg
                    # index identifies the citation within that msg
                    key=f"source_{msg_index}_{index}",
                    )


def _render_message(message: dict, msg_index: int) -> None:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            if message.get("audio"):
                st.caption("Voice message")
                st.audio(message["audio"], format="audio/wav")
                if message.get("text"):
                    st.markdown(f"**Transcript:** {message['text']}")
            else:
                st.write(message["text"])
        elif "text" in message:
            st.write(message["text"])
        elif message.get("error"):
            st.error(message["error"])
        else:
            _display_result(message["result"], msg_index)


def main() -> None:
    # page setup, runs on every rerun
    st.set_page_config(page_title="HPV Guide SG", page_icon="🔎")
    st.title("HPV Guide SG")
    st.header("Your guide to understanding HPV, vaccination and cervical cancer prevention in Singapore.")

    # initialise convo
    if "messages" not in st.session_state:
        st.session_state["messages"] = _initial_messages()

    with st.sidebar:
        st.header("Backend connection")
        backend_url = st.text_input("FastAPI URL", value=DEFAULT_BACKEND_URL).strip()

        if st.button("Check backend health"):
            health = _request(backend_url, "GET", "/health")
            if error:
                st.error(error)
            else:
                st.success("Backend is reachable.")
                st.json(health)

        if st.button("Clear chat"):
            st.session_state["messages"] = _initial_messages()
            st.rerun()

    # loop to re-render convo history from session state after each Streamlit rerun
    for index, message in enumerate(st.session_state["messages"]):
        _render_message(message, index)
    
    # text and audio tgt in one input box
    submission = st.chat_input(
        accept_audio=True,
        max_chars=100,
    )
    if submission is None:
        return

    text = (submission.text or "").strip()
    audio = submission.audio

    if not text and audio is None:
        return

    if audio is not None:
        audio_bytes = audio.getvalue()
        duration = _wav_duration_seconds(audio_bytes)
        if duration is not None and duration > MAX_RECORDING_SECONDS:
            st.warning(f"Recording duration exceeded, keep it within {MAX_RECORDING_SECONDS} seconds")
            return
        user_message={"role": "user", "audio": audio_bytes}
    else:
        user_message = {"role": "user", "text": text}

    # append and display the current user message once
    st.session_state["messages"].append(user_message)
    _render_message(user_message, len(st.session_state["messages"]) - 1)

    # build convo history, excluding the current msg
    conversation_history = []

    for message in st.session_state["messages"][:-1]: 
        if message["role"] == "user":
            content = message.get("text", "")

        elif message["role"] == "assistant" and"result" in message:
                content = message["result"].get("answer", "")

        else:
            continue # skip error-only assistant msgs

        if content:
            conversation_history.append({
                "role": message["role"],
                "content": content
            })


    with st.chat_message("assistant"):
        if audio is not None:
            # loading indicator
            with st.spinner("Transcribing and checking sources..."):
                result, error = _request(
                    backend_url, 
                    "POST", 
                    "/ask/voice",
                    files={"audio": ("recording.wav", audio_bytes, "audio/wav")},
                    data={"history": json.dumps(conversation_history)},
                    )

                if result and result.get("transcript"):
                    user_message["text"] = result["transcript"]
        else:
            # call fastapi
            with st.spinner("Checking sources..."):
                result, error = _request(
                    backend_url,
                    "POST",
                    "/ask",
                    json={
                        "question": text,
                        "history": conversation_history    
                    }
                )

        if error:
            reply = {"role": "assistant", "error": error}
        else:
            reply = {"role": "assistant", "result": result}

        st.session_state["messages"].append(reply)
        st.rerun() # rerender convo

if __name__ == "__main__":
    main()