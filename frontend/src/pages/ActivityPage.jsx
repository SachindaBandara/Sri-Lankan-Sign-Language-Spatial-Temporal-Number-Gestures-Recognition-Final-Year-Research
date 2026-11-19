import { useCallback, useEffect, useRef, useState } from "react";
import { Brain, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import WebcamRecorder from "../components/WebcamRecorder";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { useTranslation } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

import {
  clearQuestionSubmissionKey,
  completeStudentActivity,
  generateQuestion,
  getQuestionSubmissionKey,
  markQuestionDisplayed,
  predictNumber,
  recordRecognition,
  startStudentActivity,
  submitLearningAnswer,
} from "../services/api";

export default function ActivityPage({
  operation,
  title,
  icon,
  initialDifficulty = "adaptive",
}) {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const navigate = useNavigate();
  const [problem, setProblem] = useState(null);
  const [livePrediction, setLivePrediction] = useState("--");
  const [result, setResult] = useState(null);
  const [score, setScore] = useState({ correct: 0, total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activityAttempt, setActivityAttempt] = useState(null);
  const [difficultyLevel, setDifficultyLevel] = useState(initialDifficulty);
  const [confidence, setConfidence] = useState(null);
  const [finished, setFinished] = useState(false);
  const questionDisplayedAt = useRef(null);
  const responseElapsedMs = useRef(0);
  const responseClockStartedAt = useRef(null);
  const displayOperator = operation === "division" ? "÷" : problem?.operator;

  const loadProblem = useCallback(async (activityId) => {
    setError("");
    setResult(null);
    setLivePrediction("--");
    setConfidence(null);
    const data = await generateQuestion(operation, activityId);
    setProblem(data);
    return data;
  }, [operation]);

  useEffect(() => {
    if (!problem?.id) return;
    const key = `learning-question-start:${problem.id}`;
    const elapsedKey = `learning-question-elapsed:${problem.id}`;
    const savedStart = Number(sessionStorage.getItem(key));
    const elapsed = Number(sessionStorage.getItem(elapsedKey));
    const start = Number.isFinite(savedStart) && savedStart > 0 ? savedStart : Date.now();
    if (!savedStart) sessionStorage.setItem(key, String(start));
    questionDisplayedAt.current = start;
    responseElapsedMs.current = Number.isFinite(elapsed) && elapsed > 0 ? elapsed : 0;
    responseClockStartedAt.current = document.visibilityState === "visible"
      ? savedStart ? Date.now() : start
      : null;
    markQuestionDisplayed(problem.id).catch((err) => setError(err.message));

    const saveActiveTime = () => {
      if (responseClockStartedAt.current !== null) {
        responseElapsedMs.current += Math.max(0, Date.now() - responseClockStartedAt.current);
        responseClockStartedAt.current = null;
        sessionStorage.setItem(elapsedKey, String(responseElapsedMs.current));
      }
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        saveActiveTime();
      } else if (responseClockStartedAt.current === null) {
        responseClockStartedAt.current = Date.now();
      }
    };
    window.addEventListener("pagehide", saveActiveTime);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("pagehide", saveActiveTime);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [problem?.id]);

  const handleVideo = useCallback(async (videoBase64, captureTiming) => {
    if (!activityAttempt || !problem) {
      setError(t("account.pleaseWait"));
      return;
    }
    setLoading(true);
    setError("");
    setLivePrediction("--");
    const startedAt = Number(captureTiming?.startedAt);
    const capturedAt = Number(captureTiming?.capturedAt);
    if (Number.isFinite(startedAt) && Number.isFinite(capturedAt) && capturedAt >= startedAt) {
      const activeStart = responseClockStartedAt.current ?? startedAt;
      responseElapsedMs.current += Math.max(0, startedAt - activeStart) + capturedAt - startedAt;
      responseClockStartedAt.current = null;
      sessionStorage.setItem(`learning-question-elapsed:${problem.id}`, String(responseElapsedMs.current));
    }

    try {
      const data = await predictNumber(videoBase64);
      try {
        await recordRecognition({
          activity_attempt_id: activityAttempt.id,
          question_id: problem?.id,
          predicted_value: data.predicted_number,
          confidence: data.confidence,
          model_key: data.model_key,
          recognition_token: data.recognition_token,
          gesture_detected: true,
        });
      } catch (trackingError) {
        setError(trackingError.message);
        return;
      }
      setConfidence(data.confidence);
      setLivePrediction(String(data.predicted_number));
    } catch (err) {
      if (err.message === "No hand landmarks detected in the video") {
        try {
          await recordRecognition({
            activity_attempt_id: activityAttempt.id,
            question_id: problem?.id,
            gesture_detected: false,
            status: "no_gesture",
          });
        } catch (trackingError) {
          setError(trackingError.message);
        }
      } else {
        try {
          await recordRecognition({
            activity_attempt_id: activityAttempt.id,
            question_id: problem?.id,
            gesture_detected: false,
            status: "processing_failed",
          });
        } catch (trackingError) {
          setError(trackingError.message);
        }
        setError(err.message);
      }
    } finally {
      responseClockStartedAt.current = document.visibilityState === "visible" ? Date.now() : null;
      if (problem?.id) {
        sessionStorage.setItem(`learning-question-elapsed:${problem.id}`, String(responseElapsedMs.current));
      }
      setLoading(false);
    }
  }, [activityAttempt, problem, t]);

  /**
   * FIXED backend payload
   */
  const submitLiveAnswer = async () => {
    if (!problem || !activityAttempt || livePrediction === "--" || confidence < 0.6) return;

    setLoading(true);
    setError("");

    try {
      const requestKey = getQuestionSubmissionKey(problem.id);
      const responseTime = Math.max(
        0,
        Math.min(
          86_400_000,
          responseElapsedMs.current + Math.max(0, Date.now() - (responseClockStartedAt.current ?? questionDisplayedAt.current))
        )
      );
      const response = await submitLearningAnswer(problem.id, {
        idempotency_key: requestKey,
        submitted_answer: Number(livePrediction),
        response_time_ms: responseTime,
        hint_used: false,
      });
      const evaluation = response.attempt;
      setResult(evaluation);
      clearQuestionSubmissionKey(problem.id);
      sessionStorage.removeItem(`learning-question-start:${problem.id}`);
      sessionStorage.removeItem(`learning-question-elapsed:${problem.id}`);
      setScore((prev) => ({
        correct: prev.correct + (evaluation.is_correct ? 1 : 0),
        total: prev.total + 1,
      }));
      if (!evaluation.is_correct) {
        responseClockStartedAt.current = null;
        const retryStart = Date.now();
        questionDisplayedAt.current = retryStart;
        responseElapsedMs.current = 0;
        sessionStorage.setItem(`learning-question-start:${problem.id}`, String(retryStart));
        sessionStorage.setItem(`learning-question-elapsed:${problem.id}`, "0");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const finishActivity = async () => {
    if (!activityAttempt || loading) return;
    setLoading(true);
    setError("");
    try {
      if (problem && !result?.is_correct) {
        await submitLearningAnswer(problem.id, {
          idempotency_key: getQuestionSubmissionKey(problem.id),
          skipped: true,
          response_time_ms: Math.max(
            0,
            Math.min(
              86_400_000,
              responseElapsedMs.current + Math.max(
                0,
                Date.now() - (responseClockStartedAt.current ?? questionDisplayedAt.current),
              ),
            ),
          ),
        });
        clearQuestionSubmissionKey(problem.id);
        sessionStorage.removeItem(`learning-question-start:${problem.id}`);
        sessionStorage.removeItem(`learning-question-elapsed:${problem.id}`);
      }
      await completeStudentActivity(
        operation,
        activityAttempt.id,
        difficultyLevel,
      );
      setActivityAttempt(null);
      setProblem(null);
      setResult(null);
      setFinished(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const retryQuestion = () => {
    if (!problem) return;
    setResult(null);
    setLivePrediction("--");
    setConfidence(null);
    responseElapsedMs.current = 0;
    questionDisplayedAt.current = Date.now();
    responseClockStartedAt.current = Date.now();
    sessionStorage.setItem(`learning-question-start:${problem.id}`, String(questionDisplayedAt.current));
    sessionStorage.setItem(`learning-question-elapsed:${problem.id}`, "0");
  };

  const nextProblem = async () => {
    setLoading(true);
    setError("");
    try {
      let activeActivity = activityAttempt;
      if (finished || !activeActivity) {
        activeActivity = await startStudentActivity(operation, difficultyLevel);
        setActivityAttempt(activeActivity);
        setFinished(false);
        setScore({ correct: 0, total: 0 });
      } else if (problem && !result?.is_correct) {
        await submitLearningAnswer(problem.id, {
          idempotency_key: getQuestionSubmissionKey(problem.id),
          skipped: true,
          response_time_ms: Math.max(
            0,
            Math.min(
              86_400_000,
              responseElapsedMs.current + Math.max(0, Date.now() - (responseClockStartedAt.current ?? questionDisplayedAt.current))
            )
          ),
        });
        clearQuestionSubmissionKey(problem.id);
        sessionStorage.removeItem(`learning-question-start:${problem.id}`);
        sessionStorage.removeItem(`learning-question-elapsed:${problem.id}`);
      }
      await loadProblem(activeActivity.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.section
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0.18 : 0.35, ease: "easeOut" }}
      className="space-y-5 sm:space-y-6"
    >
      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-violet-100 text-violet-700">
          {(() => {
            const IconComp = icon || Brain;
            return <IconComp className="h-6 w-6" aria-hidden="true" />;
          })()}
        </span>
        <div>
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-violet-600">
            {t("activity.challengeLabel")}
          </p>
          <h1 className="mt-1 text-2xl font-black tracking-tight text-slate-900 sm:text-3xl">
            {title}
          </h1>
        </div>
      </div>

      {(!activityAttempt || finished) && (
        <Card className="learning-card">
          <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-end sm:justify-between sm:p-6">
            <div className="w-full space-y-2 sm:max-w-xs">
              <label htmlFor="activity-difficulty" className="text-sm font-bold text-slate-700">
                {t("activity.difficulty")}
              </label>
              <select
                id="activity-difficulty"
                value={difficultyLevel}
                onChange={(event) => setDifficultyLevel(event.target.value)}
                className="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
              >
                <option value="adaptive">{t("activity.adaptive")}</option>
                <option value="easy">{t("activity.easy")}</option>
                <option value="standard">{t("activity.standard")}</option>
                <option value="hard">{t("activity.hard")}</option>
              </select>
            </div>
            <Button onClick={nextProblem} disabled={loading} className="w-full sm:w-auto">
              {t("activity.start")}
            </Button>
          </CardContent>
        </Card>
      )}

      {activityAttempt && (
        <Card className="learning-card overflow-hidden">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="text-base font-bold text-slate-600">
                {t("activity.solveThis")}
              </CardTitle>
              <span className="rounded-full bg-violet-100 px-3 py-1 text-xs font-bold text-violet-700">
                {t(`activity.${activityAttempt.difficulty_level}`)}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div aria-live="polite" className="flex min-h-24 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-r from-violet-50 to-sky-50 px-3 py-5 text-3xl font-black tracking-wide text-slate-900 sm:min-h-28 sm:text-5xl">
              <AnimatePresence mode="wait">
                <motion.span
                  key={problem ? `${problem.left}-${problem.operator}-${problem.right}` : "loading"}
                  className={problem ? "english-font" : undefined}
                  initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.92, y: 8 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: -6 }}
                  transition={{ duration: reduceMotion ? 0.15 : 0.2, ease: "easeOut" }}
                >
                  {problem
                    ? `${problem.left} ${displayOperator} ${problem.right} = ?`
                    : <span className="text-base font-semibold text-slate-500">{t("activity.loadingQuestion")}</span>}
                </motion.span>
              </AnimatePresence>
            </div>
          </CardContent>
        </Card>
      )}

      {activityAttempt && (
        <div className="grid gap-4 lg:grid-cols-2">
          {!finished && <WebcamRecorder onVideoCapture={handleVideo} />}

          <Card className="flex min-h-[28rem] flex-col items-center justify-center overflow-hidden rounded-[1.5rem] border-0 bg-gradient-to-br from-violet-600 to-indigo-700 text-white shadow-[0_16px_40px_rgba(87,65,194,0.18)]">
            <CardContent className="flex w-full flex-1 flex-col items-center justify-center p-6 text-center sm:p-8">
              <motion.span
                className="grid h-12 w-12 place-items-center rounded-2xl bg-white/15 text-amber-200 ring-1 ring-white/20"
                initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.7, rotate: -10 }}
                animate={{ opacity: 1, scale: 1, rotate: 0 }}
                transition={{ duration: reduceMotion ? 0.18 : 0.35, ease: "easeOut" }}
              >
                <Sparkles className="h-6 w-6" aria-hidden="true" />
              </motion.span>
              <p className="mt-4 text-sm font-bold text-white/75">{t("activity.predicted")}</p>
              <p aria-live="polite" className="mt-1 min-h-[4.5rem] text-7xl font-black leading-none tracking-tight">
                <AnimatePresence mode="wait">
                  <motion.span
                    key={loading ? "processing" : livePrediction}
                    initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.7, y: 8 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.85, y: -6 }}
                    transition={{ duration: reduceMotion ? 0.15 : 0.22, ease: "easeOut" }}
                    className="english-font inline-block"
                  >
                    {loading ? "…" : livePrediction}
                  </motion.span>
                </AnimatePresence>
              </p>
              <p className="mt-3 text-sm font-semibold text-white/80">
                {t("activity.score")}:{" "}
                <span className="english-font">{score.correct}/{score.total}</span>
              </p>

              {!result && !finished && (
                <motion.div
                  className="mt-5 w-full sm:w-auto"
                  whileTap={reduceMotion ? undefined : { scale: 0.96 }}
                >
                  <Button
                    className="w-full bg-amber-300 text-violet-950 hover:bg-amber-200 sm:w-auto"
                    onClick={submitLiveAnswer}
                    disabled={!problem || livePrediction === "--" || confidence < 0.6 || loading}
                  >
                    {t("activity.submit")}
                  </Button>
                </motion.div>
              )}
              {confidence !== null && confidence < 0.6 && !finished && (
                <p role="status" className="mt-4 text-sm text-amber-100">{t("activity.lowConfidence")}</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {result && (
        <motion.div
          initial={reduceMotion
            ? { opacity: 0 }
            : { opacity: 0, y: 12, scale: result.is_correct ? 0.92 : 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={reduceMotion
            ? { duration: 0.18 }
            : result.is_correct
              ? { type: "spring", stiffness: 260, damping: 16 }
              : { duration: 0.25, ease: "easeOut" }}
        >
          <Card className={`learning-card border-l-4 ${result.is_correct ? "border-l-emerald-500" : "border-l-amber-500"}`}>
            <CardContent className="space-y-2 p-5 sm:p-6">
              <p className="font-semibold text-slate-700">
                {t("activity.recognized")}:{" "}
                <span className="english-font">{result.predicted_answer}</span>
              </p>
              <p className="font-semibold text-slate-700">
                {t("activity.expected")}:{" "}
                <span className="english-font">{result.expected_answer}</span>
              </p>
              <p className={`font-extrabold ${result.is_correct ? "text-emerald-700" : "text-amber-700"}`}>
                {result.is_correct ? t("activity.correct") : t("activity.wrong")}
              </p>
            </CardContent>
          </Card>
        </motion.div>
      )}
      {activityAttempt && result && !result.is_correct && (
        <Button onClick={retryQuestion} disabled={loading}>
          {t("activity.tryAgain")}
        </Button>
      )}

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3 sm:flex-row">
        {activityAttempt && (
          <Button
            variant="secondary"
            onClick={nextProblem}
            disabled={loading}
            className="w-full sm:w-auto"
          >
            {t("activity.next")}
          </Button>
        )}

        {activityAttempt && !finished && (
          <Button variant="outline" onClick={finishActivity} disabled={loading || !activityAttempt}>
            {t("activity.finish")}
          </Button>
        )}

        <Button
          variant="outline"
          onClick={() => navigate("/activity-report")}
          className="w-full sm:w-auto"
        >
          {t("activity.report") || "View report"}
        </Button>
      </div>
    </motion.section>
  );
}