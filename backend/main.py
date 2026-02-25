import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 1. Setup App
app = FastAPI(title="Agent V2 Backend")

# 2. Setup CORS — allow all in development/docker mode for ease of use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-conversation-id"]
)

# 3. Import Models BEFORE create_all to ensure they are registered in Base.metadata
from database import Base, engine
from models import db_models  # CRITICAL: Ensures models are registered
Base.metadata.create_all(bind=engine)

# 4. Setup Image Generation Directory Mounting
data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data"))
os.makedirs(data_dir, exist_ok=True)
app.mount("/data", StaticFiles(directory=data_dir), name="data")

# 5. Include Routers
from routers import chat, models, settings
app.include_router(chat.router)
app.include_router(models.router)
app.include_router(settings.router)

@app.get("/")
def read_root():
    return {"status": "Backend V2 is running", "mounted": "/data"}
