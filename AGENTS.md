# AgentDemo — AI Agent Context

> This file is designed to be read by AI coding assistants to quickly understand
> the project structure, conventions, and key files without re-exploring the codebase.

## Stack

| Layer     | Technology                                          | Port  |
|-----------|-----------------------------------------------------|-------|
| Frontend  | Next.js 16, React 19, Tailwind CSS 4, TypeScript   | 3000  |
| Backend   | FastAPI (Python 3.11+), SQLAlchemy, httpx           | 8001  |
| Database  | SQLite (`chat_history.db` at project root)          | —     |
| LLM API   | OpenRouter.ai OR Internal Emulator (configurable)   | —     |
| Emulator  | vLLM + FastAPI wrapper (Docker, OpenRouter-compat)   | 8000  |
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
- `backend/settings.py` — Runtime singleton with `_network_enabled` flag and `LLM_BASE_URL` (configurable via env var, defaults to OpenRouter).
  - `is_internal_llm()` — returns True when pointing at the internal emulator.
- `backend/database.py` — SQLAlchemy engine pointing to `../chat_history.db`.
- `api_key.txt` — OpenRouter API key (git-ignored). Skipped when using internal emulator.

### Emulator (Docker)
- `docker/emulator/emulator_app.py` — FastAPI wrapper translating vLLM's API to OpenRouter format.
- `docker/emulator/start.sh` — Entrypoint: starts vLLM on port 5000, emulator on port 8000.
- `docker/Dockerfile` — Production image (vLLM + emulator).
- `docker/Dockerfile.test` — Test image (downloads small model for local GPU testing).
- `docker/deploy-openshift.ps1` — Interactive deployment script.

## Conventions

1. **SSE Streaming**: All `/chat` responses are `text/event-stream`. Each chunk: `data: {"choices":[{"delta":{"content":"..."}}]}\n\n`.
2. **Conversation IDs**: Returned in `x-conversation-id` response header. Frontend sends `conversation_id` in subsequent requests.
3. **Skill Triggers**: Prefixed with `@`. Currently only `@generate_image <prompt>` is implemented. Detected in `skills.process_skills()` before the LLM is called.
4. **Modes**: `auto`, `fast`, `thinking`, `pro` — injected as system instructions in `openrouter.py`.
5. **Offline Mode**: Disables tool injection; adds system instruction about no internet access.
6. **Error Handling**: Backend wraps errors in `data: {"error": "..."}` SSE chunks. Frontend displays them as `> ⚠️ Error: ...` blockquotes.
7. **Configurable LLM**: Set `LLM_BASE_URL` env var to switch between OpenRouter and internal emulator. Default: `https://openrouter.ai/api/v1`.
8. **Unified Routing**: ALL models (including internal) route through `generate_chat_openrouter()`. No special-case fallbacks.

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

## ⚠️ MANDATORY TESTING RULES ⚠️

**These rules are NON-NEGOTIABLE. Failure to follow them is unacceptable.**

### 1. All Tests Must Pass Before Completing Any Task
- After finishing any code change, run `python -m pytest tests/ -v` from the project root.
- **100% of tests MUST pass.** If any test fails, you MUST fix the failure before continuing to other tasks. You CANNOT skip failing tests or proceed to other work.

### 2. Every New Feature or Bugfix MUST Add Regression Tests
- Every change that adds, modifies, or fixes a feature MUST include corresponding test(s) in `tests/test_unified_integration.py` (or the appropriate existing test file).
- These tests prevent the fixed/added behavior from ever regressing.
- **Past tests may NEVER be deleted.** They may only be modified if the project is being fundamentally restructured.

### 3. Integration Tests Use Random Model Selection
- The unified integration test (`tests/test_unified_integration.py`) randomly selects **5 different OpenRouter models** per run.
- This ensures you never create a fix for one model that breaks other models.
- The emulator must also be tested alongside OpenRouter — never skip emulator tests.

### 4. All Testing Is Programmatic — Never Browser-Based
- All functionality is validated via code (HTTP requests, SSE parsing, content assertions).
- Never look at the browser to verify results — dissect every response programmatically.

### 5. Comprehensive Validation
- Check that response content is non-empty (no empty chat bubbles).
- Check that titles are generated, correct, and displayed.
- Check that thinking mode produces `<think>` tags or reasoning content.
- Check that skills (e.g., `@generate_image`) return valid markdown or friendly errors.
- Check that web search returns results and the search indicator appears.
- Check that markdown rendering pipeline preserves code blocks, links, lists, bold/italic, LaTeX, etc.
- If a model doesn't support a feature (e.g., tool use), verify the graceful fallback works — no empty bubbles or crashes.

### 6. Emulator Docker Must Be Running
- The emulator Docker container must be up before running integration tests.
- If it's down, start it before proceeding. Never skip emulator tests.

### 7. API Key Is Always Available
- The API key is always available via `locked_secrets/api_key.zip` (password: see `tests/test_openrouter.py`).
- Never skip OpenRouter tests claiming the key is unavailable.
