# AgentDemo — Enterprise LLM Chat Agent

A full-stack AI chat application with **streaming LLM responses**, **web search tool use**, **AI image generation**, **multimodal input** (image attachments), and **conversation history persistence**. Built with a FastAPI backend and a Next.js 16 + React 19 frontend.

---

## 📂 Project Structure

```
AgentDemo/
├── api_key.txt               # OpenRouter API key (git-ignored, unlocked at runtime)
├── pytest.ini                # Pytest config (asyncio auto mode)
├── .gitignore                # Git exclusions
│
├── backend/                  # ── FastAPI Backend ──────────────────────
│   ├── main.py               # App entry point, CORS, static mount, router wiring
│   ├── database.py           # SQLAlchemy engine + SessionLocal factory
│   ├── settings.py           # Runtime settings singleton (network toggle)
│   │
│   ├── models/
│   │   ├── db_models.py      # SQLAlchemy ORM: ConversationDB table
│   │   └── schemas.py        # Pydantic schemas: Message, ChatRequest, NetworkToggle, UnlockRequest
│   │
│   ├── routers/
│   │   ├── chat.py           # POST /chat (streaming SSE), GET /chat/conversations
│   │   ├── models.py         # GET /models (aggregates internal + OpenRouter models)
│   │   └── settings.py       # GET/PUT /settings/network-mode, API key unlock
│   │
│   └── services/
│       ├── history.py        # CRUD helpers for ConversationDB
│       ├── openrouter.py     # OpenRouter streaming proxy with tool-use (web_search)
│       └── skills.py         # @generate_image skill (Pollinations AI)
│
├── frontend/                 # ── Next.js 16 Frontend ──────────────────
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx    # Root layout with Geist fonts
│   │   │   ├── page.tsx      # Main chat page (client component)
│   │   │   └── globals.css   # Tailwind + custom scrollbar/animation styles
│   │   │
│   │   ├── components/
│   │   │   ├── ApiKeyModal.tsx       # First-run unlock dialog
│   │   │   ├── MarkdownRenderer.tsx  # Rich markdown with KaTeX, GFM, <think> tags, DSML scrubbing
│   │   │   ├── ModelSelector.tsx     # Dropdown for model selection
│   │   │   └── Sidebar.tsx           # Conversation history sidebar
│   │   │
│   │   └── lib/
│   │       └── utils.ts      # Utility: cn() for Tailwind class merging
│   │
│   └── __tests__/            # Jest + React Testing Library
│       ├── ApiKeyModal.test.tsx
│       ├── MarkdownRenderer.test.tsx
│       ├── ModelSelector.test.tsx
│       ├── Sidebar.test.tsx
│       ├── layout.test.tsx
│       └── page.test.tsx
│
├── tests/                    # ── Backend Pytest Suite ──────────────────
│   ├── test_api_key.py       # API key file detection
│   ├── test_backend_health.py # Root endpoint health check
│   ├── test_chat.py          # Chat endpoint + skill interception
│   ├── test_history.py       # Conversation CRUD operations
│   ├── test_models.py        # Model listing endpoint
│   ├── test_openrouter.py    # OpenRouter streaming, tool fallback, context retention
│   ├── test_settings.py      # Network mode toggle
│   ├── test_skills.py        # Image generation: success, retry, error paths
│   └── test_titling_model.py # Background title generation
│
├── docker/                   # ── Containerization ─────────────────────
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── openshift-deployment.yaml
│
├── docs/                     # ── Documentation ────────────────────────
│   ├── deployment_guide.md
│   └── prompts/              # Original planning prompts
│       ├── init_prompt.txt
│       └── init_ui_plan.md.resolved
│
├── locked_secrets/           # ── Encrypted credentials ────────────────
│   ├── api_key.zip           # AES-encrypted OpenRouter key
│   ├── encrypt_key.py        # Script to re-encrypt the key
│   └── secrets.tar.gz        # Legacy archive
│
└── data/                     # ── Runtime artifacts (git-ignored) ──────
    └── gen_*.jpg              # Locally saved generated images
```

---

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│  Browser (Next.js 16 @ localhost:3000)                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Sidebar   │  │ Chat Page    │  │ ModelSelector /       │   │
│  │ (history) │  │ (SSE stream) │  │ ApiKeyModal / Modes  │   │
│  └──────────┘  └──────┬───────┘  └──────────────────────┘   │
│                        │ POST /chat (SSE)                     │
└────────────────────────┼─────────────────────────────────────┘
                         ▸
┌────────────────────────┼─────────────────────────────────────┐
│  FastAPI Backend (@ localhost:8001)                            │
│                        │                                      │
│  ┌─────────────────────▿──────────────────────────────────┐  │
│  │  /chat router                                          │  │
│  │   1. Save to history (SQLite via SQLAlchemy)           │  │
│  │   2. Check for skill trigger (@generate_image)         │  │
│  │   3. If no skill → proxy to OpenRouter (streaming)     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌─ Services ────────────────────────────────────────────┐   │
│  │                                                        │   │
│  │  openrouter.py                                         │   │
│  │  ├── Streaming SSE proxy to OpenRouter API             │   │
│  │  ├── Tool-use: web_search → DDGS text + news scrape    │   │
│  │  ├── Auto-retry without tools if model rejects them    │   │
│  │  └── Background title generation after first message   │   │
│  │                                                        │   │
│  │  skills.py                                             │   │
│  │  ├── @generate_image → Pollinations AI (Flux model)    │   │
│  │  ├── 3-attempt retry with exponential backoff          │   │
│  │  └── Saves generated images to /data/ directory        │   │
│  │                                                        │   │
│  │  history.py                                            │   │
│  │  └── CRUD operations on ConversationDB (SQLite/JSON)   │   │
│  └────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                         │
                         ▸ HTTPS
            ┌────────────────────────┐
            │  OpenRouter.ai API     │
            │  (GPT-4o, DeepSeek,    │
            │   Claude, Gemini, etc) │
            └────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** with pip
