from fastapi import APIRouter, HTTPException
from .schemas import (
    PredictRequest,
    PredictResponse,
    EmbedRequest,
    EmbedResponse,
    ModelsResponse,
    SessionStartResponse,
    SessionEndResponse,
    SessionStatusResponse,
)
from . import services

router = APIRouter()


def _require_active(function_name: str) -> None:
    if not services.is_session_active():
        raise HTTPException(
            status_code=409,
            detail="Session is inactive. Call /session/start first.",
        )
    services.record_function_call(function_name)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/session/start", response_model=SessionStartResponse)
async def session_start():
    return services.start_session()


@router.post("/session/end", response_model=SessionEndResponse)
async def session_end():
    return services.end_session()


@router.get("/session/status", response_model=SessionStatusResponse)
async def session_status():
    return services.get_session_status()


@router.get("/info")
async def info():
    _require_active("/info")
    return {"name": "hackathon-api", "version": "0.1.0"}


@router.get("/models", response_model=ModelsResponse)
async def models():
    _require_active("/models")
    return ModelsResponse(models=services.list_models())


@router.post("/predict", response_model=PredictResponse)
async def predict_endpoint(req: PredictRequest):
    _require_active("/predict")
    result = services.predict(req.text)
    return PredictResponse(prediction=result)


@router.post("/embed", response_model=EmbedResponse)
async def embed_endpoint(req: EmbedRequest):
    _require_active("/embed")
    vec = services.embed(req.text)
    return EmbedResponse(embedding=vec)


@router.post("/predict/trigger", response_model=PredictResponse)
async def predict_trigger():
    """Triggerable endpoint for button presses (no request body)."""
    _require_active("/predict/trigger")
    result = services.predict_default()
    return PredictResponse(prediction=result)


@router.post("/embed/trigger", response_model=EmbedResponse)
async def embed_trigger():
    """Triggerable endpoint for button presses (no request body)."""
    _require_active("/embed/trigger")
    vec = services.embed_default()
    return EmbedResponse(embedding=vec)
