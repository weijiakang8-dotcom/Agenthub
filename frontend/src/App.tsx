import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";

import { Layout } from "@/components/layout/Layout";
import { getAccessToken } from "@/lib/api";
import Landing from "@/pages/Landing";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const ExecutionDetail = lazy(() => import("@/pages/ExecutionDetail"));
const Executions = lazy(() => import("@/pages/Executions"));
const Quality = lazy(() => import("@/pages/Quality"));
const Settings = lazy(() => import("@/pages/Settings"));
const Workflows = lazy(() => import("@/pages/Workflows"));
const WorkflowEditor = lazy(() => import("@/pages/WorkflowEditor"));
const Alerts = lazy(() => import("@/pages/Alerts"));
const AlertRules = lazy(() => import("@/pages/AlertRules"));
const Chat = lazy(() => import("@/pages/Chat"));
const Dispatch = lazy(() => import("@/pages/Dispatch"));
const History = lazy(() => import("@/pages/History"));
const Skills = lazy(() => import("@/pages/Skills"));
const Agents = lazy(() => import("@/pages/Agents"));
const Savings = lazy(() => import("@/pages/Savings"));
const Tools = lazy(() => import("@/pages/Tools"));
const UserGuide = lazy(() => import("@/pages/UserGuide"));

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
      <Suspense fallback={<div className="min-h-screen bg-background" />}>
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
              path="/dispatch"
              element={
                <RequireAuth>
                  <Dispatch />
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
              path="/agents"
              element={
                <RequireAuth>
                  <Agents />
                </RequireAuth>
              }
            />
            <Route
              path="/savings"
              element={
                <RequireAuth>
                  <Savings />
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
      </Suspense>
    </TooltipProvider>
  );
}
