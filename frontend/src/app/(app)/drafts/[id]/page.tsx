"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/app/providers";
import { apiFetch } from "@/lib/api";

type AgentLog = {
  id: number;
  agent_name: string;
  start_ts: string;
  end_ts: string;
  duration_ms: number;
  input_summary: string;
  output_summary: string;
  model_used: string | null;
  errors: string | null;
  warnings: string[];
};

type DraftDetail = {
  draft: {
    id: string;
    run_id: string;
    created_at: string;
    expires_at: string;
    status: string;
    thread_enabled: boolean;
    final_text: string;
    tweets: string[] | null;
    char_count: number;
    materials: unknown;
    topic_plan: unknown;
    style_profile: unknown;
    candidates: unknown;
    edited_draft: unknown;
    policy_report: unknown;
    evidence_map?: unknown;
    published_tweet_ids: string[] | null;
    last_error: string | null;
  };
  run: {
    run_id: string;
    source: string;
    status: string;
    created_at: string;
    finished_at: string | null;
    duration_ms: number | null;
    last_error: string | null;
  } | null;
  agent_logs: AgentLog[];
};

function stringifyJson(v: unknown) {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return "";
  }
}

export default function DraftDetailPage() {
  const params = useParams<{ id: string }>();
  const draftId = params.id;
  const { csrfToken } = useAuth();

  const [detail, setDetail] = useState<DraftDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [texts, setTexts] = useState<string[]>([""]);
  const [policyReport, setPolicyReport] = useState<unknown>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const mode = useMemo(() => {
    const t = detail?.draft.tweets;
    if (t && t.length > 0) return "thread";
    return "single";
  }, [detail?.draft.tweets]);

  const liveCharCounts = useMemo(() => {
    const per = texts.map((t) => t.length);
    const total = per.reduce((a, b) => a + b, 0);
    return { per, total };
  }, [texts]);

  const evidenceMap = useMemo(() => {
    const topicPlan = detail?.draft.topic_plan as { evidence_map?: unknown } | undefined;
    if (topicPlan && typeof topicPlan === "object" && "evidence_map" in topicPlan) {
      return topicPlan.evidence_map ?? null;
    }
    const policy = detail?.draft.policy_report as { evidence_map?: unknown } | undefined;
    if (policy && typeof policy === "object" && "evidence_map" in policy) {
      return policy.evidence_map ?? null;
    }
    return null;
  }, [detail?.draft.policy_report, detail?.draft.topic_plan]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch(`/api/drafts/${draftId}`, { method: "GET" });
        if (!res.ok) {
          const msg = await res.text();
          throw new Error(msg || "Failed to load draft");
        }
        const data = (await res.json()) as DraftDetail;
        if (cancelled) return;
        setDetail(data);
        const initialTexts =
          data.draft.tweets && data.draft.tweets.length > 0 ? data.draft.tweets : [data.draft.final_text || ""];
        setTexts(initialTexts);
        setPolicyReport(data.draft.policy_report);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load draft");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [draftId]);

  async function validate(save: boolean) {
    if (!csrfToken) return;
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await apiFetch(`/api/drafts/${draftId}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body: JSON.stringify({ texts, save }),
      });
      const data = (await res.json()) as { status_code: number; policy_report: unknown };
      setPolicyReport(data.policy_report);
      if (save) setActionMsg("Saved.");
    } finally {
      setBusy(false);
    }
  }

  async function doAction(action: "approve" | "skip" | "regenerate" | "resume") {
    if (!csrfToken) return;
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await apiFetch(`/api/drafts/${draftId}/${action}`, {
        method: "POST",
        headers: { "x-csrf-token": csrfToken },
      });
      const data = (await res.json()) as { status_code: number; message: string };
      setActionMsg(`${data.status_code}: ${data.message}`);
      const reload = await apiFetch(`/api/drafts/${draftId}`, { method: "GET" });
      if (reload.ok) {
        const refreshed = (await reload.json()) as DraftDetail;
        setDetail(refreshed);
        setPolicyReport(refreshed.draft.policy_report);
      }
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-zinc-600">Loading…</div>;
  }

  if (error) {
    return <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>;
  }

  if (!detail) return null;

  return (
    <div className="grid gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900">Draft</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-zinc-600">
            <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs">{detail.draft.status}</span>
            <span className="font-mono text-xs">{detail.draft.id}</span>
            <span className="text-xs">{liveCharCounts.total} chars</span>
            <span className="text-xs">mode={mode}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
            onClick={() => doAction("approve")}
          >
            Approve
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
            onClick={() => doAction("skip")}
          >
            Skip
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
            onClick={() => doAction("regenerate")}
          >
            Regenerate
          </button>
          {detail.draft.status === "error" ? (
            <button
              type="button"
              disabled={busy}
              className="rounded-md border px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
              onClick={() => doAction("resume")}
            >
              Resume
            </button>
          ) : null}
        </div>
      </div>

      {actionMsg ? <div className="rounded-md border bg-white p-3 text-sm text-zinc-700">{actionMsg}</div> : null}

      <div className="grid gap-4 rounded-xl bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-zinc-700">Edit</div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy}
              className="rounded-md border px-3 py-2 text-sm hover:bg-zinc-50 disabled:opacity-50"
              onClick={() => validate(false)}
            >
              Re-run policy check
            </button>
            <button
              type="button"
              disabled={busy}
              className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
              onClick={() => validate(true)}
            >
              Save
            </button>
          </div>
        </div>

        <div className="grid gap-3">
          {texts.map((t, idx) => (
            <div key={idx} className="grid gap-2">
              <div className="text-xs text-zinc-500">
                {mode === "thread" ? `Tweet ${idx + 1}: ` : ""}
                {liveCharCounts.per[idx] ?? 0} chars
              </div>
              <textarea
                className="min-h-24 w-full resize-y rounded-md border p-3 font-mono text-sm"
                value={t}
                onChange={(e) => {
                  const next = [...texts];
                  next[idx] = e.target.value;
                  setTexts(next);
                }}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="rounded-xl bg-white p-4 shadow-sm">
          <div className="text-sm font-medium text-zinc-700">Policy Report</div>
          <pre className="mt-3 overflow-auto rounded-md bg-zinc-50 p-3 text-xs text-zinc-800">
            {stringifyJson(policyReport)}
          </pre>
        </div>

        <div className="rounded-xl bg-white p-4 shadow-sm">
          <div className="text-sm font-medium text-zinc-700">Run</div>
          <pre className="mt-3 overflow-auto rounded-md bg-zinc-50 p-3 text-xs text-zinc-800">
            {stringifyJson(detail.run)}
          </pre>
        </div>
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm">
        <div className="text-sm font-medium text-zinc-700">Evidence Map</div>
        <pre className="mt-3 overflow-auto rounded-md bg-zinc-50 p-3 text-xs text-zinc-800">
          {stringifyJson(evidenceMap)}
        </pre>
      </div>

      <div className="rounded-xl bg-white p-4 shadow-sm">
        <div className="text-sm font-medium text-zinc-700">Agent logs</div>
        <div className="mt-3 overflow-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-zinc-500">
                <th className="py-2 pr-3">Agent</th>
                <th className="py-2 pr-3">Duration</th>
                <th className="py-2 pr-3">Model</th>
                <th className="py-2 pr-3">Errors</th>
              </tr>
            </thead>
            <tbody>
              {detail.agent_logs.map((l) => (
                <tr key={l.id} className="border-b last:border-b-0">
                  <td className="py-2 pr-3 font-medium text-zinc-900">{l.agent_name}</td>
                  <td className="py-2 pr-3 text-zinc-700">{l.duration_ms} ms</td>
                  <td className="py-2 pr-3 font-mono text-xs text-zinc-700">{l.model_used || ""}</td>
                  <td className="py-2 pr-3 text-xs text-zinc-700">{l.errors || ""}</td>
                </tr>
              ))}
              {detail.agent_logs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-4 text-center text-sm text-zinc-600">
                    No agent logs.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
