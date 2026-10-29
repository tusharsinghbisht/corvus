"use client";

import { ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Radio,
  SlidersHorizontal,
  LogOut,
  ArrowUpRight,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { Brand } from "./brand";
import { api, ApiError } from "@/lib/api";

const SIDEBAR_PREFERENCE = "corvus.sidebar.collapsed";

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ username: string } | null>(null);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem(SIDEBAR_PREFERENCE) === "true");
    } catch {
      /* Storage can be disabled without affecting navigation. */
    }
    let active = true;
    api<{ username: string }>("/auth/me")
      .then((value) => {
        if (active) setUser(value);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401)
          router.replace("/login");
        else
          setError(
            "The workspace is unavailable. Check the server connection and reload.",
          );
      });
    return () => {
      active = false;
    };
  }, [router]);

  function toggleSidebar() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(SIDEBAR_PREFERENCE, String(next));
    } catch {
      /* The preference is optional. */
    }
  }

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST", body: "{}" });
      router.replace("/login");
    } catch {
      setError("Could not sign out. Please try again.");
    }
  }

  if (!user)
    return (
      <main className="workspace-loading">
        <Brand />
        <p role="status">{error || "Opening your workspace…"}</p>
      </main>
    );
  const alertsActive = path === "/soc" || path.startsWith("/soc/alerts");
  const connectionsActive = path.startsWith("/soc/connections");
  return (
    <div className={`soc${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside
        id="workspace-sidebar"
        className="sidebar"
        aria-label="Workspace navigation"
      >
        <Brand dark />
        <div
          className="workspace-label"
          title={
            collapsed ? "Security operations · private workspace" : undefined
          }
        >
          <div className="workspace-avatar">C</div>
          <div className="workspace-label-copy">
            Security operations<small>Private workspace</small>
          </div>
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          <Link
            href="/soc"
            className={alertsActive ? "active" : ""}
            aria-current={alertsActive ? "page" : undefined}
            aria-label="Alerts"
            title={collapsed ? "Alerts" : undefined}
          >
            <Radio size={18} />
            <span className="nav-label">Alerts</span>
          </Link>
          <Link
            href="/soc/connections"
            className={connectionsActive ? "active" : ""}
            aria-current={connectionsActive ? "page" : undefined}
            aria-label="Connections"
            title={collapsed ? "Connections" : undefined}
          >
            <SlidersHorizontal size={18} />
            <span className="nav-label">Connections</span>
          </Link>
        </nav>
        <div className="sidebar-bottom">
          <span className="read-only" title="Read-only access">
            <span className="dot" />
            <span className="sidebar-copy">Read-only access</span>
          </span>
          <p className="sidebar-copy">Source systems stay in control.</p>
          <Link
            href="/"
            aria-label="About Corvus"
            title={collapsed ? "About Corvus" : undefined}
          >
            <span className="sidebar-copy">About Corvus</span>
            <ArrowUpRight size={15} />
          </Link>
        </div>
      </aside>
      <div className="soc-main">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="sidebar-toggle"
              onClick={toggleSidebar}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!collapsed}
              aria-controls="workspace-sidebar"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? (
                <PanelLeftOpen size={18} />
              ) : (
                <PanelLeftClose size={18} />
              )}
            </button>
            <span className="muted">Workspace</span>
            <span className="slash">/</span>
            <span>{connectionsActive ? "Connections" : "Alerts"}</span>
          </div>
          <div className="account">
            <span>{user.username}</span>
            <button onClick={logout} title="Sign out" aria-label="Sign out">
              <LogOut size={17} />
            </button>
          </div>
        </header>
        {error && (
          <div role="alert" className="notice error">
            {error}
          </div>
        )}
        <div className="soc-content">{children}</div>
        <footer className="soc-footer">
          <span>Original sources. Explicit uncertainty.</span>
          <span>Corvus · read-only</span>
        </footer>
      </div>
    </div>
  );
}
