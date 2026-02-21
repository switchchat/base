from pydantic import BaseModel
from typing import List


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