- **Node.js 20+** with npm
- An **OpenRouter API key** (or unlock the encrypted one via the UI)

### 1. Backend

```bash
cd backend
pip install fastapi uvicorn sqlalchemy httpx ddgs beautifulsoup4 pyzipper
python -m uvicorn main:app --reload --port 8001
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** in your browser.

### 3. API Key Setup

Either:
- Place your OpenRouter API key in `api_key.txt` at the project root, or
- Use the in-app unlock modal (it decrypts `locked_secrets/api_key.zip` with a password)

---

## 🔌 API Reference

| Method | Endpoint                          | Description                                       |
|--------|-----------------------------------|---------------------------------------------------|
| GET    | `/`                               | Health check                                      |
| GET    | `/models`                         | List available models (internal + OpenRouter)     |
| GET    | `/chat/conversations`             | List all conversations (newest first)             |
| GET    | `/chat/conversations/{id}`        | Load a single conversation with messages          |
| POST   | `/chat`                           | Stream a chat completion (SSE) or trigger a skill |
| GET    | `/settings/network-mode`          | Get online/offline toggle state                   |
| PUT    | `/settings/network-mode`          | Toggle online/offline mode                        |
| GET    | `/settings/api-key-status`        | Check if API key exists and is valid              |
| POST   | `/settings/unlock-key`            | Decrypt API key from zip with password            |
| GET    | `/data/{filename}`                | Serve generated images (static mount)             |

### POST `/chat` — Request Body

```json
{
  "messages": [{"role": "user", "content": "Hello!"}],
  "model": "openai/gpt-4o-mini",
  "mode": "auto",               // auto | fast | thinking | pro
  "conversation_id": null       // null = new conversation
}
```

### Response

Server-Sent Events (SSE) stream. Each event:

```
data: {"choices": [{"delta": {"content": "Hello! How can..."}}]}
```

Response header `x-conversation-id` contains the conversation UUID.

---

## 🧪 Testing

### Backend Tests (pytest)

```bash
# From project root
python -m pytest tests/ -v
```

| Test File              | What It Covers                                                      |
|------------------------|---------------------------------------------------------------------|
| `test_backend_health`  | Root `/` endpoint returns 200                                       |
| `test_api_key`         | API key file detection and validation                               |
| `test_models`          | `/models` returns at least the internal model                       |
| `test_settings`        | Network mode toggle round-trip                                      |
| `test_history`         | Create, read, update, delete conversations                          |
| `test_chat`            | Chat endpoint streaming + skill interception                        |
| `test_openrouter`      | Mode injection, tool-call fallback, context retention               |
| `test_skills`          | Image gen success, retry on 530, permanent failure error message    |
| `test_titling_model`   | Background conversation title generation                            |

### Frontend Tests (Jest)

```bash
cd frontend
npx jest
```

| Test File                        | What It Covers                                    |
|----------------------------------|---------------------------------------------------|
| `ApiKeyModal.test.tsx`           | Modal rendering and dismiss behavior              |
| `MarkdownRenderer.test.tsx`      | Markdown, LaTeX, think-tag, DSML tag scrubbing    |
| `ModelSelector.test.tsx`         | Model dropdown rendering and selection            |
| `Sidebar.test.tsx`               | Conversation list rendering                       |
| `layout.test.tsx`                | Root layout structure                             |
| `page.test.tsx`                  | Main page rendering and UI state                  |

---

## 🧠 Key Features & Design Decisions

### Chat Modes
| Mode       | Behavior |
|------------|----------|
| **Auto**   | Model decides whether to use `<think>` reasoning tags |
| **Fast**   | Low temperature, 512 max tokens, concise responses |
| **Thinking** | Forces `<think>...</think>` step-by-step reasoning before answering |
| **Pro**    | Expert-level, detailed professional responses |

### Web Search (Tool Use)
- When **online**, the backend injects a `web_search` tool schema into the OpenRouter request.
- If the model calls `web_search`, the backend executes a DuckDuckGo search (text + news), scrapes top results, and feeds them back to the model for a grounded answer.
- If a model doesn't support tools (returns a 404/error), the backend retries without tools and injects a system notice explaining the limitation.

### Image Generation (`@generate_image`)
- Completely **bypasses the LLM** — a client-side skill trigger.
- Uses **Pollinations.ai** (free, no auth, Flux model) with 3-attempt retry.
- Saves generated images locally in `data/` and serves them via FastAPI static mount.
- On failure, returns a user-friendly error message (no raw HTTP codes leaked).

### DSML Tag Scrubbing
- Some models (notably DeepSeek) leak internal `< | DSML | function_calls >` XML tags into the response content.
- The `MarkdownRenderer` automatically strips these before rendering.

### Offline Mode
- Toggled via the UI header button.
- Disables tool injection (no web search), and instructs the model that it has no internet access.
- Model list always fetches from OpenRouter regardless (so you can still pick models).

---

## 🐳 Docker

```bash
cd docker
docker-compose up --build
```

See `docs/deployment_guide.md` for OpenShift deployment instructions.

---

## 📜 License

Internal project — not publicly licensed.
