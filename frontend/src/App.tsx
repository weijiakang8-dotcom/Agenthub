import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "@/components/layout/Layout";
import { getAccessToken } from "@/lib/api";
import Dashboard from "@/pages/Dashboard";
import ExecutionDetail from "@/pages/ExecutionDetail";
import Executions from "@/pages/Executions";
import Quality from "@/pages/Quality";
import Settings from "@/pages/Settings";
import Workflows from "@/pages/Workflows";
import WorkflowEditor from "@/pages/WorkflowEditor";
import Alerts from "@/pages/Alerts";
import AlertRules from "@/pages/AlertRules";
import Login from "@/pages/Login";
import Register from "@/pages/Register";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = getAccessToken();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="/workflows" element={<Workflows />} />
        <Route path="/workflows/editor" element={<WorkflowEditor />} />
        <Route path="/executions" element={<Executions />} />
        <Route path="/executions/:id" element={<ExecutionDetail />} />
        <Route path="/quality" element={<Quality />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/alerts/rules" element={<AlertRules />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
