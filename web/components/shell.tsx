"use client";

import { ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Radio, SlidersHorizontal, LogOut, ArrowUpRight } from "lucide-react";
import { Brand } from "./brand";
import { api, ApiError } from "@/lib/api";

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<{ username: string } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
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
  return (
    <div className="soc">
      <aside className="sidebar">
        <Brand dark />
        <div className="workspace-label">
          <div className="workspace-avatar">C</div>
          <div>
            Security operations<small>Private workspace</small>
          </div>
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav>
          <Link
            href="/soc"
            className={
              path === "/soc" || path.startsWith("/soc/alerts") ? "active" : ""
            }
          >
            <Radio size={17} />
            Alerts
          </Link>
          <Link
            href="/soc/connections"
            className={path.startsWith("/soc/connections") ? "active" : ""}
          >
            <SlidersHorizontal size={17} />
            Connections
          </Link>
        </nav>
        <div className="sidebar-bottom">
          <span className="read-only">
            <span className="dot" />
            Read-only access
          </span>
          <p>Source systems stay in control.</p>
          <Link href="/">
            About Corvus <ArrowUpRight size={13} />
          </Link>
        </div>
      </aside>
      <div className="soc-main">
        <header className="topbar">
          <div>
            <span className="muted">Workspace</span>
            <span className="slash">/</span>
            {path.includes("connections") ? "Connections" : "Alerts"}
          </div>
          <div className="account">
            <span>{user.username}</span>
            <button onClick={logout} title="Sign out" aria-label="Sign out">
              <LogOut size={16} />
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
