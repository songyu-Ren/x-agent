"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/app/providers";
import { apiFetch } from "@/lib/api";

type SettingsPayload = {
  schedule: {
    hour: number;
    minute: number;
    timezone: string;
  };
  thread: {
    enabled: boolean;
    max_tweets: number;
    numbering_enabled: boolean;
  };
  blocked_terms: string[];
};

function toBlockedTermsText(terms: string[]) {
  return (terms || []).join("\n");
}

function parseBlockedTermsText(text: string) {
  return text
    .split("\n")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

export default function SettingsPage() {
  const { csrfToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const [scheduleHour, setScheduleHour] = useState<number>(9);
  const [scheduleMinute, setScheduleMinute] = useState<number>(0);
  const [timezone, setTimezone] = useState<string>("UTC");
  const [threadEnabled, setThreadEnabled] = useState<boolean>(false);
  const [threadMaxTweets, setThreadMaxTweets] = useState<number>(5);
  const [threadNumberingEnabled, setThreadNumberingEnabled] = useState<boolean>(true);
  const [blockedTermsText, setBlockedTermsText] = useState<string>("");

  const payload = useMemo<SettingsPayload>(
    () => ({
      schedule: { hour: scheduleHour, minute: scheduleMinute, timezone },
      thread: {
        enabled: threadEnabled,
        max_tweets: threadMaxTweets,
        numbering_enabled: threadNumberingEnabled,
      },
      blocked_terms: parseBlockedTermsText(blockedTermsText),
    }),
    [blockedTermsText, scheduleHour, scheduleMinute, threadEnabled, threadMaxTweets, threadNumberingEnabled, timezone],
  );

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch("/api/settings", { method: "GET" });
        if (!res.ok) {
          const msg = await res.text();
          throw new Error(msg || "Failed to load settings");
        }
        const data = (await res.json()) as SettingsPayload;
        if (cancelled) return;
        setScheduleHour(data.schedule.hour);
        setScheduleMinute(data.schedule.minute);
        setTimezone(data.schedule.timezone);
        setThreadEnabled(Boolean(data.thread.enabled));
        setThreadMaxTweets(data.thread.max_tweets);
        setThreadNumberingEnabled(Boolean(data.thread.numbering_enabled));
        setBlockedTermsText(toBlockedTermsText(data.blocked_terms || []));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load settings");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!csrfToken) return;
    setSaving(true);
    setSavedMsg(null);
    setError(null);
    try {
      const res = await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || "Failed to save settings");
      }
      setSavedMsg("Saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900">Settings</h1>
        <p className="mt-1 text-sm text-zinc-600">Admin configuration stored in the database.</p>
      </div>

      {loading ? <div className="text-sm text-zinc-600">Loading…</div> : null}
      {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div> : null}
      {savedMsg ? <div className="rounded-md border bg-white p-3 text-sm text-zinc-700">{savedMsg}</div> : null}

      <form onSubmit={onSubmit} className="grid gap-6 rounded-xl bg-white p-6 shadow-sm">
        <div className="grid gap-3">
          <div className="text-sm font-medium text-zinc-700">Schedule</div>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="grid gap-1 text-sm">
              <span className="text-zinc-600">Hour</span>
              <input
                type="number"
                min={0}
                max={23}
                className="rounded-md border px-3 py-2"
                value={scheduleHour}
                onChange={(e) => setScheduleHour(Number(e.target.value))}
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="text-zinc-600">Minute</span>
              <input
                type="number"
                min={0}
                max={59}
                className="rounded-md border px-3 py-2"
                value={scheduleMinute}
                onChange={(e) => setScheduleMinute(Number(e.target.value))}
              />
            </label>
            <label className="grid gap-1 text-sm">
              <span className="text-zinc-600">Timezone</span>
              <input
                className="rounded-md border px-3 py-2"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              />
            </label>
          </div>
        </div>

        <div className="grid gap-3">
          <div className="text-sm font-medium text-zinc-700">Thread</div>
          <label className="flex items-center gap-2 text-sm text-zinc-700">
            <input
              type="checkbox"
              checked={threadEnabled}
              onChange={(e) => setThreadEnabled(e.target.checked)}
            />
            Enable threads
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-sm">
              <span className="text-zinc-600">Max tweets</span>
              <input
                type="number"
                min={1}
                max={25}
                className="rounded-md border px-3 py-2"
                value={threadMaxTweets}
                onChange={(e) => setThreadMaxTweets(Number(e.target.value))}
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-700">
              <input
                type="checkbox"
                checked={threadNumberingEnabled}
                onChange={(e) => setThreadNumberingEnabled(e.target.checked)}
              />
              Number thread tweets
            </label>
          </div>
        </div>

        <div className="grid gap-3">
          <div className="text-sm font-medium text-zinc-700">Blocked terms</div>
          <textarea
            className="min-h-40 w-full resize-y rounded-md border p-3 font-mono text-sm"
            value={blockedTermsText}
            onChange={(e) => setBlockedTermsText(e.target.value)}
          />
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            className="rounded-md bg-zinc-900 px-3 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50"
            disabled={saving || loading}
          >
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
    </div>
  );
}
