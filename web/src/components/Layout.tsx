import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { BrandLogo } from "./BrandLogo";
import { MilestoneToast } from "./MilestoneToast";
import { MissionHeader } from "./MissionHeader";
import { NavIcon } from "./ui/NavIcon";
import { deckHomePath, useIsDesktop } from "../hooks/useMediaQuery";
import { useEngagement } from "../hooks/useEngagement";
import type { SessionUser } from "../types";

interface LayoutProps {
  user: SessionUser | null;
  onLogout: () => void;
}

export function Layout({ user, onLogout }: LayoutProps) {
  const location = useLocation();
  const isDesktop = useIsDesktop();
  const { newMilestones, clearMilestones } = useEngagement();
  const homePath = deckHomePath(isDesktop);
  const isDeck = location.pathname.startsWith("/deck");
  const isDeckSearch = location.pathname.startsWith("/deck/search");
  const isSwipe = location.pathname === "/deck" || location.pathname === "/deck/";
  const isTodo = location.pathname.startsWith("/todo") || location.pathname.startsWith("/applications");
  const isAdvisor = location.pathname.startsWith("/advisor");
  const isAdvisorChat = location.pathname.startsWith("/advisor/chat") || location.pathname === "/advisor";
  const isImmersiveMain = isSwipe || isAdvisorChat;
  const shellViewportClass = "h-dvh overflow-hidden";
  const mainOverflowClass = isImmersiveMain ? "overflow-hidden" : "overflow-y-auto touch-pan-y";

  const mobileNav = [
    { to: homePath, label: "Deck", icon: "deck" as const, match: (p: string) => p.startsWith("/deck") },
    { to: "/todo", label: "Apply", icon: "apply" as const, match: (p: string) => p.startsWith("/todo") || p.startsWith("/applications") },
    {
      to: "/advisor/chat",
      label: "Advisor",
      icon: "advisor" as const,
      match: (p: string) => p.startsWith("/advisor"),
    },
  ];

  const desktopNav = [
    {
      to: "/deck",
      label: "Swipe",
      icon: "swipe" as const,
      match: (p: string) => p === "/deck" || p === "/deck/",
    },
    { to: "/todo", label: "Apply", icon: "apply" as const, match: (p: string) => p.startsWith("/todo") || p.startsWith("/applications") },
    {
      to: "/advisor/chat",
      label: "Advisor",
      icon: "advisor" as const,
      match: (p: string) => p.startsWith("/advisor"),
    },
    {
      to: "/settings",
      label: "Settings",
      icon: "settings" as const,
      match: (p: string) => p.startsWith("/settings") || p.startsWith("/progress"),
    },
  ];

  if (isDesktop) {
    return (
      <div className={`app-shell relative flex ${shellViewportClass}`}>
        <aside className="sticky top-0 flex h-dvh w-56 shrink-0 flex-col border-r border-border-subtle bg-canvas/95 backdrop-blur-md">
          <div className="border-b border-border-subtle px-4 py-4">
            <Link to={homePath} className="transition opacity-90 hover:opacity-100">
              <BrandLogo size="sm" />
            </Link>
          </div>
          <nav className="flex flex-1 flex-col gap-1 p-3">
            {desktopNav.map(({ to, label, icon, match }) => {
              const active = match(location.pathname);
              return (
                <NavLink
                  key={`${to}-${label}`}
                  to={to}
                  end={to === "/deck"}
                  className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                    active
                      ? "bg-brand-muted text-brand-strong"
                      : "text-muted hover:bg-surface-raised hover:text-ink-text"
                  }`}
                >
                  <NavIcon name={icon} active={active} />
                  {label}
                </NavLink>
              );
            })}
          </nav>
          {user ? (
            <div className="border-t border-border-subtle p-3">
              <p className="truncate px-2 text-xs text-subtle">{user.email}</p>
              <button
                type="button"
                onClick={onLogout}
                className="mt-2 w-full rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-subtle transition hover:bg-surface-raised hover:text-ink-text"
              >
                Log out
              </button>
            </div>
          ) : null}
        </aside>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <main
            className={`relative mx-auto flex w-full max-w-7xl min-h-0 flex-1 flex-col ${mainOverflowClass} px-5 ${
              isSwipe || isAdvisorChat ? "py-3" : isAdvisor ? "py-3" : "py-6"
            }`}
          >
            {!isImmersiveMain && !location.pathname.startsWith("/progress") ? (
              <MissionHeader variant={isTodo ? "full" : "full"} />
            ) : null}
            <Outlet />
          </main>
        </div>
        <MilestoneToast milestoneIds={newMilestones} onDismiss={clearMilestones} />
      </div>
    );
  }

  return (
    <div className={`app-shell relative flex flex-col ${shellViewportClass}`}>
      <header className="shrink-0 border-b border-border-subtle bg-canvas/95 shadow-sm backdrop-blur-md">
        <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-3 sm:max-w-3xl">
          <Link to={homePath} className="transition opacity-90 hover:opacity-100">
            <BrandLogo size="sm" />
          </Link>
          {user ? (
            <div className="flex items-center gap-2">
              <Link
                to="/settings"
                className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-subtle transition hover:bg-surface-raised hover:text-muted"
              >
                Settings
              </Link>
              <span className="hidden max-w-[140px] truncate text-xs text-subtle sm:inline">
                {user.email}
              </span>
              <button
                type="button"
                onClick={onLogout}
                className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-subtle transition hover:bg-surface-raised hover:text-muted"
              >
                Log out
              </button>
            </div>
          ) : null}
        </div>
      </header>

      <main
        className={`relative mx-auto flex w-full max-w-lg min-h-0 flex-1 flex-col ${mainOverflowClass} px-3 sm:max-w-3xl sm:px-4 ${
          isDeck && !isDeckSearch ? "py-2 sm:py-3" : isAdvisor || isTodo ? "py-2 sm:py-3" : "py-4 sm:py-6"
        }`}
      >
        {!isImmersiveMain && !location.pathname.startsWith("/progress") ? (
          <MissionHeader variant={isDeck ? "compact" : "full"} />
        ) : null}
        <Outlet />
      </main>

      <MilestoneToast milestoneIds={newMilestones} onDismiss={clearMilestones} />

      <nav className="shrink-0 border-t border-border-subtle bg-canvas/98 pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_20px_-8px_rgba(15,23,42,0.08)] backdrop-blur-md">
        <div className="mx-auto flex max-w-lg items-stretch justify-around sm:max-w-3xl">
          {mobileNav.map(({ to, label, icon, match }) => {
            const active = match(location.pathname);
            return (
              <Link
                key={label}
                to={to}
                className={`relative flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] transition ${
                  active ? "text-brand-strong" : "text-subtle hover:text-muted"
                }`}
              >
                {active ? (
                  <span className="absolute top-1.5 h-0.5 w-7 rounded-full bg-accent" aria-hidden />
                ) : null}
                <NavIcon name={icon} active={active} />
                {label}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
