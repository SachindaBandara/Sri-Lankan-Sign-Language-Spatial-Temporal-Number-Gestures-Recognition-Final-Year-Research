import React from "react";
import { Plus, Minus, X, Divide } from "lucide-react";
import { motion } from "framer-motion";
import { useSearchParams } from "react-router-dom";
import { cn } from "../lib/utils";
import { useTranslation } from "../i18n";
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";

const ACTIVITY_MODULES = [
  { key: "addition", labelKey: "activity.addition", icon: Plus },
  { key: "subtraction", labelKey: "activity.subtraction", icon: Minus },
  { key: "multiplication", labelKey: "activity.multiplication", icon: X },
  { key: "division", labelKey: "activity.division", icon: Divide },
];

export default function ActivityNav({ className }) {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const [searchParams, setSearchParams] = useSearchParams();
  const current = searchParams.get("tab") || "addition";

  function select(key) {
    searchParams.set("tab", key);
    setSearchParams(searchParams, { replace: true });
  }

  return (
    <div
      role="group"
      aria-label={t("activity.chooseGame")}
      className={cn("grid grid-cols-2 gap-2 px-1 py-1 sm:flex sm:flex-nowrap sm:overflow-x-auto", className)}
    >
      {ACTIVITY_MODULES.map((m) => {
        const Icon = m.icon;
        const active = current === m.key;
        return (
          <motion.button
            key={m.key}
            onClick={() => select(m.key)}
            aria-pressed={active}
            whileHover={reduceMotion ? undefined : { y: -2 }}
            whileTap={reduceMotion ? undefined : { scale: 0.96 }}
            transition={{ duration: reduceMotion ? 0 : 0.16 }}
            className={cn(
              "inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full px-2 py-2 text-center text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 sm:w-auto sm:shrink-0 sm:px-4 sm:text-sm",
              active
                ? "bg-violet-600 text-white shadow-sm"
                : "border border-slate-200 bg-white/80 text-slate-600 hover:bg-violet-50 hover:text-violet-700"
            )}
          >
            <Icon className="h-4 w-4" />
            {t(m.labelKey)}
          </motion.button>
        );
      })}
    </div>
  );
}
