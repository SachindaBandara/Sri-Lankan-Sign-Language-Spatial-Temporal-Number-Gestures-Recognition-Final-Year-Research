import { useCallback, useEffect, useState } from "react";
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
  generateQuestion,
  predictNumber,
  validateActivityAnswer,
} from "../services/api";

const ACTIVITY_REPORT_KEY = "activity-performance-report";

function readReportEntries() {
  try {
    return JSON.parse(localStorage.getItem(ACTIVITY_REPORT_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeReportEntry(entry) {
  const current = readReportEntries();
  localStorage.setItem(ACTIVITY_REPORT_KEY, JSON.stringify([entry, ...current]));
}

export default function ActivityPage({ operation, title, icon }) {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const navigate = useNavigate();
  const [problem, setProblem] = useState(null);
  const [livePrediction, setLivePrediction] = useState("--");
  const [result, setResult] = useState(null);
  const [score, setScore] = useState({ correct: 0, total: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const displayOperator = operation === "division" ? "÷" : problem?.operator;

  const loadProblem = async () => {
    setError("");
    setResult(null);
    const storageKey = `activity-current-problem-${operation}`;
    // If a saved problem exists for this operation, load it (persist across navigation/refresh)
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setProblem(parsed);
        return;
      } catch {
        // fall through to fetch a new problem
      }
    }

    const data = await generateQuestion(operation);
    setProblem(data);
    try {
      localStorage.setItem(storageKey, JSON.stringify(data));
    } catch {}
  };

  useEffect(() => {
    loadProblem().catch((err) => setError(err.message));
  }, [operation]);

  /**
   * FIX: video-based prediction (not frame streaming)
   */
  const handleVideo = useCallback(async (videoBase64) => {
    setLoading(true);
    setError("");
    setLivePrediction("--");

    try {
      const data = await predictNumber(videoBase64);

      setLivePrediction(String(data.predicted_number));
    } catch (err) {
      if (err.message !== "No hand landmarks detected in the video") {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * FIXED backend payload
   */
  const submitLiveAnswer = async () => {
    if (!problem || livePrediction === "--") return;

    setLoading(true);
    setError("");

    try {
      const evaluation = await validateActivityAnswer({
        operation,
        left: problem.left,
        right: problem.right,
        predicted_number: Number(livePrediction), // ✅ FIXED
      });

      setResult(evaluation);

      writeReportEntry({
        id: crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        operation,
        title,
        question: `${problem.left} ${displayOperator} ${problem.right} = ?`,
        correctAnswer: evaluation.expected_answer,
        submittedAnswer: livePrediction,
        isCorrect: Boolean(evaluation.is_correct),
        points: evaluation.is_correct ? 1 : 0,
        createdAt: new Date().toISOString(),
      });

      setScore((prev) => ({
        correct: prev.correct + (evaluation.is_correct ? 1 : 0),
        total: prev.total + 1,
      }));
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

      <Card className="learning-card overflow-hidden">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-bold text-slate-600">
            {t("activity.solveThis")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div aria-live="polite" className="flex min-h-24 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-r from-violet-50 to-sky-50 px-3 py-5 text-3xl font-black tracking-wide text-slate-900 sm:min-h-28 sm:text-5xl">
            <AnimatePresence mode="wait">
              <motion.span
                key={problem ? `${problem.left}-${problem.operator}-${problem.right}` : "loading"}
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

      <div className="grid gap-4 lg:grid-cols-2">
        <WebcamRecorder onVideoCapture={handleVideo} />

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
                  className="inline-block"
                >
                  {loading ? "…" : livePrediction}
                </motion.span>
              </AnimatePresence>
            </p>
            <p className="mt-3 text-sm font-semibold text-white/80">
              {t("activity.score")}: {score.correct}/{score.total}
            </p>

            {!result && (
              <motion.div
                className="mt-5 w-full sm:w-auto"
                whileTap={reduceMotion ? undefined : { scale: 0.96 }}
              >
                <Button
                  className="w-full bg-amber-300 text-violet-950 hover:bg-amber-200 sm:w-auto"
                  onClick={submitLiveAnswer}
                  disabled={!problem || livePrediction === "--" || loading}
                >
                  {t("activity.submit")}
                </Button>
              </motion.div>
            )}
          </CardContent>
        </Card>
      </div>

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
              <p className="font-semibold text-slate-700">{t("activity.recognized")}: {result.predicted_answer}</p>
              <p className="font-semibold text-slate-700">{t("activity.expected")}: {result.expected_answer}</p>
              <p className={`font-extrabold ${result.is_correct ? "text-emerald-700" : "text-amber-700"}`}>
                {result.is_correct ? t("activity.correct") : t("activity.wrong")}
              </p>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          variant="secondary"
          onClick={async () => {
            // Force-generate a new problem and persist it
            setError("");
            setResult(null);
            setLivePrediction("--");
            setLoading(true);
            try {
              const data = await generateQuestion(operation);
              setProblem(data);
              const storageKey = `activity-current-problem-${operation}`;
              try { localStorage.setItem(storageKey, JSON.stringify(data)); } catch {}
            } catch (err) {
              setError(err.message);
            } finally {
              setLoading(false);
            }
          }}
          disabled={loading}
          className="w-full sm:w-auto"
        >
          {t("activity.next")}
        </Button>

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