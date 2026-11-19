import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Award,
  BookOpen,
  ChartNoAxesColumnIncreasing,
  CheckCircle2,
  Target,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import AccountPage from "./AccountPage";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { useTranslation } from "../i18n";
import { getAssignedStudents, getPersonalizedDashboard } from "../services/api";

function activityHref(operation) {
  return operation === "number_identification"
    ? "/number-identification"
    : `/activities?tab=${encodeURIComponent(operation)}`;
}

function learningPathHref(step) {
  if (step.operation_type === "number_identification") {
    return "/number-identification";
  }
  return `/activities?tab=${encodeURIComponent(step.operation_type)}&difficulty=${encodeURIComponent(step.difficulty_level)}`;
}

function MetricBar({ value, label }) {
  const percentage = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percentage}
      className="h-2.5 overflow-hidden rounded-full bg-slate-100"
    >
      <div className="h-full rounded-full bg-violet-600 transition-[width]" style={{ width: `${percentage}%` }} />
    </div>
  );
}

export default function LearningDashboardPage() {
  const { t, lang } = useTranslation();
  const { user, loading: authLoading } = useAuth();
  const isTeacher = user?.role === "teacher";
  const [students, setStudents] = useState([]);
  const [studentId, setStudentId] = useState("");
  const [dashboard, setDashboard] = useState(null);
  const [loadingStudents, setLoadingStudents] = useState(isTeacher);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isTeacher) return undefined;
    let active = true;
    setLoadingStudents(true);
    getAssignedStudents()
      .then(({ items }) => {
        if (!active) return;
        setStudents(items);
        setStudentId((selected) => selected || (items[0] ? String(items[0].id) : ""));
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoadingStudents(false);
      });
    return () => { active = false; };
  }, [isTeacher]);

  useEffect(() => {
    if (!user || (isTeacher && !studentId)) {
      setDashboard(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setDashboard(null);
    setError("");
    getPersonalizedDashboard(isTeacher ? studentId : undefined)
      .then((data) => {
        if (active) setDashboard(data);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [isTeacher, studentId, user]);

  const operationLabels = useMemo(() => ({
    number_identification: t("dashboard.numberIdentification"),
    addition: t("activity.addition"),
    subtraction: t("activity.subtraction"),
    multiplication: t("activity.multiplication"),
    division: t("activity.division"),
  }), [t]);

  const difficultyLabel = (difficulty) => t(`activity.${difficulty}`);
  const percent = (value) => value === null || value === undefined
    ? t("dashboard.notAvailable")
    : `${Math.round(value * 100)}%`;
  const recommendationReason = (recommendation) => {
    const progress = dashboard?.operations.find(
      (item) => item.operation_type === recommendation.operation_type,
    );
    if (recommendation.kind === "build_evidence") {
      return t("dashboard.recommendationReasons.buildEvidence", {
        count: Math.max(
          0,
          dashboard.minimum_attempts_for_adaptation - (progress?.total_attempts || 0),
        ),
      });
    }
    const explanation = t("dashboard.recommendationReasons.weakArea", {
      accuracy: percent(progress?.accuracy),
      recent: percent(progress?.recent_accuracy),
      difficulty: difficultyLabel(recommendation.difficulty_level),
    });
    const signals = dashboard?.weak_area_signals?.[recommendation.operation_type] || [];
    if (signals.length === 0) return explanation;
    return `${explanation} ${t("dashboard.weakSignalEvidence", {
      signals: signals.map((signal) => t(`dashboard.weakAreaSignals.${signal}`)).join(", "),
    })}`;
  };
  const formatResponseTime = (milliseconds) => milliseconds === null
    ? t("dashboard.notAvailable")
    : `${(milliseconds / 1000).toFixed(1)} s`;
  const weeklyDays = dashboard?.weekly_progress?.days || [];
  const maxDailyAttempts = Math.max(
    1,
    ...weeklyDays.map((day) => day.total_attempts),
  );
  const formatWeekday = (date) => new Date(`${date}T12:00:00Z`).toLocaleDateString(
    lang === "si" ? "si-LK" : "en-US",
    { weekday: "short", timeZone: "UTC" },
  );
  const formatShortDate = (date) => new Date(`${date}T12:00:00Z`).toLocaleDateString(
    lang === "si" ? "si-LK" : "en-US",
    { month: "numeric", day: "numeric", timeZone: "UTC" },
  );

  if (authLoading) return <p className="py-12 text-center text-slate-600">{t("account.pleaseWait")}</p>;
  if (!user) return <AccountPage />;

  return (
    <section className="space-y-6 sm:space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-violet-600">
            {t("dashboard.eyebrow")}
          </p>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900 sm:text-4xl">
            {isTeacher ? t("dashboard.teacherTitle") : t("dashboard.title")}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            {t("dashboard.subtitle")}
          </p>
        </div>
        {isTeacher && students.length > 0 && (
          <div className="w-full sm:max-w-xs">
            <label htmlFor="dashboard-student" className="mb-1.5 block text-sm font-bold text-slate-700">
              {t("dashboard.selectStudent")}
            </label>
            <select
              id="dashboard-student"
              value={studentId}
              onChange={(event) => setStudentId(event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500"
            >
              {students.map((student) => (
                <option key={student.id} value={student.id}>
                  {student.username}{student.grade ? ` · ${t("account.grade")} ${student.grade}` : ""}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm font-semibold text-rose-800">
          {error}
        </div>
      )}
      {loadingStudents && <p className="py-8 text-center text-slate-600">{t("account.pleaseWait")}</p>}
      {isTeacher && !loadingStudents && students.length === 0 && (
        <Card><CardContent className="p-6 text-sm text-slate-600">{t("dashboard.noStudents")}</CardContent></Card>
      )}
      {loading && <p className="py-8 text-center text-slate-600">{t("account.pleaseWait")}</p>}

      {dashboard && !loading && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Card className="learning-card">
              <CardContent className="flex items-center gap-4 p-5">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-violet-100 text-violet-700">
                  <ChartNoAxesColumnIncreasing className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-500">{t("dashboard.totalAttempts")}</p>
                  <p className="english-font text-2xl font-black text-slate-900">{dashboard.summary.total_attempts}</p>
                </div>
              </CardContent>
            </Card>
            <Card className="learning-card">
              <CardContent className="flex items-center gap-4 p-5">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-100 text-emerald-700">
                  <Target className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-500">{t("dashboard.overallAccuracy")}</p>
                  <p className="english-font text-2xl font-black text-slate-900">{percent(dashboard.summary.accuracy)}</p>
                </div>
              </CardContent>
            </Card>
            <Card className="learning-card">
              <CardContent className="flex items-center gap-4 p-5">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-sky-100 text-sky-700">
                  <TrendingUp className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-500">{t("dashboard.correctAnswers")}</p>
                  <p className="english-font text-2xl font-black text-slate-900">{dashboard.summary.correct_answers}</p>
                </div>
              </CardContent>
            </Card>
          </div>

          <section aria-labelledby="dashboard-weekly-title">
            <Card className="learning-card">
              <CardHeader>
                <CardTitle id="dashboard-weekly-title" className="text-lg font-black text-slate-900">
                  {t("dashboard.weeklyProgress")}
                </CardTitle>
                <p className="text-sm text-slate-600">{t("dashboard.weeklyProgressSubtitle")}</p>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-xs font-semibold text-slate-500">{t("dashboard.weeklyAttempts")}</p>
                    <p className="english-font mt-1 text-xl font-black text-slate-900">{dashboard.weekly_progress.total_attempts}</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-xs font-semibold text-slate-500">{t("dashboard.activeDays")}</p>
                    <p className="english-font mt-1 text-xl font-black text-slate-900">{dashboard.weekly_progress.active_days}/7</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-xs font-semibold text-slate-500">{t("dashboard.weeklyAccuracy")}</p>
                    <p className="english-font mt-1 text-xl font-black text-slate-900">{percent(dashboard.weekly_progress.accuracy)}</p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-3">
                    <p className="text-xs font-semibold text-slate-500">{t("dashboard.weeklyCompletedActivities")}</p>
                    <p className="english-font mt-1 text-xl font-black text-slate-900">{dashboard.weekly_progress.activities_completed}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-4 text-xs font-semibold text-slate-600" aria-hidden="true">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-3 w-3 rounded-sm bg-violet-300" />
                    {t("dashboard.dailyAttempts")}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <span className="h-3 w-3 rounded-sm bg-emerald-500" />
                    {t("dashboard.dailyCorrect")}
                  </span>
                </div>
                <div
                  role="img"
                  aria-label={t("dashboard.weeklyChartAria")}
                  className="grid grid-cols-7 gap-1 sm:gap-3"
                >
                  {weeklyDays.map((day) => {
                    const attemptsHeight = day.total_attempts
                      ? Math.max(8, (day.total_attempts / maxDailyAttempts) * 100)
                      : 0;
                    const correctHeight = day.correct_answers
                      ? Math.max(8, (day.correct_answers / maxDailyAttempts) * 100)
                      : 0;
                    return (
                      <div key={day.date} className="min-w-0 text-center">
                        <div aria-hidden="true" className="flex h-24 items-end justify-center gap-1 border-b border-slate-200">
                          <span
                            className="w-2.5 rounded-t bg-violet-300 sm:w-4"
                            style={{ height: `${attemptsHeight}%` }}
                          />
                          <span
                            className="w-2.5 rounded-t bg-emerald-500 sm:w-4"
                            style={{ height: `${correctHeight}%` }}
                          />
                        </div>
                        <p className="mt-2 truncate text-[10px] font-bold text-slate-600 sm:text-xs">
                          {formatWeekday(day.date)}
                        </p>
                        <p className="text-[10px] text-slate-500 sm:text-xs">{formatShortDate(day.date)}</p>
                        <p className="english-font mt-1 text-xs font-bold text-slate-800">{day.total_attempts}</p>
                        <p className="text-[10px] text-slate-500">{percent(day.accuracy)}</p>
                      </div>
                    );
                  })}
                </div>
                <div className="sr-only">
                  {weeklyDays.map((day) => (
                    <p key={`summary-${day.date}`}>
                      {formatWeekday(day.date)} {formatShortDate(day.date)}: {day.total_attempts}{" "}
                      {t("dashboard.dailyAttempts")}, {day.correct_answers} {t("dashboard.dailyCorrect")},
                      {" "}{t("dashboard.weeklyAccuracy")}: {percent(day.accuracy)}.
                    </p>
                  ))}
                </div>
              </CardContent>
            </Card>
          </section>

          <section aria-labelledby="dashboard-completion-title">
            <Card className="learning-card">
              <CardHeader>
                <CardTitle id="dashboard-completion-title" className="text-lg font-black text-slate-900">
                  {t("dashboard.activityCompletion")}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl bg-violet-50 p-4">
                    <p className="text-sm font-semibold text-slate-600">{t("dashboard.completedActivities")}</p>
                    <p className="english-font mt-1 text-2xl font-black text-violet-800">
                      {dashboard.activity_completion.completed_activities}/{dashboard.activity_completion.total_activities}
                    </p>
                  </div>
                  <div className="rounded-xl bg-emerald-50 p-4">
                    <p className="text-sm font-semibold text-slate-600">{t("dashboard.activityCompletionRate")}</p>
                    <p className="english-font mt-1 text-2xl font-black text-emerald-800">
                      {percent(dashboard.activity_completion.completion_rate)}
                    </p>
                  </div>
                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-sm font-semibold text-slate-600">{t("dashboard.activityStatus")}</p>
                    <p className="mt-1 text-xs leading-5 text-slate-700">
                      {t("dashboard.activityStatusSummary", {
                        inProgress: dashboard.activity_completion.in_progress_activities,
                        abandoned: dashboard.activity_completion.abandoned_activities,
                      })}
                    </p>
                  </div>
                </div>
                <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                  {dashboard.activity_completion.by_operation.map((item) => (
                    <div key={item.operation_type} className="space-y-1.5">
                      <div className="flex justify-between gap-3 text-xs">
                        <span className="font-bold text-slate-700">{operationLabels[item.operation_type]}</span>
                        <span className="english-font text-slate-600">
                          {item.completed_activities}/{item.total_activities} · {percent(item.completion_rate)}
                        </span>
                      </div>
                      <div
                        role="meter"
                        aria-label={t("dashboard.operationCompletion", {
                          operation: operationLabels[item.operation_type],
                        })}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={item.completion_rate === null ? 0 : Math.round(item.completion_rate * 100)}
                        className="h-2 overflow-hidden rounded-full bg-slate-100"
                      >
                        <div
                          className="h-full rounded-full bg-emerald-500"
                          style={{ width: `${item.completion_rate === null ? 0 : item.completion_rate * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </section>

          <section aria-labelledby="dashboard-strengths-title" className="grid gap-5 lg:grid-cols-2">
            <Card className="learning-card">
              <CardHeader>
                <CardTitle id="dashboard-strengths-title" className="flex items-center gap-2 text-lg font-black text-slate-900">
                  <Award className="h-5 w-5 text-amber-600" aria-hidden="true" />
                  {t("dashboard.strengths")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {dashboard.strengths.length === 0 ? (
                  <p className="text-sm leading-6 text-slate-600">{t("dashboard.noStrengths")}</p>
                ) : (
                  <ul className="space-y-3">
                    {dashboard.strengths.map((strength) => (
                      <li key={strength.operation_type} className="rounded-xl bg-amber-50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-extrabold text-slate-900">{operationLabels[strength.operation_type]}</span>
                          <span className="english-font rounded-full bg-white px-3 py-1 text-sm font-black text-amber-800">
                            {percent(strength.accuracy)}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-600">
                          {t("dashboard.strengthEvidence", {
                            attempts: strength.total_attempts,
                            recent: percent(strength.recent_accuracy),
                          })}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card className="learning-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg font-black text-slate-900">
                  <Trophy className="h-5 w-5 text-amber-600" aria-hidden="true" />
                  {t("dashboard.achievements")}
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 sm:grid-cols-2">
                {dashboard.achievements.map((achievement) => (
                  <div
                    key={achievement.id}
                    className={`rounded-xl border p-3 ${achievement.earned ? "border-amber-200 bg-amber-50" : "border-slate-100 bg-slate-50"}`}
                  >
                    <div className="flex items-start gap-2">
                      <CheckCircle2
                        className={`mt-0.5 h-4 w-4 shrink-0 ${achievement.earned ? "text-emerald-600" : "text-slate-300"}`}
                        aria-hidden="true"
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-extrabold text-slate-900">
                          {t(`dashboard.achievementNames.${achievement.id}`)}
                        </p>
                        {achievement.id === "operation_strength" && achievement.operation_type && (
                          <p className="mt-1 text-xs text-slate-600">
                            {operationLabels[achievement.operation_type]}
                          </p>
                        )}
                        <p className="mt-1 text-xs text-slate-600">
                          {achievement.earned
                            ? t("dashboard.achievementEarned")
                            : t("dashboard.achievementProgress", {
                              progress: achievement.progress,
                              target: achievement.target,
                            })}
                        </p>
                      </div>
                    </div>
                    <div
                      role="progressbar"
                      aria-label={t(`dashboard.achievementNames.${achievement.id}`)}
                      aria-valuemin={0}
                      aria-valuemax={achievement.target}
                      aria-valuenow={achievement.progress}
                      className="mt-3 h-1.5 overflow-hidden rounded-full bg-white"
                    >
                      <div
                        className="h-full rounded-full bg-amber-500"
                        style={{ width: `${Math.min(100, (achievement.progress / achievement.target) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </section>

          <section aria-labelledby="dashboard-performance-title" className="space-y-4">
            <div>
              <h2 id="dashboard-performance-title" className="text-xl font-black text-slate-900">
                {t("dashboard.performance")}
              </h2>
              <p className="mt-1 text-sm text-slate-600">{t("dashboard.numberIdentificationNote")}</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {dashboard.operations.map((operation) => {
                const isRecognition = operation.operation_type === "number_identification";
                const value = operation.accuracy;
                return (
                  <Card key={operation.operation_type} className="learning-card">
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <CardTitle className="text-base font-extrabold text-slate-900">
                          {operationLabels[operation.operation_type]}
                        </CardTitle>
                        {!isRecognition && (
                          <span className="shrink-0 rounded-full bg-violet-50 px-3 py-1 text-xs font-bold text-violet-700">
                            {difficultyLabel(operation.current_difficulty)}
                          </span>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex justify-between gap-3 text-sm">
                        <span className="font-semibold text-slate-600">
                          {isRecognition ? t("dashboard.numberAccuracy") : t("dashboard.accuracy")}
                        </span>
                        <span className="english-font font-black text-slate-900">{percent(value)}</span>
                      </div>
                      {value === null || value === undefined ? (
                        <p className="text-xs text-slate-500">{t("dashboard.noPerformanceData")}</p>
                      ) : (
                        <MetricBar value={value} label={operationLabels[operation.operation_type]} />
                      )}
                      {isRecognition ? (
                        <div className="space-y-2 text-xs leading-5 text-slate-600">
                          <p>
                            {t("dashboard.targetAnswers", {
                              correct: operation.correct_answers,
                              total: operation.total_attempts,
                            })}
                          </p>
                          <p>
                            {t("dashboard.averageConfidence")}: {percent(operation.average_recognition_confidence)}
                          </p>
                          <p className="text-slate-500">
                            {t("dashboard.highConfidenceRecognitions", {
                              recognized: operation.high_confidence_recognitions,
                              total: operation.recognition_events,
                            })}
                          </p>
                        </div>
                      ) : (
                        <>
                          <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-600">
                            <span>{t("dashboard.correctAnswers")}: {operation.correct_answers}/{operation.total_attempts}</span>
                            <span>
                              {operation.sample_sufficient
                                ? t("dashboard.evidenceReady")
                                : t("dashboard.moreEvidence", {
                                  count: Math.max(0, dashboard.minimum_attempts_for_adaptation - operation.total_attempts),
                                })}
                            </span>
                          </div>
                          <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-600">
                            <span>{t("dashboard.recentAccuracy")}: {percent(operation.recent_accuracy)}</span>
                            <span>
                              {t("dashboard.trend")}: {operation.improvement_rate === null
                                ? t("dashboard.notAvailable")
                                : `${operation.improvement_rate > 0 ? "+" : ""}${Math.round(operation.improvement_rate * 100)}%`}
                            </span>
                          </div>
                          <p className="text-xs text-slate-600">
                            {t("dashboard.averageResponseTime")}: {formatResponseTime(operation.average_response_time_ms)}
                          </p>
                        </>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="learning-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg font-black">
                  <Target className="h-5 w-5 text-rose-600" aria-hidden="true" />
                  {t("dashboard.weakAreas")}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {dashboard.weak_areas.length === 0 ? (
                  <p className="text-sm leading-6 text-slate-600">{t("dashboard.noWeakAreas")}</p>
                ) : (
                  <ul className="space-y-2">
                    {dashboard.weak_areas.map((operation) => {
                      const signals = dashboard.weak_area_signals?.[operation] || [];
                      return (
                        <li key={operation} className="flex items-center justify-between gap-3 rounded-xl bg-rose-50 px-4 py-3">
                          <div className="min-w-0">
                            <span className="font-bold text-slate-800">{operationLabels[operation]}</span>
                            {signals.length > 0 && (
                              <p className="mt-1 text-xs leading-5 text-rose-800">
                                {signals.map((signal) => t(`dashboard.weakAreaSignals.${signal}`)).join(" · ")}
                              </p>
                            )}
                          </div>
                          {!isTeacher && (
                            <Link className="shrink-0 text-sm font-extrabold text-violet-700 hover:text-violet-900" to={activityHref(operation)}>
                              {t("dashboard.practice")} <ArrowRight className="inline h-4 w-4" aria-hidden="true" />
                            </Link>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card className="learning-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg font-black">
                  <BookOpen className="h-5 w-5 text-violet-600" aria-hidden="true" />
                  {t("dashboard.recommendations")}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {dashboard.recommendations.length === 0 ? (
                  <p className="text-sm leading-6 text-slate-600">{t("dashboard.noRecommendations")}</p>
                ) : dashboard.recommendations.map((recommendation) => (
                  <div key={recommendation.id} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-extrabold text-slate-900">
                          {recommendation.activity?.title_key
                            ? t(recommendation.activity.title_key)
                            : operationLabels[recommendation.operation_type]}
                        </p>
                        {recommendation.activity && (
                          <div className="mt-1 space-y-1 text-sm leading-5 text-slate-600">
                            <p>{t(`dashboard.activityTypes.${recommendation.activity.activity_type}`)}</p>
                            <p>{t(recommendation.activity.description_key)}</p>
                            <p>
                              <span className="font-bold">{t("dashboard.learningObjective")}:</span>{" "}
                              {t(recommendation.activity.objective_key)}
                            </p>
                          </div>
                        )}
                        <p className="mt-1 text-sm leading-5 text-slate-600">{recommendationReason(recommendation)}</p>
                      </div>
                      {recommendation.operation_type !== "number_identification" && (
                        <span className="shrink-0 rounded-full bg-violet-100 px-2.5 py-1 text-xs font-bold text-violet-700">
                          {difficultyLabel(recommendation.difficulty_level)}
                        </span>
                      )}
                    </div>
                    {!isTeacher && (
                      <Link to={recommendation.activity?.route || activityHref(recommendation.operation_type)} className="mt-3 inline-flex items-center gap-1 text-sm font-extrabold text-violet-700 hover:text-violet-900">
                        {t("dashboard.practice")} <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </Link>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <Card className="learning-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg font-black">
                <BookOpen className="h-5 w-5 text-sky-700" aria-hidden="true" />
                {t("dashboard.learningPath")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dashboard.learning_path && (
                <div className="mb-5 space-y-2">
                  <div className="flex justify-between gap-3 text-sm">
                    <span className="font-semibold text-slate-600">{t("dashboard.pathProgress")}</span>
                    <span className="english-font font-black text-slate-900">
                      {dashboard.learning_path.progress_percentage}%
                    </span>
                  </div>
                  <div
                    role="progressbar"
                    aria-label={t("dashboard.pathProgress")}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={dashboard.learning_path.progress_percentage}
                    className="h-2.5 overflow-hidden rounded-full bg-slate-100"
                  >
                    <div
                      className="h-full rounded-full bg-sky-600 transition-[width]"
                      style={{ width: `${dashboard.learning_path.progress_percentage}%` }}
                    />
                  </div>
                </div>
              )}
              <ol className="grid gap-3 md:grid-cols-2">
                {dashboard.learning_path?.steps.map((step) => (
                  <li key={step.id} className={`rounded-xl border p-4 ${step.status === "in_progress" ? "border-violet-200 bg-violet-50" : "border-slate-100 bg-white"}`}>
                    <div className="flex items-start gap-3">
                      <span className={`english-font grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-black ${step.status === "completed" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}`}>
                        {step.sequence_number}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-extrabold text-slate-900">
                          {t(`dashboard.pathSkills.${step.skill_key}`)}
                        </p>
                        <p className="mt-1 text-xs font-semibold text-slate-500">
                          {operationLabels[step.operation_type]}
                        </p>
                        <p className="mt-1 text-sm leading-5 text-slate-600">{t(`dashboard.pathReasons.${step.reason}`)}</p>
                        <p className="mt-2 text-xs font-bold text-violet-700">
                          {t(`dashboard.stepStatus.${step.status}`)}
                          {step.operation_type !== "number_identification" && ` · ${difficultyLabel(step.difficulty_level)}`}
                        </p>
                        {!isTeacher && step.status === "in_progress" && (
                          <Link to={learningPathHref(step)} className="mt-3 inline-flex items-center gap-1 text-sm font-extrabold text-violet-700">
                            {t("dashboard.openStep")} <ArrowRight className="h-4 w-4" aria-hidden="true" />
                          </Link>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>

          <Card className="learning-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg font-black">
                <TrendingUp className="h-5 w-5 text-emerald-700" aria-hidden="true" />
                {t("dashboard.difficultyHistory")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {dashboard.difficulty_history.length === 0 ? (
                <p className="text-sm leading-6 text-slate-600">{t("dashboard.noAdjustments")}</p>
              ) : (
                <ol className="space-y-3">
                  {dashboard.difficulty_history.map((adjustment, index) => (
                    <li key={`${adjustment.operation_type}-${adjustment.created_at}-${index}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 p-4">
                      <div>
                        <p className="font-extrabold text-slate-900">{operationLabels[adjustment.operation_type]}</p>
                        <p className="mt-1 text-sm text-slate-600">
                          {difficultyLabel(adjustment.previous_difficulty)} → {difficultyLabel(adjustment.new_difficulty)}
                        </p>
                      </div>
                      <p className="text-xs font-semibold text-slate-600">
                        {t("dashboard.recentAccuracy")}: {percent(adjustment.recent_accuracy)}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </section>
  );
}
