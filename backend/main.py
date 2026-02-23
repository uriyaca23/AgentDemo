import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import Base, engine

# Initialize Models
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent V2 Backend")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-conversation-id"]
)

# Setup Image Generation Directory Mounting
data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data"))
os.makedirs(data_dir, exist_ok=True)
app.mount("/data", StaticFiles(directory=data_dir), name="data")

# Include Routers
from routers import chat, models, settings

app.include_router(chat.router)
app.include_router(models.router)
app.include_router(settings.router)

@app.get("/")
def read_root():
    return {"status": "Backend V2 is running", "mounted": "/data"}
