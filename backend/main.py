"""
Backend FastAPI app — minimal.
The Gradio UI calls the service layer directly (no REST round-trip for chat).
This file is kept for potential future REST API extensions.
"""

from fastapi import FastAPI

app = FastAPI(title="LLM Agent Hub — Backend")


@app.get("/")
def read_root():
    return {"status": "Backend is available (Gradio UI is the primary interface)"}
