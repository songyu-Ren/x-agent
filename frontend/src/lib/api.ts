export async function apiFetch(path: string, init?: RequestInit) {
  const url = path.startsWith("http") ? path : path;
  return fetch(url, { ...init, credentials: "include" });
}

export type DraftListItem = {
  id: string;
  created_at: string;
  status: string;
  final_text: string;
  char_count: number;
};

export type RunListItem = {
  run_id: string;
  status: string;
  created_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  last_error: string | null;
};

