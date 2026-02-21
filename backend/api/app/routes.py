from fastapi import APIRouter
from .schemas import (
    PredictRequest,
    PredictResponse,
    EmbedRequest,
    EmbedResponse,
    ModelsResponse,
)
from . import services

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/info")
async def info():
    return {"name": "hackathon-api", "version": "0.1.0"}


@router.get("/models", response_model=ModelsResponse)
async def models():
    return ModelsResponse(models=services.list_models())


@router.post("/predict", response_model=PredictResponse)
async def predict_endpoint(req: PredictRequest):
    result = services.predict(req.text)
    return PredictResponse(prediction=result)


@router.post("/embed", response_model=EmbedResponse)
async def embed_endpoint(req: EmbedRequest):
    vec = services.embed(req.text)
    return EmbedResponse(embedding=vec)


@router.post("/predict/trigger", response_model=PredictResponse)
async def predict_trigger():
    """Triggerable endpoint for button presses (no request body)."""
    result = services.predict_default()
    return PredictResponse(prediction=result)


@router.post("/embed/trigger", response_model=EmbedResponse)
async def embed_trigger():
    """Triggerable endpoint for button presses (no request body)."""
    vec = services.embed_default()
    return EmbedResponse(embedding=vec)
