from sqlalchemy import or_, select

from extensions import db
from models import (
    ActivityAttempt,
    LearningQuestion,
    LearningSession,
    QuestionAttempt,
    RecognitionLog,
    utcnow,
)
from utils.activity_engine import generate_question
from services.personalized_learning_service import PersonalizedLearningService


class StudentLearningDataService:
    @staticmethod
    def start_session(student_id: int, identifier: str) -> LearningSession:
        learning_session = LearningSession(identifier=identifier, student_id=student_id)
        db.session.add(learning_session)
        db.session.commit()
        return learning_session

    @staticmethod
    def start_activity(
        student_id: int,
        session_id: int,
        operation: str,
        request_key: str,
        difficulty_level: str = "standard",
    ) -> ActivityAttempt:
        learning_session = db.session.scalar(
            select(LearningSession)
            .where(LearningSession.id == session_id, LearningSession.student_id == student_id)
            .with_for_update()
        )
        if learning_session is None or learning_session.status != "in_progress":
            raise ValueError("Learning session is no longer active")
        activity = ActivityAttempt(
            request_key=request_key,
            student_id=student_id,
            session_id=session_id,
            operation_type=operation,
            difficulty_level=difficulty_level,
        )
        db.session.add(activity)
        db.session.commit()
        return activity

    @staticmethod
    def complete_activity(activity: ActivityAttempt) -> ActivityAttempt:
        locked_activity = db.session.scalar(
            select(ActivityAttempt).where(ActivityAttempt.id == activity.id).with_for_update()
        )
        if locked_activity and locked_activity.status == "in_progress":
            locked_activity.status = "completed"
            locked_activity.completed_at = utcnow()
            db.session.commit()
            PersonalizedLearningService.activity_completed(locked_activity)
            return locked_activity
        return locked_activity or activity

    @staticmethod
    def get_or_create_question(activity: ActivityAttempt) -> LearningQuestion:
        activity = db.session.scalar(
            select(ActivityAttempt).where(ActivityAttempt.id == activity.id).with_for_update()
        )
        if activity is None or activity.status != "in_progress":
            raise ValueError("Activity is no longer active")
        completed_question_exists = (
            select(QuestionAttempt.id)
            .where(
                QuestionAttempt.question_id == LearningQuestion.id,
                or_(
                    QuestionAttempt.is_correct.is_(True),
                    QuestionAttempt.skipped.is_(True),
                ),
            )
            .correlate(LearningQuestion)
            .exists()
        )
        active_question = db.session.scalar(
            select(LearningQuestion)
            .where(
                LearningQuestion.activity_attempt_id == activity.id,
                ~completed_question_exists,
            )
            .order_by(LearningQuestion.created_at.desc())
            .limit(1)
        )
        if active_question is not None:
            return active_question
        generated = generate_question(activity.operation_type, activity.difficulty_level)
        question = LearningQuestion(
            activity_attempt_id=activity.id,
            left_operand=generated["left"],
            right_operand=generated["right"],
            operator_symbol=generated["operator"],
            expected_answer=generated["answer"],
            question_content=f'{generated["left"]} {generated["operator"]} {generated["right"]} = ?',
        )
        db.session.add(question)
        activity.total_questions += 1
        db.session.commit()
        return question

    @staticmethod
    def save_question_attempt(
        activity: ActivityAttempt,
        attempt: QuestionAttempt,
        is_correct: bool | None,
        recognition_logs: list[RecognitionLog],
    ) -> QuestionAttempt:
        for recognition in recognition_logs:
            recognition.question_attempt = attempt
        db.session.add(attempt)
        if is_correct is not None:
            activity.total_attempts += 1
        if is_correct is True:
            activity.correct_answers += 1
            activity.completed_questions += 1
        elif is_correct is False:
            activity.incorrect_answers += 1
        if attempt.skipped:
            activity.skipped_questions += 1
        db.session.flush()
        if is_correct is not None:
            PersonalizedLearningService.refresh_student(
                activity.student_id,
                evaluated_attempt_id=attempt.id,
            )
        db.session.commit()
        return attempt

    @staticmethod
    def save_recognition_log(log: RecognitionLog) -> RecognitionLog:
        db.session.add(log)
        db.session.flush()
        activity = db.session.get(ActivityAttempt, log.activity_attempt_id)
        if activity is not None and activity.operation_type == "number_identification":
            if log.is_correct is not None:
                activity.total_attempts += 1
                if log.is_correct:
                    activity.correct_answers += 1
                    activity.completed_questions += 1
                else:
                    activity.incorrect_answers += 1
            PersonalizedLearningService.refresh_recognition(activity.student_id)
        db.session.commit()
        return log

    @staticmethod
    def end_session(learning_session: LearningSession, status: str = "completed") -> LearningSession:
        locked_session = db.session.scalar(
            select(LearningSession)
            .where(LearningSession.id == learning_session.id)
            .with_for_update()
        )
        if locked_session and locked_session.status == "in_progress":
            locked_session.ended_at = utcnow()
            locked_session.total_duration_ms = max(
                0,
                int((locked_session.ended_at - locked_session.started_at).total_seconds() * 1000),
            )
            locked_session.status = status
            for activity in locked_session.activities:
                if activity.status == "in_progress":
                    activity.status = "abandoned"
                    activity.completed_at = locked_session.ended_at
            db.session.commit()
            return locked_session
        return locked_session or learning_session
