from flask import Blueprint, jsonify

from security import student_required

activity_bp = Blueprint("activity", __name__)


def _retired_response():
    return jsonify({
        "error": "This legacy endpoint is retired because it does not persist learning data.",
        "replacement": {
            "start_activity": "POST /api/student-activities/start",
            "generate_question": "POST /api/student-activities/<activity_id>/questions",
            "submit_answer": "POST /api/student-question-attempts/<question_id>",
        },
    }), 410


@activity_bp.post("/activity/generate-question")
@student_required
def generate_activity_question():
    return _retired_response()


@activity_bp.post("/activity/validate-answer")
@student_required
def validate_activity_answer():
    return _retired_response()