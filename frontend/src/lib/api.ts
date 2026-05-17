export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:10001";

export interface PipelineReport {
  pulse_md: string;
  themes: any;
  last_updated: number | null;
}

export async function getLatestReport(): Promise<PipelineReport> {
  const resp = await fetch(`${BACKEND_URL}/latest-report`, {
    cache: "no-store"
  });
  if (!resp.ok) throw new Error("Failed to fetch latest report");
  return resp.json();
}

export async function triggerPipeline(weeks: number = 12): Promise<{ message: string; status: string }> {
  const resp = await fetch(`${BACKEND_URL}/run?weeks=${weeks}&scrape=True&dry_run=False`, {
    method: "POST"
  });
  if (!resp.ok) throw new Error("Failed to trigger pipeline");
  return resp.json();
}

export async function checkHealth(): Promise<{ status: string }> {
  const resp = await fetch(`${BACKEND_URL}/health`);
  if (!resp.ok) throw new Error("Backend offline");
  return resp.json();
}
