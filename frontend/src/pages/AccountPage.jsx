import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { useAuth } from "../auth/AuthContext";
import { useTranslation } from "../i18n";

export default function AccountPage() {
  const { user, signIn, signUp, signOut } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [grade, setGrade] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const credentials = { username, password };
      const authenticatedUser = registering
        ? await signUp({ ...credentials, grade })
        : await signIn(credentials);
      navigate(authenticatedUser.role === "teacher" ? "/dashboard" : "/activities", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const leave = async () => {
    setError("");
    try {
      await signOut();
      navigate("/", { replace: true });
    } catch (requestError) {
      setError(requestError.message);
    }
  };

  return (
    <section className="mx-auto max-w-lg space-y-5">
      <Card className="learning-card">
        <CardHeader>
          <CardTitle>{user ? t("account.title") : registering ? t("account.register") : t("account.login")}</CardTitle>
        </CardHeader>
        <CardContent>
          {user ? (
            <div className="space-y-4">
              <p>{t("account.signedInAs")}: <strong>{user.username}</strong></p>
              {user.grade && <p>{t("account.grade")}: {user.grade}</p>}
              <Button onClick={leave}>{t("account.logout")}</Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <label className="block space-y-1">
                <span className="text-sm font-semibold">{t("account.username")}</span>
                <input
                  autoComplete="username"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  minLength={3}
                  maxLength={80}
                  required
                />
              </label>
              <label className="block space-y-1">
                <span className="text-sm font-semibold">{t("account.password")}</span>
                <input
                  autoComplete={registering ? "new-password" : "current-password"}
                  type="password"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  minLength={registering ? 12 : 1}
                  maxLength={256}
                  required
                />
              </label>
              {registering && (
                <label className="block space-y-1">
                  <span className="text-sm font-semibold">{t("account.grade")} ({t("account.optional")})</span>
                  <input
                    type="number"
                    min="1"
                    max="13"
                    className="w-full rounded-xl border border-slate-300 px-3 py-2"
                    value={grade}
                    onChange={(event) => setGrade(event.target.value)}
                  />
                </label>
              )}
              {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
              <Button type="submit" disabled={busy} className="w-full">
                {busy ? t("account.pleaseWait") : registering ? t("account.register") : t("account.login")}
              </Button>
              <button
                type="button"
                className="w-full text-sm font-semibold text-violet-700 underline"
                onClick={() => { setRegistering(!registering); setError(""); }}
              >
                {registering ? t("account.haveAccount") : t("account.needAccount")}
              </button>
            </form>
          )}
          {error && user && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
        </CardContent>
      </Card>
    </section>
  );
}
