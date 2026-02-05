"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch, DraftListItem } from "@/lib/api";

export default function DraftsPage() {
  const [status, setStatus] = useState<string>("");
  const [days, setDays] = useState<number>(14);
  const [items, setItems] = useState<DraftListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    params.set("days", String(days));
    return params.toString();
  }, [days, status]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch(`/api/drafts?${query}`, { method: "GET" });
        if (!res.ok) {
          const msg = await res.text();
          throw new Error(msg || "Failed to load drafts");
        }
        const data = (await res.json()) as { items: DraftListItem[] };
        if (!cancelled) setItems(data.items || []);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load drafts");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [query]);

  return (
    <div className="grid gap-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Drafts</h1>
          <p className="mt-1 text-sm text-zinc-600">Review, edit, and approve drafts.</p>
        </div>
        <div className="flex items-end gap-3">
          <label className="grid gap-1 text-sm">
            <span className="text-zinc-600">Status</span>
            <select
              className="rounded-md border bg-white px-3 py-2"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="needs_human_attention">Needs attention</option>
              <option value="publishing">Publishing</option>
              <option value="posted">Posted</option>
              <option value="dry_run_posted">Dry run posted</option>
              <option value="skipped">Skipped</option>
              <option value="error">Error</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm">
            <span className="text-zinc-600">Days</span>
            <input
              className="w-24 rounded-md border bg-white px-3 py-2"
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </label>
        </div>
      </div>

      {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}

      <div className="rounded-xl bg-white shadow-sm">
        <div className="border-b px-4 py-3 text-sm font-medium text-zinc-700">
          {loading ? "Loading…" : `${items.length} drafts`}
        </div>
        <div className="divide-y">
          {items.map((d) => (
            <div key={d.id} className="flex items-start justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <div className="truncate text-sm font-medium text-zinc-900">{d.final_text || "(empty)"}</div>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                  <span className="rounded bg-zinc-100 px-2 py-0.5">{d.status}</span>
                  <span>{d.created_at}</span>
                  <span>{d.char_count} chars</span>
                  <span className="font-mono">{d.id.slice(0, 8)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  href={`/drafts/${d.id}`}
                  className="rounded-md border px-3 py-2 text-sm hover:bg-zinc-50"
                >
                  Open
                </Link>
              </div>
            </div>
          ))}
          {!loading && items.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-zinc-600">No drafts found.</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

