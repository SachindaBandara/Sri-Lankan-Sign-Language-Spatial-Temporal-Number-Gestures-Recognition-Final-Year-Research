from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import validates
from sqlalchemy.dialects.mysql import DATETIME
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

_DATETIME_TYPE = db.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


teacher_students = db.Table(
    "teacher_students",
    db.Column("teacher_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("student_id", db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("`role` IN ('student', 'teacher')", name="ck_users_role"),
        CheckConstraint("`is_active` IN (0, 1)", name="ck_users_active_boolean"),
        CheckConstraint(
            "`grade` IS NULL OR `grade` BETWEEN 1 AND 13",
            name="ck_users_grade",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="student")
    grade = db.Column(db.SmallInteger)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    students = db.relationship(
        "User",
        secondary=teacher_students,
        primaryjoin=id == teacher_students.c.teacher_id,
        secondaryjoin=id == teacher_students.c.student_id,
        backref="teachers",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def public_data(self) -> dict:
        return {"id": self.id, "username": self.username, "role": self.role, "grade": self.grade}


class LearningSession(db.Model):
    __tablename__ = "student_learning_sessions"
    __table_args__ = (
        CheckConstraint(
            "`status` IN ('in_progress', 'completed', 'abandoned')",
            name="ck_learning_sessions_status",
        ),
        CheckConstraint(
            "`total_duration_ms` IS NULL OR `total_duration_ms` >= 0",
            name="ck_learning_sessions_duration",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid4()))
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    started_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    ended_at = db.Column(_DATETIME_TYPE)
    total_duration_ms = db.Column(db.BigInteger)
    status = db.Column(db.String(16), nullable=False, default="in_progress")
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    student = db.relationship("User")
    activities = db.relationship("ActivityAttempt", back_populates="session", passive_deletes="all")


class ActivityAttempt(db.Model):
    __tablename__ = "student_activity_attempts"
    __table_args__ = (
        CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_activity_operation",
        ),
        CheckConstraint(
            "`difficulty_level` IN ('easy', 'standard', 'hard')",
            name="ck_activity_difficulty",
        ),
        CheckConstraint(
            "`operation_type` <> 'number_identification' OR `difficulty_level` = 'standard'",
            name="ck_activity_number_difficulty",
        ),
        CheckConstraint(
            "`status` IN ('in_progress', 'completed', 'abandoned')",
            name="ck_activity_status",
        ),
        CheckConstraint(
            "`total_questions` >= 0 AND `total_attempts` >= 0 "
            "AND `completed_questions` >= 0 AND `skipped_questions` >= 0 "
            "AND `correct_answers` >= 0 AND `incorrect_answers` >= 0",
            name="ck_activity_nonnegative_counts",
        ),
        CheckConstraint(
            "`total_attempts` = `correct_answers` + `incorrect_answers`",
            name="ck_activity_attempt_summary",
        ),
        CheckConstraint(
            "`completed_questions` <= `correct_answers` "
            "AND `completed_questions` + `skipped_questions` <= `total_questions`",
            name="ck_activity_question_summary",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(36), nullable=False, unique=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("student_learning_sessions.id", ondelete="RESTRICT"), nullable=False, index=True)
    operation_type = db.Column(db.String(32), nullable=False, index=True)
    difficulty_level = db.Column(db.String(24), nullable=False, default="standard")
    started_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    completed_at = db.Column(_DATETIME_TYPE)
    status = db.Column(db.String(16), nullable=False, default="in_progress")
    total_questions = db.Column(db.Integer, nullable=False, default=0)
    total_attempts = db.Column(db.Integer, nullable=False, default=0)
    completed_questions = db.Column(db.Integer, nullable=False, default=0)
    skipped_questions = db.Column(db.Integer, nullable=False, default=0)
    correct_answers = db.Column(db.Integer, nullable=False, default=0)
    incorrect_answers = db.Column(db.Integer, nullable=False, default=0)
    session = db.relationship("LearningSession", back_populates="activities")
    questions = db.relationship("LearningQuestion", back_populates="activity", passive_deletes="all")
    recognition_logs = db.relationship("RecognitionLog", back_populates="activity", passive_deletes="all")
    number_questions = db.relationship(
        "NumberIdentificationQuestion",
        back_populates="activity",
        passive_deletes="all",
    )


class LearningQuestion(db.Model):
    __tablename__ = "learning_questions"
    __table_args__ = (
        CheckConstraint(
            "`left_operand` >= 0 AND `right_operand` >= 0",
            name="ck_question_nonnegative_operands",
        ),
        CheckConstraint(
            "`expected_answer` BETWEEN 0 AND 50",
            name="ck_question_answer_range",
        ),
        CheckConstraint(
            "`operator_symbol` IN ('+', '-', 'x', '/')",
            name="ck_question_operator",
        ),
        CheckConstraint(
            "(`operator_symbol` = '+' AND `expected_answer` = `left_operand` + `right_operand`) "
            "OR (`operator_symbol` = '-' AND `expected_answer` = `left_operand` - `right_operand`) "
            "OR (`operator_symbol` = 'x' AND `expected_answer` = `left_operand` * `right_operand`) "
            "OR (`operator_symbol` = '/' AND `right_operand` > 0 "
            "AND `left_operand` = `expected_answer` * `right_operand`)",
            name="ck_question_answer_matches_operands",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    activity_attempt_id = db.Column(db.Integer, db.ForeignKey("student_activity_attempts.id", ondelete="RESTRICT"), nullable=False, index=True)
    question_content = db.Column(db.String(160), nullable=False)
    left_operand = db.Column(db.Integer, nullable=False)
    right_operand = db.Column(db.Integer, nullable=False)
    operator_symbol = db.Column(db.String(4), nullable=False)
    question_type = db.Column(db.String(24), nullable=False, default="arithmetic")
    expected_answer = db.Column(db.Integer, nullable=False)
    displayed_at = db.Column(_DATETIME_TYPE)
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    activity = db.relationship("ActivityAttempt", back_populates="questions")
    attempts = db.relationship(
        "QuestionAttempt",
        back_populates="question",
        order_by="QuestionAttempt.attempted_at",
        passive_deletes="all",
    )


class NumberIdentificationQuestion(db.Model):
    __tablename__ = "number_identification_questions"
    __table_args__ = (
        db.UniqueConstraint(
            "activity_attempt_id",
            "sequence_number",
            name="uq_number_question_activity_sequence",
        ),
        CheckConstraint(
            "`expected_value` BETWEEN 0 AND 50",
            name="ck_number_question_expected_value",
        ),
        CheckConstraint(
            "`sequence_number` >= 1",
            name="ck_number_question_sequence",
        ),
        CheckConstraint(
            "`status` IN ('in_progress', 'completed', 'skipped')",
            name="ck_number_question_status",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    activity_attempt_id = db.Column(
        db.Integer,
        db.ForeignKey("student_activity_attempts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence_number = db.Column(db.SmallInteger, nullable=False)
    expected_value = db.Column(db.SmallInteger, nullable=False)
    status = db.Column(db.String(16), nullable=False, default="in_progress")
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    completed_at = db.Column(_DATETIME_TYPE)
    activity = db.relationship("ActivityAttempt", back_populates="number_questions")
    recognition_logs = db.relationship("RecognitionLog", back_populates="number_question")


class QuestionAttempt(db.Model):
    __tablename__ = "student_question_attempts"
    __table_args__ = (
        CheckConstraint("`attempt_number` >= 1", name="ck_attempt_number_positive"),
        CheckConstraint(
            "`response_time_ms` IS NULL OR `response_time_ms` >= 0",
            name="ck_attempt_response_time_nonnegative",
        ),
        CheckConstraint(
            "`gesture_attempt_count` >= 0",
            name="ck_attempt_gesture_count_nonnegative",
        ),
        CheckConstraint("`hint_used` IN (0, 1)", name="ck_attempt_hint_boolean"),
        CheckConstraint(
            "`submitted_answer` IS NULL OR `submitted_answer` BETWEEN 0 AND 50",
            name="ck_attempt_submitted_answer_range",
        ),
        CheckConstraint(
            "(`status` = 'completed' AND `submitted_answer` IS NOT NULL "
            "AND `is_correct` = 1 AND `skipped` = 0) "
            "OR (`status` = 'incorrect' AND `submitted_answer` IS NOT NULL "
            "AND `is_correct` = 0 AND `skipped` = 0) "
            "OR (`status` = 'skipped' AND `submitted_answer` IS NULL "
            "AND `is_correct` IS NULL AND `skipped` = 1) "
            "OR (`status` IN ('unanswered', 'invalid') AND `submitted_answer` IS NULL "
            "AND `is_correct` IS NULL AND `skipped` = 0)",
            name="ck_attempt_status_consistency",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    idempotency_key = db.Column(db.String(36), nullable=False, unique=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("student_learning_sessions.id", ondelete="RESTRICT"), nullable=False, index=True)
    activity_attempt_id = db.Column(db.Integer, db.ForeignKey("student_activity_attempts.id", ondelete="RESTRICT"), nullable=False, index=True)
    question_id = db.Column(db.String(36), db.ForeignKey("learning_questions.id", ondelete="RESTRICT"), nullable=False, index=True)
    expected_answer = db.Column(db.Integer, nullable=False)
    submitted_answer = db.Column(db.Integer)
    is_correct = db.Column(db.Boolean)
    attempt_number = db.Column(db.Integer, nullable=False)
    response_time_ms = db.Column(db.BigInteger)
    first_gesture_at = db.Column(_DATETIME_TYPE)
    gesture_attempt_count = db.Column(db.Integer, nullable=False, default=0)
    hint_used = db.Column(db.Boolean, nullable=False, default=False)
    skipped = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(16), nullable=False)
    attempted_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    question = db.relationship("LearningQuestion", back_populates="attempts")
    recognition_logs = db.relationship("RecognitionLog", back_populates="question_attempt")


class RecognitionLog(db.Model):
    __tablename__ = "student_sign_recognition_logs"
    __table_args__ = (
        CheckConstraint(
            "`status` IN ('recognized', 'low_confidence', 'no_gesture', 'processing_failed')",
            name="ck_recognition_status",
        ),
        CheckConstraint(
            "`recognition_attempt_number` >= 1",
            name="ck_recognition_attempt_number_positive",
        ),
        CheckConstraint(
            "`predicted_value` IS NULL OR `predicted_value` BETWEEN 0 AND 50",
            name="ck_recognition_predicted_range",
        ),
        CheckConstraint(
            "`confidence` IS NULL OR `confidence` BETWEEN 0 AND 1",
            name="ck_recognition_confidence_range",
        ),
        CheckConstraint(
            "(`status` IN ('recognized', 'low_confidence') AND `gesture_detected` = 1 "
            "AND `predicted_value` IS NOT NULL AND `confidence` IS NOT NULL) "
            "OR (`status` IN ('no_gesture', 'processing_failed') AND `gesture_detected` = 0 "
            "AND `predicted_value` IS NULL AND `confidence` IS NULL)",
            name="ck_recognition_status_consistency",
        ),
        CheckConstraint(
            "`is_correct` IS NULL OR "
            "(`status` = 'recognized' AND `number_question_id` IS NOT NULL)",
            name="ck_recognition_number_answer_consistency",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    activity_attempt_id = db.Column(db.Integer, db.ForeignKey("student_activity_attempts.id", ondelete="RESTRICT"), nullable=False, index=True)
    question_attempt_id = db.Column(db.Integer, db.ForeignKey("student_question_attempts.id", ondelete="SET NULL"), index=True)
    learning_question_id = db.Column(db.String(36), db.ForeignKey("learning_questions.id", ondelete="SET NULL"), index=True)
    number_question_id = db.Column(
        db.String(36),
        db.ForeignKey("number_identification_questions.id", ondelete="RESTRICT"),
        index=True,
    )
    recognition_token_id = db.Column(db.String(36), unique=True, index=True)
    predicted_value = db.Column(db.SmallInteger)
    confidence = db.Column(db.Float)
    is_correct = db.Column(db.Boolean)
    model_key = db.Column(db.String(32))
    status = db.Column(db.String(24), nullable=False)
    gesture_detected = db.Column(db.Boolean, nullable=False)
    recognition_attempt_number = db.Column(db.Integer, nullable=False)
    recognized_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    activity = db.relationship("ActivityAttempt", back_populates="recognition_logs")
    question_attempt = db.relationship("QuestionAttempt", back_populates="recognition_logs")
    question = db.relationship("LearningQuestion")
    number_question = db.relationship(
        "NumberIdentificationQuestion",
        back_populates="recognition_logs",
    )

    @validates("learning_question_id", "number_question_id")
    def validate_single_question_reference(self, key, value):
        other_key = (
            "number_question_id"
            if key == "learning_question_id"
            else "learning_question_id"
        )
        if value is not None and getattr(self, other_key) is not None:
            raise ValueError("A recognition log can reference only one question type.")
        return value


class StudentLearningProgress(db.Model):
    __tablename__ = "student_learning_progress"
    __table_args__ = (
        db.UniqueConstraint("student_id", "operation_type", name="uq_learning_progress_student_operation"),
        CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_learning_progress_operation",
        ),
        CheckConstraint(
            "`current_difficulty` IN ('easy', 'standard', 'hard')",
            name="ck_learning_progress_difficulty",
        ),
        CheckConstraint(
            "`total_attempts` >= 0 AND `correct_answers` >= 0 "
            "AND `incorrect_answers` >= 0 AND `recognition_events` >= 0 "
            "AND `high_confidence_recognitions` >= 0 "
            "AND `correct_answers` + `incorrect_answers` = `total_attempts` "
            "AND `high_confidence_recognitions` <= `recognition_events` "
            "AND `last_evaluated_attempt_id` >= 0",
            name="ck_learning_progress_counts",
        ),
        CheckConstraint(
            "`average_response_time_ms` IS NULL OR `average_response_time_ms` >= 0",
            name="ck_learning_progress_response_time",
        ),
        CheckConstraint(
            "`improvement_rate` IS NULL OR `improvement_rate` BETWEEN -1 AND 1",
            name="ck_learning_progress_improvement_rate",
        ),
        CheckConstraint(
            "`accuracy` IS NULL OR `accuracy` BETWEEN 0 AND 1",
            name="ck_learning_progress_accuracy",
        ),
        CheckConstraint(
            "`recent_accuracy` IS NULL OR `recent_accuracy` BETWEEN 0 AND 1",
            name="ck_learning_progress_recent_accuracy",
        ),
        CheckConstraint(
            "`average_recognition_confidence` IS NULL "
            "OR `average_recognition_confidence` BETWEEN 0 AND 1",
            name="ck_learning_progress_recognition_confidence",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation_type = db.Column(db.String(32), nullable=False)
    current_difficulty = db.Column(db.String(24), nullable=False, default="easy")
    total_attempts = db.Column(db.Integer, nullable=False, default=0)
    correct_answers = db.Column(db.Integer, nullable=False, default=0)
    incorrect_answers = db.Column(db.Integer, nullable=False, default=0)
    accuracy = db.Column(db.Float)
    recent_accuracy = db.Column(db.Float)
    average_response_time_ms = db.Column(db.BigInteger)
    improvement_rate = db.Column(db.Float)
    recognition_events = db.Column(db.Integer, nullable=False, default=0)
    high_confidence_recognitions = db.Column(db.Integer, nullable=False, default=0)
    average_recognition_confidence = db.Column(db.Float)
    last_evaluated_attempt_id = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow, onupdate=utcnow)


class DifficultyAdjustmentHistory(db.Model):
    __tablename__ = "student_difficulty_adjustments"
    __table_args__ = (
        CheckConstraint(
            "`operation_type` IN ('addition', 'subtraction', 'multiplication', 'division')",
            name="ck_difficulty_adjustment_operation",
        ),
        CheckConstraint(
            "`previous_difficulty` IN ('easy', 'standard', 'hard') "
            "AND `new_difficulty` IN ('easy', 'standard', 'hard') "
            "AND `previous_difficulty` <> `new_difficulty`",
            name="ck_difficulty_adjustment_levels",
        ),
        CheckConstraint(
            "`recent_accuracy` BETWEEN 0 AND 1 AND `historical_accuracy` BETWEEN 0 AND 1",
            name="ck_difficulty_adjustment_accuracy",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation_type = db.Column(db.String(32), nullable=False)
    previous_difficulty = db.Column(db.String(24), nullable=False)
    new_difficulty = db.Column(db.String(24), nullable=False)
    recent_accuracy = db.Column(db.Float, nullable=False)
    historical_accuracy = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(240), nullable=False)
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)


class LearningRecommendation(db.Model):
    __tablename__ = "student_learning_recommendations"
    __table_args__ = (
        db.UniqueConstraint("student_id", "recommendation_key", name="uq_recommendation_student_key"),
        CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_recommendation_operation",
        ),
        CheckConstraint(
            "`difficulty_level` IN ('easy', 'standard', 'hard')",
            name="ck_recommendation_difficulty",
        ),
        CheckConstraint(
            "`operation_type` <> 'number_identification' OR `difficulty_level` = 'standard'",
            name="ck_recommendation_number_difficulty",
        ),
        CheckConstraint(
            "`status` IN ('pending', 'in_progress', 'completed', 'dismissed')",
            name="ck_recommendation_status",
        ),
        CheckConstraint("`priority` BETWEEN 1 AND 5", name="ck_recommendation_priority"),
        CheckConstraint(
            "`baseline_accuracy` IS NULL OR `baseline_accuracy` BETWEEN 0 AND 1",
            name="ck_recommendation_baseline_accuracy",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    operation_type = db.Column(db.String(32), nullable=False)
    recommendation_key = db.Column(db.String(96), nullable=False)
    difficulty_level = db.Column(db.String(24), nullable=False)
    kind = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    explanation = db.Column(db.String(500), nullable=False)
    priority = db.Column(db.SmallInteger, nullable=False, default=3)
    status = db.Column(db.String(16), nullable=False, default="pending")
    baseline_accuracy = db.Column(db.Float)
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    updated_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow, onupdate=utcnow)
    completed_at = db.Column(_DATETIME_TYPE)


class StudentLearningPath(db.Model):
    __tablename__ = "student_learning_paths"
    __table_args__ = (
        CheckConstraint("`status` IN ('active', 'completed')", name="ck_learning_path_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    title = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="active")
    created_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow)
    updated_at = db.Column(_DATETIME_TYPE, nullable=False, default=utcnow, onupdate=utcnow)


class LearningPathStep(db.Model):
    __tablename__ = "student_learning_path_steps"
    __table_args__ = (
        db.UniqueConstraint("path_id", "skill_key", name="uq_learning_path_step_skill"),
        db.UniqueConstraint("path_id", "sequence_number", name="uq_learning_path_step_sequence"),
        CheckConstraint("`sequence_number` >= 1", name="ck_learning_path_step_sequence"),
        CheckConstraint(
            "`operation_type` IN "
            "('number_identification', 'addition', 'subtraction', 'multiplication', 'division')",
            name="ck_learning_path_step_operation",
        ),
        CheckConstraint(
            "`difficulty_level` IN ('easy', 'standard', 'hard')",
            name="ck_learning_path_step_difficulty",
        ),
        CheckConstraint(
            "`operation_type` <> 'number_identification' OR `difficulty_level` = 'standard'",
            name="ck_learning_path_step_number_difficulty",
        ),
        CheckConstraint(
            "`status` IN ('locked', 'in_progress', 'completed')",
            name="ck_learning_path_step_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    path_id = db.Column(
        db.Integer,
        db.ForeignKey("student_learning_paths.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence_number = db.Column(db.SmallInteger, nullable=False)
    operation_type = db.Column(db.String(32), nullable=False)
    skill_key = db.Column(db.String(64), nullable=False)
    difficulty_level = db.Column(db.String(24), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    reason = db.Column(db.String(240), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="locked")
    completed_at = db.Column(_DATETIME_TYPE)
