import random
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import (
    ActivityAttempt,
    LearningQuestion,
    LearningSession,
    NumberIdentificationQuestion,
    QuestionAttempt,
    RecognitionLog,
    StudentLearningProgress,
    User,
    utcnow,
)
from services.student_learning_data_service import StudentLearningDataService
from services.personalized_learning_service import PersonalizedLearningService
from security import authenticated_user, require_student
from utils.activity_engine import DIFFICULTY_LEVELS, validate_answer
from utils.request_payload import json_object

learning_bp = Blueprint("learning", __name__, url_prefix="/api")
OPERATIONS = {"number_identification", "addition", "subtraction", "multiplication", "division"}
RECOGNITION_THRESHOLD = 0.60
MAX_PAGE_SIZE = 100


def parse_uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def activity_for_student(activity_id: int, student_id: int):
    return db.session.scalar(
        select(ActivityAttempt).where(
            ActivityAttempt.id == activity_id,
            ActivityAttempt.student_id == student_id,
        )
    )


def resolve_student_scope(user: User, requested_student_id):
    if user.role == "student":
        return user.id if requested_student_id in (None, user.id, str(user.id)) else None
    if user.role == "teacher" and requested_student_id is not None:
        try:
            student_id = int(requested_student_id)
        except (TypeError, ValueError):
            return None
        return student_id if any(student.id == student_id for student in user.students) else None
    return None


def page_args():
    try:
        page = max(1, int(request.args.get("page", 1)))
        page_size = min(MAX_PAGE_SIZE, max(1, int(request.args.get("page_size", 25))))
    except ValueError:
        return None
    return page, page_size


@learning_bp.post("/learning-sessions/start")
def start_learning_session():
    user, error = require_student()
    if error:
        return error
    identifier = parse_uuid(json_object().get("session_identifier"))
    if identifier is None:
        return jsonify({"error": "A valid session_identifier UUID is required"}), 400
    existing = db.session.scalar(select(LearningSession).where(LearningSession.identifier == identifier))
    if existing:
        if existing.student_id != user.id:
            return jsonify({"error": "Session identifier is already in use"}), 409
        return jsonify({"session": session_data(existing)})

    try:
        learning_session = StudentLearningDataService.start_session(user.id, identifier)
    except IntegrityError:
        db.session.rollback()
        learning_session = db.session.scalar(
            select(LearningSession).where(LearningSession.identifier == identifier)
        )
        if learning_session is None or learning_session.student_id != user.id:
            return jsonify({"error": "Session identifier is already in use"}), 409
    return jsonify({"session": session_data(learning_session)}), 201


