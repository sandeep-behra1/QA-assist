import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";
import type { HealthInfo } from "../types";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/leads", label: "Sales" },
  { to: "/leads/new", label: "Add Lead" },
  { to: "/review", label: "QA Review" },
  { to: "/configuration", label: "Configuration" },
];

export function Layout() {
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const links = health?.demo_mode ? [...NAV, { to: "/demo-data", label: "Demo data", end: false }] : NAV;

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
          {links.map((item) => (
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
        {health && (
          <div className="app-status" title="What this backend is connected to">
            <span className={`status-pill ${health.stt_ready ? "status-on" : "status-off"}`}>
              Speech: {health.stt_ready ? "live" : "offline demo"}
            </span>
            <span className={`status-pill ${health.llm_provider !== "mock" && health.llm_ready ? "status-on" : "status-off"}`}>
              LLM: {health.llm_provider === "mock" ? "mock" : health.llm_ready ? health.llm_provider : "not configured"}
            </span>
          </div>
        )}
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
