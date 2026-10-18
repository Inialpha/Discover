import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Shell from "./components/Shell";
import Login from "./pages/Login";
import NewAnalysis from "./pages/NewAnalysis";
import Analysis from "./pages/Analysis";
import PersonaPage from "./pages/Persona";
import History from "./pages/History";

function Protected() {
  const { user, ready } = useAuth();
  const loc = useLocation();
  if (!ready) return <div className="boot">Loading…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <Shell><Outlet /></Shell>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected />}>
        <Route path="/" element={<NewAnalysis />} />
        <Route path="/history" element={<History />} />
        <Route path="/analysis/:id" element={<Analysis />} />
        <Route path="/analysis/:id/persona/:index" element={<PersonaPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
