from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from flask import Blueprint, current_app, jsonify
from itsdangerous import URLSafeTimedSerializer

from security import require_student
from utils.request_payload import json_object

if TYPE_CHECKING:
    from utils.inference_engine import InferenceManager


prediction_bp = Blueprint("prediction", __name__)
project_root = Path(__file__).resolve().parents[2]
models_dir = Path(os.environ.get("MODEL_DIR", project_root / "models")).expanduser()
if not models_dir.is_absolute():
    models_dir = project_root / models_dir
inference_manager: InferenceManager | None = None
inference_manager_lock = threading.Lock()


def get_inference_manager() -> InferenceManager:
    global inference_manager
    if inference_manager is None:
        with inference_manager_lock:
            if inference_manager is None:
                from utils.inference_engine import InferenceManager

                inference_manager = InferenceManager(models_dir=models_dir)
    return inference_manager


@prediction_bp.post("/predict-number")
def predict_number():
    """
    Expect a JSON body:
        {
            "video": "<base64-encoded video, ~3 seconds>"
        }

    The endpoint decodes the video, samples frames at a fixed rate, runs all
    five models over the full frame set, and returns the number predicted by
    the model that achieved the highest confidence score.

    Response (200):
        { "predicted_number": <int>, "model_key": <str>, "confidence": <float> }

    Error responses:
        400  – missing or undecodable video payload
        422  – no hand landmarks detected in any frame
    """
    user, error = require_student()
    if error:
        return error

    payload = json_object()
    video_base64 = payload.get("video")

    if not video_base64:
        return jsonify({"error": "Missing video payload"}), 400

    result = get_inference_manager().predict_video(video_base64)

    if result is None:
        return jsonify({"error": "No hand landmarks detected in the video"}), 422

    confidence = round(result.confidence, 4)
    token_id = uuid4().hex
    recognition_token = URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"], salt="slsl-recognition"
    ).dumps({
        "user_id": user.id,
        "predicted_number": result.predicted_number,
        "confidence": confidence,
        "model_key": result.model_key,
        "token_id": token_id,
    })
    return jsonify({
        "predicted_number": result.predicted_number,
        "model_key": result.model_key,
        "confidence": confidence,
        "recognition_token": recognition_token,
    })