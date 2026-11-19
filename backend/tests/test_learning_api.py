import os
import unittest
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app import create_app
from extensions import db
from itsdangerous import URLSafeTimedSerializer
from models import (
    ActivityAttempt,
    LearningQuestion,
    LearningPathStep,
    LearningSession,
    NumberIdentificationQuestion,
    QuestionAttempt,
    RecognitionLog,
    StudentLearningProgress,
    User,
)
from sqlalchemy.engine import make_url


def test_database_uri() -> str:
    database_uri = os.environ.get("TEST_DATABASE_URL")
    if not database_uri:
        return "sqlite://"
    database_name = make_url(database_uri).database
    if not database_name or not database_name.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must target a database whose name ends with '_test'.")
    return database_uri


class LearningApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": test_database_uri(),
            "SESSION_COOKIE_SECURE": False,
        })
        self.context = self.app.app_context()
        self.context.push()
        if db.engine.dialect.name == "sqlite":
            with db.engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        db.create_all()
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/auth/me").get_json()["csrf_token"]
        registration = self.client.post(
            "/api/auth/register",
            json={"username": "student-one", "password": "a-strong-password", "grade": 5},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(registration.status_code, 201)
        self.csrf = registration.get_json()["csrf_token"]

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def post(self, path, body):
        return self.client.post(path, json=body, headers={"X-CSRF-Token": self.csrf})

    def recognition_token(self, predicted_value, confidence, model_key="0-9"):
        user = User.query.filter_by(username="student-one").one()
        return URLSafeTimedSerializer(self.app.config["SECRET_KEY"], salt="slsl-recognition").dumps({
            "user_id": user.id,
            "predicted_number": predicted_value,
            "confidence": confidence,
            "model_key": model_key,
            "token_id": uuid4().hex,
        })

    def create_question(self, operation="addition", difficulty_level="standard"):
        session_id = str(uuid4())
        learning_session = self.post(
            "/api/learning-sessions/start",
            {"session_identifier": session_id},
        ).get_json()["session"]
        activity = self.post(
            "/api/student-activities/start",
            {
                "operation_type": operation,
                "difficulty_level": difficulty_level,
                "session_identifier": session_id,
                "request_key": str(uuid4()),
            },
        ).get_json()["activity"]
        question_response = self.post(
            f'/api/student-activities/{activity["id"]}/questions',
            {},
        )
        self.assertIn(question_response.status_code, (200, 201))
        question = question_response.get_json()
        self.post(f'/api/learning-questions/{question["id"]}/displayed', {})
        return activity, question, learning_session

    def create_number_question(self):
        session_identifier = str(uuid4())
        learning_session = self.post(
            "/api/learning-sessions/start",
            {"session_identifier": session_identifier},
        ).get_json()["session"]
        activity = self.post(
            "/api/student-activities/start",
            {
                "operation_type": "number_identification",
                "session_identifier": session_identifier,
                "request_key": str(uuid4()),
            },
        ).get_json()["activity"]
        question_response = self.post(
            f'/api/student-activities/{activity["id"]}/number-questions',
            {},
        )
        self.assertEqual(question_response.status_code, 201)
        return activity, question_response.get_json(), learning_session

    def test_difficulty_level_is_persisted_and_controls_question_generation(self):
        session_identifier = str(uuid4())
        self.post(
            "/api/learning-sessions/start",
            {"session_identifier": session_identifier},
        )
        request_key = str(uuid4())
        activity_response = self.post(
            "/api/student-activities/start",
            {
                "operation_type": "addition",
                "difficulty_level": "hard",
                "session_identifier": session_identifier,
                "request_key": request_key,
            },
        )
        self.assertEqual(activity_response.status_code, 201)
        activity = activity_response.get_json()["activity"]
        self.assertEqual(activity["difficulty_level"], "hard")

        conflicting_retry = self.post(
            "/api/student-activities/start",
            {
                "operation_type": "addition",
                "difficulty_level": "easy",
                "session_identifier": session_identifier,
                "request_key": request_key,
            },
        )
        self.assertEqual(conflicting_retry.status_code, 409)

        question_response = self.post(
            f'/api/student-activities/{activity["id"]}/questions',
            {},
        )
        question = question_response.get_json()
        self.assertEqual(question_response.status_code, 200)
        self.assertEqual(question["difficulty_level"], "hard")
        self.assertGreaterEqual(question["left"], 10)
        self.assertGreaterEqual(question["right"], 10)
        self.assertLessEqual(question["left"], 25)
        self.assertLessEqual(question["right"], 25)
        self.assertLessEqual(question["left"] + question["right"], 50)

    def test_invalid_difficulty_level_is_rejected(self):
        session_identifier = str(uuid4())
        self.post(
            "/api/learning-sessions/start",
            {"session_identifier": session_identifier},
        )
        response = self.post(
            "/api/student-activities/start",
            {
                "operation_type": "addition",
                "difficulty_level": "impossible",
                "session_identifier": session_identifier,
                "request_key": str(uuid4()),
            },
        )
        self.assertEqual(response.status_code, 400)

        default_response = self.post(
            "/api/student-activities/start",
            {
                "operation_type": "addition",
                "session_identifier": session_identifier,
                "request_key": str(uuid4()),
            },
        )
        self.assertEqual(default_response.status_code, 201)
        self.assertEqual(default_response.get_json()["activity"]["difficulty_level"], "standard")

    def test_tracking_records_server_calculated_result_and_is_idempotent(self):
        activity, question, _ = self.create_question("subtraction")
        with self.app.app_context():
            saved_question = db.session.get(LearningQuestion, question["id"])
            expected = saved_question.expected_answer
        confidence = 0.9
        self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "question_id": question["id"],
                "predicted_value": expected,
                "confidence": confidence,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(expected, confidence),
                "gesture_detected": True,
            },
        )
        payload = {
            "idempotency_key": str(uuid4()),
            "submitted_answer": expected,
            "response_time_ms": 2400,
            "hint_used": False,
        }
        first = self.post(f'/api/student-question-attempts/{question["id"]}', payload)
        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.get_json()["attempt"]["is_correct"])
        self.assertEqual(first.get_json()["attempt"]["gesture_attempt_count"], 1)
        recognition = RecognitionLog.query.filter_by(
            question_attempt_id=first.get_json()["attempt"]["id"]
        ).one()
        self.assertEqual(recognition.model_key, "0-9")

        duplicate = self.post(f'/api/student-question-attempts/{question["id"]}', payload)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.get_json()["duplicate"])
        self.assertEqual(
            db.session.query(QuestionAttempt).count(),
            1,
        )
        history = self.client.get("/api/student-question-attempts").get_json()
        self.assertEqual(
            history["summary"],
            {"total_attempts": 1, "correct": 1, "points": 1},
        )
        saved_activity = db.session.get(ActivityAttempt, activity["id"])
        self.assertEqual(saved_activity.total_questions, 1)
        self.assertEqual(saved_activity.total_attempts, 1)
        self.assertEqual(saved_activity.correct_answers, 1)

    def test_low_confidence_is_logged_separately_and_cannot_be_submitted_by_ui_path(self):
        activity, question, _ = self.create_question()
        response = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "question_id": question["id"],
                "predicted_value": 6,
                "confidence": 0.2,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(6, 0.2),
                "gesture_detected": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["status"], "low_confidence")
        blocked = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": 6,
                "response_time_ms": 1500,
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(db.session.query(QuestionAttempt).count(), 0)

    def test_number_identification_scores_only_confident_signs_against_server_prompt(self):
        activity, question, learning_session = self.create_number_question()
        repeated_prompt = self.post(
            f'/api/student-activities/{activity["id"]}/number-questions',
            {},
        )
        self.assertEqual(repeated_prompt.status_code, 200)
        self.assertEqual(repeated_prompt.get_json()["id"], question["id"])
        target = question["target_value"]

        incorrect_value = (target + 1) % 51
        incorrect = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "number_question_id": question["id"],
                "predicted_value": incorrect_value,
                "confidence": 0.9,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(incorrect_value, 0.9),
                "gesture_detected": True,
            },
        )
        self.assertEqual(incorrect.status_code, 201)
        self.assertFalse(incorrect.get_json()["is_correct"])
        self.assertEqual(incorrect.get_json()["target_value"], target)
        self.assertEqual(incorrect.get_json()["number_question_status"], "in_progress")

        correct_payload = {
            "activity_attempt_id": activity["id"],
            "number_question_id": question["id"],
            "predicted_value": target,
            "confidence": 0.9,
            "model_key": "0-9",
            "recognition_token": self.recognition_token(target, 0.9),
            "gesture_detected": True,
        }
        correct = self.post("/api/student-recognition-logs", correct_payload)
        self.assertEqual(correct.status_code, 201)
        self.assertTrue(correct.get_json()["is_correct"])
        self.assertEqual(correct.get_json()["number_question_status"], "completed")

        duplicate = self.post("/api/student-recognition-logs", correct_payload)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.get_json()["duplicate"])

        progress = StudentLearningProgress.query.filter_by(
            student_id=User.query.filter_by(username="student-one").one().id,
            operation_type="number_identification",
        ).one()
        self.assertEqual(progress.total_attempts, 2)
        self.assertEqual(progress.correct_answers, 1)
        self.assertEqual(progress.incorrect_answers, 1)
        self.assertEqual(progress.accuracy, 0.5)

        saved_activity = db.session.get(ActivityAttempt, activity["id"])
        self.assertEqual(saved_activity.total_questions, 1)
        self.assertEqual(saved_activity.total_attempts, 2)
        self.assertEqual(saved_activity.correct_answers, 1)
        self.assertEqual(saved_activity.incorrect_answers, 1)
        self.assertEqual(saved_activity.completed_questions, 1)
        self.assertEqual(
            RecognitionLog.query.filter_by(
                number_question_id=question["id"]
            ).count(),
            2,
        )

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        number_progress = next(
            item for item in dashboard["operations"]
            if item["operation_type"] == "number_identification"
        )
        self.assertEqual(number_progress["total_attempts"], 2)
        self.assertEqual(number_progress["accuracy"], 0.5)

        completion = self.post(
            f'/api/student-activities/{activity["id"]}/complete',
            {},
        )
        self.assertEqual(completion.status_code, 200)
        path = self.client.get("/api/personalized-learning/dashboard").get_json()["learning_path"]
        self.assertEqual(path["steps"][0]["status"], "in_progress")
        self.assertEqual(path["steps"][0]["reason"], "evidence_needed")

        session_summary = self.post(
            f'/api/learning-sessions/{learning_session["identifier"]}/end',
            {},
        ).get_json()["session"]
        self.assertEqual(session_summary["total_attempts"], 2)
        self.assertEqual(session_summary["correct_answers"], 1)
        self.assertEqual(session_summary["incorrect_answers"], 1)

    def test_number_identification_path_unlocks_only_after_mastery_evidence(self):
        activity, question, _ = self.create_number_question()
        for attempt_index in range(8):
            target = question["target_value"]
            answer = self.post(
                "/api/student-recognition-logs",
                {
                    "activity_attempt_id": activity["id"],
                    "number_question_id": question["id"],
                    "predicted_value": target,
                    "confidence": 0.9,
                    "model_key": "0-9",
                    "recognition_token": self.recognition_token(target, 0.9),
                    "gesture_detected": True,
                },
            )
            self.assertEqual(answer.status_code, 201)
            self.assertTrue(answer.get_json()["is_correct"])
            if attempt_index < 7:
                question_response = self.post(
                    f'/api/student-activities/{activity["id"]}/number-questions',
                    {},
                )
                self.assertEqual(question_response.status_code, 201)
                question = question_response.get_json()

        completion = self.post(
            f'/api/student-activities/{activity["id"]}/complete',
            {},
        )
        self.assertEqual(completion.status_code, 200)
        path = self.client.get("/api/personalized-learning/dashboard").get_json()["learning_path"]
        self.assertEqual(path["steps"][0]["operation_type"], "number_identification")
        self.assertEqual(path["steps"][0]["skill_key"], "number_identification_0_9")
        self.assertEqual(path["steps"][0]["status"], "completed")
        self.assertEqual(path["steps"][1]["skill_key"], "number_identification_10_19")
        self.assertEqual(path["steps"][1]["status"], "in_progress")
        next_activity, next_question, _ = self.create_number_question()
        self.assertGreaterEqual(next_question["target_value"], 10)
        self.assertLessEqual(next_question["target_value"], 19)
        target = next_question["target_value"]
        response = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": next_activity["id"],
                "number_question_id": next_question["id"],
                "predicted_value": target,
                "confidence": 0.9,
                "model_key": "10-19",
                "recognition_token": self.recognition_token(target, 0.9, "10-19"),
                "gesture_detected": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.post(f'/api/student-activities/{next_activity["id"]}/complete', {})
        updated_path = self.client.get(
            "/api/personalized-learning/dashboard"
        ).get_json()["learning_path"]
        self.assertEqual(updated_path["steps"][1]["status"], "in_progress")
        self.assertEqual(updated_path["steps"][1]["reason"], "evidence_needed")

    def test_math_path_unlocks_only_after_mastery_evidence(self):
        activity, question, _ = self.create_question("addition", difficulty_level="easy")
        for attempt_index in range(8):
            with self.app.app_context():
                saved_question = db.session.get(LearningQuestion, question["id"])
                expected_answer = saved_question.expected_answer
            recognition = self.post(
                "/api/student-recognition-logs",
                {
                    "activity_attempt_id": activity["id"],
                    "question_id": question["id"],
                    "predicted_value": expected_answer,
                    "confidence": 0.9,
                    "model_key": "0-9",
                    "recognition_token": self.recognition_token(expected_answer, 0.9),
                    "gesture_detected": True,
                },
            )
            self.assertEqual(recognition.status_code, 201)
            answer = self.post(
                f'/api/student-question-attempts/{question["id"]}',
                {
                    "idempotency_key": str(uuid4()),
                    "submitted_answer": expected_answer,
                    "response_time_ms": 1500,
                    "hint_used": False,
                },
            )
            self.assertEqual(answer.status_code, 201)
            self.assertTrue(answer.get_json()["attempt"]["is_correct"])
            if attempt_index < 7:
                question_response = self.post(
                    f'/api/student-activities/{activity["id"]}/questions',
                    {},
                )
                self.assertIn(question_response.status_code, (200, 201))
                question = question_response.get_json()
                displayed = self.post(
                    f'/api/learning-questions/{question["id"]}/displayed',
                    {},
                )
                self.assertEqual(displayed.status_code, 200)

        completion = self.post(
            f'/api/student-activities/{activity["id"]}/complete',
            {},
        )
        self.assertEqual(completion.status_code, 200)
        path = self.client.get("/api/personalized-learning/dashboard").get_json()["learning_path"]
        self.assertEqual(path["steps"][0]["operation_type"], "addition")
        self.assertEqual(path["steps"][0]["skill_key"], "addition_easy")
        self.assertEqual(path["steps"][0]["status"], "completed")
        addition_standard = next(
            step for step in path["steps"]
            if step["skill_key"] == "addition_standard"
        )
        self.assertEqual(addition_standard["status"], "locked")

        with self.app.app_context():
            saved_steps = LearningPathStep.query.all()
            standard_step = next(
                step for step in saved_steps
                if step.skill_key == "addition_standard"
            )
            for step in saved_steps:
                step.status = "completed"
            standard_step.status = "in_progress"
            standard_step.reason = "evidence_needed"
            db.session.commit()

        off_stage_activity, off_stage_question, _ = self.create_question(
            "addition",
            difficulty_level="easy",
        )
        with self.app.app_context():
            saved_question = db.session.get(LearningQuestion, off_stage_question["id"])
            expected_answer = saved_question.expected_answer
        off_stage_recognition = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": off_stage_activity["id"],
                "question_id": off_stage_question["id"],
                "predicted_value": expected_answer,
                "confidence": 0.9,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(expected_answer, 0.9),
                "gesture_detected": True,
            },
        )
        self.assertEqual(off_stage_recognition.status_code, 201)
        off_stage_answer = self.post(
            f'/api/student-question-attempts/{off_stage_question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": expected_answer,
                "response_time_ms": 1500,
                "hint_used": False,
            },
        )
        self.assertEqual(off_stage_answer.status_code, 201)
        self.post(
            f'/api/student-activities/{off_stage_activity["id"]}/complete',
            {},
        )
        updated_path = self.client.get(
            "/api/personalized-learning/dashboard"
        ).get_json()["learning_path"]
        standard_step = next(
            step for step in updated_path["steps"]
            if step["skill_key"] == "addition_standard"
        )
        self.assertEqual(standard_step["status"], "in_progress")
        self.assertEqual(standard_step["reason"], "evidence_needed")

        standard_activity, standard_question, _ = self.create_question(
            "addition",
            difficulty_level="standard",
        )
        with self.app.app_context():
            saved_question = db.session.get(LearningQuestion, standard_question["id"])
            expected_answer = saved_question.expected_answer
        standard_recognition = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": standard_activity["id"],
                "question_id": standard_question["id"],
                "predicted_value": expected_answer,
                "confidence": 0.9,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(expected_answer, 0.9),
                "gesture_detected": True,
            },
        )
        self.assertEqual(standard_recognition.status_code, 201)
        self.post(
            f'/api/student-question-attempts/{standard_question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": expected_answer,
                "response_time_ms": 1500,
                "hint_used": False,
            },
        )
        self.post(
            f'/api/student-activities/{standard_activity["id"]}/complete',
            {},
        )
        verified_path = self.client.get(
            "/api/personalized-learning/dashboard"
        ).get_json()["learning_path"]
        standard_step = next(
            step for step in verified_path["steps"]
            if step["skill_key"] == "addition_standard"
        )
        self.assertEqual(standard_step["status"], "in_progress")
        self.assertEqual(standard_step["reason"], "evidence_needed")

    def test_low_confidence_number_sign_does_not_change_answer_accuracy(self):
        activity, question, _ = self.create_number_question()
        target = question["target_value"]
        response = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "number_question_id": question["id"],
                "predicted_value": target,
                "confidence": 0.2,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(target, 0.2),
                "gesture_detected": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["status"], "low_confidence")
        self.assertIsNone(response.get_json()["is_correct"])
        self.assertEqual(
            response.get_json()["number_question_status"],
            "in_progress",
        )
        progress = StudentLearningProgress.query.filter_by(
            student_id=User.query.filter_by(username="student-one").one().id,
            operation_type="number_identification",
        ).one()
        self.assertEqual(progress.total_attempts, 0)
        self.assertIsNone(progress.accuracy)
        completion = self.post(
            f'/api/student-activities/{activity["id"]}/complete',
            {},
        )
        self.assertEqual(completion.status_code, 200)
        path = self.client.get("/api/personalized-learning/dashboard").get_json()["learning_path"]
        self.assertEqual(path["steps"][0]["status"], "in_progress")

    def test_number_identification_accuracy_can_trigger_targeted_practice(self):
        activity, question, _ = self.create_number_question()
        target = question["target_value"]
        incorrect_value = (target + 1) % 51
        for _ in range(8):
            response = self.post(
                "/api/student-recognition-logs",
                {
                    "activity_attempt_id": activity["id"],
                    "number_question_id": question["id"],
                    "predicted_value": incorrect_value,
                    "confidence": 0.9,
                    "model_key": "0-9",
                    "recognition_token": self.recognition_token(incorrect_value, 0.9),
                    "gesture_detected": True,
                },
            )
            self.assertEqual(response.status_code, 201)
            self.assertFalse(response.get_json()["is_correct"])

        dashboard = self.client.get("/api/personalized-learning/dashboard").get_json()
        self.assertIn("number_identification", dashboard["weak_areas"])
        recommendation = next(
            item for item in dashboard["recommendations"]
            if item["operation_type"] == "number_identification"
        )
        self.assertEqual(recommendation["kind"], "practice_weak_area")
        completion = self.post(
            f'/api/student-activities/{activity["id"]}/complete',
            {},
        )
        self.assertEqual(completion.status_code, 200)
        path = self.client.get("/api/personalized-learning/dashboard").get_json()["learning_path"]
        self.assertEqual(path["steps"][0]["status"], "in_progress")
        self.assertEqual(path["steps"][0]["reason"], "mastery_needed")

    def test_student_cannot_read_another_students_question(self):
        _, question, _ = self.create_question()
        other_client = self.app.test_client()
        other_csrf = other_client.get("/api/auth/me").get_json()["csrf_token"]
        registration = other_client.post(
            "/api/auth/register",
            json={"username": "student-two", "password": "another-strong-password"},
            headers={"X-CSRF-Token": other_csrf},
        )
        self.assertEqual(registration.status_code, 201)
        response = other_client.post(
            f'/api/learning-questions/{question["id"]}/displayed',
            json={},
            headers={"X-CSRF-Token": registration.get_json()["csrf_token"]},
        )
        self.assertEqual(response.status_code, 404)

    def test_negative_response_time_is_rejected(self):
        _, question, _ = self.create_question()
        response = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {"idempotency_key": str(uuid4()), "submitted_answer": 1, "response_time_ms": -1},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.session.query(QuestionAttempt).count(), 0)

    def test_non_object_json_payload_returns_client_error(self):
        response = self.post("/api/learning-sessions/start", [])
        self.assertEqual(response.status_code, 400)

    def test_confident_incorrect_answer_is_recorded_as_incorrect(self):
        activity, question, learning_session = self.create_question()
        saved_question = db.session.get(LearningQuestion, question["id"])
        expected = saved_question.expected_answer
        predicted = (expected + 1) % 51
        confidence = 0.9
        recognition = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "question_id": question["id"],
                "predicted_value": predicted,
                "confidence": confidence,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(predicted, confidence),
                "gesture_detected": True,
            },
        )
        self.assertEqual(recognition.status_code, 201)
        incorrect_key = str(uuid4())
        response = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": incorrect_key,
                "submitted_answer": predicted,
                "response_time_ms": 1500,
            },
        )
        self.assertEqual(response.status_code, 201)
        incorrect_attempt = response.get_json()["attempt"]
        self.assertFalse(incorrect_attempt["is_correct"])
        self.assertEqual(incorrect_attempt["status"], "incorrect")
        self.assertEqual(incorrect_attempt["attempt_number"], 1)
        saved_activity = db.session.get(ActivityAttempt, activity["id"])
        self.assertEqual(saved_activity.total_questions, 1)
        self.assertEqual(saved_activity.total_attempts, 1)
        self.assertEqual(saved_activity.completed_questions, 0)
        self.assertEqual(saved_activity.incorrect_answers, 1)

        duplicate = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": incorrect_key,
                "submitted_answer": predicted,
                "response_time_ms": 1500,
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.get_json()["duplicate"])

        active_question = self.post(
            f'/api/student-activities/{activity["id"]}/questions',
            {},
        ).get_json()
        self.assertEqual(active_question["id"], question["id"])
        second_wrong_recognition = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "question_id": question["id"],
                "predicted_value": predicted,
                "confidence": confidence,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(predicted, confidence),
                "gesture_detected": True,
            },
        )
        self.assertEqual(second_wrong_recognition.status_code, 201)
        second_wrong_response = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": predicted,
                "response_time_ms": 1500,
            },
        )
        self.assertEqual(second_wrong_response.status_code, 201, second_wrong_response.get_json())
        self.assertEqual(second_wrong_response.get_json()["attempt"]["attempt_number"], 2)

        correct_recognition = self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "question_id": question["id"],
                "predicted_value": expected,
                "confidence": confidence,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(expected, confidence),
                "gesture_detected": True,
            },
        )
        self.assertEqual(correct_recognition.status_code, 201)
        correct_response = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": expected,
                "response_time_ms": 1500,
            },
        )
        self.assertEqual(correct_response.status_code, 201)
        correct_attempt = correct_response.get_json()["attempt"]
        self.assertTrue(correct_attempt["is_correct"])
        self.assertEqual(correct_attempt["attempt_number"], 3)
        duplicate_completion = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": expected,
                "response_time_ms": 1500,
            },
        )
        self.assertEqual(duplicate_completion.status_code, 409)

        saved_activity = db.session.get(ActivityAttempt, activity["id"])
        self.assertEqual(saved_activity.total_questions, 1)
        self.assertEqual(saved_activity.total_attempts, 3)
        self.assertEqual(saved_activity.completed_questions, 1)
        self.assertEqual(saved_activity.correct_answers, 1)
        self.assertEqual(saved_activity.incorrect_answers, 2)
        session_response = self.post(
            f'/api/learning-sessions/{learning_session["identifier"]}/end',
            {},
        )
        self.assertEqual(session_response.status_code, 200)
        summary = session_response.get_json()["session"]
        self.assertEqual(summary["total_questions"], 1)
        self.assertEqual(summary["completed_questions"], 1)
        self.assertEqual(summary["total_attempts"], 3)
        self.assertEqual(summary["correct_answers"], 1)
        self.assertEqual(summary["incorrect_answers"], 2)
        self.assertEqual(summary["accuracy_percent"], 33.33)
        filtered_history = self.client.get(
            f'/api/student-question-attempts?session_id={learning_session["id"]}'
        ).get_json()
        self.assertEqual(filtered_history["total"], 3)

    def test_total_attempts_excludes_invalid_and_skipped_records_consistently(self):
        activity, question, learning_session = self.create_question()
        invalid = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": "not-an-integer",
                "response_time_ms": 0,
            },
        )
        self.assertEqual(invalid.status_code, 422)
        skipped = self.post(
            f'/api/student-question-attempts/{question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "skipped": True,
                "response_time_ms": 0,
            },
        )
        self.assertEqual(skipped.status_code, 201)

        next_question = self.post(
            f'/api/student-activities/{activity["id"]}/questions',
            {},
        ).get_json()
        self.post(f'/api/learning-questions/{next_question["id"]}/displayed', {})
        expected = db.session.get(LearningQuestion, next_question["id"]).expected_answer
        confidence = 0.9
        self.post(
            "/api/student-recognition-logs",
            {
                "activity_attempt_id": activity["id"],
                "question_id": next_question["id"],
                "predicted_value": expected,
                "confidence": confidence,
                "model_key": "0-9",
                "recognition_token": self.recognition_token(expected, confidence),
                "gesture_detected": True,
            },
        )
        valid = self.post(
            f'/api/student-question-attempts/{next_question["id"]}',
            {
                "idempotency_key": str(uuid4()),
                "submitted_answer": expected,
                "response_time_ms": 0,
            },
        )
        self.assertEqual(valid.status_code, 201)

        activity_total = db.session.get(ActivityAttempt, activity["id"]).total_attempts
        self.assertEqual(activity_total, 1)
        session_response = self.post(
            f'/api/learning-sessions/{learning_session["identifier"]}/end',
            {},
        )
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(
            session_response.get_json()["session"]["total_attempts"],
            activity_total,
        )
        history = self.client.get(
            f'/api/student-question-attempts?session_id={learning_session["id"]}'
        ).get_json()
        self.assertEqual(history["total"], 3)
        self.assertEqual(history["summary"]["total_attempts"], activity_total)

    def test_database_rejects_invalid_values_and_inconsistent_learning_summaries(self):
        activity, question, learning_session = self.create_question()
        user = User.query.filter_by(username="student-one").one()

        user.role = "administrator"
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        saved_activity = db.session.get(ActivityAttempt, activity["id"])
        saved_activity.total_attempts = 1
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        saved_question = db.session.get(LearningQuestion, question["id"])
        saved_question.left_operand += 1
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        invalid_attempt = QuestionAttempt(
            idempotency_key=str(uuid4()),
            student_id=user.id,
            session_id=learning_session["id"],
            activity_attempt_id=activity["id"],
            question_id=question["id"],
            expected_answer=saved_question.expected_answer,
            submitted_answer=saved_question.expected_answer,
            is_correct=False,
            attempt_number=1,
            status="completed",
        )
        db.session.add(invalid_attempt)
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        invalid_recognition = RecognitionLog(
            activity_attempt_id=activity["id"],
            learning_question_id=question["id"],
            predicted_value=1,
            confidence=1.1,
            status="recognized",
            gesture_detected=True,
            recognition_attempt_number=1,
        )
        db.session.add(invalid_recognition)
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

    def test_learning_session_can_be_abandoned_with_summary(self):
        activity, _, learning_session = self.create_question()
        response = self.post(
            f'/api/learning-sessions/{learning_session["identifier"]}/abandon',
            {},
        )
        self.assertEqual(response.status_code, 200)
        summary = response.get_json()["session"]
        self.assertEqual(summary["status"], "abandoned")
        self.assertEqual(summary["total_questions"], 1)
        self.assertEqual(summary["completed_questions"], 0)
        self.assertEqual(summary["total_attempts"], 0)
        self.assertEqual(db.session.get(ActivityAttempt, activity["id"]).status, "abandoned")

    def test_teacher_can_only_view_assigned_student_history(self):
        assigned_student = User(username="assigned-student", role="student")
        assigned_student.set_password("a-strong-password")
        unassigned_student = User(username="unassigned-student", role="student")
        unassigned_student.set_password("a-strong-password")
        teacher = User(username="teacher-one", role="teacher")
        teacher.set_password("a-strong-password")
        teacher.students.append(assigned_student)
        db.session.add_all([assigned_student, unassigned_student, teacher])
        db.session.commit()

        teacher_client = self.app.test_client()
        teacher_csrf = teacher_client.get("/api/auth/me").get_json()["csrf_token"]
        login = teacher_client.post(
            "/api/auth/login",
            json={"username": "teacher-one", "password": "a-strong-password"},
            headers={"X-CSRF-Token": teacher_csrf},
        )
        self.assertEqual(login.status_code, 200)
        allowed = teacher_client.get(
            f"/api/student-question-attempts?student_id={assigned_student.id}"
        )
        denied = teacher_client.get(
            f"/api/student-question-attempts?student_id={unassigned_student.id}"
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(denied.status_code, 403)

    def test_learning_endpoints_require_login(self):
        self.client.post("/api/auth/logout", headers={"X-CSRF-Token": self.csrf})
        response = self.client.get("/api/learning-sessions")
        self.assertEqual(response.status_code, 401)

    def test_csrf_token_rotates_on_login_and_rejects_the_previous_token(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "student-one", "password": "a-strong-password"},
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(response.status_code, 200)
        refreshed_csrf = response.get_json()["csrf_token"]
        self.assertNotEqual(refreshed_csrf, self.csrf)

        payload = {"session_identifier": str(uuid4())}
        stale_response = self.client.post(
            "/api/learning-sessions/start",
            json=payload,
            headers={"X-CSRF-Token": self.csrf},
        )
        self.assertEqual(stale_response.status_code, 403)

        valid_response = self.client.post(
            "/api/learning-sessions/start",
            json=payload,
            headers={"X-CSRF-Token": refreshed_csrf},
        )
        self.assertEqual(valid_response.status_code, 201)

    def test_api_routes_require_authentication_and_student_role(self):
        anonymous_client = self.app.test_client()
        for path, body in (
            ("/activity/generate-question", {"operation": "addition"}),
            ("/activity/validate-answer", {
                "operation": "addition",
                "left": 1,
                "right": 1,
                "predicted_number": 2,
            }),
            ("/predict-number", {"video": "unused"}),
        ):
            response = anonymous_client.post(path, json=body)
            self.assertEqual(response.status_code, 401, path)

        teacher = User(username="teacher-two", role="teacher")
        teacher.set_password("a-strong-password")
        db.session.add(teacher)
        db.session.commit()
        teacher_client = self.app.test_client()
        teacher_csrf = teacher_client.get("/api/auth/me").get_json()["csrf_token"]
        login = teacher_client.post(
            "/api/auth/login",
            json={"username": "teacher-two", "password": "a-strong-password"},
            headers={"X-CSRF-Token": teacher_csrf},
        )
        self.assertEqual(login.status_code, 200)
        teacher_csrf = login.get_json()["csrf_token"]
        response = teacher_client.post(
            "/activity/generate-question",
            json={"operation": "addition"},
            headers={"X-CSRF-Token": teacher_csrf},
        )
        self.assertEqual(response.status_code, 403)
        prediction = teacher_client.post(
            "/predict-number",
            json={},
            headers={"X-CSRF-Token": teacher_csrf},
        )
        self.assertEqual(prediction.status_code, 403)

    def test_legacy_arithmetic_endpoints_are_retired_without_exposing_answers(self):
        baseline_activities = db.session.query(ActivityAttempt).count()
        baseline_questions = db.session.query(LearningQuestion).count()
        baseline_attempts = db.session.query(QuestionAttempt).count()
        legacy_requests = (
            ("/activity/generate-question", {"operation": "addition"}),
            (
                "/activity/validate-answer",
                {
                    "operation": "addition",
                    "left": 2,
                    "right": 3,
                    "predicted_number": 5,
                },
            ),
        )

        for path, body in legacy_requests:
            with self.subTest(path=path):
                response = self.post(path, body)
                self.assertEqual(response.status_code, 410)
                response_data = response.get_json()
                self.assertNotIn("answer", response_data)
                self.assertNotIn("expected_answer", response_data)
                self.assertIn("replacement", response_data)

        self.assertEqual(db.session.query(ActivityAttempt).count(), baseline_activities)
        self.assertEqual(db.session.query(LearningQuestion).count(), baseline_questions)
        self.assertEqual(db.session.query(QuestionAttempt).count(), baseline_attempts)

    def test_deleting_a_parent_cannot_cascade_through_learning_history(self):
        activity, question, learning_session = self.create_question()
        student = User.query.filter_by(username="student-one").one()
        saved_question = db.session.get(LearningQuestion, question["id"])
        question_attempt = QuestionAttempt(
            idempotency_key=str(uuid4()),
            student_id=student.id,
            session_id=learning_session["id"],
            activity_attempt_id=activity["id"],
            question_id=question["id"],
            expected_answer=saved_question.expected_answer,
            submitted_answer=saved_question.expected_answer,
            is_correct=True,
            attempt_number=1,
            status="completed",
        )
        recognition_log = RecognitionLog(
            activity_attempt_id=activity["id"],
            question_attempt=question_attempt,
            learning_question_id=question["id"],
            predicted_value=saved_question.expected_answer,
            confidence=0.9,
            status="recognized",
            gesture_detected=True,
            recognition_attempt_number=1,
        )
        db.session.add_all([question_attempt, recognition_log])
        db.session.commit()
        record_ids = {
            "student": student.id,
            "session": learning_session["id"],
            "activity": activity["id"],
            "question": question["id"],
        }

        for model, record_id in (
            (User, record_ids["student"]),
            (LearningSession, record_ids["session"]),
            (ActivityAttempt, record_ids["activity"]),
            (LearningQuestion, record_ids["question"]),
        ):
            with self.subTest(model=model.__name__):
                with self.assertRaises(IntegrityError):
                    db.session.delete(db.session.get(model, record_id))
                    db.session.flush()
                db.session.rollback()

        self.assertEqual(db.session.query(LearningSession).count(), 1)
        self.assertEqual(db.session.query(ActivityAttempt).count(), 1)
        self.assertEqual(db.session.query(LearningQuestion).count(), 1)
        self.assertEqual(db.session.query(QuestionAttempt).count(), 1)
        self.assertEqual(db.session.query(RecognitionLog).count(), 1)

    def test_deactivated_account_session_is_rejected(self):
        user = User.query.filter_by(username="student-one").one()
        user.is_active = False
        db.session.commit()
        response = self.client.get("/api/learning-sessions")
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.client.get("/api/auth/me").get_json()["user"])

    def test_recognition_log_cannot_reference_both_question_types(self):
        with self.assertRaisesRegex(ValueError, "only one question type"):
            RecognitionLog(
                learning_question_id=str(uuid4()),
                number_question_id=str(uuid4()),
            )

    def test_login_and_registration_require_csrf_and_registration_is_student_only(self):
        client = self.app.test_client()
        self.assertEqual(
            client.post(
                "/api/auth/login",
                json={"username": "student-one", "password": "a-strong-password"},
            ).status_code,
            403,
        )
        csrf = client.get("/api/auth/me").get_json()["csrf_token"]
        weak_registration = client.post(
            "/api/auth/register",
            json={"username": "student-weak", "password": "short", "role": "teacher"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(weak_registration.status_code, 400)
        registration = client.post(
            "/api/auth/register",
            json={"username": "student-three", "password": "a-strong-password", "role": "teacher"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(registration.status_code, 201)
        self.assertEqual(registration.get_json()["user"]["role"], "student")

    def test_login_is_rate_limited(self):
        client = self.app.test_client()
        csrf = client.get("/api/auth/me").get_json()["csrf_token"]
        status_codes = []
        for _ in range(6):
            response = client.post(
                "/api/auth/login",
                json={"username": "student-one", "password": "a-strong-password"},
                headers={"X-CSRF-Token": csrf},
            )
            status_codes.append(response.status_code)
            if response.status_code == 200:
                csrf = response.get_json()["csrf_token"]
        self.assertEqual(status_codes[:5], [200] * 5)
        self.assertEqual(status_codes[5], 429)

    def test_multiplication_questions_stay_in_recognizer_number_range(self):
        for _ in range(100):
            _, question, _ = self.create_question("multiplication")
            with self.app.app_context():
                saved_question = db.session.get(LearningQuestion, question["id"])
                self.assertLessEqual(saved_question.expected_answer, 50)


if __name__ == "__main__":
    unittest.main()
