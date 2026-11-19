import os
import unittest
from datetime import datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app import create_app
from extensions import db
from models import (
    ActivityAttempt,
    DifficultyAdjustmentHistory,
    LearningQuestion,
    LearningSession,
    LearningPathStep,
    QuestionAttempt,
    RecognitionLog,
    StudentLearningPath,
    StudentLearningProgress,
    User,
    utcnow,
)
from services.student_learning_data_service import StudentLearningDataService


def test_database_uri() -> str:
    database_uri = os.environ.get("TEST_DATABASE_URL")
    if not database_uri:
        return "sqlite://"
    database_name = make_url(database_uri).database
    if not database_name or not database_name.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must target a database whose name ends with '_test'.")
    return database_uri


class PersonalizedLearningTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "personalization-test-secret",
            "SQLALCHEMY_DATABASE_URI": test_database_uri(),
            "SESSION_COOKIE_SECURE": False,
            "PERSONALIZATION_MIN_ATTEMPTS": 8,
            "PERSONALIZATION_RECENT_WINDOW": 10,
            "PERSONALIZATION_PROMOTION_STREAK": 5,
            "PERSONALIZATION_DEMOTION_STREAK": 3,
        })
        self.context = self.app.app_context()
        self.context.push()
        if db.engine.dialect.name == "sqlite":
            with db.engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        db.create_all()
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/auth/me").get_json()["csrf_token"]
        response = self.client.post(
            "/api/auth/register",
            json={"username": "progress-student", "password": "a-strong-password", "grade": 5},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 201)
        self.csrf = response.get_json()["csrf_token"]
        self.student = User.query.filter_by(username="progress-student").one()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def _record_math_answer(
        self,
        operation="addition",
        correct=True,
        difficulty="easy",
        refresh_progress=True,
        hint_used=False,
        skipped=False,
    ):
        learning_session = LearningSession(
            identifier=str(uuid4()),
            student_id=self.student.id,
        )
        db.session.add(learning_session)
        db.session.flush()
        activity = ActivityAttempt(
            request_key=str(uuid4()),
            student_id=self.student.id,
            session_id=learning_session.id,
            operation_type=operation,
            difficulty_level=difficulty,
            total_questions=1,
        )
        db.session.add(activity)
        db.session.flush()
        question = LearningQuestion(
            activity_attempt_id=activity.id,
            question_content="1 + 1 = ?",
            left_operand=1,
            right_operand=1,
            operator_symbol="+",
            expected_answer=2,
        )
        db.session.add(question)
        db.session.flush()
        answer_result = None if skipped else correct
        attempt = QuestionAttempt(
            idempotency_key=str(uuid4()),
            student_id=self.student.id,
            session_id=learning_session.id,
            activity_attempt_id=activity.id,
            question_id=question.id,
            expected_answer=2,
            submitted_answer=None if skipped else 2 if correct else 1,
            is_correct=answer_result,
            attempt_number=1,
            response_time_ms=1000,
            gesture_attempt_count=0 if skipped else 1,
            hint_used=hint_used,
            skipped=skipped,
            status="skipped" if skipped else "completed" if correct else "incorrect",
        )
        if refresh_progress:
            StudentLearningDataService.save_question_attempt(
                activity,
                attempt,
                answer_result,
                [],
            )
        else:
            activity.total_attempts = int(answer_result is not None)
            activity.correct_answers = int(answer_result is True)
            activity.incorrect_answers = int(answer_result is False)
            activity.completed_questions = int(answer_result is True)
            activity.skipped_questions = int(skipped)
            db.session.add(attempt)
            db.session.commit()
        return attempt

    def test_dashboard_distinguishes_insufficient_evidence_and_recognition_confidence(self):
        learning_session = LearningSession(identifier=str(uuid4()), student_id=self.student.id)
        db.session.add(learning_session)
        db.session.flush()
        skipped_activity = ActivityAttempt(
            request_key=str(uuid4()),
            student_id=self.student.id,
            session_id=learning_session.id,
            operation_type="addition",
            difficulty_level="easy",
            total_questions=1,
        )
        db.session.add(skipped_activity)
        db.session.flush()
        skipped_question = LearningQuestion(
            activity_attempt_id=skipped_activity.id,
            question_content="1 + 1 = ?",
            left_operand=1,
            right_operand=1,
            operator_symbol="+",
            expected_answer=2,
        )
        db.session.add(skipped_question)
        db.session.flush()
        StudentLearningDataService.save_question_attempt(
            skipped_activity,
            QuestionAttempt(
                idempotency_key=str(uuid4()),
                student_id=self.student.id,
                session_id=learning_session.id,
                activity_attempt_id=skipped_activity.id,
                question_id=skipped_question.id,
                expected_answer=2,
                submitted_answer=None,
                is_correct=None,
                attempt_number=1,
                response_time_ms=1000,
                gesture_attempt_count=0,
                hint_used=False,
                skipped=True,
                status="skipped",
            ),
            None,
            [],
        )
        activity = ActivityAttempt(
            request_key=str(uuid4()),
            student_id=self.student.id,
            session_id=learning_session.id,
            operation_type="number_identification",
            difficulty_level="standard",
        )
        db.session.add(activity)
        db.session.flush()
        db.session.add(
            RecognitionLog(
                activity_attempt_id=activity.id,
                predicted_value=7,
                confidence=0.92,
                model_key="0-9",
                status="recognized",
                gesture_detected=True,
                recognition_attempt_number=1,
            )
        )
        db.session.commit()

        response = self.client.get("/api/personalized-learning/dashboard")
        self.assertEqual(response.status_code, 200)
        dashboard = response.get_json()
        self.assertEqual(dashboard["summary"]["total_attempts"], 0)
        self.assertIsNone(dashboard["summary"]["accuracy"])
        number_progress = next(
            item for item in dashboard["operations"]
            if item["operation_type"] == "number_identification"
        )
        self.assertIsNone(number_progress["accuracy"])
        self.assertEqual(number_progress["recognition_events"], 1)
        self.assertAlmostEqual(number_progress["average_recognition_confidence"], 0.92)
        addition = next(
            item for item in dashboard["operations"]
            if item["operation_type"] == "addition"
        )
        self.assertFalse(addition["sample_sufficient"])
        self.assertEqual(dashboard["learning_path"]["steps"][0]["operation_type"], "number_identification")
        self.assertEqual(len(dashboard["recommendations"]), 1)
        self.assertEqual(
            dashboard["recommendations"][0]["activity"]["catalogue_id"],
            "number-identification-target-practice",
        )
        self.assertEqual(
            dashboard["recommendations"][0]["activity"]["route"],
            "/number-identification",
        )

        StudentLearningDataService.complete_activity(activity)
        updated = self.client.get("/api/personalized-learning/dashboard").get_json()
        self.assertEqual(updated["learning_path"]["steps"][0]["status"], "in_progress")
        self.assertEqual(updated["learning_path"]["steps"][1]["status"], "locked")

    def test_dashboard_includes_daily_progress_and_activity_completion_statistics(self):
        today = utcnow().date()
        samples = [
            (self._record_math_answer(correct=True), today - timedelta(days=5), "completed"),
            (self._record_math_answer(correct=False), today - timedelta(days=1), "abandoned"),
            (self._record_math_answer(correct=True), today, "in_progress"),
            (self._record_math_answer(correct=True), today - timedelta(days=8), "completed"),
        ]
        for attempt, activity_day, status in samples:
            activity = db.session.get(ActivityAttempt, attempt.activity_attempt_id)
            learning_session = db.session.get(LearningSession, activity.session_id)
            event_time = datetime.combine(activity_day, time(hour=12))
            attempt.attempted_at = event_time
            activity.started_at = event_time - timedelta(minutes=5)
            activity.status = status
            activity.completed_at = event_time if status != "in_progress" else None
            learning_session.started_at = activity.started_at
            learning_session.status = "in_progress" if status == "in_progress" else status
            learning_session.ended_at = None if status == "in_progress" else event_time
            learning_session.total_duration_ms = (
                None if status == "in_progress" else 300_000
            )
        db.session.commit()

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        weekly = dashboard["weekly_progress"]
        daily = {item["date"]: item for item in weekly["days"]}
        self.assertEqual(len(weekly["days"]), 7)
        self.assertEqual(weekly["total_attempts"], 3)
        self.assertEqual(weekly["correct_answers"], 2)
        self.assertAlmostEqual(weekly["accuracy"], 2 / 3)
        self.assertEqual(weekly["active_days"], 3)
        self.assertEqual(
            daily[(today - timedelta(days=5)).isoformat()]["activities_completed"],
            1,
        )
        self.assertEqual(
            daily[(today - timedelta(days=1)).isoformat()]["correct_answers"],
            0,
        )
        self.assertEqual(
            daily[today.isoformat()]["total_attempts"],
            1,
        )
        completion = dashboard["activity_completion"]
        self.assertEqual(completion["total_activities"], 4)
        self.assertEqual(completion["completed_activities"], 2)
        self.assertEqual(completion["in_progress_activities"], 1)
        self.assertEqual(completion["abandoned_activities"], 1)
        self.assertEqual(completion["completion_rate"], 0.5)
        addition = next(
            item for item in completion["by_operation"]
            if item["operation_type"] == "addition"
        )
        self.assertEqual(addition["total_activities"], 4)
        self.assertEqual(addition["completed_activities"], 2)

    def test_dashboard_reports_strengths_and_evidence_based_achievements(self):
        attempts = [self._record_math_answer(correct=True) for _ in range(8)]
        activity = db.session.get(ActivityAttempt, attempts[0].activity_attempt_id)
        StudentLearningDataService.complete_activity(activity)

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        self.assertEqual(len(dashboard["strengths"]), 1)
        self.assertEqual(dashboard["strengths"][0]["operation_type"], "addition")
        self.assertEqual(dashboard["strengths"][0]["accuracy"], 1.0)
        achievements = {item["id"]: item for item in dashboard["achievements"]}
        self.assertTrue(achievements["first_completed_activity"]["earned"])
        self.assertTrue(achievements["operation_strength"]["earned"])
        self.assertFalse(achievements["weekly_practice"]["earned"])
        self.assertFalse(achievements["mastery_step"]["earned"])

    def test_valid_answer_evidence_promotes_difficulty_and_drives_adaptive_start(self):
        for _ in range(8):
            self._record_math_answer()

        progress = db.session.scalar(
            select(StudentLearningProgress).where(
                StudentLearningProgress.student_id == self.student.id,
                StudentLearningProgress.operation_type == "addition",
            )
        )
        self.assertEqual(progress.current_difficulty, "standard")
        self.assertEqual(progress.total_attempts, 8)
        self.assertEqual(progress.correct_answers, 8)
        adjustment = db.session.scalar(
            select(DifficultyAdjustmentHistory).where(
                DifficultyAdjustmentHistory.student_id == self.student.id,
                DifficultyAdjustmentHistory.operation_type == "addition",
            )
        )
        self.assertIsNotNone(adjustment)
        self.assertEqual(adjustment.previous_difficulty, "easy")
        self.assertEqual(adjustment.new_difficulty, "standard")
        self.assertEqual(adjustment.recent_accuracy, 1.0)
        self.assertEqual(adjustment.historical_accuracy, 1.0)
        self.assertIn("consecutive correct", adjustment.reason)
        self.assertIn("at easy difficulty", adjustment.reason)

        self._record_math_answer(difficulty="easy")
        self.assertEqual(progress.current_difficulty, "standard")

        session_identifier = str(uuid4())
        self.client.post(
            "/api/learning-sessions/start",
            json={"session_identifier": session_identifier},
            headers={"X-CSRF-Token": self.csrf},
        )
        response = self.client.post(
            "/api/student-activities/start",
            json={
                "operation_type": "addition",
                "difficulty_level": "adaptive",
                "session_identifier": session_identifier,
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["activity"]["difficulty_level"], "standard")

        self._record_math_answer(correct=False, difficulty="standard")
        self.assertEqual(progress.current_difficulty, "standard")
        for _ in range(6):
            self._record_math_answer(correct=False, difficulty="standard")
        self.assertEqual(progress.current_difficulty, "standard")
        self._record_math_answer(correct=False, difficulty="standard")
        self.assertEqual(progress.current_difficulty, "easy")
        adjustments = db.session.scalars(
            select(DifficultyAdjustmentHistory).where(
                DifficultyAdjustmentHistory.student_id == self.student.id,
                DifficultyAdjustmentHistory.operation_type == "addition",
            )
        ).all()
        self.assertEqual(len(adjustments), 2)
        self.assertEqual(adjustments[1].recent_accuracy, 0.0)
        self.assertEqual(adjustments[1].historical_accuracy, 0.0)
        self.assertIn("at standard difficulty", adjustments[1].reason)

    def test_existing_answer_history_is_used_for_first_adaptive_start(self):
        for _ in range(8):
            self._record_math_answer(refresh_progress=False)
        self.assertEqual(
            db.session.scalars(
                select(StudentLearningProgress).where(
                    StudentLearningProgress.student_id == self.student.id
                )
            ).all(),
            [],
        )
        session_identifier = str(uuid4())
        self.client.post(
            "/api/learning-sessions/start",
            json={"session_identifier": session_identifier},
            headers={"X-CSRF-Token": self.csrf},
        )
        response = self.client.post(
            "/api/student-activities/start",
            json={
                "operation_type": "addition",
                "difficulty_level": "adaptive",
                "session_identifier": session_identifier,
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["activity"]["difficulty_level"], "standard")

    def test_persistent_recommendation_identifies_a_weak_math_operation(self):
        for _ in range(8):
            self._record_math_answer(correct=False)

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        self.assertIn("addition", dashboard["weak_areas"])
        recommendation = next(
            item for item in dashboard["recommendations"]
            if item["operation_type"] == "addition"
        )
        self.assertEqual(recommendation["kind"], "practice_weak_area")
        self.assertEqual(recommendation["status"], "pending")
        self.assertEqual(
            recommendation["activity"]["catalogue_id"],
            "addition-generated-practice",
        )
        self.assertEqual(
            recommendation["activity"]["activity_type"],
            "generated_arithmetic_practice",
        )
        self.assertEqual(recommendation["activity"]["route"], "/activities?tab=addition")

    def test_weak_area_detection_includes_recent_accuracy_decline(self):
        for _ in range(10):
            self._record_math_answer(correct=True)
        for attempt_index in range(10):
            self._record_math_answer(correct=attempt_index < 8)

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        addition = next(
            item for item in dashboard["operations"]
            if item["operation_type"] == "addition"
        )
        self.assertAlmostEqual(addition["accuracy"], 0.9)
        self.assertAlmostEqual(addition["recent_accuracy"], 0.8)
        self.assertAlmostEqual(addition["improvement_rate"], -0.2)
        self.assertEqual(
            dashboard["weak_area_signals"]["addition"],
            ["declining_trend"],
        )

    def test_weak_area_detection_includes_hint_use_skips_and_error_streaks(self):
        for _ in range(8):
            self._record_math_answer(hint_used=True)
        for _ in range(8):
            self._record_math_answer(skipped=True)

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        self.assertEqual(
            dashboard["weak_area_signals"]["addition"],
            ["frequent_skips", "hint_dependence"],
        )
        recommendation = next(
            item for item in dashboard["recommendations"]
            if item["operation_type"] == "addition"
        )
        self.assertEqual(recommendation["kind"], "practice_weak_area")

        for _ in range(8):
            self._record_math_answer(correct=True)
        for _ in range(3):
            self._record_math_answer(correct=False)

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        self.assertIn("repeated_errors", dashboard["weak_area_signals"]["addition"])

    def test_learning_path_reprioritizes_locked_steps_as_weak_areas_change(self):
        initial = self.client.get("/api/personalized-learning/dashboard").get_json()
        initial_path = initial["learning_path"]
        self.assertEqual(initial_path["progress_percentage"], 0)
        self.assertEqual(initial_path["completed_steps"], 0)
        self.assertEqual(initial_path["total_steps"], 17)

        for _ in range(8):
            self._record_math_answer(operation="division", correct=False)

        updated = self.client.get("/api/personalized-learning/dashboard").get_json()
        steps = updated["learning_path"]["steps"]
        self.assertEqual(steps[0]["operation_type"], "number_identification")
        self.assertEqual(steps[0]["status"], "in_progress")
        self.assertEqual(steps[1]["operation_type"], "division")
        self.assertEqual(steps[1]["reason"], "weak_area")

    def test_completed_path_resumes_when_student_starts_another_activity(self):
        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        path = db.session.scalar(
            select(StudentLearningPath).where(
                StudentLearningPath.student_id == self.student.id
            )
        )
        steps = db.session.scalars(
            select(LearningPathStep).where(LearningPathStep.path_id == path.id)
        ).all()
        for step in steps:
            step.status = "completed"
        path.status = "completed"
        db.session.commit()
        self.assertEqual(dashboard["learning_path"]["status"], "active")

        session_identifier = str(uuid4())
        self.client.post(
            "/api/learning-sessions/start",
            json={"session_identifier": session_identifier},
            headers={"X-CSRF-Token": self.csrf},
        )
        response = self.client.post(
            "/api/student-activities/start",
            json={
                "operation_type": "division",
                "difficulty_level": "adaptive",
                "session_identifier": session_identifier,
                "request_key": str(uuid4()),
            },
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 201)
        division_step = next(step for step in steps if step.operation_type == "division")
        db.session.refresh(path)
        db.session.refresh(division_step)
        self.assertEqual(path.status, "active")
        self.assertEqual(division_step.status, "in_progress")
        self.assertIsNone(division_step.completed_at)

    def test_teacher_can_only_read_assigned_students(self):
        assigned_teacher = User(username="assigned-teacher", role="teacher")
        assigned_teacher.set_password("a-teacher-password")
        other_teacher = User(username="other-teacher", role="teacher")
        other_teacher.set_password("another-teacher-password")
        assigned_teacher.students.append(self.student)
        db.session.add_all([assigned_teacher, other_teacher])
        db.session.commit()

        assigned_client = self.app.test_client()
        assigned_csrf = assigned_client.get("/api/auth/me").get_json()["csrf_token"]
        login = assigned_client.post(
            "/api/auth/login",
            json={"username": "assigned-teacher", "password": "a-teacher-password"},
            headers={"X-CSRF-Token": assigned_csrf},
        )
        assigned_csrf = login.get_json()["csrf_token"]
        allowed = assigned_client.get(
            f"/api/personalized-learning/dashboard?student_id={self.student.id}"
        )
        self.assertEqual(allowed.status_code, 200)
        roster = assigned_client.get("/api/personalized-learning/students")
        self.assertEqual([item["id"] for item in roster.get_json()["items"]], [self.student.id])

        other_client = self.app.test_client()
        other_csrf = other_client.get("/api/auth/me").get_json()["csrf_token"]
        other_client.post(
            "/api/auth/login",
            json={"username": "other-teacher", "password": "another-teacher-password"},
            headers={"X-CSRF-Token": other_csrf},
        )
        denied = other_client.get(
            f"/api/personalized-learning/dashboard?student_id={self.student.id}"
        )
        self.assertEqual(denied.status_code, 403)
        self.assertNotEqual(assigned_csrf, "")
