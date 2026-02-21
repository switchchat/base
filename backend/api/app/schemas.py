from pydantic import BaseModel
from typing import List, Optional


class PredictRequest(BaseModel):
    text: str


class PredictResponse(BaseModel):
    prediction: str


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: List[float]


class ModelsResponse(BaseModel):
    models: List[str]


class SessionStartResponse(BaseModel):
    message: str
    session_id: str
    active: bool


class SessionEndResponse(BaseModel):
    message: str
    session_id: Optional[str]
    active: bool
    called_functions: List[str]


class SessionStatusResponse(BaseModel):
    session_id: Optional[str]
    active: bool
    called_functions: List[str]
