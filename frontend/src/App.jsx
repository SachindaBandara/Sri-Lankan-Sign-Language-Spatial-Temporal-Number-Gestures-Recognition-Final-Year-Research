import { Calculator, Hand, House, Sparkles, UserRound } from "lucide-react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import ActivitiesPage from "./pages/ActivitiesPage";
import ActivityReportPage from "./pages/ActivityReportPage";
import HomePage from "./pages/HomePage";
import NumberIdentificationPage from "./pages/NumberIdentificationPage";
import LearningDashboardPage from "./pages/LearningDashboardPage";
import { cn } from "./lib/utils";
import { I18nProvider, useTranslation } from "./i18n";
import LanguageSelector from "./components/LanguageSelector";
import ActivityNav from "./components/ActivityNav";
import StudentOnly from "./components/StudentOnly";
import AccountPage from "./pages/AccountPage";
import { AuthProvider, useAuth } from "./auth/AuthContext";

function InnerApp() {
  const { lang, t } = useTranslation();
  const { user, loading: authLoading } = useAuth();
  const location = useLocation();

  const navItems = !user
    ? []
    : user.role === "teacher"
    ? [
      { path: "/", label: t("nav.home"), mobileLabel: t("nav.mobile.home"), icon: House },
      { path: "/dashboard", label: t("nav.teacherDashboard"), mobileLabel: t("nav.mobile.teacherDashboard"), icon: Sparkles },
      { path: "/account", label: user.username || t("nav.account"), mobileLabel: t("nav.mobile.account"), icon: UserRound },
    ]
    : [
      { path: "/", label: t("nav.home"), mobileLabel: t("nav.mobile.home"), icon: House },
      ...(user?.role === "student"
        ? [{ path: "/dashboard", label: t("nav.dashboard"), mobileLabel: t("nav.mobile.dashboard"), icon: Sparkles }]
        : []),
      { path: "/number-identification", label: t("nav.number"), mobileLabel: t("nav.mobile.number"), icon: Hand },
      { path: "/activities", label: t("nav.activities"), mobileLabel: t("nav.mobile.activities"), icon: Calculator },
      { path: "/account", label: user?.username || t("nav.account"), mobileLabel: t("nav.mobile.account"), icon: UserRound },
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

          <div className="flex shrink-0 items-center gap-3">
            {navItems.length > 0 && (
              <nav aria-label={t("app.mainNavigation")} className="hidden min-w-0 items-center gap-1 rounded-full border border-white/80 bg-white/75 p-1 shadow-sm lg:flex">
                {navItems.map((item) => {
                  const accountOnly = item.path === "/account";
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.path === "/"}
                      aria-label={item.label}
                      title={item.label}
                      className={({ isActive }) =>
                        cn(
                          "inline-flex min-h-11 items-center justify-center gap-2 rounded-full text-sm font-bold leading-tight transition-colors",
                          accountOnly
                            ? "h-11 w-11 shrink-0"
                            : "min-w-[5.5rem] max-w-36 px-3 py-2 text-center",
                          isActive
                            ? "bg-violet-600 text-white shadow-sm"
                            : "text-slate-600 hover:bg-violet-50 hover:text-violet-700"
                        )
                      }
                    >
                      <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      {!accountOnly && <span className="min-w-0 break-words">{item.label}</span>}
                    </NavLink>
                  );
                })}
              </nav>
            )}
            {!authLoading && !user && (
              <NavLink
                to="/account"
                className="inline-flex min-h-11 shrink-0 items-center justify-center whitespace-nowrap rounded-full bg-violet-600 px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-violet-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2"
              >
                {t("account.login")}
              </NavLink>
            )}
            <LanguageSelector className="shrink-0" />
          </div>
        </div>
      </header>

      <main className={cn(
        "mx-auto min-h-[calc(100vh-5rem)] w-full max-w-6xl px-4 pt-5 sm:px-6 sm:pt-8",
        navItems.length > 0 ? "pb-28 lg:pb-12" : "pb-12",
      )}>
        {location.pathname === "/activities" && (
          <div className="mb-6">
            <ActivityNav />
          </div>
        )}
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/number-identification" element={<StudentOnly><NumberIdentificationPage /></StudentOnly>} />
          <Route path="/activities" element={<StudentOnly><ActivitiesPage /></StudentOnly>} />
          <Route path="/activity-report" element={<StudentOnly><ActivityReportPage /></StudentOnly>} />
          <Route path="/dashboard" element={<LearningDashboardPage />} />
          <Route path="/account" element={<AccountPage />} />
        </Routes>
      </main>

      {navItems.length > 0 && (
        <nav aria-label={t("app.mainNavigation")} className="mobile-nav lg:hidden">
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
      )}
    </div>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <InnerApp />
      </AuthProvider>
    </I18nProvider>
  );
}
