import { NavLink, Outlet, useLocation } from "react-router-dom";

const TABS = [
  { to: "/deck", label: "Swipe", end: true },
  { to: "/deck/search", label: "Search", end: true },
] as const;

/** Deck area shell — swipe deck and corpus search. */
export function DeckShell() {
  const location = useLocation();
  const isSearch = location.pathname.startsWith("/deck/search");

  return (
    <div className={`flex min-h-0 flex-1 flex-col ${isSearch ? "overflow-y-auto" : "overflow-hidden"}`}>
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
      <div className={`flex min-h-0 flex-1 flex-col ${isSearch ? "" : "overflow-hidden"}`}>
        <Outlet />
      </div>
    </div>
  );
}
