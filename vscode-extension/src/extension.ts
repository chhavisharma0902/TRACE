import * as vscode from 'vscode';
import { BackendError, checkBackend, describeError, getEgoGraph, getRecommendations, TargetQuery } from './backendClient';
import { cfg } from './config';
import { friendlyName } from './names';
import { isIgnoredPath } from './pathCore';
import { isPython, resolveInWorkspace, toBackendLine } from './pathUtils';
import { SidebarProvider } from './sidebarProvider';
import { SuggestFlow } from './suggestFlow';
import { locateBlock } from './locator';
import { BackendState, GraphData, RecRow } from './types';

let log: vscode.OutputChannel;
let statusBar: vscode.StatusBarItem;
let sidebar: SidebarProvider;
let suggest: SuggestFlow;
let editedFile: string | undefined; // the file the developer actually edited (not one picked from the graph)
let activeFolder: vscode.WorkspaceFolder | undefined; // multi-root: the folder that file belongs to
let debounceTimer: NodeJS.Timeout | undefined;
let healthTimer: NodeJS.Timeout | undefined;
let requestSeq = 0; // ignore responses that arrive after a newer request started
let backendMode: 'real' | 'mock' | 'unavailable' | undefined;
let resolverLoaded = true;
const MOCK_DEFAULT_ID = 'src/auth.py::login';

export function activate(context: vscode.ExtensionContext): void {
  log = vscode.window.createOutputChannel('Trace');
  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
  statusBar.command = 'trace.checkBackend';
  statusBar.show();

  sidebar = new SidebarProvider(context.extensionUri, {
    retry: () => void refreshBackendStatus(),
    open: (id) => void openFunction(id),
    focus: (id) => void analyse('node-click', undefined, id),
    suggest: (id) => void suggest.request(id, editedFile, activeFolder),
    accept: () => void suggest.accept(),
    dismiss: () => suggest.dismiss(),
    review: () => void suggest.review(),
  });
  suggest = new SuggestFlow(sidebar, log);

  context.subscriptions.push(
    log,
    statusBar,
    vscode.window.registerWebviewViewProvider(SidebarProvider.viewId, sidebar),
    vscode.workspace.registerTextDocumentContentProvider(SuggestFlow.scheme, suggest),

    vscode.commands.registerCommand('trace.checkBackend', () => refreshBackendStatus()),
    vscode.commands.registerCommand('trace.refresh', () => scheduleAnalysis('manual', vscode.window.activeTextEditor?.document)),

    // Checkpoint 5.1: log the relative path on every save.
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const hit = isPython(doc) ? resolveInWorkspace(doc.uri) : undefined;
      if (hit) {
        const editor = vscode.window.visibleTextEditors.find((e) => e.document === doc);
        const line = editor ? toBackendLine(editor.selection.active.line) : 1;
        console.log(`[Trace] saved ${hit.rel} (line ${line})`);
        log.appendLine(`saved ${hit.rel} (line ${line})`);
      }
      scheduleAnalysis('save', doc);
    }),

    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor) {
        scheduleAnalysis('editor-switch', editor.document);
      }
    }),

    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('trace')) {
        void refreshBackendStatus();
      }
    })
  );

  // Keep the Backend Offline / online state fresh without any user action.
  healthTimer = setInterval(() => {
    if (vscode.window.state.focused) {
      void pollBackend();
    }
  }, 30_000);
  context.subscriptions.push({ dispose: () => healthTimer && clearInterval(healthTimer) });

  void refreshBackendStatus();
  log.appendLine('Trace activated');
}

export function deactivate(): void {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
}

/** Quiet re-check: updates the status only if something changed, so the sidebar never flickers. */
async function pollBackend(): Promise<void> {
  try {
    setBackend(await checkBackend());
  } catch (err) {
    log.appendLine(`health check failed: ${(err as Error).message}`);
  }
}

async function refreshBackendStatus(): Promise<void> {
  setBackend({ status: 'checking' });
  setBackend(await checkBackend());
}

function setBackend(backend: BackendState): void {
  if (backend.status === 'online') {
    backendMode = backend.mode;
    resolverLoaded = backend.resolverLoaded;
  }
  sidebar.update({ backend });
  if (backend.status === 'online') {
    statusBar.text = `$(pulse) Trace${backend.mode === 'mock' ? ' (mock)' : ''}`;
    statusBar.tooltip = 'Trace backend connected. Click to re-check.';
    statusBar.backgroundColor = undefined;
  } else if (backend.status === 'offline') {
    statusBar.text = '$(warning) Trace offline';
    statusBar.tooltip = `${backend.message}. Click to retry.`;
    statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  } else {
    statusBar.text = '$(sync~spin) Trace';
    statusBar.tooltip = 'Checking backend…';
  }
}

/** Debounced so autosave or rapid tab switching can never flood the backend. */
function scheduleAnalysis(reason: string, doc?: vscode.TextDocument): void {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(() => {
    analyse(reason, doc).catch((err) => {
      // A bug here must never take the editor down: log it and show a calm message.
      log.appendLine(`analyse crashed: ${(err as Error).stack ?? err}`);
      sidebar.update({ loading: false, notice: 'Something unexpected happened. Details are in the Trace output panel.' });
    });
  }, cfg().debounceMs);
}

