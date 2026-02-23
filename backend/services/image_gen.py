import os
import uuid
import httpx
import urllib.parse
import json
from sqlalchemy.orm import Session
from models.schemas import ChatRequest
from services import history

async def generate_image_stream(request: ChatRequest, offline_mode: bool, conv_id: str = None, db: Session = None):
    # Extract text from the last message
    last_message = request.messages[-1]
    text = ""
    if isinstance(last_message.content, str):
        text = last_message.content
    elif isinstance(last_message.content, list):
        for item in last_message.content:
            if item.get("type") == "text":
                text = item.get("text", "")
                break
                
    query = text.replace("@generate_image", "").strip()
    
    if offline_mode:
        msg = "⚠️ Image generation skill is disabled in offline mode."
        yield f"data: {json.dumps({'choices': [{'delta': {'content': msg}}]})}\n\n"
        if conv_id and db:
            db_conv = history.get_conversation(db, conv_id)
            if db_conv:
                updated_msgs = db_conv.messages + [{"role": "assistant", "content": msg}]
                history.update_conversation(db, conv_id, updated_msgs)
        return
        
    if not query:
        msg = "Please provide a prompt for the image generation."
        yield f"data: {json.dumps({'choices': [{'delta': {'content': msg}}]})}\n\n"
        return
        
    try:
        encoded = urllib.parse.quote(query)
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?nologo=true&seed={uuid.uuid4().int % 1000}"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        os.makedirs("data", exist_ok=True)
        filename = f"gen_{uuid.uuid4().hex[:8]}.jpg"
        filepath = os.path.abspath(f"data/{filename}")
        
        # Download image in backend to bypass browser CORS / 403 blocks
        async with httpx.AsyncClient() as client:
            r = await client.get(image_url, headers=headers, timeout=30.0, follow_redirects=True)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
                
        # Return markdown pointing to backend static endpoint
        backend_url = f"http://localhost:8001/data/{filename}"
        markdown_response = f"![Generated Image]({backend_url})\n\n*Image generated successfully for: {query}*"
        
        # Yeild exactly how OpenAISSE handles deltas
        chunk = json.dumps({"choices": [{"delta": {"content": markdown_response}}]})
        yield f"data: {chunk}\n\n"
        
        # Save history
        if conv_id and db:
            db_conv = history.get_conversation(db, conv_id)
            if db_conv:
                updated_msgs = db_conv.messages + [{"role": "assistant", "content": markdown_response}]
                history.update_conversation(db, conv_id, updated_msgs)
                
    except Exception as e:
        error_msg = f"⚠️ Image generation failed: {e}"
        yield f"data: {json.dumps({'choices': [{'delta': {'content': error_msg}}]})}\n\n"
