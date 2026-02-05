"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/app/providers";

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user) {
    router.replace("/");
    return null;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ username, password });
      router.replace("/");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">Approval Console</h1>
          <p className="mt-2 text-sm text-zinc-600">Login with your admin credentials.</p>
        </div>

        <form onSubmit={onSubmit} className="rounded-xl bg-white p-6 shadow-sm">
          <div className="grid gap-4">
            <label className="grid gap-1">
              <span className="text-sm font-medium text-zinc-700">Username</span>
              <input
                className="rounded-md border px-3 py-2"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </label>
            <label className="grid gap-1">
              <span className="text-sm font-medium text-zinc-700">Password</span>
              <input
                className="rounded-md border px-3 py-2"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                autoComplete="current-password"
              />
            </label>
            {error ? <div className="text-sm text-red-600">{error}</div> : null}
            <button
              type="submit"
              className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
              disabled={submitting}
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