def session_data(item):
    activity_count = db.session.scalar(
        select(func.count()).select_from(ActivityAttempt).where(ActivityAttempt.session_id == item.id)
    )
    question_count = db.session.scalar(
        select(func.count())
        .select_from(LearningQuestion)
        .join(ActivityAttempt)
        .where(ActivityAttempt.session_id == item.id)
    )
    number_question_count = db.session.scalar(
        select(func.count())
        .select_from(NumberIdentificationQuestion)
        .join(ActivityAttempt)
        .where(ActivityAttempt.session_id == item.id)
    )
    math_total_attempts = db.session.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(
            QuestionAttempt.session_id == item.id,
            QuestionAttempt.is_correct.is_not(None),
        )
    )
    math_completed_questions = db.session.scalar(
        select(func.count(func.distinct(QuestionAttempt.question_id)))
        .where(
            QuestionAttempt.session_id == item.id,
            QuestionAttempt.is_correct.is_(True),
        )
    )
    math_correct_answers = db.session.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(
            QuestionAttempt.session_id == item.id,
            QuestionAttempt.is_correct.is_(True),
        )
    )
    math_incorrect_answers = db.session.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(
            QuestionAttempt.session_id == item.id,
            QuestionAttempt.is_correct.is_(False),
        )
    )
    math_skipped_questions = db.session.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(
            QuestionAttempt.session_id == item.id,
            QuestionAttempt.skipped.is_(True),
        )
    )
    number_total_attempts = db.session.scalar(
        select(func.count())
        .select_from(RecognitionLog)
        .join(ActivityAttempt)
        .where(
            ActivityAttempt.session_id == item.id,
            RecognitionLog.is_correct.is_not(None),
        )
    )
    number_completed_questions = db.session.scalar(
        select(func.count())
        .select_from(NumberIdentificationQuestion)
        .join(ActivityAttempt)
        .where(
            ActivityAttempt.session_id == item.id,
            NumberIdentificationQuestion.status == "completed",
        )
    )
    number_skipped_questions = db.session.scalar(
        select(func.count())
        .select_from(NumberIdentificationQuestion)
        .join(ActivityAttempt)
        .where(
            ActivityAttempt.session_id == item.id,
            NumberIdentificationQuestion.status == "skipped",
        )
    )
    number_correct_answers = db.session.scalar(
        select(func.count())
        .select_from(RecognitionLog)
        .join(ActivityAttempt)
        .where(
            ActivityAttempt.session_id == item.id,
            RecognitionLog.is_correct.is_(True),
        )
    )
    number_incorrect_answers = db.session.scalar(
        select(func.count())
        .select_from(RecognitionLog)
        .join(ActivityAttempt)
        .where(
            ActivityAttempt.session_id == item.id,
            RecognitionLog.is_correct.is_(False),
        )
    )
    total_attempts = (math_total_attempts or 0) + (number_total_attempts or 0)
    completed_questions = (math_completed_questions or 0) + (number_completed_questions or 0)
    correct_answers = (math_correct_answers or 0) + (number_correct_answers or 0)
    incorrect_answers = (math_incorrect_answers or 0) + (number_incorrect_answers or 0)
    skipped_questions = (math_skipped_questions or 0) + (number_skipped_questions or 0)
    average_response_time = db.session.scalar(
        select(func.avg(QuestionAttempt.response_time_ms)).where(
            QuestionAttempt.session_id == item.id,
            QuestionAttempt.is_correct.is_not(None),
        )
    )
    accuracy = round(correct_answers * 100 / total_attempts, 2) if total_attempts else 0
    return {
        "id": item.id,
        "identifier": item.identifier,
        "started_at": item.started_at.isoformat() + "Z",
        "ended_at": item.ended_at.isoformat() + "Z" if item.ended_at else None,
        "status": item.status,
        "total_duration_ms": item.total_duration_ms,
        "total_activities": activity_count or 0,
        "total_questions": (question_count or 0) + (number_question_count or 0),
        "completed_questions": completed_questions,
        "total_attempts": total_attempts,
        "correct_answers": correct_answers,
        "incorrect_answers": incorrect_answers,
        "skipped_questions": skipped_questions,
        "accuracy_percent": accuracy,
        "average_response_time_ms": round(float(average_response_time)) if average_response_time is not None else None,
    }


@learning_bp.post("/learning-sessions/<identifier>/end")
def end_learning_session(identifier):
    user, error = require_student()
    if error:
        return error
    normalized = parse_uuid(identifier)
    learning_session = db.session.scalar(
        select(LearningSession).where(
            LearningSession.identifier == normalized,
            LearningSession.student_id == user.id,
        )
    ) if normalized else None
    if learning_session is None:
        return jsonify({"error": "Learning session not found"}), 404
    StudentLearningDataService.end_session(learning_session)
    return jsonify({"session": session_data(learning_session)})


@learning_bp.post("/learning-sessions/<identifier>/abandon")
def abandon_learning_session(identifier):
    user, error = require_student()
    if error:
        return error
    normalized = parse_uuid(identifier)
    learning_session = db.session.scalar(
        select(LearningSession).where(
            LearningSession.identifier == normalized,
            LearningSession.student_id == user.id,
        )
    ) if normalized else None
    if learning_session is None:
        return jsonify({"error": "Learning session not found"}), 404
    StudentLearningDataService.end_session(learning_session, status="abandoned")
    return jsonify({"session": session_data(learning_session)})


@learning_bp.get("/learning-sessions")
def list_learning_sessions():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    page_data = page_args()
    if page_data is None:
        return jsonify({"error": "page and page_size must be integers"}), 400
    page, page_size = page_data
    student_id = resolve_student_scope(user, request.args.get("student_id"))
    if student_id is None:
        return jsonify({"error": "You are not authorized to view these records"}), 403
    query = select(LearningSession).where(LearningSession.student_id == student_id).order_by(LearningSession.started_at.desc())
    items = db.session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    total = db.session.scalar(select(func.count()).select_from(LearningSession).where(LearningSession.student_id == student_id))
    return jsonify({"items": [session_data(item) for item in items], "page": page, "page_size": page_size, "total": total})


