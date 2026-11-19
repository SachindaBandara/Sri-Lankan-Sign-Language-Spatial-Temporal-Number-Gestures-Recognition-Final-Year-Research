import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import AccountPage from "../pages/AccountPage";

export default function StudentOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="py-12 text-center text-slate-600">Loading account…</p>;
  if (!user || user.role !== "student") return <AccountPage />;
  return children || <Navigate to="/account" replace />;
}
