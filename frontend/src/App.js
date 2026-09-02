import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Loading } from "./components/common";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import CreateSimulation from "./pages/CreateSimulation";
import SimulationHistory from "./pages/SimulationHistory";
import SimulationDetail from "./pages/SimulationDetail";
import Recipients from "./pages/Recipients";
import Departments from "./pages/Departments";
import LandingPages from "./pages/LandingPages";
import Forms from "./pages/Forms";
import Reports from "./pages/Reports";
import Senders from "./pages/Senders";
import Sandbox from "./pages/Sandbox";
import AuditLogs from "./pages/AuditLogs";
import SettingsPage from "./pages/Settings";
import PublicLanding from "./pages/PublicLanding";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === null) return <Loading label="Verifying session…" />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/lp/:token" element={<PublicLanding />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/create-simulation" element={<CreateSimulation />} />
        <Route path="/history" element={<SimulationHistory />} />
        <Route path="/history/:id" element={<SimulationDetail />} />
        <Route path="/recipients" element={<Recipients />} />
        <Route path="/departments" element={<Departments />} />
        <Route path="/landing-pages" element={<LandingPages />} />
        <Route path="/awareness-forms" element={<Forms />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/email-senders" element={<Senders />} />
        <Route path="/sandbox" element={<Sandbox />} />
        <Route path="/audit-logs" element={<AuditLogs />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
        <Toaster position="top-right" richColors />
      </BrowserRouter>
    </AuthProvider>
  );
}
