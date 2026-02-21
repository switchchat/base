from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import router
import os

app = FastAPI(title="Hackathon API")

# Configure CORS for frontend access. Set ALLOWED_ORIGINS env var as comma-separated list.
origins_env = os.getenv("ALLOWED_ORIGINS", "*")
if origins_env == "*":
    allow_origins = ["*"]
else:
    allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Hackathon API running"}
