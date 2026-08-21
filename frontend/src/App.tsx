import { Navigate, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";

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
import Chat from "@/pages/Chat";
import History from "@/pages/History";
import Skills from "@/pages/Skills";
import Tools from "@/pages/Tools";
import Landing from "@/pages/Landing";
import UserGuide from "@/pages/UserGuide";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = getAccessToken();
  if (!token) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function Home() {
  return getAccessToken() ? <Navigate to="/chat" replace /> : <Landing />;
}

export default function App() {
  return (
    <TooltipProvider delayDuration={250}>
      <Routes>
      <Route path="/" element={<Home />} />
      <Route element={<Layout />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route
          path="/chat"
          element={
            <RequireAuth>
              <Chat />
            </RequireAuth>
          }
        />
        <Route
          path="/history"
          element={
            <RequireAuth>
              <History />
            </RequireAuth>
          }
        />
        <Route
          path="/skills"
          element={
            <RequireAuth>
              <Skills />
            </RequireAuth>
          }
        />
        <Route
          path="/tools"
          element={
            <RequireAuth>
              <Tools />
            </RequireAuth>
          }
        />
        <Route
          path="/workflows"
          element={
            <RequireAuth>
              <Workflows />
            </RequireAuth>
          }
        />
        <Route
          path="/workflows/editor"
          element={
            <RequireAuth>
              <WorkflowEditor />
            </RequireAuth>
          }
        />
        <Route
          path="/executions"
          element={
            <RequireAuth>
              <Executions />
            </RequireAuth>
          }
        />
        <Route
          path="/executions/:id"
          element={
            <RequireAuth>
              <ExecutionDetail />
            </RequireAuth>
          }
        />
        <Route
          path="/quality"
          element={
            <RequireAuth>
              <Quality />
            </RequireAuth>
          }
        />
        <Route
          path="/alerts"
          element={
            <RequireAuth>
              <Alerts />
            </RequireAuth>
          }
        />
        <Route
          path="/alerts/rules"
          element={
            <RequireAuth>
              <AlertRules />
            </RequireAuth>
          }
        />
        <Route
          path="/settings"
          element={
            <RequireAuth>
              <Settings />
            </RequireAuth>
          }
        />
        <Route path="/guide" element={<UserGuide />} />
      </Route>
      </Routes>
    </TooltipProvider>
  );
}
