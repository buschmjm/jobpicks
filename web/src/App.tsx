import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useEffect } from "react";
import { DeckHomeRedirect } from "./components/DeckHomeRedirect";
import { Layout } from "./components/Layout";
import { LoadingSpinner } from "./components/ui/NavIcon";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { deckHomePath, useIsDesktop } from "./hooks/useMediaQuery";
import { APP_MOUNT_PATH } from "./lib/mountPath";
import { ApplicationPreparePage } from "./pages/ApplicationPrepare";
import { AdvisorProfilePage } from "./pages/AdvisorProfile";
import { AdvisorGeneratorPage } from "./pages/AdvisorGenerator";
import { AdvisorShell } from "./pages/AdvisorShell";
import { CareerAdvisorPage } from "./pages/CareerAdvisor";
import { ResumeBuilderChatPage } from "./pages/ResumeBuilderChat";
import { DeckPage } from "./pages/Deck";
import { DeckShell } from "./pages/DeckShell";
import { LoginPage } from "./pages/Login";
import { OnboardingPage } from "./pages/Onboarding";
import { TodoListPage } from "./pages/TodoList";
import { SearchPage } from "./pages/Search";
import { ApplicationReportPage } from "./pages/ApplicationReportPage";
import { PreparedApplicationsPage } from "./pages/PreparedApplicationsPage";
import { ProgressPage } from "./pages/ProgressPage";
import { SettingsPage } from "./pages/Settings";

function LoadingScreen({ label }: { label: string }) {
  return (
    <div className="app-shell relative flex min-h-dvh items-center justify-center">
      <LoadingSpinner label={label} />
    </div>
  );
}

function AdvisorRoute() {
  const { user } = useAuth();
  const location = useLocation();
  const allowDuringOnboarding = location.pathname.startsWith("/advisor/build");
  if (user && !user.onboarding_complete && !allowDuringOnboarding) {
    return <Navigate to="/onboarding" replace />;
  }
  return <AdvisorShell />;
}

function AppRoutes() {
  const { user, checking, signOut } = useAuth();
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();

  async function handleLogout() {
    await signOut();
    navigate("/login");
  }

  return (
    <Routes>
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route
        path="/login"
        element={
          checking ? (
            <LoadingScreen label="Loading JobPicks…" />
          ) : user ? (
            <Navigate to={deckHomePath(isDesktop)} replace />
          ) : (
            <LoginPage />
          )
        }
      />
      <Route
        element={
          checking ? (
            <LoadingScreen label="Loading JobPicks…" />
          ) : user ? (
            <Layout user={user} onLogout={handleLogout} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      >
        <Route
          path="/onboarding"
          element={
            user?.onboarding_complete ? (
              <Navigate to={deckHomePath(isDesktop)} replace />
            ) : (
              <OnboardingPage />
            )
          }
        />
        <Route
          path="/deck"
          element={
            user && !user.onboarding_complete ? (
              <Navigate to="/onboarding" replace />
            ) : (
              <DeckShell />
            )
          }
        >
          <Route index element={<DeckPage />} />
          <Route path="search" element={<SearchPage />} />
        </Route>
        <Route path="/todo" element={<TodoListPage />} />
        <Route path="/todo/prepared" element={<Navigate to="/applications" replace />} />
        <Route path="/applications" element={<PreparedApplicationsPage />} />
        <Route
          path="/applications/:packetId"
          element={
            user && !user.onboarding_complete ? (
              <Navigate to="/onboarding" replace />
            ) : (
              <ApplicationReportPage />
            )
          }
        />
        <Route path="/search" element={<Navigate to="/deck/search" replace />} />
        <Route
          path="/todo/:todoId/prepare"
          element={
            user && !user.onboarding_complete ? (
              <Navigate to="/onboarding" replace />
            ) : (
              <ApplicationPreparePage />
            )
          }
        />
        <Route path="/advisor" element={<AdvisorRoute />}>
          <Route index element={<Navigate to="chat" replace />} />
          <Route path="chat" element={<CareerAdvisorPage />} />
          <Route path="build" element={<ResumeBuilderChatPage />} />
          <Route path="profile" element={<AdvisorProfilePage />} />
          <Route path="experience" element={<Navigate to="/advisor/profile" replace />} />
          <Route path="generator" element={<AdvisorGeneratorPage />} />
        </Route>
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/progress" element={<ProgressPage />} />
        <Route path="/browse" element={<Navigate to="/deck" replace />} />
        <Route path="/deck/browse" element={<Navigate to="/deck" replace />} />
        <Route path="/deck/assist" element={<Navigate to="/deck" replace />} />
        <Route path="/" element={<DeckHomeRedirect />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function AuthCallback() {
  const { user, checking } = useAuth();
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();

  useEffect(() => {
    if (checking) return;
    if (user) {
      navigate(user.onboarding_complete ? deckHomePath(isDesktop) : "/onboarding", {
        replace: true,
      });
      return;
    }
    navigate("/login?error=session", { replace: true });
  }, [checking, user, navigate, isDesktop]);

  return <LoadingScreen label="Finishing sign-in…" />;
}

export default function App() {
  return (
    <BrowserRouter basename={APP_MOUNT_PATH || undefined}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
