from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import chat, models, settings

app = FastAPI(title="Offline LLM Chat Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(models.router)
app.include_router(settings.router)

@app.get("/")
def read_root():
    return {"status": "Backend is running"}
