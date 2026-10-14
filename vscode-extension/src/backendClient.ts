import { cfg } from './config';
import { BackendState, EgoGraphResponse, HealthInfo, RecommendResponse, SuggestFixResponse } from './types';

/** fetch with a hard timeout so a slow or dead backend can never hang the extension. */
export async function fetchJson<T>(path: string, init?: RequestInit, timeoutOverrideMs?: number): Promise<T> {
  const { backendUrl, timeoutMs: defaultTimeout } = cfg();
  const timeoutMs = timeoutOverrideMs ?? defaultTimeout;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${backendUrl}${path}`, { ...init, signal: controller.signal });
    if (!res.ok) {
      let detail = '';
      try {
        detail = ((await res.json()) as { detail?: string }).detail ?? '';
      } catch {
        /* body wasn't JSON */
      }
      throw new BackendError(res.status, detail || res.statusText);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof BackendError) {
      throw err;
    }
    const aborted = (err as Error).name === 'AbortError';
    throw new BackendError(0, aborted ? 'Backend timed out' : 'Backend unreachable');
  } finally {
    clearTimeout(timer);
  }
}

export class BackendError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
  /** status 0 means we never got a response (offline / timeout). */
  get isOffline(): boolean {
    return this.status === 0;
  }
}

/** Pings GET / and turns the answer into a sidebar-friendly state. Never throws. */
export async function checkBackend(): Promise<BackendState> {
  try {
    const h = await fetchJson<HealthInfo>('/');
    const warning =
      h.mode === 'unavailable'
        ? h.error ?? 'Backend is running but has no data loaded.'
        : !h.resolver_loaded
        ? h.mode === 'mock'
          ? 'Mock mode: set "trace.mockFunctionId" (e.g. src/auth.py::login) in settings to test without function_ranges.json.'
          : 'Backend cannot map file + line to a function (function_ranges.json not loaded).'
        : undefined;
    return {
      status: 'online',
      mode: h.mode,
      nodes: h.nodes,
      resolverLoaded: h.resolver_loaded,
      llmConfigured: h.llm_configured,
      warning,
    };
  } catch (err) {
    const e = err as BackendError;
    return { status: 'offline', message: e.message };
  }
}

export interface TargetQuery {
  functionId?: string;
  filePath?: string;
  line?: number; // 1-based
}

function targetParams(q: TargetQuery): URLSearchParams {
  const p = new URLSearchParams();
  if (q.functionId) {
    p.set('function_id', q.functionId);
  } else if (q.filePath && q.line) {
    p.set('file_path', q.filePath);
    p.set('line', String(q.line));
  }
  return p;
}

export function getRecommendations(q: TargetQuery, k = 8): Promise<RecommendResponse> {
  const p = targetParams(q);
  p.set('k', String(k));
  return fetchJson<RecommendResponse>(`/api/recommend?${p.toString()}`);
}

export function getEgoGraph(q: TargetQuery, maxNodes = 25): Promise<EgoGraphResponse> {
  const p = targetParams(q);
  p.set('radius', '1');
  p.set('max_nodes', String(maxNodes));
  return fetchJson<EgoGraphResponse>(`/api/ego-graph?${p.toString()}`);
}

/** The LLM can take a while, so this call gets a much longer timeout than the others. */
export function suggestFix(body: { function_id: string; diff: string; function_source?: string }): Promise<SuggestFixResponse> {
  return fetchJson<SuggestFixResponse>(
    '/api/suggest-fix',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) },
    60_000
  );
}

/** One place that turns backend failures into sentences a developer can act on. */
export function describeError(e: BackendError): string {
  if (e.isOffline) {
    return e.message === 'Backend timed out' ? 'The backend took too long to answer. Is it overloaded?' : 'Backend Offline. Start it and press Retry above.';
  }
  switch (e.status) {
    case 404:
      return "This function isn't in the dependency graph yet. It may be new, or the graph needs to be rebuilt.";
    case 422:
      return "The backend couldn't understand the request (bad file path or line). Check the Trace output panel.";
    case 429:
      return e.message;
    case 503:
      return e.message || 'The backend is still starting up. Try again in a moment.';
  }
  return e.status >= 500 ? `Backend error (${e.status}): ${e.message}` : e.message;
}