async function analyse(reason: string, doc?: vscode.TextDocument, overrideId?: string): Promise<void> {
  let query: TargetQuery;
  let where = '';

  if (overrideId) {
    query = { functionId: overrideId };
    where = overrideId;
  } else {
    if (!doc || !isPython(doc)) {
      return;
    }
    const hit = resolveInWorkspace(doc.uri);
    if (!hit) {
      return; // outside every workspace folder
    }
    const filePath = hit.rel;
    if (isIgnoredPath(filePath)) {
      sidebar.update({
        loading: false,
        rows: undefined,
        graph: undefined,
        notice: 'Trace skips virtual environments and other third-party folders.',
        graphNotice: 'Trace skips virtual environments and other third-party folders.',
      });
      return;
    }
    activeFolder = hit.folder;
    const editor = vscode.window.visibleTextEditors.find((e) => e.document === doc);
    const line = toBackendLine(editor ? editor.selection.active.line : 0);
    editedFile = filePath;

    // Mock mode has no function_ranges.json, so it cannot map file+line. Use a fixed function id instead.
    const useFixedId = backendMode === 'mock' && !resolverLoaded;
    const fixedId = cfg().mockFunctionId || (useFixedId ? MOCK_DEFAULT_ID : '');
    query = fixedId ? { functionId: fixedId } : { filePath, line };
    where = fixedId || `${filePath}:${line}`;
    sidebar.update({ target: { filePath, line, title: filePath.split('/').pop() ?? filePath, subtitle: filePath } });
  }

  const seq = ++requestSeq;
  sidebar.update({ loading: true, notice: undefined, graphNotice: undefined });
  log.appendLine(`analyse (${reason}): ${where}`);

  const [recRes, graphRes] = await Promise.allSettled([getRecommendations(query), getEgoGraph(query)]);
  if (seq !== requestSeq) {
    return; // a newer request is in flight
  }

  // Backend down: show it clearly and stop.
  const failure = [recRes, graphRes].find((r) => r.status === 'rejected') as PromiseRejectedResult | undefined;
  if (failure && (failure.reason as BackendError).isOffline) {
    setBackend({ status: 'offline', message: (failure.reason as BackendError).message });
    sidebar.update({ loading: false, rows: undefined, graph: undefined, notice: 'Backend Offline. Start it and press Retry above.', graphNotice: 'Backend Offline.' });
    return;
  }

  // Table
  let centerId: string | null = null;
  if (recRes.status === 'fulfilled') {
    centerId = recRes.value.function_id;
    if (!centerId) {
      sidebar.update({ loading: false, rows: undefined, graph: undefined, notice: "Your cursor isn't inside a function. Click inside one and save again.", graphNotice: "Your cursor isn't inside a function." });
      return;
    }
    const name = friendlyName(centerId);
    const max = Math.max(...recRes.value.recommendations.map((r) => r.score), 0.0001);
    const rows: RecRow[] = recRes.value.recommendations.map((r) => {
      const n = friendlyName(r.function_id);
      return { id: r.function_id, title: n.title, subtitle: n.subtitle, score: r.score, pct: Math.round((r.score / max) * 100), viaCall: r.via_call, viaCochange: r.via_cochange };
    });
    sidebar.update({
      target: { filePath: centerId.split('::')[0], line: 0, title: name.title, subtitle: name.subtitle },
      rows,
      notice: undefined,
    });
  } else {
    sidebar.update({ rows: undefined, notice: describeError(recRes.reason as BackendError) });
  }

  // Mind-tree
  if (graphRes.status === 'fulfilled' && graphRes.value.center) {
    const g = graphRes.value;
    const graph: GraphData = {
      center: g.center as string,
      nodes: g.nodes.map((id) => ({ id, label: friendlyName(id).title, file: id, isCenter: id === g.center })),
      edges: g.edges.map((e) => ({ from: e.source, to: e.target, type: e.edge_type, count: e.count })),
      truncated: g.truncated,
      totalNodes: g.total_nodes,
    };
    sidebar.update({ graph, graphNotice: undefined });
  } else {
    const msg = graphRes.status === 'rejected' ? describeError(graphRes.reason as BackendError) : 'No graph for this function.';
    sidebar.update({ graph: undefined, graphNotice: msg });
  }
  sidebar.update({ loading: false });
}

/** Opens the file that holds a function and puts the cursor on its `def` line. */
async function openFunction(functionId: string): Promise<void> {
  const [file, qualified = ''] = functionId.split('::');
  const folder = activeFolder ?? vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    return;
  }
  try {
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.joinPath(folder.uri, ...file.split('/')));
    const block = qualified && qualified !== '<module>' ? await locateBlock(doc, qualified) : undefined;
    const pos = new vscode.Position(block?.defLine ?? 0, 0);
    const range = new vscode.Range(pos, pos);
    const editor = await vscode.window.showTextDocument(doc, { preview: false, selection: range });
    editor.revealRange(range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
  } catch {
    void vscode.window.showWarningMessage(`Trace: couldn't open ${file} in this workspace.`);
  }
}
