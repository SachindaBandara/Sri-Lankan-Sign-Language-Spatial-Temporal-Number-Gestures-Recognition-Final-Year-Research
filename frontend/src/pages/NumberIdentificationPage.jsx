import { useCallback, useState } from "react";
import { Hand, LoaderCircle, Sparkles } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import WebcamRecorder from "../components/WebcamRecorder";
import { predictNumber } from "../services/api";
import { Card, CardContent } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { useTranslation } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

export default function NumberIdentificationPage() {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleVideo = useCallback(async (videoBase64) => {
    setLoading(true);
    setError("");
    setPrediction(null);

    try {
      const data = await predictNumber(videoBase64);
      setPrediction(data.predicted_number);
    } catch (err) {
      setError(
        err.message === "No hand landmarks detected in the video"
          ? t("number.noHandDetected")
          : err.message
      );
    } finally {
      setLoading(false);
    }
  }, [t]);

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
        <WebcamRecorder onVideoCapture={handleVideo} className="learning-card" />

        <Card className="flex min-h-[28rem] flex-col items-center justify-center overflow-hidden rounded-[1.5rem] border-0 bg-gradient-to-br from-sky-500 via-blue-600 to-violet-700 text-white shadow-[0_16px_40px_rgba(54,91,197,0.2)]">
          <CardContent className="flex w-full flex-1 flex-col items-center justify-center p-6 text-center sm:p-8">
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-white/15 text-sky-100 ring-1 ring-white/20">
              {loading ? (
                <LoaderCircle className="h-7 w-7 animate-spin" aria-hidden="true" />
              ) : prediction !== null ? (
                <Sparkles className="h-7 w-7" aria-hidden="true" />
              ) : (
                <Hand className="h-7 w-7" aria-hidden="true" />
              )}
            </div>
            <p className="text-sm font-bold text-white/80">{t("number.predicted")}</p>
            <p aria-live="polite" className="mt-2 min-h-[5rem] text-7xl font-black leading-none tracking-tight sm:text-8xl">
              <AnimatePresence mode="wait">
                <motion.span
                  key={loading ? "processing" : prediction ?? "waiting"}
                  initial={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.7, y: 8 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.85, y: -6 }}
                  transition={{ duration: reduceMotion ? 0.15 : 0.22, ease: "easeOut" }}
                  className="inline-block"
                >
                  {loading ? "…" : prediction ?? "?"}
                </motion.span>
              </AnimatePresence>
            </p>
            <p className="mt-4 max-w-xs text-sm leading-6 text-white/80">
              {loading
                ? t("number.processing")
                : prediction !== null
                  ? t("number.resultHint")
                  : t("number.waitingHint")}
            </p>
          </CardContent>
        </Card>
      </div>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </motion.section>
  );
}
