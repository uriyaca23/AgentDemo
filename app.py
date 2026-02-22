"""
LLM Agent Hub — Gradio UI
==========================
Single-file Gradio Blocks application that replaces the Next.js frontend.
All LLM interaction flows through the backend services directly.
"""

import sys, os, asyncio, re, base64, urllib.parse, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import gradio as gr
from database import get_db, engine
from models.db_models import Base
from services.llm_router import get_chat_generator
from services.models import fetch_models, INTERNAL_MODELS
from services import history
from settings import settings

# ---------------------------------------------------------------------------
# Database init
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Global model registry (populated on app start)
# ---------------------------------------------------------------------------
ALL_MODELS: list[dict] = []
MODEL_MAP: dict[str, dict] = {}  # id -> model dict


async def refresh_model_list():
    global ALL_MODELS, MODEL_MAP
    ALL_MODELS = await fetch_models()
    MODEL_MAP = {m["id"]: m for m in ALL_MODELS}


def _model_display(m: dict) -> str:
    """Human-readable label for model dropdown."""
    provider_tag = "🖥️ Local" if m["provider"] == "internal" else "☁️ OpenRouter"
    cost = "Free" if m["cost_per_m"] == 0 else f"${m['cost_per_m']:.2f}/M"
    ctx = f"{m['context_length'] // 1000}K"
    return f"{m['name']}  [{provider_tag} · {cost} · {ctx}]"


def _model_choices(offline: bool = False) -> list[str]:
    choices = []
    for m in ALL_MODELS:
        if offline and m["provider"] != "internal":
            continue
        choices.append(_model_display(m))
    return choices


def _display_to_model_id(display: str) -> str | None:
    for m in ALL_MODELS:
        if _model_display(m) == display:
            return m["id"]
    return None


# ---------------------------------------------------------------------------
# Thinking-block post-processing  (<think>…</think> → collapsible HTML)
# ---------------------------------------------------------------------------
def _process_thinking_blocks(text: str) -> str:
    """Convert <think>…</think> blocks into collapsible <details> HTML."""

    def _replace_closed(match):
        inner = match.group(1).strip()
        if not inner:
            return ""
        return (
            '<details style="margin:8px 0;padding:8px 12px;border-radius:8px;'
            "background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);"
            'cursor:pointer">'
            '<summary style="font-size:0.8em;font-weight:600;color:#94a3b8;'
            'text-transform:uppercase;letter-spacing:0.05em;user-select:none">'
            "💭 Thought Process</summary>"
            f'<div style="margin-top:8px;font-style:italic;color:#94a3b8">\n\n{inner}\n\n</div></details>'
        )

    def _replace_open(match):
        inner = match.group(1).strip()
        if not inner:
            return ""
        return (
            '<details open style="margin:8px 0;padding:8px 12px;border-radius:8px;'
            "background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);"
            'cursor:pointer">'
            '<summary style="font-size:0.8em;font-weight:600;color:#f59e0b;'
            'text-transform:uppercase;letter-spacing:0.05em;user-select:none">'
            "⏳ Thinking…</summary>"
            f'<div style="margin-top:8px;font-style:italic;color:#94a3b8">\n\n{inner}\n\n</div></details>'
        )

    # Closed blocks first
    text = re.sub(
        r"<think>([\s\S]*?)</think>", _replace_closed, text
    )
    # Unclosed (still streaming)
    text = re.sub(r"<think>([\s\S]*?)$", _replace_open, text)
    return text


