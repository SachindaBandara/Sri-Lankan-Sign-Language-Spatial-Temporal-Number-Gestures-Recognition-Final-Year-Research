from flask import Blueprint, jsonify, request
from sqlalchemy import select

from extensions import db
from models import DifficultyAdjustmentHistory, User
from routes.learning_routes import resolve_student_scope
from security import authenticated_user
from services.personalized_learning_service import PersonalizedLearningService

personalized_learning_bp = Blueprint(
    "personalized_learning",
    __name__,
    url_prefix="/api/personalized-learning",
)


def _authorized_student(user):
    student_id = resolve_student_scope(user, request.args.get("student_id"))
    if student_id is None:
        return None, (jsonify({"error": "You are not authorized to view these records"}), 403)
    student = db.session.get(User, student_id)
    if student is None or student.role != "student" or not student.is_active:
        return None, (jsonify({"error": "Student account not found"}), 404)
    return student_id, None


@personalized_learning_bp.get("/students")
def assigned_students():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    if user.role != "teacher":
        return jsonify({"error": "Teacher account required"}), 403
    students = sorted(
        (student for student in user.students if student.is_active and student.role == "student"),
        key=lambda student: student.username.casefold(),
    )
    return jsonify({
        "items": [
            {"id": student.id, "username": student.username, "grade": student.grade}
            for student in students
        ]
    })


@personalized_learning_bp.get("/dashboard")
def dashboard():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    student_id, error = _authorized_student(user)
    if error:
        return error
    data = PersonalizedLearningService.dashboard(student_id)
    db.session.commit()
    return jsonify(data)


@personalized_learning_bp.get("/recommendations")
def recommendations():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    student_id, error = _authorized_student(user)
    if error:
        return error
    data = PersonalizedLearningService.dashboard(student_id)
    db.session.commit()
    return jsonify({"items": data["recommendations"]})


@personalized_learning_bp.get("/learning-path")
def learning_path():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    student_id, error = _authorized_student(user)
    if error:
        return error
    data = PersonalizedLearningService.dashboard(student_id)
    db.session.commit()
    return jsonify({"learning_path": data["learning_path"]})


@personalized_learning_bp.get("/difficulty-history")
def difficulty_history():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    student_id, error = _authorized_student(user)
    if error:
        return error
    records = db.session.scalars(
        select(DifficultyAdjustmentHistory)
        .where(DifficultyAdjustmentHistory.student_id == student_id)
        .order_by(DifficultyAdjustmentHistory.created_at.desc(), DifficultyAdjustmentHistory.id.desc())
        .limit(50)
    ).all()
    return jsonify({
        "items": [
            {
                "operation_type": item.operation_type,
                "previous_difficulty": item.previous_difficulty,
                "new_difficulty": item.new_difficulty,
                "recent_accuracy": item.recent_accuracy,
                "historical_accuracy": item.historical_accuracy,
                "reason": item.reason,
                "created_at": item.created_at.isoformat() + "Z",
            }
            for item in records
        ]
    })