@learning_bp.get("/learning-sessions/<identifier>")
def get_learning_session(identifier):
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    student_id = resolve_student_scope(user, request.args.get("student_id"))
    if student_id is None:
        return jsonify({"error": "You are not authorized to view these records"}), 403
    normalized = parse_uuid(identifier)
    learning_session = db.session.scalar(
        select(LearningSession).where(
            LearningSession.identifier == normalized,
            LearningSession.student_id == student_id,
        )
    ) if normalized else None
    if learning_session is None:
        return jsonify({"error": "Learning session not found"}), 404
    return jsonify({"session": session_data(learning_session)})


@learning_bp.post("/student-activities/start")
def start_activity():
    user, error = require_student()
    if error:
        return error
    payload = json_object()
    operation = payload.get("operation_type")
    difficulty_level = payload.get("difficulty_level", "standard")
    adaptive_difficulty = difficulty_level == "adaptive"
    request_key = parse_uuid(payload.get("request_key"))
    session_identifier = parse_uuid(payload.get("session_identifier"))
    if (
        not isinstance(operation, str)
        or operation not in OPERATIONS
        or request_key is None
        or session_identifier is None
    ):
        return jsonify({"error": "Valid operation_type, request_key, and session_identifier are required"}), 400
    if not isinstance(difficulty_level, str) or (
        difficulty_level not in DIFFICULTY_LEVELS and not adaptive_difficulty
    ):
        return jsonify({
            "error": "difficulty_level must be adaptive, easy, standard, or hard"
        }), 400
    if operation == "number_identification" and difficulty_level not in {"standard", "adaptive"}:
        return jsonify({"error": "difficulty_level is only configurable for math activities"}), 400
    learning_session = db.session.scalar(
        select(LearningSession).where(
            LearningSession.identifier == session_identifier,
            LearningSession.student_id == user.id,
            LearningSession.status == "in_progress",
        )
    )
    if learning_session is None:
        return jsonify({"error": "Active learning session not found"}), 404
    existing = db.session.scalar(select(ActivityAttempt).where(ActivityAttempt.request_key == request_key))
    if existing:
        if (
            existing.student_id != user.id
            or existing.session_id != learning_session.id
            or existing.operation_type != operation
            or (not adaptive_difficulty and existing.difficulty_level != difficulty_level)
        ):
            return jsonify({"error": "Request key is already in use"}), 409
        return jsonify({"activity": activity_data(existing)})
    if adaptive_difficulty:
        if operation != "number_identification":
            PersonalizedLearningService.refresh_student(user.id, create_path=False)
        difficulty_level = "standard" if operation == "number_identification" else (
            db.session.scalar(
                select(StudentLearningProgress.current_difficulty).where(
                    StudentLearningProgress.student_id == user.id,
                    StudentLearningProgress.operation_type == operation,
                )
            ) or "easy"
        )
    try:
        activity = StudentLearningDataService.start_activity(
            user.id, learning_session.id, operation, request_key, difficulty_level
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 409
    except IntegrityError:
        db.session.rollback()
        existing = db.session.scalar(
            select(ActivityAttempt).where(ActivityAttempt.request_key == request_key)
        )
        if (
            existing is None
            or existing.student_id != user.id
            or existing.session_id != learning_session.id
            or existing.operation_type != operation
            or existing.difficulty_level != difficulty_level
        ):
            return jsonify({"error": "Request key is already in use"}), 409
        activity = existing
    PersonalizedLearningService.activity_started(activity)
    return jsonify({"activity": activity_data(activity)}), 201


def activity_data(item):
    return {
        "id": item.id,
        "operation_type": item.operation_type,
        "difficulty_level": item.difficulty_level,
        "status": item.status,
        "started_at": item.started_at.isoformat() + "Z",
        "completed_at": item.completed_at.isoformat() + "Z" if item.completed_at else None,
        "total_questions": item.total_questions,
        "total_attempts": item.total_attempts,
        "completed_questions": item.completed_questions,
        "skipped_questions": item.skipped_questions,
        "correct_answers": item.correct_answers,
        "incorrect_answers": item.incorrect_answers,
    }


@learning_bp.post("/student-activities/<int:activity_id>/complete")
def complete_activity(activity_id):
    user, error = require_student()
    if error:
        return error
    activity = activity_for_student(activity_id, user.id)
    if activity is None:
        return jsonify({"error": "Activity not found"}), 404
    completed = StudentLearningDataService.complete_activity(activity)
    return jsonify({"activity": activity_data(completed)})


@learning_bp.post("/student-activities/<int:activity_id>/questions")
def create_learning_question(activity_id):
    user, error = require_student()
    if error:
        return error
    activity = activity_for_student(activity_id, user.id)
    if activity is None:
        return jsonify({"error": "Activity not found"}), 404
    if activity.status != "in_progress" or activity.operation_type == "number_identification":
        return jsonify({"error": "This activity cannot receive arithmetic questions"}), 409
    try:
        question = StudentLearningDataService.get_or_create_question(activity)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 409
    return jsonify(question_data(question))


@learning_bp.post("/student-activities/<int:activity_id>/number-questions")
def create_number_identification_question(activity_id):
    user, error = require_student()
    if error:
        return error
    activity = db.session.scalar(
        select(ActivityAttempt)
        .where(
            ActivityAttempt.id == activity_id,
            ActivityAttempt.student_id == user.id,
        )
        .with_for_update()
    )
    if activity is None:
        return jsonify({"error": "Activity not found"}), 404
    if activity.operation_type != "number_identification":
        return jsonify({"error": "This activity does not use number-identification questions"}), 409
    if activity.status != "in_progress":
        return jsonify({"error": "Activity is no longer active"}), 409

    active_question = db.session.scalar(
        select(NumberIdentificationQuestion)
        .where(
            NumberIdentificationQuestion.activity_attempt_id == activity.id,
            NumberIdentificationQuestion.status == "in_progress",
        )
        .order_by(NumberIdentificationQuestion.sequence_number.desc())
        .limit(1)
    )
    if active_question is not None:
        return jsonify(number_question_data(active_question))

    last_sequence = db.session.scalar(
        select(func.max(NumberIdentificationQuestion.sequence_number)).where(
            NumberIdentificationQuestion.activity_attempt_id == activity.id
        )
    ) or 0
    target_min, target_max = PersonalizedLearningService.number_identification_target_range(
        activity.student_id
    )
    question = NumberIdentificationQuestion(
        activity_attempt_id=activity.id,
        sequence_number=last_sequence + 1,
        expected_value=random.randint(target_min, target_max),
    )
    activity.total_questions += 1
    db.session.add(question)
    db.session.commit()
    return jsonify(number_question_data(question)), 201


def number_question_data(question):
    return {
        "id": question.id,
        "activity_attempt_id": question.activity_attempt_id,
        "sequence_number": question.sequence_number,
        "target_value": question.expected_value,
        "status": question.status,
    }


def question_data(question):
    return {
        "id": question.id,
        "activity_attempt_id": question.activity_attempt_id,
        "operation": question.activity.operation_type,
        "left": question.left_operand,
        "right": question.right_operand,
        "operator": question.operator_symbol,
        "display": question.question_content,
        "difficulty_level": question.activity.difficulty_level,
    }


def completed_question_attempt(question_id):
    return db.session.scalar(
        select(QuestionAttempt)
        .where(
            QuestionAttempt.question_id == question_id,
            (
                QuestionAttempt.is_correct.is_(True)
                | QuestionAttempt.skipped.is_(True)
            ),
        )
        .order_by(QuestionAttempt.attempted_at.desc())
        .limit(1)
    )


@learning_bp.post("/learning-questions/<question_id>/displayed")
def mark_question_displayed(question_id):
    user, error = require_student()
    if error:
        return error
    normalized = parse_uuid(question_id)
    question = db.session.scalar(
        select(LearningQuestion).where(LearningQuestion.id == normalized).with_for_update()
    ) if normalized else None
    if question is None or question.activity.student_id != user.id:
        return jsonify({"error": "Question not found"}), 404
    if question.activity.status != "in_progress":
        return jsonify({"error": "Activity is no longer active"}), 409
    if completed_question_attempt(question.id) is not None:
        return jsonify({"error": "Question has already been submitted"}), 409
    if question.displayed_at is None:
        question.displayed_at = utcnow()
        db.session.commit()
    return jsonify({"displayed_at": question.displayed_at.isoformat() + "Z"})


@learning_bp.post("/student-question-attempts/<question_id>")
def submit_question_attempt(question_id):
    user, error = require_student()
    if error:
        return error
    normalized = parse_uuid(question_id)
    question = db.session.get(LearningQuestion, normalized) if normalized else None
    if question is None or question.activity.student_id != user.id:
        return jsonify({"error": "Question not found"}), 404
    payload = json_object()
    idempotency_key = parse_uuid(payload.get("idempotency_key"))
    if idempotency_key is None:
        return jsonify({"error": "A valid idempotency_key UUID is required"}), 400
    existing_attempt = db.session.scalar(
        select(QuestionAttempt).where(QuestionAttempt.idempotency_key == idempotency_key)
    )
    if existing_attempt is not None:
        if existing_attempt.student_id != user.id or existing_attempt.question_id != question.id:
            return jsonify({"error": "Idempotency key is already in use"}), 409
        return jsonify({"attempt": question_attempt_data(existing_attempt), "duplicate": True})

    activity = db.session.scalar(
        select(ActivityAttempt)
        .where(ActivityAttempt.id == question.activity_attempt_id)
        .with_for_update()
    )
    db.session.refresh(question)
    if activity is None or activity.status != "in_progress" or question.displayed_at is None:
        return jsonify({"error": "Question must be displayed in an active activity before submission"}), 409
    if completed_question_attempt(question.id) is not None:
        return jsonify({"error": "Question has already been completed or skipped"}), 409
    response_time = payload.get("response_time_ms")
    if response_time is not None and (
        isinstance(response_time, bool)
        or not isinstance(response_time, int)
        or response_time < 0
        or response_time > 86_400_000
    ):
        return jsonify({"error": "response_time_ms must be an integer from 0 to 86400000"}), 400

    raw_answer = payload.get("submitted_answer")
    skipped = payload.get("skipped", False) is True
    status = "skipped" if skipped else "unanswered"
    submitted_answer = None
    is_correct = None
    if not skipped and raw_answer is not None:
        try:
            if isinstance(raw_answer, bool):
                raise ValueError
            submitted_answer = int(raw_answer)
            if str(submitted_answer) != str(raw_answer).strip() or not 0 <= submitted_answer <= 50:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            status = "invalid"
        else:
            status = "incorrect"
            is_correct = validate_answer(
                question.activity.operation_type,
                question.left_operand,
                question.right_operand,
                submitted_answer,
            )["is_correct"]
            if is_correct:
                status = "completed"

    if not skipped and raw_answer is None:
        status = "unanswered"
    previous_attempt = db.session.scalar(
        select(QuestionAttempt)
        .where(QuestionAttempt.question_id == question.id)
        .order_by(QuestionAttempt.attempted_at.desc())
        .limit(1)
    )
    attempted_at = utcnow()
    response_start = previous_attempt.attempted_at if previous_attempt else question.displayed_at
    server_elapsed_ms = max(
        0,
        int((attempted_at - response_start).total_seconds() * 1000),
    )
    if response_time is None:
        response_time = server_elapsed_ms
    else:
        if response_time > server_elapsed_ms + 5000:
            return jsonify({"error": "response_time_ms exceeds the measured response window"}), 400
        response_time = min(response_time, server_elapsed_ms)
    latest_recognition = None
    if is_correct is not None:
        latest_recognition = db.session.scalar(
            select(RecognitionLog)
            .where(RecognitionLog.learning_question_id == question.id)
            .where(RecognitionLog.status == "recognized")
            .where(RecognitionLog.predicted_value == submitted_answer)
            .where(RecognitionLog.question_attempt_id.is_(None))
            .where(
                RecognitionLog.recognized_at > previous_attempt.attempted_at
                if previous_attempt
                else RecognitionLog.recognized_at >= question.displayed_at
            )
            .order_by(RecognitionLog.recognized_at.desc())
            .limit(1)
        )
        if (
            latest_recognition is None
        ):
            return jsonify({"error": "A current, confidently recognized gesture is required before submission"}), 409
    recognition_filter = [RecognitionLog.learning_question_id == question.id]
    recognition_filter.append(
        RecognitionLog.recognized_at > previous_attempt.attempted_at
        if previous_attempt
        else RecognitionLog.recognized_at >= question.displayed_at
    )
    question_recognitions = db.session.scalars(
        select(RecognitionLog)
        .where(*recognition_filter)
        .order_by(RecognitionLog.recognized_at.asc())
    ).all()
    attempt_number = db.session.scalar(
        select(func.count())
        .select_from(QuestionAttempt)
        .where(QuestionAttempt.question_id == question.id)
    ) + 1
    attempt = QuestionAttempt(
        idempotency_key=idempotency_key,
        student_id=user.id,
        session_id=question.activity.session_id,
        activity_attempt_id=question.activity_attempt_id,
        question_id=question.id,
        expected_answer=question.expected_answer,
        submitted_answer=submitted_answer,
        is_correct=is_correct,
        attempt_number=attempt_number,
        response_time_ms=response_time,
        first_gesture_at=next(
            (item.recognized_at for item in question_recognitions if item.gesture_detected),
            None,
        ),
        gesture_attempt_count=len(question_recognitions),
        hint_used=payload.get("hint_used") is True,
        skipped=skipped,
        status=status,
        attempted_at=attempted_at,
    )
    StudentLearningDataService.save_question_attempt(
        activity,
        attempt,
        is_correct,
        [latest_recognition] if latest_recognition is not None else [],
    )

    result = question_attempt_data(attempt)
    if status == "invalid":
        return jsonify({"error": "submitted_answer must be an integer", "attempt": result}), 422
    return jsonify({"attempt": result}), 201


def question_attempt_data(item):
    return {
        "id": item.id,
        "question_id": item.question_id,
        "activity_attempt_id": item.activity_attempt_id,
        "operation_type": item.question.activity.operation_type,
        "difficulty_level": item.question.activity.difficulty_level,
        "question": item.question.question_content,
        "expected_answer": item.expected_answer,
        "submitted_answer": item.submitted_answer,
        "is_correct": item.is_correct,
        "attempt_number": item.attempt_number,
        "response_time_ms": item.response_time_ms,
        "displayed_at": item.question.displayed_at.isoformat() + "Z" if item.question.displayed_at else None,
        "first_gesture_at": item.first_gesture_at.isoformat() + "Z" if item.first_gesture_at else None,
        "gesture_attempt_count": item.gesture_attempt_count,
        "hint_used": item.hint_used,
        "skipped": item.skipped,
        "status": item.status,
        "attempted_at": item.attempted_at.isoformat() + "Z",
    }


@learning_bp.post("/student-recognition-logs")
def create_recognition_log():
    user, error = require_student()
    if error:
        return error
    payload = json_object()
    try:
        activity_id = int(payload.get("activity_attempt_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "activity_attempt_id is required"}), 400
    activity = db.session.scalar(
        select(ActivityAttempt)
        .where(
            ActivityAttempt.id == activity_id,
            ActivityAttempt.student_id == user.id,
        )
        .with_for_update()
    )
    if activity is None or activity.status != "in_progress":
        return jsonify({"error": "Active activity not found"}), 404

    question = None
    question_id = payload.get("question_id")
    if question_id is not None:
        normalized = parse_uuid(question_id)
        question = db.session.get(LearningQuestion, normalized) if normalized else None
        if question is None or question.activity_attempt_id != activity.id:
            return jsonify({"error": "Question does not belong to this activity"}), 400
    number_question = None
    number_question_id = payload.get("number_question_id")
    if number_question_id is not None:
        normalized = parse_uuid(number_question_id)
        number_question = (
            db.session.get(NumberIdentificationQuestion, normalized)
            if normalized
            else None
        )
        if number_question is None or number_question.activity_attempt_id != activity.id:
            return jsonify({"error": "Number question does not belong to this activity"}), 400
    if activity.operation_type == "number_identification":
        if question is not None or number_question is None:
            return jsonify({"error": "An active number-identification question is required"}), 400
    elif number_question is not None:
        return jsonify({"error": "Number questions are only valid for number-identification activities"}), 400
    predicted_value = payload.get("predicted_value")
    confidence = payload.get("confidence")
    gesture_detected = payload.get("gesture_detected") is True
    recognition_token_id = None
    if gesture_detected:
        if isinstance(predicted_value, bool) or not isinstance(predicted_value, int) or not 0 <= predicted_value <= 50:
            return jsonify({"error": "predicted_value must be an integer from 0 to 50"}), 400
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            return jsonify({"error": "confidence must be between 0 and 1"}), 400
        recognition_token = payload.get("recognition_token")
        if not isinstance(recognition_token, str):
            return jsonify({"error": "A signed recognition_token is required"}), 400
        try:
            token_data = URLSafeTimedSerializer(
                current_app.config["SECRET_KEY"], salt="slsl-recognition"
            ).loads(recognition_token, max_age=600)
        except BadSignature:
            return jsonify({"error": "Recognition token is invalid or expired"}), 400
        token_model_key = token_data.get("model_key")
        if (
            token_data.get("user_id") != user.id
            or token_data.get("predicted_number") != predicted_value
            or token_data.get("confidence") != float(confidence)
            or token_model_key != payload.get("model_key")
        ):
            return jsonify({"error": "Recognition token does not match this result"}), 403
        model_key = token_model_key
        if not isinstance(model_key, str) or len(model_key) > 32:
            return jsonify({"error": "Recognition model identifier is invalid"}), 400
        recognition_token_id = token_data.get("token_id")
        if not isinstance(recognition_token_id, str):
            return jsonify({"error": "Recognition token is invalid"}), 400
        existing_log = db.session.scalar(
            select(RecognitionLog).where(RecognitionLog.recognition_token_id == recognition_token_id)
        )
        if existing_log is not None:
            if (
                existing_log.activity_attempt_id == activity.id
                and existing_log.learning_question_id == (question.id if question else None)
                and existing_log.number_question_id == (
                    number_question.id if number_question else None
                )
            ):
                return jsonify({
                    "id": existing_log.id,
                    "status": existing_log.status,
                    "predicted_value": existing_log.predicted_value,
                    "confidence": existing_log.confidence,
                    "model_key": existing_log.model_key,
                    "is_correct": existing_log.is_correct,
                    "target_value": (
                        existing_log.number_question.expected_value
                        if existing_log.number_question
                        else None
                    ),
                    "number_question_status": (
                        existing_log.number_question.status
                        if existing_log.number_question
                        else None
                    ),
                    "recognized_at": existing_log.recognized_at.isoformat() + "Z",
                    "duplicate": True,
                })
            return jsonify({"error": "Recognition token has already been used"}), 409
        status = "recognized" if confidence >= RECOGNITION_THRESHOLD else "low_confidence"
    else:
        predicted_value = None
        confidence = None
        model_key = None
        status = payload.get("status", "no_gesture")
        if not isinstance(status, str) or status not in {"no_gesture", "processing_failed"}:
            return jsonify({"error": "Invalid recognition status"}), 400

    if number_question is not None and number_question.status != "in_progress":
        return jsonify({"error": "Number question has already been completed or skipped"}), 409
    if question is not None and completed_question_attempt(question.id) is not None:
        return jsonify({"error": "Recognition cannot be added after question submission"}), 409
    is_correct = None
    if number_question is not None and status == "recognized":
        is_correct = predicted_value == number_question.expected_value
        if is_correct:
            number_question.status = "completed"
            number_question.completed_at = utcnow()
    recognition_filter = [RecognitionLog.activity_attempt_id == activity.id]
    recognition_filter.append(
        RecognitionLog.number_question_id == number_question.id
        if number_question is not None
        else (
            RecognitionLog.learning_question_id.is_(None)
            if question is None
            else RecognitionLog.learning_question_id == question.id
        )
    )
    previous_count = db.session.scalar(
        select(func.count()).select_from(RecognitionLog).where(*recognition_filter)
    )
    log = RecognitionLog(
        activity_attempt_id=activity.id,
        learning_question_id=question.id if question else None,
        number_question_id=number_question.id if number_question else None,
        recognition_token_id=recognition_token_id,
        predicted_value=predicted_value,
        confidence=float(confidence) if confidence is not None else None,
        is_correct=is_correct,
        model_key=model_key,
        status=status,
        gesture_detected=gesture_detected,
        recognition_attempt_number=(previous_count or 0) + 1,
    )
    try:
        StudentLearningDataService.save_recognition_log(log)
    except IntegrityError:
        db.session.rollback()
        if recognition_token_id is None:
            raise
        existing_log = db.session.scalar(
            select(RecognitionLog).where(RecognitionLog.recognition_token_id == recognition_token_id)
        )
        if (
            existing_log is None
            or existing_log.activity_attempt_id != activity.id
            or existing_log.learning_question_id != (question.id if question else None)
            or existing_log.number_question_id != (
                number_question.id if number_question else None
            )
        ):
            return jsonify({"error": "Recognition token has already been used"}), 409
        log = existing_log
    return jsonify({
        "id": log.id,
        "status": log.status,
        "predicted_value": log.predicted_value,
        "confidence": log.confidence,
        "model_key": log.model_key,
        "is_correct": log.is_correct,
        "target_value": number_question.expected_value if number_question else None,
        "number_question_status": number_question.status if number_question else None,
        "recognized_at": log.recognized_at.isoformat() + "Z",
    }), 201


@learning_bp.get("/student-question-attempts")
def list_question_attempts():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    page_data = page_args()
    if page_data is None:
        return jsonify({"error": "page and page_size must be integers"}), 400
    page, page_size = page_data
    student_id = resolve_student_scope(user, request.args.get("student_id"))
    if student_id is None:
        return jsonify({"error": "You are not authorized to view these records"}), 403
    query = select(QuestionAttempt).where(QuestionAttempt.student_id == student_id)
    session_id = request.args.get("session_id")
    if session_id is not None:
        try:
            session_id = int(session_id)
        except ValueError:
            return jsonify({"error": "session_id must be an integer"}), 400
        learning_session = db.session.scalar(
            select(LearningSession).where(
                LearningSession.id == session_id,
                LearningSession.student_id == student_id,
            )
        )
        if learning_session is None:
            return jsonify({"error": "Learning session not found"}), 404
        query = query.where(QuestionAttempt.session_id == session_id)
    operation = request.args.get("operation_type")
    if operation:
        if operation not in OPERATIONS:
            return jsonify({"error": "Invalid operation_type"}), 400
        query = query.join(LearningQuestion).join(ActivityAttempt).where(ActivityAttempt.operation_type == operation)
    query = query.order_by(QuestionAttempt.attempted_at.desc())
    items = db.session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    count_query = select(func.count()).select_from(QuestionAttempt).where(
        QuestionAttempt.student_id == student_id
    )
    if session_id is not None:
        count_query = count_query.where(QuestionAttempt.session_id == session_id)
    if operation:
        count_query = count_query.join(LearningQuestion).join(ActivityAttempt).where(
            ActivityAttempt.operation_type == operation
        )
    total = db.session.scalar(count_query)
    total_attempts = db.session.scalar(
        count_query.where(QuestionAttempt.is_correct.is_not(None))
    )
    correct = db.session.scalar(count_query.where(QuestionAttempt.is_correct.is_(True)))
    return jsonify({
        "items": [question_attempt_data(item) for item in items],
        "page": page,
        "page_size": page_size,
        "total": total,
        "summary": {
            "total_attempts": total_attempts or 0,
            "correct": correct or 0,
            "points": correct or 0,
        },
    })


@learning_bp.get("/student-question-attempts/<int:attempt_id>")
def get_question_attempt(attempt_id):
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    attempt = db.session.get(QuestionAttempt, attempt_id)
    if attempt is None:
        return jsonify({"error": "Attempt not found"}), 404
    student_id = resolve_student_scope(user, attempt.student_id)
    if student_id != attempt.student_id:
        return jsonify({"error": "Attempt not found"}), 404
    return jsonify({
        "attempt": question_attempt_data(attempt),
        "recognition_logs": [
            {
                "predicted_value": log.predicted_value,
                "confidence": log.confidence,
                "model_key": log.model_key,
                "status": log.status,
                "gesture_detected": log.gesture_detected,
                "recognition_attempt_number": log.recognition_attempt_number,
                "recognized_at": log.recognized_at.isoformat() + "Z",
            }
            for log in attempt.recognition_logs
        ],
    })


@learning_bp.get("/student-activities/history")
def activity_history():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    page_data = page_args()
    if page_data is None:
        return jsonify({"error": "page and page_size must be integers"}), 400
    page, page_size = page_data
    student_id = resolve_student_scope(user, request.args.get("student_id"))
    if student_id is None:
        return jsonify({"error": "You are not authorized to view these records"}), 403
    query = select(ActivityAttempt).where(ActivityAttempt.student_id == student_id).order_by(ActivityAttempt.started_at.desc())
    items = db.session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    total = db.session.scalar(select(func.count()).select_from(ActivityAttempt).where(ActivityAttempt.student_id == student_id))
    return jsonify({"items": [activity_data(item) for item in items], "page": page, "page_size": page_size, "total": total})


@learning_bp.get("/student-recognition-logs")
def recognition_history():
    user = authenticated_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    page_data = page_args()
    if page_data is None:
        return jsonify({"error": "page and page_size must be integers"}), 400
    page, page_size = page_data
    student_id = resolve_student_scope(user, request.args.get("student_id"))
    if student_id is None:
        return jsonify({"error": "You are not authorized to view these records"}), 403
    query = (
        select(RecognitionLog)
        .join(ActivityAttempt)
        .where(ActivityAttempt.student_id == student_id)
        .order_by(RecognitionLog.recognized_at.desc())
    )
    items = db.session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return jsonify({
        "items": [
            {
                "id": item.id,
                "activity_attempt_id": item.activity_attempt_id,
                "question_attempt_id": item.question_attempt_id,
                "predicted_value": item.predicted_value,
                "number_question_id": item.number_question_id,
                "target_value": (
                    item.number_question.expected_value
                    if item.number_question
                    else None
                ),
                "is_correct": item.is_correct,
                "confidence": item.confidence,
                "model_key": item.model_key,
                "status": item.status,
                "gesture_detected": item.gesture_detected,
                "recognition_attempt_number": item.recognition_attempt_number,
                "recognized_at": item.recognized_at.isoformat() + "Z",
            }
            for item in items
        ],
        "page": page,
        "page_size": page_size,
    })
