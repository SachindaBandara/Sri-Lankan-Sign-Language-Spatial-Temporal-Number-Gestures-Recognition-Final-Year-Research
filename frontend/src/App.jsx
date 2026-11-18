import { Calculator, Hand, House, Sparkles } from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import ActivitiesPage from "./pages/ActivitiesPage";
import ActivityReportPage from "./pages/ActivityReportPage";
import HomePage from "./pages/HomePage";
import NumberIdentificationPage from "./pages/NumberIdentificationPage";
import { cn } from "./lib/utils";
import { I18nProvider, useTranslation } from "./i18n";
import LanguageSelector from "./components/LanguageSelector";
import ActivityNav from "./components/ActivityNav";

function InnerApp() {
  const { lang, t } = useTranslation();
  const location = useLocation();

  const navItems = [
    { path: "/", label: t("nav.home"), mobileLabel: t("nav.mobile.home"), icon: House },
    { path: "/number-identification", label: t("nav.number"), mobileLabel: t("nav.mobile.number"), icon: Hand },
    { path: "/activities", label: t("nav.activities"), mobileLabel: t("nav.mobile.activities"), icon: Calculator },
  ];

  return (
    <div className="app-shell" lang={lang}>
      <header className="app-header">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6 sm:py-4">
          <NavLink to="/" className="flex min-w-0 items-center gap-3 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500">
            <span className="brand-mark" aria-hidden="true">
              <Sparkles className="h-5 w-5" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-extrabold tracking-tight text-slate-900 sm:text-base">
                {t("title")}
              </span>
              <span className="hidden text-xs font-medium text-slate-500 sm:block">
                {t("app.eyebrow")}
              </span>
            </span>
          </NavLink>

          <nav aria-label={t("app.mainNavigation")} className="hidden items-center gap-1 rounded-full border border-white/80 bg-white/75 p-1 shadow-sm md:flex">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                className={({ isActive }) =>
                  cn(
                    "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-bold transition-colors",
                    isActive
                      ? "bg-violet-600 text-white shadow-sm"
                      : "text-slate-600 hover:bg-violet-50 hover:text-violet-700"
                  )
                }
              >
                <item.icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <LanguageSelector className="shrink-0" />
        </div>
      </header>

      <main className="mx-auto min-h-[calc(100vh-5rem)] w-full max-w-6xl px-4 pb-28 pt-5 sm:px-6 sm:pb-12 sm:pt-8">
        {location.pathname === "/activities" && (
          <div className="mb-6">
            <ActivityNav />
          </div>
        )}
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/number-identification" element={<NumberIdentificationPage />} />
          <Route path="/activities" element={<ActivitiesPage />} />
          <Route path="/activity-report" element={<ActivityReportPage />} />
        </Routes>
      </main>

      <nav aria-label={t("app.mainNavigation")} className="mobile-nav md:hidden">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              cn(
                "mobile-nav-link",
                isActive && "mobile-nav-link-active"
              )
            }
          >
            <item.icon className="h-5 w-5" aria-hidden="true" />
            <span>{item.mobileLabel}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <InnerApp />
    </I18nProvider>
  );
}
