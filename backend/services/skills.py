import os
import uuid
import json
import asyncio
import httpx
import urllib.parse
from sqlalchemy.orm import Session
from services import history

# ── helpers ──────────────────────────────────────────────────────────────────

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
POLLINATIONS_MAX_ATTEMPTS = 3
POLLINATIONS_RETRY_DELAY = 2.0          # seconds between attempts


def _build_pollinations_url(query: str, seed: int) -> str:
    encoded = urllib.parse.quote(query)
    return (
        f"{POLLINATIONS_BASE}/{encoded}"
        f"?nologo=true&seed={seed}&width=768&height=768&model=flux"
    )


async def _try_pollinations(client: httpx.AsyncClient, query: str) -> bytes:
    """Try up to POLLINATIONS_MAX_ATTEMPTS times, raising on final failure."""
    last_status = None
    for attempt in range(POLLINATIONS_MAX_ATTEMPTS):
        seed = uuid.uuid4().int % 100_000
        url = _build_pollinations_url(query, seed)
        try:
            r = await client.get(url, timeout=35.0, follow_redirects=True)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
                return r.content                  # ← success
            last_status = r.status_code
        except (httpx.TimeoutException, httpx.RequestError):
            last_status = "timeout"

        if attempt < POLLINATIONS_MAX_ATTEMPTS - 1:
            await asyncio.sleep(POLLINATIONS_RETRY_DELAY)

    raise RuntimeError(f"Pollinations unavailable after {POLLINATIONS_MAX_ATTEMPTS} attempts (last HTTP status: {last_status})")





def _save_image(data: bytes, ext: str = "jpg") -> tuple[str, str]:
    """Save raw bytes to disk and return (filepath, backend_url)."""
    os.makedirs("data", exist_ok=True)
    filename = f"gen_{uuid.uuid4().hex[:10]}.{ext}"
    filepath = os.path.abspath(f"data/{filename}")
    with open(filepath, "wb") as f:
        f.write(data)
    backend_url = f"http://localhost:8001/data/{filename}"
    return filepath, backend_url


# ── main skill handler ────────────────────────────────────────────────────────

async def handle_generate_image(query: str, db: Session, conv_id: str):
    try:
        async with httpx.AsyncClient() as client:
            # ── Primary: Pollinations AI ──────────────────────────────────
            try:
                image_bytes = await _try_pollinations(client, query)
                _, backend_url = _save_image(image_bytes)
                markdown = (
                    f"![Generated Image]({backend_url})\n\n"
                    f"*Image generated for: {query}*"
                )

            except RuntimeError as poll_err:
                markdown = (
                    f"⚠️ **Image generation failed**: {poll_err}. "
                    f"Please try again later."
                )

        # Save to conversation history
        if conv_id and db:
            db_conv = history.get_conversation(db, conv_id)
            if db_conv:
                updated_msgs = db_conv.messages + [{"role": "assistant", "content": markdown}]
                history.update_conversation(db, conv_id, updated_msgs)

        yield f"data: {json.dumps({'choices': [{'delta': {'content': markdown}}]})}\n\n"

    except httpx.HTTPStatusError as e:
        msg = (
            f"⚠️ Image generation failed: Server returned HTTP {e.response.status_code}. "
            f"The service may be temporarily overloaded — please try again shortly."
        )
        yield f"data: {json.dumps({'choices': [{'delta': {'content': msg}}]})}\n\n"
    except Exception as e:
        msg = f"⚠️ Image generation failed unexpectedly: {e}"
        yield f"data: {json.dumps({'choices': [{'delta': {'content': msg}}]})}\n\n"


# ── skill dispatcher ──────────────────────────────────────────────────────────

async def process_skills(text_input: str, db: Session, conv_id: str):
    """Checks the user input for skill triggers. Returns an async generator if triggered, else None."""
    if text_input.startswith("@generate_image"):
        query = text_input.replace("@generate_image", "").strip()
        if not query:
            return None
        return handle_generate_image(query, db, conv_id)
    return None
