import * as vscode from 'vscode';
import { ViewState } from './types';

export interface SidebarHandlers {
  retry: () => void;
  open: (functionId: string) => void;
  focus: (functionId: string) => void;
  suggest: (functionId: string) => void;
  accept: () => void;
  dismiss: () => void;
  review: () => void;
}

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewId = 'trace.sidebar';
  private view?: vscode.WebviewView;
  private state: ViewState = { backend: { status: 'checking' } };

  constructor(private readonly extensionUri: vscode.Uri, private readonly h: SidebarHandlers) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, 'media')],
    };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage((msg: { type: string; id?: string }) => {
      switch (msg.type) {
        case 'ready': this.push(); break;
        case 'retry': this.h.retry(); break;
        case 'open': if (msg.id) { this.h.open(msg.id); } break;
        case 'focus': if (msg.id) { this.h.focus(msg.id); } break;
        case 'suggest': if (msg.id) { this.h.suggest(msg.id); } break;
        case 'accept': this.h.accept(); break;
        case 'dismiss': this.h.dismiss(); break;
        case 'review': this.h.review(); break;
      }
    });
  }

  update(patch: Partial<ViewState>): void {
    this.state = { ...this.state, ...patch };
    this.push();
  }

  private push(): void {
    this.view?.webview.postMessage({ type: 'state', state: this.state });
  }

  private html(webview: vscode.Webview): string {
    const visUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, 'media', 'vendor', 'vis-network.min.js'));
    const nonce = Array.from({ length: 24 }, () => Math.random().toString(36)[2]).join('');
    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); color: var(--vscode-foreground); padding: 8px 12px; }
  h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; opacity: .7; margin: 18px 0 8px; font-weight: 600; }
  .card { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 10px 12px; background: var(--vscode-editorWidget-background); }
  .row { display: flex; align-items: center; gap: 8px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .dot.online { background: var(--vscode-testing-iconPassed, #3fb950); }
  .dot.offline { background: var(--vscode-testing-iconFailed, #f85149); }
  .dot.checking { background: var(--vscode-testing-iconQueued, #d29922); }
  .muted { opacity: .65; font-size: .92em; }
  .warn { margin-top: 8px; color: var(--vscode-editorWarning-foreground); font-size: .92em; }
  .target-title { font-weight: 600; }
  .empty { padding: 14px 4px; opacity: .6; text-align: center; font-size: .95em; }
  button { margin-top: 10px; background: var(--vscode-button-background); color: var(--vscode-button-foreground);
           border: none; padding: 5px 12px; border-radius: 3px; cursor: pointer; }
  button:hover { background: var(--vscode-button-hoverBackground); }
  .rec { padding: 8px 6px; border-radius: 4px; cursor: pointer; border-bottom: 1px solid var(--vscode-panel-border); }
  .rec:hover { background: var(--vscode-list-hoverBackground); }
  .rec-top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
  .rec-name { font-weight: 600; word-break: break-all; }
  .rec-score { font-variant-numeric: tabular-nums; opacity: .85; flex: none; }
  .bar { height: 4px; border-radius: 2px; background: var(--vscode-panel-border); margin: 6px 0 5px; overflow: hidden; }
  .bar > i { display: block; height: 100%; background: var(--vscode-progressBar-background); }
  .badge { font-size: .78em; padding: 0 6px; border-radius: 8px; margin-right: 5px; border: 1px solid; }
  .badge.call { color: #58a6ff; border-color: #58a6ff; }
  .badge.cochange { color: #f0883e; border-color: #f0883e; }
  .spin { opacity: .7; padding: 14px 4px; text-align: center; }
  #netwrap { height: 340px; overflow: auto; border: 1px solid var(--vscode-panel-border); border-radius: 6px; background: var(--vscode-editorWidget-background); }
  #net { background: var(--vscode-editorWidget-background); }
  .tools { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
  .tools button { margin: 0; padding: 2px 9px; min-width: 28px; }
  .tools label { font-size: .85em; opacity: .85; display: flex; align-items: center; gap: 4px; margin-left: auto; cursor: pointer; }
  .legend { display: flex; gap: 14px; margin-top: 6px; font-size: .85em; opacity: .85; flex-wrap: wrap; }
  .legend i { display: inline-block; width: 18px; height: 0; border-top: 3px solid; vertical-align: middle; margin-right: 5px; }
  button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
  button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button.sf { margin: 6px 0 0; padding: 2px 9px; font-size: .85em; }
  button:disabled { opacity: .5; cursor: default; }
  .btns { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .btns button { margin: 0; }
  pre.diff { margin: 8px 0 0; padding: 8px; overflow-x: auto; background: var(--vscode-textCodeBlock-background); border-radius: 4px; font-family: var(--vscode-editor-font-family); font-size: .88em; line-height: 1.45; }
  .dl { display: block; white-space: pre; }
  .dl.add { color: var(--vscode-gitDecoration-addedResourceForeground, #3fb950); }
  .dl.del { color: var(--vscode-gitDecoration-deletedResourceForeground, #f85149); }
  .dl.hunk { opacity: .55; }
  .sug-title { font-weight: 600; margin-bottom: 6px; }
  .note { margin-top: 8px; font-size: .9em; color: var(--vscode-editorWarning-foreground); }
  .err { color: var(--vscode-errorForeground); }
  .pill { font-size: .8em; padding: 1px 7px; border-radius: 10px; border: 1px solid var(--vscode-panel-border); margin-left: 6px; }
</style>
</head>
<body>
  <div id="status" class="card"></div>

  <h2>Editing</h2>
  <div id="target" class="card"></div>

  <div id="sugsec" style="display:none">
    <h2>Suggested fix</h2>
    <div id="sug" class="card"></div>
  </div>

  <h2>Related functions</h2>
  <div id="table" class="empty">Save a Python file to see which functions may need review.</div>

  <h2>Mind-tree</h2>
  <div id="tree" class="empty">The dependency and co-change graph will appear here.</div>

<script nonce="${nonce}" src="${visUri}"></script>
<script nonce="${nonce}">
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  function renderStatus(b) {
    if (b.status === 'checking') {
      $('status').innerHTML = '<div class="row"><span class="dot checking"></span>Connecting to Trace backend…</div>';
    } else if (b.status === 'offline') {
      $('status').innerHTML =
        '<div class="row"><span class="dot offline"></span><b>Backend Offline</b></div>' +
        '<div class="muted" style="margin-top:6px">' + esc(b.message) + '. Start it with <code>uvicorn src.main:app --port 8000</code> from the backend folder.</div>' +
        '<button id="retry">Retry</button>';
      $('retry').onclick = () => vscode.postMessage({ type: 'retry' });
    } else {
      const modeLabel = b.mode === 'mock' ? 'mock data' : b.mode === 'real' ? 'live graph' : 'no data';
      $('status').innerHTML =
        '<div class="row"><span class="dot online"></span><b>Backend online</b><span class="pill">' + modeLabel + '</span></div>' +
        (b.nodes != null ? '<div class="muted" style="margin-top:6px">' + b.nodes + ' functions in graph</div>' : '') +
        (b.warning ? '<div class="warn">' + esc(b.warning) + '</div>' : '');
    }
  }

  function renderTarget(t) {
    if (!t) {
      $('target').innerHTML = '<div class="muted">Open a Python file and save it.</div>';
      return;
    }
    $('target').innerHTML =
      '<div class="target-title">' + esc(t.title) + '</div>' +
      '<div class="muted">' + esc(t.subtitle || t.filePath) + ' · line ' + t.line + '</div>';
  }

  function renderTable(st) {
    const el = $('table');
    if (st.loading) { el.className = 'spin'; el.textContent = 'Finding related functions…'; return; }
    if (st.notice) { el.className = 'empty'; el.textContent = st.notice; return; }
    if (!st.rows) { el.className = 'empty'; el.textContent = 'Save a Python file to see which functions may need review.'; return; }
    if (st.rows.length === 0) { el.className = 'empty'; el.textContent = 'No related functions found for this one.'; return; }
    el.className = '';
    const canSuggest = st.backend && st.backend.status === 'online' && st.backend.llmConfigured;
    const busy = !!(st.suggestion && st.suggestion.status === 'loading');
    el.innerHTML = st.rows.map((r) =>
      '<div class="rec" data-id="' + esc(r.id) + '" title="Open ' + esc(r.subtitle) + '">' +
        '<div class="rec-top"><span class="rec-name">' + esc(r.title) + '</span><span class="rec-score">' + r.score.toFixed(2) + '</span></div>' +
        '<div class="bar"><i style="width:' + r.pct + '%"></i></div>' +
        (r.viaCall ? '<span class="badge call">calls</span>' : '') +
        (r.viaCochange ? '<span class="badge cochange">changes together</span>' : '') +
        '<span class="muted">' + esc(r.subtitle) + '</span>' +
        (canSuggest ? '<div><button class="sf secondary" data-sf="' + esc(r.id) + '"' + (busy ? ' disabled' : '') + '>Suggest fix</button></div>' : '') +
      '</div>').join('');
    el.querySelectorAll('.rec').forEach((n) => n.addEventListener('click', () => vscode.postMessage({ type: 'open', id: n.dataset.id })));
    el.querySelectorAll('button.sf').forEach((b) => b.addEventListener('click', (ev) => {
      ev.stopPropagation();
      vscode.postMessage({ type: 'suggest', id: b.dataset.sf });
    }));
  }

  function renderDiff(diff) {
    return '<pre class="diff">' + diff.split('\\n').map((l) => {
      const c = l.startsWith('@@') ? 'hunk' : l.startsWith('+') && !l.startsWith('+++') ? 'add' : l.startsWith('-') && !l.startsWith('---') ? 'del' : '';
      return '<span class="dl ' + c + '">' + esc(l || ' ') + '</span>';
    }).join('') + '</pre>';
  }

  let lastSugKey = '';
  function renderSuggestion(st) {
    const sec = $('sugsec'), box = $('sug'), s = st.suggestion;
    if (!s) { sec.style.display = 'none'; lastSugKey = ''; return; }
    sec.style.display = '';
    const head = '<div class="sug-title">' + esc(s.title) + (s.subtitle ? ' <span class="muted">· ' + esc(s.subtitle) + '</span>' : '') + '</div>';
    let body = '';
    if (s.status === 'loading') {
      body = '<div class="muted">' + esc(s.message || 'Working…') + '</div><div class="btns"><button class="secondary" id="sdismiss">Cancel</button></div>';
    } else if (s.status === 'error') {
      body = '<div class="err">' + esc(s.message || 'Something went wrong.') + '</div><div class="btns"><button class="secondary" id="sdismiss">Close</button></div>';
    } else if (s.status === 'nochange') {
      body = '<div>No change needed.</div><div class="muted" style="margin-top:4px">' + esc(s.explanation || '') + '</div><div class="btns"><button class="secondary" id="sdismiss">Close</button></div>';
    } else if (s.status === 'advice') {
      body = '<div>' + esc(s.explanation || '') + '</div><div class="btns"><button class="secondary" id="sdismiss">Close</button></div>';
    } else {
      body = '<div>' + esc(s.explanation || '') + '</div>' + (s.diff ? renderDiff(s.diff) : '') +
        (s.canApply
          ? '<div class="btns"><button id="saccept">Accept</button><button class="secondary" id="sreview">Review diff</button><button class="secondary" id="sdismiss">Dismiss</button></div>' +
            '<div class="muted" style="margin-top:6px">Nothing changes until you press Accept.</div>'
          : '<div class="note">' + esc(s.cantApplyReason || '') + '</div><div class="btns"><button class="secondary" id="sdismiss">Dismiss</button></div>');
    }
    box.innerHTML = head + body;
    const on = (id, type) => { const b = $(id); if (b) b.onclick = () => vscode.postMessage({ type }); };
    on('saccept', 'accept'); on('sreview', 'review'); on('sdismiss', 'dismiss');
    const key = s.functionId + '|' + s.status;
    if (key !== lastSugKey) { lastSugKey = key; sec.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
  }

  const CALL = '#58a6ff', CO = '#f0883e';
  const ZOOMS = [1, 1.5, 2, 3, 4];
  let network = null, graphKey = '', clickTimer = null, lastState = null;
  let zoomIdx = 1, showNeighborLinks = false;
  const cssVar = (n, fb) => getComputedStyle(document.body).getPropertyValue(n).trim() || fb;

  function sizeCanvas(center) {
    const wrap = $('netwrap'), net = $('net');
    if (!wrap || !net || !network) return;
    const z = ZOOMS[zoomIdx];
    const w = Math.round(wrap.clientWidth * z), h = Math.round(340 * z);
    net.style.width = w + 'px'; net.style.height = h + 'px';
    network.setSize(w + 'px', h + 'px');
    network.redraw();
    network.fit({ animation: false });
    if (center !== false) {
      wrap.scrollLeft = Math.max(0, (w - wrap.clientWidth) / 2);
      wrap.scrollTop = Math.max(0, (h - wrap.clientHeight) / 2);
    }
  }

  function renderGraph(st) {
    lastState = st;
    const el = $('tree');
    if (!st.graph) {
      if (st.loading && graphKey) return; // keep the old graph while refreshing
      if (network) { network.destroy(); network = null; }
      graphKey = '';
      el.className = 'empty';
      el.textContent = st.graphNotice || 'The dependency and co-change graph will appear here.';
      return;
    }
    const g = st.graph;
    const key = g.center + '|' + g.nodes.map((n) => n.id).join(',') + '|' + g.edges.length + '|' + showNeighborLinks;
    if (key === graphKey) return;
    graphKey = key;
    el.className = '';
    el.innerHTML =
      '<div class="tools">' +
        '<button id="zout" title="Zoom out">&minus;</button><button id="zin" title="Zoom in">+</button><button id="zfit" title="Reset view">Fit</button>' +
        '<label><input type="checkbox" id="nlinks"' + (showNeighborLinks ? ' checked' : '') + '> links between neighbors</label>' +
      '</div>' +
      '<div id="netwrap"><div id="net"></div></div>' +
      '<div class="legend"><span><i style="border-color:' + CALL + '"></i>calls</span><span><i style="border-color:' + CO + '"></i>changes together</span></div>' +
      '<div class="muted" style="margin-top:4px">' + (g.truncated ? 'Showing ' + g.nodes.length + ' of ' + g.totalNodes + ' functions. ' : '') + 'Click a node to re-center, double-click to jump to its code. Use the scrollbars or +/- to explore.</div>';
    if (network) network.destroy();

    $('zin').onclick = () => { zoomIdx = Math.min(ZOOMS.length - 1, zoomIdx + 1); sizeCanvas(); };
    $('zout').onclick = () => { zoomIdx = Math.max(0, zoomIdx - 1); sizeCanvas(); };
    $('zfit').onclick = () => { zoomIdx = 1; sizeCanvas(); };
    $('nlinks').onchange = (ev) => { showNeighborLinks = ev.target.checked; graphKey = ''; renderGraph(lastState); };

    const fg = cssVar('--vscode-foreground', '#ccc');
    const accent = cssVar('--vscode-button-background', '#0e639c');
    const panel = cssVar('--vscode-editorWidget-background', '#252526');
    const border = cssVar('--vscode-panel-border', '#555');
    const shown = g.edges.filter((e) => showNeighborLinks || e.from === g.center || e.to === g.center);
    const pairTypes = {};
    shown.forEach((e) => { const k = [e.from, e.to].sort().join('>'); (pairTypes[k] = pairTypes[k] || new Set()).add(e.type); });

    const nodes = new vis.DataSet(g.nodes.map((n) => ({
      id: n.id, label: n.label, title: n.file,
      shape: 'box', margin: 6,
      color: { background: n.isCenter ? accent : panel, border: n.isCenter ? accent : border, highlight: { background: accent, border: accent } },
      font: { color: n.isCenter ? cssVar('--vscode-button-foreground', '#fff') : fg, size: n.isCenter ? 14 : 12, face: cssVar('--vscode-font-family', 'sans-serif') },
      borderWidth: n.isCenter ? 2 : 1,
    })));
    const edges = new vis.DataSet(shown.map((e, i) => {
      const both = pairTypes[[e.from, e.to].sort().join('>')].size > 1;
      return {
        id: i, from: e.from, to: e.to,
        color: { color: e.type === 'call' ? CALL : CO, opacity: e.type === 'call' ? 1 : 0.7 },
        width: e.type === 'call' ? 2.2 : 1 + Math.min(e.count, 9) / 3,
        arrows: e.type === 'call' ? 'to' : undefined,
        dashes: e.type === 'cochange',
        title: e.type === 'call' ? 'calls' : 'changed together ' + e.count + 'x',
        smooth: both ? { type: e.type === 'call' ? 'curvedCW' : 'curvedCCW', roundness: 0.25 } : false,
      };
    }));

    network = new vis.Network($('net'), { nodes, edges }, {
      physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -120, springLength: 140, avoidOverlap: 0.8 }, stabilization: { iterations: 200 } },
      interaction: { hover: true, tooltipDelay: 200, zoomView: false, dragView: false },
    });
    sizeCanvas();
    network.once('stabilizationIterationsDone', () => { network.setOptions({ physics: false }); sizeCanvas(); });
    network.on('click', (p) => {
      const id = p.nodes[0];
      if (!id || id === g.center) return;
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => vscode.postMessage({ type: 'focus', id }), 260);
    });
    network.on('doubleClick', (p) => {
      clearTimeout(clickTimer);
      if (p.nodes[0]) vscode.postMessage({ type: 'open', id: p.nodes[0] });
    });
  }

  window.addEventListener('message', (e) => {
    if (e.data.type === 'state') {
      renderGraph(e.data.state);
      renderSuggestion(e.data.state);
      renderStatus(e.data.state.backend);
      renderTarget(e.data.state.target);
      renderTable(e.data.state);
    }
  });
  vscode.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
  }
}
