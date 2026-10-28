"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, LockKeyhole } from "lucide-react";
import { Brand } from "@/components/brand";
import { api } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          username: form.get("username"),
          password: form.get("password"),
        }),
      });
      router.replace("/soc");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <Brand />
      <section className="login-card">
        <div className="login-icon">
          <LockKeyhole size={22} />
        </div>
        <div className="eyebrow">YOUR SOC WORKSPACE</div>
        <h1>Welcome back.</h1>
        <p>Sign in to view your connected telemetry.</p>
        <form onSubmit={submit}>
          <label>
            Username
            <input
              name="username"
              autoComplete="username"
              required
              maxLength={128}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={2048}
            />
          </label>
          {error && (
            <div role="alert" className="form-error">
              {error}
            </div>
          )}
          <button className="button primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
            <ArrowRight size={16} />
          </button>
        </form>
        <small>Private workspace. No public registration.</small>
      </section>
      <span className="login-caption">Evidence before conclusions.</span>
    </main>
  );
}
