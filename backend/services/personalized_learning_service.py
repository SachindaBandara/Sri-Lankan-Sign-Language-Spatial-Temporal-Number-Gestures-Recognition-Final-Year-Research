from datetime import datetime, time, timedelta
from statistics import mean

from flask import current_app
from sqlalchemy import case, func, or_, select

from extensions import db
from models import (
    ActivityAttempt,
    DifficultyAdjustmentHistory,
    LearningPathStep,
    LearningRecommendation,
    NumberIdentificationQuestion,
    QuestionAttempt,
    RecognitionLog,
    StudentLearningPath,
    StudentLearningProgress,
    User,
    utcnow,
)
from services.learning_activity_catalogue import LEARNING_ACTIVITY_CATALOGUE

MATH_OPERATIONS = ("addition", "subtraction", "multiplication", "division")
OPERATIONS = ("number_identification", *MATH_OPERATIONS)
DIFFICULTY_LEVELS = ("easy", "standard", "hard")
_DIFFICULTY_INDEX = {level: index for index, level in enumerate(DIFFICULTY_LEVELS)}
PATH_SKILLS_BY_OPERATION = {
    "number_identification": (
        ("number_identification_0_9", "standard", 0, 9),
        ("number_identification_10_19", "standard", 10, 19),
        ("number_identification_20_29", "standard", 20, 29),
        ("number_identification_30_39", "standard", 30, 39),
        ("number_identification_40_50", "standard", 40, 50),
    ),
    **{
        operation: tuple(
            (f"{operation}_{difficulty}", difficulty, None, None)
            for difficulty in DIFFICULTY_LEVELS
        )
        for operation in MATH_OPERATIONS
    },
}
PATH_SKILLS = tuple(
    (skill_key, operation, difficulty, target_min, target_max)
    for operation in OPERATIONS
    for skill_key, difficulty, target_min, target_max
    in PATH_SKILLS_BY_OPERATION[operation]
)
_PATH_SKILL_BY_KEY = {skill[0]: skill for skill in PATH_SKILLS}
_PATH_SKILL_POSITION = {
    skill_key: index for index, (skill_key, *_) in enumerate(PATH_SKILLS)
}