# ---------------------------------------------------------------------------
# Chat handler (streaming generator)
# ---------------------------------------------------------------------------
async def chat_handler(
    user_input: dict,  # MultimodalTextbox returns {"text": ..., "files": [...]}
    chat_history: list,
    model_display: str,
    mode: str,
    offline: bool,
    conv_id: str | None,
):
    """
    Gradio chatbot streaming handler.
    Returns an async generator that updates (chat_history, conv_id).
    """
    text = user_input.get("text", "").strip() if isinstance(user_input, dict) else str(user_input).strip()
    files = user_input.get("files", []) if isinstance(user_input, dict) else []

    if not text and not files:
        yield chat_history, conv_id or ""
        return

    # Build the user content (text + optional images)
    if files:
        content_parts = []
        if text:
            content_parts.append({"type": "text", "text": text})
        for f in files:
            file_path = f if isinstance(f, str) else f.get("path", f.get("name", ""))
            try:
                with open(file_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode()
                ext = os.path.splitext(file_path)[1].lower().lstrip(".")
                mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
                content_parts.append(
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                )
            except Exception:
                pass  # skip unreadable files
        user_content = content_parts
    else:
        user_content = text

    # Handle Skills (@web_browser, @generate_image)
    if text.startswith("@web_browser"):
        query = text.replace("@web_browser", "").strip()
        if offline:
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": "⚠️ Web browser skill is disabled in offline mode."})
            yield chat_history, conv_id or ""
            return
            
        if not query:
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": "Please provide a query for the web browser."})
            yield chat_history, conv_id or ""
            return
            
        try:
            from duckduckgo_search import DDGS
            results = DDGS().text(query, max_results=3)
            if not results:
                user_content = f"I tried to search the web for '{query}', but no results were returned. Please let the user know."
            else:
                search_context = "\n".join([f"- **{r['title']}**: {r['body']}" for r in results])
                user_content = f"I searched the web for '{query}'. Here are the results:\n{search_context}\n\nPlease summarize or answer my query based on these results."
        except Exception as e:
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": f"⚠️ Web search failed: {e}"})
            yield chat_history, conv_id or ""
            return

    elif text.startswith("@generate_image"):
        query = text.replace("@generate_image", "").strip()
        if offline:
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": "⚠️ Image generation skill is disabled in offline mode."})
            yield chat_history, conv_id or ""
            return
            
        if not query:
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": "Please provide a prompt for the image generation."})
            yield chat_history, conv_id or ""
            return
            
        try:
            import httpx, urllib.parse, uuid, os
            encoded = urllib.parse.quote(query)
            image_url = f"https://image.pollinations.ai/prompt/{encoded}?nologo=true&seed={uuid.uuid4().int % 1000}"
            headers = {"User-Agent": "Mozilla/5.0"}
            
            os.makedirs("data", exist_ok=True)
            filepath = os.path.abspath(f"data/gen_{uuid.uuid4().hex[:8]}.jpg")
            
            # Download image in backend to bypass browser CORS / Pollinations 403 blocks
            with httpx.Client() as client:
                r = client.get(image_url, headers=headers, timeout=30.0, follow_redirects=True)
                r.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(r.content)
            
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": (filepath,)})
            chat_history.append({"role": "assistant", "content": f"*Image generated successfully for: {query}*"})
            
            db = next(get_db())
            try:
                messages_for_llm = []
                if conv_id:
                    db_conv = history.get_conversation(db, conv_id)
                    if db_conv and db_conv.messages:
                        messages_for_llm = list(db_conv.messages)
                
                messages_for_llm.append({"role": "user", "content": text})
                messages_for_llm.append({"role": "assistant", "content": f"[Generated Image Saved To: {filepath}]"})
            
                if not conv_id:
                    title = text[:35] + ("..." if len(text) > 35 else "")
                    db_conv = history.create_conversation(db, title=title, messages=messages_for_llm)
                    conv_id = db_conv.id
                else:
                    history.update_conversation(db, conv_id, messages_for_llm)
                    
                yield chat_history, conv_id
                return
            finally:
                db.close()
        except Exception as e:
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": f"⚠️ Image generation failed: {e}"})
            yield chat_history, conv_id or ""
            return

    # Build display message for the chatbot widget
    display_files = []
    for f in files:
        fp = f if isinstance(f, str) else f.get("path", f.get("name", ""))
        display_files.append({"path": fp})

    user_display = {"role": "user", "content": text}
    if display_files:
        # Show images inline in the chatbot
        user_display = {"role": "user", "content": text}

    # Append user message to chat history
    chat_history = list(chat_history) + [
        {"role": "user", "content": text},
    ]
    # If there are images, show them as separate image messages
    for f in files:
        fp = f if isinstance(f, str) else f.get("path", f.get("name", ""))
        chat_history.append({"role": "user", "content": gr.Image(fp)})

    # Build messages list for the LLM (full conversation)
    messages_for_llm = []
    db = next(get_db())
    try:
        # Load existing conversation messages if resuming
        if conv_id:
            db_conv = history.get_conversation(db, conv_id)
            if db_conv and db_conv.messages:
                messages_for_llm = list(db_conv.messages)

        # Append the new user message
        messages_for_llm.append({"role": "user", "content": user_content})

        # Create or update conversation
        if not conv_id:
            title_text = text if text else "Image chat"
            title = title_text[:35] + ("..." if len(title_text) > 35 else "")
            db_conv = history.create_conversation(db, title=title, messages=messages_for_llm)
            conv_id = db_conv.id
        else:
            history.update_conversation(db, conv_id, messages_for_llm)

        # Resolve model ID
        model_id = _display_to_model_id(model_display)
        if not model_id:
            chat_history.append({"role": "assistant", "content": "⚠️ Please select a model."})
            yield chat_history, conv_id or ""
            return

        # Start streaming assistant response
        chat_history.append({"role": "assistant", "content": ""})
        full_response = ""

        generator = get_chat_generator(
            model=model_id,
            messages=messages_for_llm,
            mode=mode.lower(),
            offline_mode=offline,
            conv_id=conv_id,
            db=db,
        )

        async for token in generator:
            full_response += token
            # Process thinking blocks for display
            display_text = _process_thinking_blocks(full_response)
            chat_history[-1] = {"role": "assistant", "content": display_text}
            yield chat_history, conv_id or ""

        # Ensure final state is flushed
        display_text = _process_thinking_blocks(full_response)
        chat_history[-1] = {"role": "assistant", "content": display_text}
        yield chat_history, conv_id or ""

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Conversation history helpers
# ---------------------------------------------------------------------------
def load_conversations(search: str = ""):
    db = next(get_db())
    try:
        convs = history.get_conversations(db, limit=100)
        if search.strip():
            convs = [c for c in convs if search.lower() in (c.title or "").lower()]
        if not convs:
            return gr.update(choices=[], value=None)
        choices = [(f"{c.title or 'Untitled'}  ({c.id[:8]}…)", c.id) for c in convs]
        return gr.update(choices=choices, value=None)
    finally:
        db.close()


def load_conversation_messages(conv_id: str):
    if not conv_id:
        return [], ""
    db = next(get_db())
    try:
        db_conv = history.get_conversation(db, conv_id)
        if not db_conv or not db_conv.messages:
            return [], conv_id

        chat_messages = []
        for msg in db_conv.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Multimodal content — extract text
                text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                content = "\n".join(text_parts) if text_parts else "[Image]"
            if role == "assistant":
                content = _process_thinking_blocks(content)
            chat_messages.append({"role": role, "content": content})
        return chat_messages, conv_id
    finally:
        db.close()


def new_chat():
    return [], "", ""


def toggle_offline(offline: bool):
    settings.set_network_enabled(not offline)
    choices = _model_choices(offline)
    return gr.update(choices=choices, value=choices[0] if choices else None)


# ---------------------------------------------------------------------------
# Custom CSS (dark premium theme matching the original UI)
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
/* Global dark premium styles */
body, .gradio-container {
    background: linear-gradient(135deg, #0b0c0f 0%, #12141a 100%) !important;
    max-width: 100% !important;
    font-family: 'Inter', sans-serif !important;
}
footer { display: none !important; }

/* Chatbot container & bubbles */
.gradio-chatbot {
    background: transparent !important;
    border: none !important;
}
.message {
    border-radius: 12px !important;
    padding: 12px 18px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1) !important;
}
/* User bubble */
.message.user {
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    color: white !important;
    border: none !important;
}
/* Bot bubble */
.message.bot {
    background: rgba(30, 41, 59, 0.8) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    color: #f1f5f9 !important;
}

/* Sidebar styling */
#sidebar {
    background: rgba(11, 13, 16, 0.95) !important;
    backdrop-filter: blur(16px) !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
    box-shadow: 4px 0 24px rgba(0,0,0,0.2) !important;
}

