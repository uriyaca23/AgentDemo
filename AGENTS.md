# AgentDemo — AI Agent Context

> This file is designed to be read by AI coding assistants to quickly understand
> the project structure, conventions, and key files without re-exploring the codebase.

## Stack

| Layer     | Technology                                          | Port  |
|-----------|-----------------------------------------------------|-------|
| Frontend  | Next.js 16, React 19, Tailwind CSS 4, TypeScript   | 3000  |
| Backend   | FastAPI (Python 3.11+), SQLAlchemy, httpx           | 8001  |
| Database  | SQLite (`chat_history.db` at project root)          | —     |
| LLM API   | OpenRouter.ai (streaming SSE proxy)                 | —     |
| Image Gen | Pollinations.ai (free, Flux model, no auth)         | —     |
| Web Search| DuckDuckGo (ddgs library, text + news + scrape)     | —     |

## Running the App

```bash
# Terminal 1: Backend
cd backend && python -m uvicorn main:app --reload --port 8001

# Terminal 2: Frontend
cd frontend && npm run dev
```

## Running Tests

```bash
# Backend (from project root)
python -m pytest tests/ -v

# Frontend (from frontend/)
cd frontend && npx jest
```

## Key Files to Understand

### Backend Entry Point
- `backend/main.py` — FastAPI app init, CORS, static mount, router registration.

### Routers (API Endpoints)
- `backend/routers/chat.py` — `POST /chat` (streaming SSE), conversation CRUD.
  - Intercepts `@generate_image` via `skills.process_skills()` before reaching OpenRouter.
  - Background-generates conversation titles via `generate_title_background()`.
- `backend/routers/models.py` — `GET /models` (fetches internal + OpenRouter model list).
- `backend/routers/settings.py` — Network mode toggle, API key status/unlock.

### Services (Business Logic)
- `backend/services/openrouter.py` — **Most complex file**.
  - Streams chat completions from OpenRouter.
  - Injects `web_search` tool schema when online.
  - Buffers `delta.tool_calls` chunks, executes DDGS search, feeds results back.
  - Auto-retries without tools if a model rejects them (e.g., 404 on tool endpoint).
  - Injects system notice explaining tool limitation on fallback.
- `backend/services/skills.py` — `@generate_image` handler.
  - Uses Pollinations.ai with 3-attempt retry (2s delay, exponential backoff).
  - On permanent failure, returns user-friendly error (no raw HTTP codes).
- `backend/services/history.py` — SQLAlchemy CRUD for `ConversationDB`.

### Data Models
- `backend/models/db_models.py` — `ConversationDB` table: `id`, `title`, `created_at`, `messages` (JSON column).
- `backend/models/schemas.py` — Pydantic: `Message`, `ChatRequest`, `NetworkToggle`, `UnlockRequest`.

### Frontend Components
- `frontend/src/app/page.tsx` — Main chat page. Client component. Handles SSE streaming, message state, attachments, skill autocomplete popup.
- `frontend/src/components/MarkdownRenderer.tsx` — Renders assistant messages.
  - Processes `<think>...</think>` tags into collapsible `<details>` blocks.
  - Scrubs leaked `< | DSML | >` tags from DeepSeek models.
  - Converts `\[...\]` and `\(...\)` to `$$...$$` and `$...$` for KaTeX.
- `frontend/src/components/Sidebar.tsx` — Polls `/chat/conversations` every 5 seconds.
- `frontend/src/components/ModelSelector.tsx` — Searchable model dropdown from `/models`.
- `frontend/src/components/ApiKeyModal.tsx` — First-run modal to unlock encrypted API key.

### Configuration
- `backend/settings.py` — Runtime singleton with `_network_enabled` flag.
- `backend/database.py` — SQLAlchemy engine pointing to `../chat_history.db`.
- `api_key.txt` — OpenRouter API key (git-ignored). Read by `get_api_key()` in multiple places.

## Conventions

1. **SSE Streaming**: All `/chat` responses are `text/event-stream`. Each chunk: `data: {"choices":[{"delta":{"content":"..."}}]}\n\n`.
2. **Conversation IDs**: Returned in `x-conversation-id` response header. Frontend sends `conversation_id` in subsequent requests.
3. **Skill Triggers**: Prefixed with `@`. Currently only `@generate_image <prompt>` is implemented. Detected in `skills.process_skills()` before OpenRouter is called.
4. **Modes**: `auto`, `fast`, `thinking`, `pro` — injected as system instructions in `openrouter.py`.
5. **Offline Mode**: Disables tool injection; adds system instruction about no internet access.
6. **Error Handling**: Backend wraps errors in `data: {"error": "..."}` SSE chunks. Frontend displays them as `> ⚠️ Error: ...` blockquotes.

## Common Pitfalls

- **DeepSeek DSML tags**: DeepSeek models sometimes stream internal XML tool-calling syntax (`< | DSML | function_calls >`) into `delta.content`. The `MarkdownRenderer` scrubs these client-side.
- **Tool fallback**: If OpenRouter returns error containing "tool" in the response body, the backend strips tools and retries with a system notice about the limitation.
- **Pollinations outages**: The image generation service returns HTTP 530 intermittently. The 3-attempt retry handles this. Test `test_pollinations_probe` auto-skips when down.
- **SQLite JSON mutation**: Must call `flag_modified(db_conv, "messages")` after mutating the JSON column for SQLAlchemy to detect the change.
- **Hydration warnings**: `suppressHydrationWarning` is applied to `<html>` and `<body>` in `layout.tsx` to suppress browser extension interference.

## Test Coverage Summary

| Area              | Backend Tests | Frontend Tests |
|-------------------|:---:|:---:|
| Health / Routing  | ✅ | ✅ |
| Chat Streaming    | ✅ | ✅ |
| Conversation CRUD | ✅ | — |
| Model Listing     | ✅ | ✅ |
| Settings Toggle   | ✅ | — |
| Skills / Image Gen| ✅ | — |
| OpenRouter Proxy  | ✅ | — |
| Tool Fallback     | ✅ | — |
| Markdown Rendering| — | ✅ |
| API Key Modal     | — | ✅ |
| Sidebar           | — | ✅ |
