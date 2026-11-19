import { useCallback, useEffect, useState } from "react";
import { Hand, LoaderCircle, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import WebcamRecorder from "../components/WebcamRecorder";
import {
  completeStudentActivity,
  getNumberIdentificationQuestion,
  predictNumber,
  recordRecognition,
  startStudentActivity,
} from "../services/api";
import { Card, CardContent } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { useTranslation } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import { Button } from "../components/ui/button";

export default function NumberIdentificationPage() {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activityAttempt, setActivityAttempt] = useState(null);
  const [numberQuestion, setNumberQuestion] = useState(null);
  const [answerCorrect, setAnswerCorrect] = useState(null);
  const [recognitionStatus, setRecognitionStatus] = useState(null);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    let active = true;
    startStudentActivity("number_identification")
      .then(async (activity) => {
        const question = await getNumberIdentificationQuestion(activity.id);
        if (active) {
          setActivityAttempt(activity);
          setNumberQuestion(question);
        }
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      });
    return () => { active = false; };
  }, []);

  const handleVideo = useCallback(async (videoBase64) => {
    if (!activityAttempt || !numberQuestion) {
      setError(t("account.pleaseWait"));
      return;
    }
    setLoading(true);
    setError("");
    setPrediction(null);
    setAnswerCorrect(null);
    setRecognitionStatus(null);

    try {
      const data = await predictNumber(videoBase64);
      let trackedResult;
      try {
        trackedResult = await recordRecognition({
          activity_attempt_id: activityAttempt.id,
          number_question_id: numberQuestion.id,
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
      setPrediction(data.predicted_number);
      setRecognitionStatus(trackedResult.status);
      setAnswerCorrect(trackedResult.is_correct);
    } catch (err) {
      if (err.message === "No hand landmarks detected in the video") {
        try {
          await recordRecognition({
            activity_attempt_id: activityAttempt.id,
            number_question_id: numberQuestion.id,
            gesture_detected: false,
            status: "no_gesture",
          });
          setRecognitionStatus("no_gesture");
        } catch (trackingError) {
          setError(trackingError.message);
        }
        setError(t("number.noHandDetected"));
      } else {
        try {
          await recordRecognition({
            activity_attempt_id: activityAttempt.id,
            number_question_id: numberQuestion.id,
            gesture_detected: false,
            status: "processing_failed",
          });
        } catch (trackingError) {
          setError(trackingError.message);
        }
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [activityAttempt, numberQuestion, t]);

  const finishActivity = async () => {
    if (!activityAttempt || loading) return;
    setLoading(true);
    setError("");
    try {
      await completeStudentActivity("number_identification", activityAttempt.id);
      setActivityAttempt(null);
      setFinished(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const startAgain = async () => {
    setLoading(true);
    setError("");
    try {
      const activity = await startStudentActivity("number_identification");
      const question = await getNumberIdentificationQuestion(activity.id);
      setActivityAttempt(activity);
      setNumberQuestion(question);
      setFinished(false);
      setPrediction(null);
      setAnswerCorrect(null);
      setRecognitionStatus(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  const nextQuestion = async () => {
    if (!activityAttempt || answerCorrect !== true || loading) return;
    setLoading(true);
    setError("");
    try {
      const question = await getNumberIdentificationQuestion(activityAttempt.id);
      setNumberQuestion(question);
      setPrediction(null);
      setAnswerCorrect(null);
      setRecognitionStatus(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.section
      initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0.18 : 0.35, ease: "easeOut" }}
      className="space-y-6 sm:space-y-8"
    >
      <div className="max-w-2xl">
        <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-sky-700">
          {t("number.eyebrow")}
        </p>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 sm:text-4xl">
          {t("number.pageTitle")}
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-600 sm:text-base">
          {t("number.pageDescription")}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr] lg:items-stretch">
        {!finished && (
          <WebcamRecorder
            onVideoCapture={handleVideo}
            className="learning-card"
          />
        )}

        <div className="grid content-center gap-4">
          <Card className="flex min-h-[15rem] flex-col items-center justify-center overflow-hidden rounded-[1.5rem] border-0 bg-gradient-to-br from-sky-500 via-blue-600 to-violet-700 text-white shadow-[0_16px_40px_rgba(54,91,197,0.2)]">
            <CardContent className="flex w-full flex-1 flex-col items-center justify-center p-6 text-center sm:p-8">
              <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-white/15 text-sky-100 ring-1 ring-white/20">
                <Hand className="h-7 w-7" aria-hidden="true" />
              </div>
              <p className="text-sm font-bold text-white/80">{t("number.signThis")}</p>
              <p className="english-font mt-2 min-h-[4rem] text-6xl font-black leading-none tracking-tight sm:text-7xl">
                {numberQuestion?.target_value ?? "…"}
              </p>
            </CardContent>
          </Card>

          <Card className="flex min-h-[12rem] flex-col items-center justify-center rounded-[1.5rem] border border-blue-100 bg-white shadow-[0_12px_30px_rgba(54,91,197,0.1)]">
            <CardContent className="flex w-full flex-1 flex-col items-center justify-center p-5 text-center sm:p-6">
              <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-violet-50 text-violet-600">
                {loading ? (
                  <LoaderCircle className="h-5 w-5 animate-spin" aria-hidden="true" />
                ) : (
                  <Sparkles className="h-5 w-5" aria-hidden="true" />
                )}
              </div>
              <p className="text-sm font-bold text-slate-500">{t("number.predicted")}</p>
              <p aria-live="polite" className="mt-1 min-h-[3.5rem] text-5xl font-black leading-none tracking-tight text-slate-900 sm:text-6xl">
                <AnimatePresence mode="wait">
                  <motion.span
                    key={loading ? "processing" : prediction ?? "waiting"}
                    initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.7, y: 8 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.85, y: -6 }}
                    transition={{ duration: reduceMotion ? 0.15 : 0.22, ease: "easeOut" }}
                    className="english-font inline-block"
                  >
                    {loading ? "…" : prediction ?? "?"}
                  </motion.span>
                </AnimatePresence>
              </p>
              <p aria-live="polite" className="mt-3 max-w-xs text-sm font-bold leading-6 text-slate-600">
                {loading ? t("number.processing")
                  : recognitionStatus === "low_confidence" ? t("activity.lowConfidence")
                    : answerCorrect === true ? t("number.correct")
                      : answerCorrect === false ? t("number.incorrect")
                        : t("number.waitingHint")}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {finished ? (
        <Button onClick={startAgain} disabled={loading}>{t("activity.next")}</Button>
      ) : (
        <div className="flex flex-wrap gap-3">
          {answerCorrect === true && (
            <Button onClick={nextQuestion} disabled={loading}>
              {t("number.nextTarget")}
            </Button>
          )}
          <Button onClick={finishActivity} disabled={!activityAttempt || loading}>
            {t("activity.finish")}
          </Button>
        </div>
      )}
    </motion.section>
  );
}
