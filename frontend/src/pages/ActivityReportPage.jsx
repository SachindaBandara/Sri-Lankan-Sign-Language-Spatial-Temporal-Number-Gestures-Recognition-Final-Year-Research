import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, BarChart3 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { useTranslation } from "../i18n";
import { getQuestionAttemptHistory } from "../services/api";

export default function ActivityReportPage() {
  const { t } = useTranslation();
  const [entries, setEntries] = useState([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState({ total_attempts: 0, correct: 0, points: 0 });
  const [error, setError] = useState("");

  useEffect(() => {
    getQuestionAttemptHistory(page)
      .then((result) => {
        setEntries(result.items);
        setTotal(result.total);
        setSummary(result.summary);
      })
      .catch((requestError) => setError(requestError.message));
  }, [page]);

  return (
    <section className="space-y-6 sm:space-y-8">
      <Card className="learning-card overflow-hidden">
        <CardHeader className="gap-5 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-7">
          <div className="flex items-start gap-3">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-violet-100 text-violet-700">
              <BarChart3 className="h-6 w-6" aria-hidden="true" />
            </span>
            <div className="space-y-2">
              <CardTitle className="text-xl font-black tracking-tight sm:text-2xl">
                {t("report.title") || "Activity Performance Report"}
              </CardTitle>
              <p className="text-sm leading-6 text-slate-600">
                {t("report.subtitle") || "Track questions, answers, correctness, and points."}
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button asChild variant="secondary">
              <Link to="/activities">
                <ArrowLeft className="mr-2 h-4 w-4" />
                {t("report.back") || "Back"}
              </Link>
            </Button>
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="learning-card">
          <CardContent className="p-6">
            <p className="text-sm text-slate-500">{t("report.totalAttempts") || "Valid answer attempts"}</p>
            <p className="english-font mt-2 text-3xl font-bold text-slate-900">{summary.total_attempts}</p>
          </CardContent>
        </Card>
        <Card className="learning-card">
          <CardContent className="p-6">
            <p className="text-sm text-slate-500">{t("report.correctAnswers") || "Correct answers"}</p>
            <p className="english-font mt-2 text-3xl font-bold text-emerald-600">{summary.correct}</p>
          </CardContent>
        </Card>
        <Card className="learning-card">
          <CardContent className="p-6">
            <p className="text-sm text-slate-500">{t("report.points") || "Points"}</p>
            <p className="english-font mt-2 text-3xl font-bold text-indigo-600">{summary.points}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="learning-card overflow-hidden">
        <CardHeader>
          <CardTitle className="text-lg font-extrabold sm:text-xl">{t("report.tableTitle") || "Performance details"}</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto px-4 sm:px-6">
          {error && <Alert variant="destructive" role="alert" className="mb-4"><AlertDescription>{error}</AlertDescription></Alert>}
          {entries.length === 0 ? (
            <p className="py-2 text-sm text-slate-500">{t("report.empty") || "No activity attempts recorded yet."}</p>
          ) : (
            <table aria-label={t("report.tableTitle") || "Performance details"} className="min-w-[42rem] border-collapse text-left text-sm">
              <thead className="bg-slate-50">
                <tr className="border-b border-slate-200 text-slate-500">
                  <th className="py-3 pr-4 font-semibold">{t("report.question") || "Question"}</th>
                  <th className="py-3 pr-4 font-semibold">{t("report.correctAnswer") || "Correct answer"}</th>
                  <th className="py-3 pr-4 font-semibold">{t("report.submittedAnswer") || "Submit answer"}</th>
                  <th className="py-3 pr-4 font-semibold">{t("report.result") || "Result"}</th>
                  <th className="py-3 pr-4 font-semibold">{t("report.points") || "Points"}</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="border-b border-slate-100 align-top transition-colors hover:bg-violet-50/50">
                    <td className="english-font py-4 pr-4 font-medium text-slate-900">{entry.question}</td>
                    <td className="english-font py-4 pr-4 text-slate-700">{entry.expected_answer ?? "—"}</td>
                    <td className="english-font py-4 pr-4 text-slate-700">{entry.submitted_answer ?? "—"}</td>
                    <td className={entry.is_correct ? "py-4 pr-4 font-semibold text-emerald-600" : "py-4 pr-4 font-semibold text-red-600"}>
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-bold ${entry.is_correct ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                        {entry.status === "skipped" ? t("activity.skipped") : entry.status === "invalid" ? t("activity.invalid") : entry.status === "unanswered" ? t("activity.unanswered") : entry.is_correct ? (t("activity.correct") || "Correct") : (t("activity.wrong") || "Incorrect")}
                      </span>
                    </td>
                    <td className="english-font py-4 pr-4 font-semibold text-indigo-600">{entry.is_correct ? 1 : 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {total > 100 && (
            <div className="flex items-center justify-between gap-3 py-4">
              <Button variant="outline" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>
                {t("report.previous")}
              </Button>
              <p className="text-sm text-slate-600">{page} / {Math.ceil(total / 100)}</p>
              <Button variant="outline" onClick={() => setPage((current) => current + 1)} disabled={page >= Math.ceil(total / 100)}>
                {t("report.next")}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}