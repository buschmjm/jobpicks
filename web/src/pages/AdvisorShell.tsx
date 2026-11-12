import { NavLink, Outlet, useLocation } from "react-router-dom";

const TABS = [
  { to: "/advisor/chat", label: "Chat", end: true },
  { to: "/advisor/build", label: "Build", end: true },
  { to: "/advisor/profile", label: "Profile", end: true },
  { to: "/advisor/generator", label: "Resume", end: true },
] as const;

export function AdvisorShell() {
  const location = useLocation();
  const isChat =
    location.pathname.startsWith("/advisor/chat") ||
    location.pathname.startsWith("/advisor/build");

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="mb-2 flex shrink-0 gap-2 overflow-x-auto border-b border-border-subtle pb-2">
        {TABS.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                isActive
                  ? "bg-brand-strong text-on-brand shadow-sm"
                  : "border border-border bg-surface text-muted hover:border-muted hover:text-ink-text"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </div>
      <div
        className={`flex min-h-0 flex-1 flex-col ${
          isChat ? "overflow-hidden" : "overflow-y-auto"
        }`}
      >
        <Outlet />
      </div>
    </div>
  );
}