/* Inputs, Dropdowns, Radios */
.gr-input, .gr-dropdown, .gr-radio, .gr-textbox input, .gr-multimodal-textbox {
    background: rgba(255, 255, 255, 0.03) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
}
.gr-input:focus, .gr-dropdown:focus, .gr-textbox input:focus {
    border-color: #4f46e5 !important;
    box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.2) !important;
}

/* Primary buttons */
.gr-button-primary {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3) !important;
    transition: transform 0.2s, box-shadow 0.2s !important;
}
.gr-button-primary:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 16px rgba(79, 70, 229, 0.4) !important;
}

/* Conversation list wrap */
#conv-list .wrap {
    max-height: 55vh;
    overflow-y: auto;
}

/* Skills accordion */
details summary {
    cursor: pointer;
    user-select: none;
    padding: 8px;
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    transition: background 0.2s;
}
details summary:hover {
    background: rgba(255,255,255,0.06);
}

/* Markdown styling inside Chatbot */
.chatbot pre {
    background: #0d1117 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 8px !important;
}
"""

# ---------------------------------------------------------------------------
# Build Gradio UI
# ---------------------------------------------------------------------------
def create_app():
    # Populate models on startup
    asyncio.get_event_loop().run_until_complete(refresh_model_list())
    initial_choices = _model_choices(offline=False)

    theme = gr.themes.Base(
        primary_hue=gr.themes.colors.indigo,
        secondary_hue=gr.themes.colors.purple,
        neutral_hue=gr.themes.colors.slate,
        font=gr.themes.GoogleFont("Inter"),
    ).set(
        body_background_fill="#0f1115",
        body_background_fill_dark="#0f1115",
        body_text_color="#f1f5f9",
        body_text_color_dark="#f1f5f9",
        block_background_fill="#1e293b",
        block_background_fill_dark="#1e293b",
        block_border_color="rgba(255,255,255,0.08)",
        block_border_color_dark="rgba(255,255,255,0.08)",
        input_background_fill="#0b0d10",
        input_background_fill_dark="#0b0d10",
        button_primary_background_fill="#4f46e5",
        button_primary_background_fill_dark="#4f46e5",
        button_primary_text_color="#ffffff",
        button_primary_text_color_dark="#ffffff",
    )

    with gr.Blocks(
        title="LLM Agent Hub | Offline Ready",
        theme=theme,
        css=CUSTOM_CSS,
        fill_height=True,
    ) as app:
        # ---- State ----
        conv_id_state = gr.State("")

        with gr.Row(equal_height=True):
            # ============ SIDEBAR ============
            with gr.Column(scale=1, min_width=280, elem_id="sidebar"):
                gr.Markdown("## 🤖 Agent Hub")

                new_chat_btn = gr.Button(
                    "➕  New Chat", variant="primary", size="lg"
                )

                gr.Markdown("---")

                history_search = gr.Textbox(
                    placeholder="🔍 Search history…",
                    show_label=False,
                    container=False,
                )

                conv_list = gr.Radio(
                    choices=[],
                    label="Recent Conversations",
                    show_label=True,
                    elem_id="conv-list",
                )

                gr.Markdown("---")

                offline_toggle = gr.Checkbox(
                    label="🌐 Offline Mode (air-gapped)",
                    value=False,
                    info="Disable cloud models and add offline system prompt",
                )

                gr.Markdown("---")

                with gr.Accordion("⚡ Available Skills", open=False):
                    gr.Markdown(
                        "- **@local_search** — Find files on disk\n"
                        "- **@web_browser** — Search the web\n"
                        "- **@generate_image** — Generate AI images natively\n\n"
                        "_Type `@skill_name query` in the chat to invoke._"
                    )

                gr.Markdown(
                    '<p style="text-align:center;font-size:0.75em;color:#64748b;margin-top:1em">'
                    "LLM Agent Hub v2.0 · Gradio Edition</p>"
                )

            # ============ MAIN CHAT AREA ============
            with gr.Column(scale=4, min_width=600):
                # ---- Top bar ----
                with gr.Row():
                    model_dropdown = gr.Dropdown(
                        choices=initial_choices,
                        value=initial_choices[0] if initial_choices else None,
                        label="Model",
                        scale=3,
                        filterable=True,
                        interactive=True,
                    )
                    mode_selector = gr.Radio(
                        choices=["Auto", "Fast", "Thinking", "Pro"],
                        value="Auto",
                        label="Mode",
                        scale=2,
                    )

                # ---- Chatbot ----
                chatbot = gr.Chatbot(
                    label="Chat",
                    height="70vh",
                    render_markdown=True,
                    latex_delimiters=[
                        {"left": "$$", "right": "$$", "display": True},
                        {"left": "$", "right": "$", "display": False},
                        {"left": "\\(", "right": "\\)", "display": False},
                        {"left": "\\[", "right": "\\]", "display": True},
                    ],
                    placeholder=(
                        '<div style="text-align:center;padding:3em">'
                        '<h2 style="margin-bottom:0.5em">💬 How can I help you today?</h2>'
                        '<p style="color:#94a3b8">I am your advanced multimodal agent. '
                        "I can analyze images, connect with local and cloud LLMs, "
                        "and use organizational skills.</p></div>"
                    ),
                )

                # ---- Input ----
                msg_input = gr.MultimodalTextbox(
                    placeholder="Ask anything, or type @ for skills…",
                    show_label=False,
                    file_count="multiple",
                    file_types=["image"],
                    submit_btn=True,
                    stop_btn=False,
                )

                gr.Markdown(
                    '<p style="text-align:center;font-size:0.75em;color:#52525b;margin-top:4px">'
                    "AI can make mistakes. Consider verifying important information.</p>"
                )

        # ============ EVENT WIRING ============

        # Send message → stream response
        msg_input.submit(
            fn=chat_handler,
            inputs=[msg_input, chatbot, model_dropdown, mode_selector, offline_toggle, conv_id_state],
            outputs=[chatbot, conv_id_state],
        ).then(
            fn=lambda: gr.update(value=None),
            inputs=None,
            outputs=msg_input,
        ).then(
            fn=load_conversations,
            inputs=history_search,
            outputs=conv_list,
        )

        # New Chat
        new_chat_btn.click(
            fn=new_chat,
            inputs=None,
            outputs=[chatbot, conv_id_state, history_search],
        )

        # Load conversation from sidebar
        conv_list.change(
            fn=load_conversation_messages,
            inputs=conv_list,
            outputs=[chatbot, conv_id_state],
        )

        # Search history
        history_search.change(
            fn=load_conversations,
            inputs=history_search,
            outputs=conv_list,
        )

        # Offline toggle → update model dropdown + backend setting
        offline_toggle.change(
            fn=toggle_offline,
            inputs=offline_toggle,
            outputs=model_dropdown,
        )

        # Refresh conversation list on app load
        app.load(
            fn=load_conversations,
            inputs=history_search,
            outputs=conv_list,
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
