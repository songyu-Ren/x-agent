"use client";

import { useEffect, useState } from "react";
import { apiFetch, RunListItem } from "@/lib/api";

export default function RunsPage() {
  const [items, setItems] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch("/api/runs", { method: "GET" });
        if (!res.ok) {
          const msg = await res.text();
          throw new Error(msg || "Failed to load runs");
        }
        const data = (await res.json()) as { items: RunListItem[] };
        if (!cancelled) setItems(data.items || []);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load runs");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900">Runs</h1>
        <p className="mt-1 text-sm text-zinc-600">Recent run history and failures.</p>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

      <div className="rounded-xl bg-white shadow-sm">
        <div className="border-b px-4 py-3 text-sm font-medium text-zinc-700">
          {loading ? "Loading…" : `${items.length} runs`}
        </div>
        <div className="divide-y">
          {items.map((r) => (
            <div key={r.run_id} className="grid gap-1 px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs">{r.status}</span>
                <span className="font-mono text-xs text-zinc-700">{r.run_id}</span>
              </div>
              <div className="text-xs text-zinc-600">
                created={r.created_at} finished={r.finished_at || "-"} duration_ms={r.duration_ms ?? "-"}
              </div>
              {r.last_error ? (
                <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
                  {r.last_error}
                </div>
              ) : null}
            </div>
          ))}
          {!loading && items.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-zinc-600">No runs found.</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
