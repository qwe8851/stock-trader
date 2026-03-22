import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import Dashboard from "./pages/Dashboard";
import Backtest from "./pages/Backtest";
import Settings from "./pages/Settings";
import Analytics from "./pages/Analytics";
import Optimization from "./pages/Optimization";
import Prediction from "./pages/Prediction";
import RiskDashboard from "./pages/RiskDashboard";
import Portfolio from "./pages/Portfolio";
import Login from "./pages/Login";
import Register from "./pages/Register";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected */}
        <Route
          path="/dashboard"
          element={<ProtectedRoute><Dashboard /></ProtectedRoute>}
        />
        <Route
          path="/backtest"
          element={<ProtectedRoute><Backtest /></ProtectedRoute>}
        />
        <Route
          path="/settings"
          element={<ProtectedRoute><Settings /></ProtectedRoute>}
        />
        <Route
          path="/analytics"
          element={<ProtectedRoute><Analytics /></ProtectedRoute>}
        />
        <Route
          path="/optimization"
          element={<ProtectedRoute><Optimization /></ProtectedRoute>}
        />
        <Route
          path="/prediction"
          element={<ProtectedRoute><Prediction /></ProtectedRoute>}
        />
        <Route
          path="/risk"
          element={<ProtectedRoute><RiskDashboard /></ProtectedRoute>}
        />
        <Route
          path="/portfolio"
          element={<ProtectedRoute><Portfolio /></ProtectedRoute>}
        />

        {/* Default */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