class PersonalizedLearningService:
    @classmethod
    def refresh_student(
        cls,
        student_id: int,
        evaluated_attempt_id: int | None = None,
        create_path: bool = True,
        preferred_operation: str | None = None,
    ):
        progress_by_operation = {}
        for operation in MATH_OPERATIONS:
            progress = cls._get_progress(student_id, operation)
            attempts = db.session.scalars(
                select(QuestionAttempt)
                .join(ActivityAttempt, ActivityAttempt.id == QuestionAttempt.activity_attempt_id)
                .where(
                    QuestionAttempt.student_id == student_id,
                    ActivityAttempt.operation_type == operation,
                    QuestionAttempt.is_correct.is_not(None),
                )
                .order_by(QuestionAttempt.attempted_at, QuestionAttempt.id)
            ).all()
            cls._update_math_progress(progress, attempts)
            attempt_to_evaluate = evaluated_attempt_id
            if (
                attempt_to_evaluate is None
                and progress.last_evaluated_attempt_id == 0
                and attempts
            ):
                attempt_to_evaluate = attempts[-1].id
            if attempt_to_evaluate is not None:
                cls._adjust_difficulty(progress, attempts, attempt_to_evaluate)
            progress_by_operation[operation] = progress

        recognition_progress = cls._get_progress(student_id, "number_identification")
        cls._update_recognition_progress(recognition_progress, student_id)
        progress_by_operation["number_identification"] = recognition_progress

        minimum = int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
        weak_area_signals = {
            operation: cls._weak_area_signals(progress_by_operation[operation], minimum)
            for operation in OPERATIONS
        }
        cls._refresh_recommendations(
            student_id,
            progress_by_operation,
            weak_area_signals,
        )
        if create_path:
            cls._ensure_learning_path(
                student_id,
                progress_by_operation,
                weak_area_signals,
                preferred_operation,
            )
        return progress_by_operation

    @classmethod
    def refresh_recognition(cls, student_id: int) -> None:
        progress = cls._get_progress(student_id, "number_identification")
        cls._update_recognition_progress(progress, student_id)

    @staticmethod
    def _get_progress(student_id: int, operation: str) -> StudentLearningProgress:
        progress = db.session.scalar(
            select(StudentLearningProgress).where(
                StudentLearningProgress.student_id == student_id,
                StudentLearningProgress.operation_type == operation,
            )
        )
        if progress is not None:
            return progress

        latest_difficulty = "standard" if operation == "number_identification" else "easy"
        if operation in MATH_OPERATIONS:
            latest_difficulty = db.session.scalar(
                select(ActivityAttempt.difficulty_level)
                .where(
                    ActivityAttempt.student_id == student_id,
                    ActivityAttempt.operation_type == operation,
                )
                .order_by(ActivityAttempt.started_at.desc(), ActivityAttempt.id.desc())
                .limit(1)
            ) or "easy"
        progress = StudentLearningProgress(
            student_id=student_id,
            operation_type=operation,
            current_difficulty=latest_difficulty,
        )
        db.session.add(progress)
        db.session.flush()
        return progress

    @staticmethod
    def _update_math_progress(
        progress: StudentLearningProgress,
        attempts: list[QuestionAttempt],
    ) -> None:
        total = len(attempts)
        correct = sum(attempt.is_correct is True for attempt in attempts)
        recent_window = max(1, int(current_app.config["PERSONALIZATION_RECENT_WINDOW"]))
        recent_attempts = attempts[-recent_window:]
        previous_attempts = attempts[-2 * recent_window:-recent_window]
        progress.total_attempts = total
        progress.correct_answers = correct
        progress.incorrect_answers = total - correct
        progress.accuracy = correct / total if total else None
        progress.recent_accuracy = (
            sum(attempt.is_correct is True for attempt in recent_attempts) / len(recent_attempts)
            if recent_attempts
            else None
        )
        response_times = [
            attempt.response_time_ms for attempt in attempts
            if attempt.response_time_ms is not None
        ]
        progress.average_response_time_ms = (
            round(mean(response_times)) if response_times else None
        )
        progress.improvement_rate = None
        if recent_attempts and previous_attempts:
            recent_accuracy = sum(item.is_correct is True for item in recent_attempts) / len(recent_attempts)
            previous_accuracy = sum(item.is_correct is True for item in previous_attempts) / len(previous_attempts)
            progress.improvement_rate = recent_accuracy - previous_accuracy
        progress.updated_at = utcnow()

    @staticmethod
    def _update_recognition_progress(
        progress: StudentLearningProgress,
        student_id: int,
    ) -> None:
        total, high_confidence, average_confidence = db.session.execute(
            select(
                func.count(RecognitionLog.id),
                func.sum(
                    case(
                        (RecognitionLog.status == "recognized", 1),
                        else_=0,
                    )
                ),
                func.avg(RecognitionLog.confidence),
            )
            .join(ActivityAttempt, ActivityAttempt.id == RecognitionLog.activity_attempt_id)
            .where(
                ActivityAttempt.student_id == student_id,
                ActivityAttempt.operation_type == "number_identification",
            )
        ).one()
        scored_attempts = db.session.scalars(
            select(RecognitionLog)
            .join(ActivityAttempt, ActivityAttempt.id == RecognitionLog.activity_attempt_id)
            .where(
                ActivityAttempt.student_id == student_id,
                ActivityAttempt.operation_type == "number_identification",
                RecognitionLog.is_correct.is_not(None),
            )
            .order_by(RecognitionLog.recognized_at, RecognitionLog.id)
        ).all()
        total_attempts = len(scored_attempts)
        correct_answers = sum(item.is_correct is True for item in scored_attempts)
        recent_window = max(1, int(current_app.config["PERSONALIZATION_RECENT_WINDOW"]))
        recent_attempts = scored_attempts[-recent_window:]
        previous_attempts = scored_attempts[-2 * recent_window:-recent_window]
        progress.recognition_events = total or 0
        progress.high_confidence_recognitions = high_confidence or 0
        progress.average_recognition_confidence = average_confidence
        progress.total_attempts = total_attempts
        progress.correct_answers = correct_answers
        progress.incorrect_answers = total_attempts - correct_answers
        progress.accuracy = correct_answers / total_attempts if total_attempts else None
        progress.recent_accuracy = (
            sum(item.is_correct is True for item in recent_attempts) / len(recent_attempts)
            if recent_attempts
            else None
        )
        progress.average_response_time_ms = None
        progress.improvement_rate = None
        if recent_attempts and previous_attempts:
            recent_accuracy = sum(item.is_correct is True for item in recent_attempts) / len(recent_attempts)
            previous_accuracy = sum(item.is_correct is True for item in previous_attempts) / len(previous_attempts)
            progress.improvement_rate = recent_accuracy - previous_accuracy
        progress.updated_at = utcnow()

    @classmethod
    def _adjust_difficulty(
        cls,
        progress: StudentLearningProgress,
        attempts: list[QuestionAttempt],
        evaluated_attempt_id: int,
    ) -> None:
        if not attempts or progress.last_evaluated_attempt_id >= evaluated_attempt_id:
            return
        progress.last_evaluated_attempt_id = evaluated_attempt_id
        if attempts[-1].id != evaluated_attempt_id:
            return

        minimum = int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
        activity_difficulty = db.session.scalar(
            select(ActivityAttempt.difficulty_level)
            .join(QuestionAttempt, QuestionAttempt.activity_attempt_id == ActivityAttempt.id)
            .where(QuestionAttempt.id == evaluated_attempt_id)
        )
        if activity_difficulty != progress.current_difficulty:
            return

        difficulty_attempts = db.session.scalars(
            select(QuestionAttempt)
            .join(ActivityAttempt, ActivityAttempt.id == QuestionAttempt.activity_attempt_id)
            .where(
                QuestionAttempt.student_id == progress.student_id,
                ActivityAttempt.operation_type == progress.operation_type,
                ActivityAttempt.difficulty_level == activity_difficulty,
                QuestionAttempt.is_correct.is_not(None),
            )
            .order_by(QuestionAttempt.attempted_at, QuestionAttempt.id)
        ).all()
        if len(difficulty_attempts) < minimum:
            return
        recent_window = max(1, int(current_app.config["PERSONALIZATION_RECENT_WINDOW"]))
        recent = difficulty_attempts[-recent_window:]
        recent_accuracy = sum(item.is_correct is True for item in recent) / len(recent)
        historical_accuracy = (
            sum(item.is_correct is True for item in difficulty_attempts)
            / len(difficulty_attempts)
        )
        promotion_streak = int(current_app.config["PERSONALIZATION_PROMOTION_STREAK"])
        demotion_streak = int(current_app.config["PERSONALIZATION_DEMOTION_STREAK"])
        latest_streak = 0
        latest_result = difficulty_attempts[-1].is_correct
        for attempt in reversed(difficulty_attempts):
            if attempt.is_correct is not latest_result:
                break
            latest_streak += 1

        current_index = _DIFFICULTY_INDEX[progress.current_difficulty]
        new_index = current_index
        reason = None
        if (
            latest_result is True
            and latest_streak >= promotion_streak
            and recent_accuracy >= float(current_app.config["PERSONALIZATION_PROMOTION_ACCURACY"])
            and historical_accuracy >= float(current_app.config["PERSONALIZATION_PROMOTION_HISTORY_ACCURACY"])
        ):
            new_index = min(len(DIFFICULTY_LEVELS) - 1, current_index + 1)
            reason = (
                f"{latest_streak} consecutive correct answers at {activity_difficulty} "
                f"difficulty; recent accuracy {recent_accuracy:.0%} and historical "
                f"accuracy {historical_accuracy:.0%} at this difficulty."
            )
        elif (
            latest_result is False
            and latest_streak >= demotion_streak
            and recent_accuracy < float(current_app.config["PERSONALIZATION_DEMOTION_ACCURACY"])
            and historical_accuracy < float(current_app.config["PERSONALIZATION_DEMOTION_HISTORY_ACCURACY"])
        ):
            new_index = max(0, current_index - 1)
            reason = (
                f"{latest_streak} consecutive incorrect answers at {activity_difficulty} "
                f"difficulty; recent accuracy {recent_accuracy:.0%} and historical "
                f"accuracy {historical_accuracy:.0%} at this difficulty."
            )
        if new_index == current_index:
            return

        previous = progress.current_difficulty
        progress.current_difficulty = DIFFICULTY_LEVELS[new_index]
        db.session.add(
            DifficultyAdjustmentHistory(
                student_id=progress.student_id,
                operation_type=progress.operation_type,
                previous_difficulty=previous,
                new_difficulty=progress.current_difficulty,
                recent_accuracy=recent_accuracy,
                historical_accuracy=historical_accuracy,
                reason=reason,
            )
        )

    @classmethod
    def _refresh_recommendations(
        cls,
        student_id: int,
        progress_by_operation: dict[str, StudentLearningProgress],
        weak_area_signals: dict[str, list[str]],
    ) -> None:
        minimum = int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
        candidates = []
        for operation in OPERATIONS:
            progress = progress_by_operation[operation]
            signals = weak_area_signals[operation]
            if signals:
                candidates.append((operation, "practice_weak_area", progress, 1, signals))

        if not candidates:
            operation = min(
                OPERATIONS,
                key=lambda item: (
                    progress_by_operation[item].total_attempts,
                    OPERATIONS.index(item),
                ),
            )
            candidates.append(
                (operation, "build_evidence", progress_by_operation[operation], 3, [])
            )

        active_keys = set()
        for operation, kind, progress, priority, signals in candidates:
            activity = LEARNING_ACTIVITY_CATALOGUE[operation]
            recommendation_key = f"catalogue:{activity['catalogue_id']}:{kind}"
            active_keys.add(recommendation_key)
            explanation = cls._recommendation_explanation(
                kind,
                progress,
                minimum,
                signals,
            )
            recommendation = db.session.scalar(
                select(LearningRecommendation).where(
                    LearningRecommendation.student_id == student_id,
                    LearningRecommendation.recommendation_key == recommendation_key,
                )
            )
            if recommendation is None:
                recommendation = LearningRecommendation(
                    student_id=student_id,
                    operation_type=operation,
                    recommendation_key=recommendation_key,
                    difficulty_level=progress.current_difficulty,
                    kind=kind,
                    title=activity["title"],
                    explanation=explanation,
                    priority=priority,
                    status="pending",
                    baseline_accuracy=progress.accuracy,
                )
                db.session.add(recommendation)
                continue

            if recommendation.status == "completed":
                accuracy_declined = (
                    progress.accuracy is not None
                    and recommendation.baseline_accuracy is not None
                    and progress.accuracy <= recommendation.baseline_accuracy - 0.10
                )
                if recommendation.kind == kind and not accuracy_declined:
                    continue
                recommendation.status = "pending"
                recommendation.completed_at = None
            elif recommendation.status == "dismissed":
                recommendation.status = "pending"
            recommendation.kind = kind
            recommendation.difficulty_level = progress.current_difficulty
            recommendation.explanation = explanation
            recommendation.priority = priority
            recommendation.updated_at = utcnow()

        if active_keys:
            stale = db.session.scalars(
                select(LearningRecommendation).where(
                    LearningRecommendation.student_id == student_id,
                    LearningRecommendation.status.in_(("pending", "in_progress")),
                )
            ).all()
            for recommendation in stale:
                if recommendation.recommendation_key not in active_keys:
                    recommendation.status = "dismissed"
                    recommendation.updated_at = utcnow()

    @staticmethod
    def _recommendation_explanation(
        kind: str,
        progress: StudentLearningProgress,
        minimum: int,
        signals: list[str],
    ) -> str:
        if kind == "build_evidence":
            remaining = max(0, minimum - progress.total_attempts)
            return (
                f"Complete more valid answers to get reliable, personalized guidance. "
                f"{remaining} more answer(s) are needed before adaptation."
            )
        accuracy = (
            f"{progress.accuracy:.0%}"
            if progress.accuracy is not None
            else "not yet available"
        )
        recent = (
            f" Recent accuracy is {progress.recent_accuracy:.0%}."
            if progress.recent_accuracy is not None
            else ""
        )
        return (
            f"Your overall accuracy is {accuracy}."
            f"{recent} Weak-area signals: {', '.join(signals)}. "
            f"Practice at {progress.current_difficulty} and review the operation."
        )

    @classmethod
    def _ensure_learning_path(
        cls,
        student_id: int,
        progress_by_operation: dict[str, StudentLearningProgress],
        weak_area_signals: dict[str, list[str]],
        preferred_operation: str | None = None,
    ) -> None:
        path = db.session.scalar(
            select(StudentLearningPath).where(StudentLearningPath.student_id == student_id)
        )
        minimum = int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
        if path is None:
            user = db.session.get(User, student_id)
            path = StudentLearningPath(
                student_id=student_id,
                title=f"Personalized learning path for {user.username if user else 'student'}",
            )
            db.session.add(path)
            db.session.flush()

            math_order = sorted(
                MATH_OPERATIONS,
                key=lambda operation: (
                    0
                    if weak_area_signals[operation]
                    else 1,
                    progress_by_operation[operation].accuracy
                    if progress_by_operation[operation].accuracy is not None
                    else 1.0,
                    MATH_OPERATIONS.index(operation),
                ),
            )
            ordered_operations = ["number_identification", *math_order]
            if preferred_operation in OPERATIONS:
                ordered_operations = [
                    preferred_operation,
                    *(operation for operation in ordered_operations if operation != preferred_operation),
                ]
            ordered_skills = [
                skill_key
                for operation in ordered_operations
                for skill_key, *_ in PATH_SKILLS_BY_OPERATION[operation]
            ]
            for index, skill_key in enumerate(ordered_skills, start=1):
                db.session.add(cls._new_path_step(
                    path.id,
                    index,
                    skill_key,
                    "in_progress" if index == 1 else "locked",
                    progress_by_operation,
                    weak_area_signals,
                    minimum,
                ))
            return

        steps = db.session.scalars(
            select(LearningPathStep)
            .where(LearningPathStep.path_id == path.id)
            .order_by(LearningPathStep.sequence_number)
        ).all()
        existing_skill_keys = {step.skill_key for step in steps}
        missing_skills = [
            skill_key for skill_key, *_ in PATH_SKILLS
            if skill_key not in existing_skill_keys
        ]
        if missing_skills:
            next_sequence = max((step.sequence_number for step in steps), default=0) + 1
            for index, skill_key in enumerate(missing_skills, start=next_sequence):
                db.session.add(cls._new_path_step(
                    path.id,
                    index,
                    skill_key,
                    "locked",
                    progress_by_operation,
                    weak_area_signals,
                    minimum,
                ))
            path.status = "active"
            db.session.flush()
            steps = db.session.scalars(
                select(LearningPathStep)
                .where(LearningPathStep.path_id == path.id)
                .order_by(LearningPathStep.sequence_number)
            ).all()
        if not steps:
            return
        if path.status == "completed":
            if preferred_operation not in OPERATIONS:
                return
            step_to_reopen = next(
                (
                    step for step in steps
                    if step.operation_type == preferred_operation
                    and step.status == "completed"
                ),
                None,
            )
            if step_to_reopen is None:
                return
            step_to_reopen.status = "in_progress"
            step_to_reopen.completed_at = None
            path.status = "active"
            path.updated_at = utcnow()

        completed = [step for step in steps if step.status == "completed"]
        current = [step for step in steps if step.status == "in_progress"]
        locked = [step for step in steps if step.status == "locked"]
        locked.sort(
            key=lambda step: (
                cls._path_priority(
                    progress_by_operation[step.operation_type],
                    minimum,
                    weak_area_signals[step.operation_type],
                ),
                _PATH_SKILL_POSITION.get(step.skill_key, len(PATH_SKILLS)),
            )
        )
        if not current and locked:
            locked[0].status = "in_progress"
            current = [locked.pop(0)]

        ordered_steps = completed + current + locked
        if [step.id for step in ordered_steps] != [step.id for step in steps]:
            temporary_sequence = len(steps) + 1
            for index, step in enumerate(ordered_steps, start=temporary_sequence):
                step.sequence_number = index
            db.session.flush()
            for index, step in enumerate(ordered_steps, start=1):
                step.sequence_number = index

        for step in locked:
            progress = progress_by_operation[step.operation_type]
            step.reason = (
                "recognition_confidence"
                if step.operation_type == "number_identification"
                else cls._path_reason(
                    progress,
                    minimum,
                    weak_area_signals[step.operation_type],
                )
            )
        path.status = "completed" if len(completed) == len(steps) else "active"

    @staticmethod
    def _new_path_step(
        path_id: int,
        sequence_number: int,
        skill_key: str,
        status: str,
        progress_by_operation: dict[str, StudentLearningProgress],
        weak_area_signals: dict[str, list[str]],
        minimum: int,
    ) -> LearningPathStep:
        _, operation, difficulty, _, _ = _PATH_SKILL_BY_KEY[skill_key]
        progress = progress_by_operation[operation]
        return LearningPathStep(
            path_id=path_id,
            sequence_number=sequence_number,
            operation_type=operation,
            skill_key=skill_key,
            difficulty_level=difficulty,
            title=skill_key.replace("_", " ").title(),
            reason=(
                "recognition_confidence"
                if operation == "number_identification"
                else PersonalizedLearningService._path_reason(
                    progress,
                    minimum,
                    weak_area_signals[operation],
                )
            ),
            status=status,
        )

    @staticmethod
    def number_identification_target_range(student_id: int) -> tuple[int, int]:
        step = db.session.scalar(
            select(LearningPathStep)
            .join(StudentLearningPath, StudentLearningPath.id == LearningPathStep.path_id)
            .where(
                StudentLearningPath.student_id == student_id,
                LearningPathStep.operation_type == "number_identification",
                LearningPathStep.status == "in_progress",
            )
        )
        if step is None:
            return 0, 50
        skill = _PATH_SKILL_BY_KEY.get(step.skill_key)
        if skill is None or skill[3] is None or skill[4] is None:
            return 0, 50
        return skill[3], skill[4]

    @staticmethod
    def _weak_area_signals(
        progress: StudentLearningProgress,
        minimum: int,
    ) -> list[str]:
        signals = []
        accuracy_threshold = float(current_app.config["PERSONALIZATION_DEMOTION_ACCURACY"])
        if progress.total_attempts >= minimum and (
            (progress.accuracy is not None and progress.accuracy < accuracy_threshold)
            or (
                progress.recent_accuracy is not None
                and progress.recent_accuracy < accuracy_threshold
            )
        ):
            signals.append("low_accuracy")

        recent_window = max(1, int(current_app.config["PERSONALIZATION_RECENT_WINDOW"]))
        trend_sample = max(minimum, 2 * recent_window)
        trend_threshold = float(current_app.config["PERSONALIZATION_WEAK_TREND_DECLINE"])
        if (
            progress.total_attempts >= trend_sample
            and progress.improvement_rate is not None
            and progress.improvement_rate <= -trend_threshold
        ):
            signals.append("declining_trend")

        behavior_window = max(
            minimum,
            recent_window,
            int(current_app.config["PERSONALIZATION_DEMOTION_STREAK"]),
        )
        if progress.operation_type in MATH_OPERATIONS:
            event_rows = db.session.execute(
                select(
                    QuestionAttempt.is_correct,
                    QuestionAttempt.skipped,
                    QuestionAttempt.hint_used,
                )
                .join(ActivityAttempt, ActivityAttempt.id == QuestionAttempt.activity_attempt_id)
                .where(
                    QuestionAttempt.student_id == progress.student_id,
                    ActivityAttempt.operation_type == progress.operation_type,
                    or_(
                        QuestionAttempt.is_correct.is_not(None),
                        QuestionAttempt.skipped.is_(True),
                    ),
                )
                .order_by(QuestionAttempt.attempted_at.desc(), QuestionAttempt.id.desc())
                .limit(behavior_window)
            ).all()
            events = list(reversed(event_rows))
            answer_rows = db.session.execute(
                select(QuestionAttempt.is_correct, QuestionAttempt.hint_used)
                .join(ActivityAttempt, ActivityAttempt.id == QuestionAttempt.activity_attempt_id)
                .where(
                    QuestionAttempt.student_id == progress.student_id,
                    ActivityAttempt.operation_type == progress.operation_type,
                    QuestionAttempt.is_correct.is_not(None),
                )
                .order_by(QuestionAttempt.attempted_at.desc(), QuestionAttempt.id.desc())
                .limit(behavior_window)
            ).all()
            answer_events = list(reversed(answer_rows))
        else:
            recognition_results = db.session.scalars(
                select(RecognitionLog.is_correct)
                .join(ActivityAttempt, ActivityAttempt.id == RecognitionLog.activity_attempt_id)
                .where(
                    ActivityAttempt.student_id == progress.student_id,
                    ActivityAttempt.operation_type == progress.operation_type,
                    RecognitionLog.is_correct.is_not(None),
                )
                .order_by(RecognitionLog.recognized_at.desc(), RecognitionLog.id.desc())
                .limit(behavior_window)
            ).all()
            events = [(result, False, False) for result in reversed(recognition_results)]
            answer_events = [(result, False) for result in reversed(recognition_results)]

        incorrect_streak = 0
        for is_correct, skipped, _ in reversed(events):
            if skipped or is_correct is not False:
                break
            incorrect_streak += 1
        if incorrect_streak >= int(current_app.config["PERSONALIZATION_DEMOTION_STREAK"]):
            signals.append("repeated_errors")

        recent_events = events[-behavior_window:]
        if len(recent_events) >= minimum:
            skip_rate = sum(skipped for _, skipped, _ in recent_events) / len(recent_events)
            if skip_rate >= float(current_app.config["PERSONALIZATION_WEAK_SKIP_RATE"]):
                signals.append("frequent_skips")

        recent_answers = answer_events[-behavior_window:]
        if len(recent_answers) >= minimum:
            hint_rate = sum(
                hint_used for _, hint_used in recent_answers
            ) / len(recent_answers)
            if hint_rate >= float(current_app.config["PERSONALIZATION_WEAK_HINT_RATE"]):
                signals.append("hint_dependence")
        return signals

    @staticmethod
    def _path_priority(
        progress: StudentLearningProgress,
        minimum: int,
        weak_area_signals: list[str],
    ) -> tuple[int, float, int, int]:
        if weak_area_signals:
            group = 0
        elif progress.total_attempts < minimum:
            group = 1
        else:
            group = 2
        accuracy = progress.accuracy if progress.accuracy is not None else 1.0
        return (
            group,
            accuracy,
            progress.total_attempts,
            MATH_OPERATIONS.index(progress.operation_type)
            if progress.operation_type in MATH_OPERATIONS
            else len(MATH_OPERATIONS),
        )

    @staticmethod
    def _path_reason(
        progress: StudentLearningProgress,
        minimum: int,
        weak_area_signals: list[str],
    ) -> str:
        if weak_area_signals:
            return "weak_area"
        if progress.total_attempts < minimum:
            return "evidence_needed"
        return "continue_mastery"

    @staticmethod
    def activity_started(activity: ActivityAttempt) -> None:
        PersonalizedLearningService.refresh_student(
            activity.student_id,
            preferred_operation=activity.operation_type,
        )

        recommendation = db.session.scalar(
            select(LearningRecommendation)
            .where(
                LearningRecommendation.student_id == activity.student_id,
                LearningRecommendation.operation_type == activity.operation_type,
                LearningRecommendation.status == "pending",
            )
            .order_by(LearningRecommendation.priority, LearningRecommendation.created_at)
        )
        if recommendation is not None:
            recommendation.status = "in_progress"
            recommendation.updated_at = utcnow()
        db.session.commit()

    @classmethod
    def activity_completed(cls, activity: ActivityAttempt) -> None:
        if activity.operation_type in MATH_OPERATIONS and activity.total_attempts == 0:
            db.session.commit()
            return
        if activity.operation_type == "number_identification":
            open_questions = db.session.scalars(
                select(NumberIdentificationQuestion).where(
                    NumberIdentificationQuestion.activity_attempt_id == activity.id,
                    NumberIdentificationQuestion.status == "in_progress",
                )
            ).all()
            for question in open_questions:
                question.status = "skipped"
                question.completed_at = utcnow()
                activity.skipped_questions += 1
            if activity.total_attempts == 0:
                db.session.commit()
                return

        step = db.session.scalar(
            select(LearningPathStep)
            .join(StudentLearningPath, StudentLearningPath.id == LearningPathStep.path_id)
            .where(
                StudentLearningPath.student_id == activity.student_id,
                LearningPathStep.operation_type == activity.operation_type,
                LearningPathStep.difficulty_level == activity.difficulty_level,
                LearningPathStep.status == "in_progress",
            )
        )
        skill_results = cls._path_skill_results(activity.student_id, step) if step else []
        if step is not None and not cls._path_skill_mastered(skill_results):
            step.reason = (
                "evidence_needed"
                if len(skill_results) < int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
                else "mastery_needed"
            )
            db.session.commit()
            return

        recommendation = db.session.scalar(
            select(LearningRecommendation)
            .where(
                LearningRecommendation.student_id == activity.student_id,
                LearningRecommendation.operation_type == activity.operation_type,
                LearningRecommendation.status == "in_progress",
            )
            .order_by(LearningRecommendation.priority, LearningRecommendation.created_at)
        )
        if recommendation is not None:
            progress = db.session.scalar(
                select(StudentLearningProgress).where(
                    StudentLearningProgress.student_id == activity.student_id,
                    StudentLearningProgress.operation_type == activity.operation_type,
                )
            )
            recommendation.status = "completed"
            recommendation.completed_at = utcnow()
            recommendation.updated_at = utcnow()
            recommendation.baseline_accuracy = progress.accuracy if progress else None

        if step is not None:
            step.status = "completed"
            step.completed_at = utcnow()
            next_step = db.session.scalar(
                select(LearningPathStep).where(
                    LearningPathStep.path_id == step.path_id,
                    LearningPathStep.sequence_number == step.sequence_number + 1,
                )
            )
            if next_step is not None:
                next_step.status = "in_progress"
            else:
                path = db.session.get(StudentLearningPath, step.path_id)
                if path is not None:
                    path.status = "completed"
                    path.updated_at = utcnow()
        db.session.commit()

    @staticmethod
    def _path_skill_results(
        student_id: int,
        step: LearningPathStep,
    ) -> list[bool]:
        skill = _PATH_SKILL_BY_KEY.get(step.skill_key)
        if skill is None:
            return []
        _, operation, difficulty, target_min, target_max = skill
        if operation == "number_identification":
            return db.session.scalars(
                select(RecognitionLog.is_correct)
                .join(
                    ActivityAttempt,
                    ActivityAttempt.id == RecognitionLog.activity_attempt_id,
                )
                .join(
                    NumberIdentificationQuestion,
                    NumberIdentificationQuestion.id == RecognitionLog.number_question_id,
                )
                .where(
                    ActivityAttempt.student_id == student_id,
                    ActivityAttempt.operation_type == operation,
                    NumberIdentificationQuestion.expected_value >= target_min,
                    NumberIdentificationQuestion.expected_value <= target_max,
                    RecognitionLog.is_correct.is_not(None),
                )
                .order_by(RecognitionLog.recognized_at, RecognitionLog.id)
            ).all()
        return db.session.scalars(
            select(QuestionAttempt.is_correct)
            .join(
                ActivityAttempt,
                ActivityAttempt.id == QuestionAttempt.activity_attempt_id,
            )
            .where(
                QuestionAttempt.student_id == student_id,
                ActivityAttempt.operation_type == operation,
                ActivityAttempt.difficulty_level == difficulty,
                QuestionAttempt.is_correct.is_not(None),
            )
            .order_by(QuestionAttempt.attempted_at, QuestionAttempt.id)
        ).all()

    @staticmethod
    def _path_skill_mastered(results: list[bool]) -> bool:
        minimum = int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
        promotion_accuracy = float(current_app.config["PERSONALIZATION_PROMOTION_ACCURACY"])
        historical_accuracy = float(
            current_app.config["PERSONALIZATION_PROMOTION_HISTORY_ACCURACY"]
        )
        if len(results) < minimum:
            return False

        recent_window = max(1, int(current_app.config["PERSONALIZATION_RECENT_WINDOW"]))
        recent_results = results[-recent_window:]
        accuracy = sum(result is True for result in results) / len(results)
        recent_accuracy = sum(result is True for result in recent_results) / len(recent_results)
        if (
            recent_accuracy < promotion_accuracy
            or accuracy < historical_accuracy
        ):
            return False

        required_streak = int(current_app.config["PERSONALIZATION_PROMOTION_STREAK"])
        streak = 0
        for result in reversed(results):
            if result is not True:
                break
            streak += 1
        return streak >= required_streak

    @staticmethod
    def _weekly_progress(student_id: int) -> dict:
        today = utcnow().date()
        week_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        start = datetime.combine(week_days[0], time.min)
        end = datetime.combine(today + timedelta(days=1), time.min)
        buckets = {
            day: {
                "date": day.isoformat(),
                "weekday": day.weekday(),
                "total_attempts": 0,
                "correct_answers": 0,
                "activities_started": 0,
                "activities_completed": 0,
            }
            for day in week_days
        }

        math_attempts = db.session.execute(
            select(QuestionAttempt.attempted_at, QuestionAttempt.is_correct)
            .join(ActivityAttempt, ActivityAttempt.id == QuestionAttempt.activity_attempt_id)
            .where(
                QuestionAttempt.student_id == student_id,
                ActivityAttempt.operation_type.in_(MATH_OPERATIONS),
                QuestionAttempt.is_correct.is_not(None),
                QuestionAttempt.attempted_at >= start,
                QuestionAttempt.attempted_at < end,
            )
        ).all()
        number_attempts = db.session.execute(
            select(RecognitionLog.recognized_at, RecognitionLog.is_correct)
            .join(ActivityAttempt, ActivityAttempt.id == RecognitionLog.activity_attempt_id)
            .where(
                ActivityAttempt.student_id == student_id,
                ActivityAttempt.operation_type == "number_identification",
                RecognitionLog.is_correct.is_not(None),
                RecognitionLog.recognized_at >= start,
                RecognitionLog.recognized_at < end,
            )
        ).all()
        for attempted_at, is_correct in [*math_attempts, *number_attempts]:
            bucket = buckets.get(attempted_at.date())
            if bucket is not None:
                bucket["total_attempts"] += 1
                bucket["correct_answers"] += int(is_correct is True)

        started_activities = db.session.scalars(
            select(ActivityAttempt.started_at).where(
                ActivityAttempt.student_id == student_id,
                ActivityAttempt.started_at >= start,
                ActivityAttempt.started_at < end,
            )
        ).all()
        for started_at in started_activities:
            bucket = buckets.get(started_at.date())
            if bucket is not None:
                bucket["activities_started"] += 1

        completed_activities = db.session.scalars(
            select(ActivityAttempt.completed_at).where(
                ActivityAttempt.student_id == student_id,
                ActivityAttempt.status == "completed",
                ActivityAttempt.completed_at.is_not(None),
                ActivityAttempt.completed_at >= start,
                ActivityAttempt.completed_at < end,
            )
        ).all()
        for completed_at in completed_activities:
            bucket = buckets.get(completed_at.date())
            if bucket is not None:
                bucket["activities_completed"] += 1

        total_attempts = sum(bucket["total_attempts"] for bucket in buckets.values())
        correct_answers = sum(bucket["correct_answers"] for bucket in buckets.values())
        days = []
        for bucket in buckets.values():
            bucket["accuracy"] = (
                bucket["correct_answers"] / bucket["total_attempts"]
                if bucket["total_attempts"]
                else None
            )
            bucket["active"] = bool(
                bucket["activities_started"] or bucket["total_attempts"]
            )
            days.append(bucket)
        return {
            "days": days,
            "active_days": sum(bucket["active"] for bucket in buckets.values()),
            "total_attempts": total_attempts,
            "correct_answers": correct_answers,
            "accuracy": correct_answers / total_attempts if total_attempts else None,
            "activities_started": sum(bucket["activities_started"] for bucket in buckets.values()),
            "activities_completed": sum(
                bucket["activities_completed"] for bucket in buckets.values()
            ),
        }

    @staticmethod
    def _activity_completion(student_id: int) -> dict:
        rows = db.session.execute(
            select(
                ActivityAttempt.operation_type,
                ActivityAttempt.status,
                func.count(ActivityAttempt.id),
            )
            .where(ActivityAttempt.student_id == student_id)
            .group_by(ActivityAttempt.operation_type, ActivityAttempt.status)
        ).all()
        by_operation = {
            operation: {
                "operation_type": operation,
                "total_activities": 0,
                "completed_activities": 0,
                "in_progress_activities": 0,
                "abandoned_activities": 0,
                "completion_rate": None,
            }
            for operation in OPERATIONS
        }
        for operation, status, count in rows:
            stats = by_operation[operation]
            stats["total_activities"] += count
            stats[f"{status}_activities"] += count

        for stats in by_operation.values():
            if stats["total_activities"]:
                stats["completion_rate"] = (
                    stats["completed_activities"] / stats["total_activities"]
                )

        total_activities = sum(item["total_activities"] for item in by_operation.values())
        completed_activities = sum(
            item["completed_activities"] for item in by_operation.values()
        )
        return {
            "total_activities": total_activities,
            "completed_activities": completed_activities,
            "in_progress_activities": sum(
                item["in_progress_activities"] for item in by_operation.values()
            ),
            "abandoned_activities": sum(
                item["abandoned_activities"] for item in by_operation.values()
            ),
            "completion_rate": (
                completed_activities / total_activities if total_activities else None
            ),
            "by_operation": [by_operation[operation] for operation in OPERATIONS],
        }

    @staticmethod
    def _strengths(
        progress_by_operation: dict[str, StudentLearningProgress],
        minimum: int,
    ) -> list[dict]:
        recent_threshold = float(current_app.config["PERSONALIZATION_PROMOTION_ACCURACY"])
        historical_threshold = float(
            current_app.config["PERSONALIZATION_PROMOTION_HISTORY_ACCURACY"]
        )
        strengths = []
        for operation in OPERATIONS:
            progress = progress_by_operation[operation]
            if (
                progress.total_attempts >= minimum
                and progress.accuracy is not None
                and progress.accuracy >= historical_threshold
                and progress.recent_accuracy is not None
                and progress.recent_accuracy >= recent_threshold
            ):
                strengths.append({
                    "operation_type": operation,
                    "total_attempts": progress.total_attempts,
                    "accuracy": progress.accuracy,
                    "recent_accuracy": progress.recent_accuracy,
                })
        return sorted(
            strengths,
            key=lambda item: (-item["accuracy"], OPERATIONS.index(item["operation_type"])),
        )

    @staticmethod
    def _achievements(
        weekly_progress: dict,
        activity_completion: dict,
        strengths: list[dict],
        completed_path_steps: int,
    ) -> list[dict]:
        completed_activities = activity_completion["completed_activities"]
        active_days = weekly_progress["active_days"]
        return [
            {
                "id": "first_completed_activity",
                "earned": completed_activities >= 1,
                "progress": min(completed_activities, 1),
                "target": 1,
            },
            {
                "id": "weekly_practice",
                "earned": active_days >= 3,
                "progress": min(active_days, 3),
                "target": 3,
            },
            {
                "id": "operation_strength",
                "earned": bool(strengths),
                "progress": int(bool(strengths)),
                "target": 1,
                "operation_type": strengths[0]["operation_type"] if strengths else None,
            },
            {
                "id": "mastery_step",
                "earned": completed_path_steps >= 1,
                "progress": min(completed_path_steps, 1),
                "target": 1,
            },
        ]

    @classmethod
    def dashboard(cls, student_id: int) -> dict:
        progress_by_operation = cls.refresh_student(student_id)
        recommendations = db.session.scalars(
            select(LearningRecommendation)
            .where(
                LearningRecommendation.student_id == student_id,
                LearningRecommendation.status.in_(("pending", "in_progress")),
            )
            .order_by(LearningRecommendation.priority, LearningRecommendation.created_at)
        ).all()
        path = db.session.scalar(
            select(StudentLearningPath).where(StudentLearningPath.student_id == student_id)
        )
        steps = db.session.scalars(
            select(LearningPathStep)
            .where(LearningPathStep.path_id == path.id)
            .order_by(LearningPathStep.sequence_number)
        ).all() if path else []
        difficulty_history = db.session.scalars(
            select(DifficultyAdjustmentHistory)
            .where(DifficultyAdjustmentHistory.student_id == student_id)
            .order_by(
                DifficultyAdjustmentHistory.created_at.desc(),
                DifficultyAdjustmentHistory.id.desc(),
            )
            .limit(10)
        ).all()
        minimum = int(current_app.config["PERSONALIZATION_MIN_ATTEMPTS"])
        weak_area_signals = {
            operation: cls._weak_area_signals(progress_by_operation[operation], minimum)
            for operation in OPERATIONS
        }
        weak_areas = [
            operation for operation, signals in weak_area_signals.items() if signals
        ]
        user = db.session.get(User, student_id)
        total_attempts = sum(
            progress_by_operation[operation].total_attempts
            for operation in OPERATIONS
        )
        total_correct = sum(
            progress_by_operation[operation].correct_answers
            for operation in OPERATIONS
        )
        weekly_progress = cls._weekly_progress(student_id)
        activity_completion = cls._activity_completion(student_id)
        strengths = cls._strengths(progress_by_operation, minimum)
        completed_path_steps = sum(step.status == "completed" for step in steps)
        achievements = cls._achievements(
            weekly_progress,
            activity_completion,
            strengths,
            completed_path_steps,
        )
        return {
            "student": {
                "id": user.id,
                "username": user.username,
                "grade": user.grade,
            },
            "minimum_attempts_for_adaptation": minimum,
            "summary": {
                "total_attempts": total_attempts,
                "correct_answers": total_correct,
                "accuracy": total_correct / total_attempts if total_attempts else None,
            },
            "weak_areas": weak_areas,
            "weak_area_signals": weak_area_signals,
            "weekly_progress": weekly_progress,
            "activity_completion": activity_completion,
            "strengths": strengths,
            "achievements": achievements,
            "operations": [
                cls._progress_data(progress_by_operation[operation], minimum)
                for operation in OPERATIONS
            ],
            "recommendations": [cls._recommendation_data(item) for item in recommendations],
            "difficulty_history": [
                cls._difficulty_adjustment_data(item) for item in difficulty_history
            ],
            "learning_path": {
                "title": path.title,
                "status": path.status,
                "completed_steps": completed_path_steps,
                "total_steps": len(steps),
                "progress_percentage": (
                    round(100 * sum(step.status == "completed" for step in steps) / len(steps))
                    if steps
                    else 0
                ),
                "steps": [cls._path_step_data(step) for step in steps],
            } if path else None,
            "metric_notes": {
                "accuracy": "Calculated only from answers with a correctness result.",
                "number_identification": (
                    "Accuracy compares confidently recognized signs with the prompted target. "
                    "Low-confidence recognition is not treated as an incorrect answer."
                ),
            },
        }

    @staticmethod
    def _progress_data(progress: StudentLearningProgress, minimum: int) -> dict:
        return {
            "operation_type": progress.operation_type,
            "current_difficulty": progress.current_difficulty,
            "total_attempts": progress.total_attempts,
            "correct_answers": progress.correct_answers,
            "incorrect_answers": progress.incorrect_answers,
            "accuracy": progress.accuracy,
            "recent_accuracy": progress.recent_accuracy,
            "average_response_time_ms": progress.average_response_time_ms,
            "improvement_rate": progress.improvement_rate,
            "sample_sufficient": progress.total_attempts >= minimum,
            "recognition_events": progress.recognition_events,
            "high_confidence_recognitions": progress.high_confidence_recognitions,
            "average_recognition_confidence": progress.average_recognition_confidence,
        }

    @staticmethod
    def _recommendation_data(item: LearningRecommendation) -> dict:
        activity = LEARNING_ACTIVITY_CATALOGUE[item.operation_type]
        return {
            "id": item.id,
            "operation_type": item.operation_type,
            "difficulty_level": item.difficulty_level,
            "kind": item.kind,
            "title": item.title,
            "activity": dict(activity),
            "explanation": item.explanation,
            "priority": item.priority,
            "status": item.status,
        }

    @staticmethod
    def _path_step_data(item: LearningPathStep) -> dict:
        skill = _PATH_SKILL_BY_KEY.get(item.skill_key)
        return {
            "id": item.id,
            "sequence_number": item.sequence_number,
            "operation_type": item.operation_type,
            "skill_key": item.skill_key,
            "difficulty_level": item.difficulty_level,
            "target_min": skill[3] if skill else None,
            "target_max": skill[4] if skill else None,
            "title": item.title,
            "reason": item.reason,
            "status": item.status,
        }

    @staticmethod
    def _difficulty_adjustment_data(item: DifficultyAdjustmentHistory) -> dict:
        return {
            "operation_type": item.operation_type,
            "previous_difficulty": item.previous_difficulty,
            "new_difficulty": item.new_difficulty,
            "recent_accuracy": item.recent_accuracy,
            "historical_accuracy": item.historical_accuracy,
            "reason": item.reason,
            "created_at": item.created_at.isoformat() + "Z",
        }
