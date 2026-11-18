import { ArrowRight, BookOpen, Calculator, Hand, Sparkles, Star } from "lucide-react";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Card, CardContent } from "../components/ui/card";
import { useTranslation } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

export default function HomePage() {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();

  const learningOptions = [
    {
      to: "/number-identification",
      icon: Hand,
      iconClass: "bg-sky-100 text-sky-700",
      className: "hover:border-sky-200",
      title: t("home.numbersTitle"),
      description: t("home.numbersDescription"),
      action: t("home.numbersAction"),
    },
    {
      to: "/activities",
      icon: Calculator,
      iconClass: "bg-amber-100 text-amber-700",
      className: "hover:border-amber-200",
      title: t("home.gamesTitle"),
      description: t("home.gamesDescription"),
      action: t("home.gamesAction"),
    },
  ];

  return (
    <section className="space-y-8 sm:space-y-10">
      <motion.div
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0.18 : 0.55, ease: "easeOut" }}
      >
        <Card className="relative isolate overflow-hidden rounded-[2rem] border-0 bg-gradient-to-br from-violet-600 via-violet-600 to-indigo-700 text-white shadow-[0_24px_70px_rgba(87,65,194,0.22)]">
          <div className="pointer-events-none absolute -right-14 -top-20 h-64 w-64 rounded-full bg-white/10" />
          <div className="pointer-events-none absolute bottom-[-5rem] right-[22%] h-48 w-48 rounded-full bg-fuchsia-400/20 blur-2xl" />
          <CardContent className="relative grid items-center gap-8 p-6 sm:p-9 md:grid-cols-[1.25fr_0.75fr] md:p-12">
            <div className="max-w-2xl">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-bold tracking-wide text-violet-50 sm:text-sm">
                <motion.span
                  className="inline-flex text-amber-300"
                  animate={reduceMotion ? undefined : { rotate: [0, -10, 10, 0], scale: [1, 1.12, 1] }}
                  transition={{ duration: 3.6, repeat: Infinity, ease: "easeInOut" }}
                >
                  <Sparkles className="h-4 w-4" aria-hidden="true" />
                </motion.span>
                {t("home.eyebrow")}
              </div>
              <h1 className="text-3xl font-black leading-tight tracking-tight sm:text-4xl md:text-5xl">
                {t("home.welcome")}
                <span className="mt-1 block text-amber-200">{t("home.headline")}</span>
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-7 text-violet-100 sm:text-base">
                {t("home.p1")}
              </p>
              <p className="mt-2 max-w-xl text-sm leading-7 text-violet-100/90 sm:text-base">
                {t("home.p2")}
              </p>
              <Link
                to="/number-identification"
                className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-2xl bg-amber-300 px-5 py-3 text-sm font-extrabold text-violet-950 shadow-lg shadow-violet-950/15 transition hover:-translate-y-0.5 hover:bg-amber-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-violet-700 sm:w-auto"
              >
                {t("home.startLearning")}
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>

            <div className="relative mx-auto hidden h-56 w-full max-w-xs items-center justify-center md:flex">
              <div className="absolute h-48 w-48 rounded-full border border-white/20 bg-white/10" />
              <div className="absolute h-36 w-36 rounded-full border border-dashed border-white/40" />
              <motion.div
                className="relative grid h-28 w-28 place-items-center rounded-[2rem] bg-amber-300 text-violet-800 shadow-xl shadow-violet-950/20"
                animate={reduceMotion ? undefined : { y: [0, -8, 0], rotate: [0, 3, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              >
                <Hand className="h-14 w-14" strokeWidth={1.8} aria-hidden="true" />
              </motion.div>
              <span className="absolute left-5 top-6 grid h-12 w-12 place-items-center rounded-2xl bg-sky-300 text-lg font-black text-sky-950 shadow-lg">0</span>
              <span className="absolute right-2 top-14 grid h-12 w-12 place-items-center rounded-2xl bg-pink-300 text-lg font-black text-pink-950 shadow-lg">5</span>
              <span className="absolute bottom-1 left-12 grid h-12 w-12 place-items-center rounded-2xl bg-emerald-300 text-lg font-black text-emerald-950 shadow-lg">10</span>
              <span className="absolute bottom-6 right-4 grid h-11 w-11 place-items-center rounded-2xl bg-white text-violet-700 shadow-lg">
                <Star className="h-5 w-5 fill-current" aria-hidden="true" />
              </span>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="grid gap-3 sm:grid-cols-2">
        <motion.div
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0.18 : 0.4, delay: reduceMotion ? 0 : 0.1 }}
          className="flex items-center gap-4 rounded-2xl border border-sky-100 bg-sky-50/80 p-4 sm:p-5"
        >
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white text-sky-600 shadow-sm">
            <Hand className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="text-lg font-black text-slate-900">0–50</p>
            <p className="text-sm font-semibold text-slate-600">{t("home.numberRange")}</p>
          </div>
        </motion.div>
        <motion.div
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0.18 : 0.4, delay: reduceMotion ? 0 : 0.18 }}
          className="flex items-center gap-4 rounded-2xl border border-amber-100 bg-amber-50/80 p-4 sm:p-5"
        >
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white text-amber-600 shadow-sm">
            <BookOpen className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="text-lg font-black text-slate-900">{t("home.learnByDoing")}</p>
            <p className="text-sm font-semibold text-slate-600">{t("home.learnByDoingDescription")}</p>
          </div>
        </motion.div>
      </div>

      <div className="space-y-4">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-violet-600">
            {t("home.chooseLabel")}
          </p>
          <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-900 sm:text-3xl">
            {t("home.chooseTitle")}
          </h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {learningOptions.map((option) => (
            <motion.div
              key={option.to}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              whileHover={reduceMotion ? undefined : { y: -4 }}
              whileTap={reduceMotion ? undefined : { scale: 0.98 }}
              transition={{ duration: reduceMotion ? 0.18 : 0.35, delay: reduceMotion ? 0 : 0.12 }}
              className="h-full"
            >
              <Link
                to={option.to}
                className="group rounded-[1.5rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2"
              >
                <Card className={`learning-card learning-card-hover h-full ${option.className}`}>
                  <CardContent className="flex h-full items-start gap-4 p-5 sm:p-6">
                    <span className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl ${option.iconClass}`}>
                      <option.icon className="h-7 w-7" aria-hidden="true" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-lg font-extrabold text-slate-900">{option.title}</h3>
                      <p className="mt-1 text-sm leading-6 text-slate-600">{option.description}</p>
                      <span className="mt-4 inline-flex items-center gap-2 text-sm font-extrabold text-violet-700">
                        {option.action}
                        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" aria-hidden="true" />
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
