import * as vscode from 'vscode';

function normaliseUrl(raw: string): string {
  let u = (raw || '').trim().replace(/\/+$/, '');
  if (!u) {
    u = 'http://localhost:8000';
  }
  return /^https?:\/\//i.test(u) ? u : `http://${u}`;
}

export function cfg() {
  const c = vscode.workspace.getConfiguration('trace');
  const clamp = (n: number, lo: number, hi: number, fallback: number) =>
    Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback;
  return {
    backendUrl: normaliseUrl(c.get<string>('backendUrl', 'http://localhost:8000')),
    debounceMs: clamp(c.get<number>('debounceMs', 700), 300, 3000, 700),
    timeoutMs: clamp(c.get<number>('requestTimeoutMs', 5000), 1000, 60000, 5000),
    mockFunctionId: c.get<string>('mockFunctionId', '').trim(),
  };
}
