import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/leads", label: "Sales" },
  { to: "/leads/new", label: "Add Lead" },
  { to: "/review", label: "QA Review" },
  { to: "/configuration", label: "Configuration" },
];

export function Layout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <span className="brand-mark">QA</span>
          <div>
            <div className="brand-title">CIMET QA Gate</div>
            <div className="brand-subtitle">Score the sale before it ships</div>
          </div>
        </div>
        <nav className="app-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link ${isActive ? "nav-link-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
