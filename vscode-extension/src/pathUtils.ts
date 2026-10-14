import * as vscode from 'vscode';
import { relativeUnix } from './pathCore';

export interface Located {
  folder: vscode.WorkspaceFolder;
  rel: string;
}

/** Which workspace folder (multi-root aware) a file belongs to, and its path relative to it. */
export function resolveInWorkspace(uri: vscode.Uri): Located | undefined {
  const folder = vscode.workspace.getWorkspaceFolder(uri);
  if (!folder) {
    return undefined;
  }
  const rel = relativeUnix(folder.uri.fsPath, uri.fsPath);
  return rel ? { folder, rel } : undefined;
}

export function isPython(doc: vscode.TextDocument): boolean {
  return doc.languageId === 'python' && doc.uri.scheme === 'file';
}

/** VS Code lines start at 0, the backend counts from 1. */
export function toBackendLine(zeroBasedLine: number): number {
  return zeroBasedLine + 1;
}
