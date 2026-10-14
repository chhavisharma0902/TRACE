import { execFile } from 'child_process';
import * as vscode from 'vscode';
import { BackendError, describeError, suggestFix } from './backendClient';
import { locateBlock } from './locator';
import { friendlyName } from './names';
import { SidebarProvider } from './sidebarProvider';
import { applyDiffToLines, parseSuggestion } from './textUtils';
import { SuggestionView } from './types';

interface Pending {
  uri: vscode.Uri;
  startLine: number;
  endLine: number;
  newText: string;
  baseText: string;
  proposedUri: vscode.Uri;
  title: string;
}

function run(cmd: string, args: string[], cwd: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, { cwd, maxBuffer: 5 * 1024 * 1024 }, (err, stdout) => (err ? reject(err) : resolve(stdout)));
  });
}

/** The developer's edit as a unified diff: everything uncommitted in that file. */
const GIT_FLAGS = ['-c', 'core.quotepath=false', '--no-pager', 'diff', '--no-color', '--no-ext-diff', '-U3'];
const MAX_DIFF_CHARS = 150_000; // the backend rejects > 200k
const MAX_SOURCE_CHARS = 100_000;

async function gitDiff(cwd: string, relPath: string): Promise<string> {
  try {
    const d = await run('git', [...GIT_FLAGS, 'HEAD', '--', relPath], cwd);
    if (d.trim()) {
      return d;
    }
  } catch {
    /* repo without commits, or not a repo: try the plain diff below */
  }
  return run('git', [...GIT_FLAGS, '--', relPath], cwd);
}

const clip = (text: string, max: number) => (text.length > max ? `${text.slice(0, max)}\n... [truncated]` : text);

/**
 * Suggest-fix lifecycle. Nothing here ever edits a file except accept(),
 * which only runs when the developer presses Accept.
 */
export class SuggestFlow implements vscode.TextDocumentContentProvider {
  static readonly scheme = 'trace-proposed';
  private proposed = new Map<string, string>();
  private pending?: Pending;
  private seq = 0;

  constructor(private readonly sidebar: SidebarProvider, private readonly log: vscode.OutputChannel) {}

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.proposed.get(uri.toString()) ?? '';
  }

  private show(s: SuggestionView | undefined): void {
    this.sidebar.update({ suggestion: s });
  }

  async request(flaggedId: string, editedFile: string | undefined, folder?: vscode.WorkspaceFolder): Promise<void> {
    const seq = ++this.seq;
    this.pending = undefined;
    const name = friendlyName(flaggedId);
    const base = { functionId: flaggedId, title: name.title, subtitle: name.subtitle };
    const fail = (message: string) => this.show({ ...base, status: 'error', message });

    if (!vscode.workspace.isTrusted) {
      return fail('Suggest fix runs git, which is switched off in Restricted Mode. Trust this workspace to use it.');
    }
    folder = folder ?? vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
      return fail('Open a folder first.');
    }
    if (!editedFile) {
      return fail('Edit and save a Python file first, so Trace knows what you changed.');
    }
    this.show({ ...base, status: 'loading', message: 'Collecting your changes…' });

    let diff = '';
    try {
      diff = await gitDiff(folder.uri.fsPath, editedFile);
    } catch (e) {
      const msg = (e as NodeJS.ErrnoException).code === 'ENOENT' ? 'git is not installed or not on your PATH' : (e as Error).message.split('\n')[0];
      return fail(`Couldn't read your changes with git (${msg}). Trace needs the project to be a git repository.`);
    }
    if (!diff.trim()) {
      return fail(`No uncommitted changes found in ${editedFile}. Make an edit, save, then try again.`);
    }

    // Source of the flagged function (it lives in another place than the one you edited).
    const [file, qualified = ''] = flaggedId.split('::');
    let doc: vscode.TextDocument | undefined;
    let block: { defLine: number; endLine: number } | undefined;
    let source: string | undefined;
    try {
      doc = await vscode.workspace.openTextDocument(vscode.Uri.joinPath(folder.uri, ...file.split('/')));
      if (qualified && qualified !== '<module>') {
        block = await locateBlock(doc, qualified);
        if (block) {
          source = doc.getText(new vscode.Range(block.defLine, 0, block.endLine, doc.lineAt(block.endLine).text.length));
        }
      }
    } catch {
      /* the model can still give plain-language advice without source */
    }

    this.show({ ...base, status: 'loading', message: 'Asking the model… this can take a few seconds.' });
    let text: string;
    try {
      text = (await suggestFix({ function_id: flaggedId, diff: clip(diff, MAX_DIFF_CHARS), function_source: source === undefined ? undefined : clip(source, MAX_SOURCE_CHARS) })).suggestion;
    } catch (e) {
      if (seq !== this.seq) {
        return;
      }
      const err = e as BackendError;
      this.log.appendLine(`suggest-fix failed (${err.status}): ${err.message}`);
      return fail(describeError(err));
    }
    if (seq !== this.seq) {
      return; // dismissed or replaced while waiting
    }

    const parsed = parseSuggestion(text);
    if (parsed.kind === 'nochange') {
      return this.show({ ...base, status: 'nochange', explanation: parsed.explanation || 'No change is needed.' });
    }
    if (parsed.kind === 'advice') {
      return this.show({ ...base, status: 'advice', explanation: parsed.explanation });
    }

    // A diff: try to turn it into a concrete edit of that function. If we can't match it, show it read-only.
    const ready: SuggestionView = { ...base, status: 'ready', explanation: parsed.explanation, diff: parsed.diff, canApply: false };
    if (!doc || !block || source === undefined) {
      ready.cantApplyReason = "Trace couldn't locate this function's source, so the diff is for reading only.";
      return this.show(ready);
    }
    const eol = doc.eol === vscode.EndOfLine.CRLF ? '\r\n' : '\n';
    const newLines = applyDiffToLines(source.split(/\r?\n/), parsed.diff);
    if (!newLines) {
      ready.cantApplyReason = "Trace couldn't match this diff to the current code, so it can't be applied safely. Review it and edit by hand.";
      return this.show(ready);
    }

    const baseText = doc.getText();
    const startOffset = doc.offsetAt(new vscode.Position(block.defLine, 0));
    const endOffset = doc.offsetAt(new vscode.Position(block.endLine, doc.lineAt(block.endLine).text.length));
    const newText = newLines.join(eol);
    const proposedUri = vscode.Uri.parse(`${SuggestFlow.scheme}:/${file}`).with({ query: String(Date.now()) });
    this.proposed.set(proposedUri.toString(), baseText.slice(0, startOffset) + newText + baseText.slice(endOffset));

    this.pending = { uri: doc.uri, startLine: block.defLine, endLine: block.endLine, newText, baseText, proposedUri, title: name.title };
    ready.canApply = true;
    this.show(ready);
    await this.review(true);
  }

  /** Opens VS Code's diff editor: your file on the left, the proposed version on the right. */
  async review(preserveFocus = false): Promise<void> {
    const p = this.pending;
    if (!p) {
      return;
    }
    await vscode.commands.executeCommand('vscode.diff', p.uri, p.proposedUri, `Trace: proposed change to ${p.title}`, {
      preview: true,
      preserveFocus,
    });
  }

  /** The ONLY place a suggestion touches a file, and only after the developer clicks Accept. */
  async accept(): Promise<void> {
    const p = this.pending;
    if (!p) {
      return;
    }
    const doc = await vscode.workspace.openTextDocument(p.uri);
    if (doc.getText() !== p.baseText) {
      this.pending = undefined;
      this.show({ functionId: '', title: p.title, subtitle: '', status: 'error', message: 'That file changed after the suggestion was made, so nothing was applied. Request a new suggestion.' });
      return;
    }
    const edit = new vscode.WorkspaceEdit();
    edit.replace(p.uri, new vscode.Range(p.startLine, 0, p.endLine, doc.lineAt(p.endLine).text.length), p.newText);
    const ok = await vscode.workspace.applyEdit(edit);
    this.pending = undefined;
    this.show(undefined);
    if (ok) {
      await vscode.window.showTextDocument(doc, { preview: false });
      void vscode.window.showInformationMessage(`Trace: applied the change to ${p.title}. It is not saved yet. Review it, then save (Ctrl+Z undoes it).`);
    } else {
      void vscode.window.showWarningMessage('Trace: VS Code refused to apply the edit.');
    }
  }

  dismiss(): void {
    this.seq++; // ignore any answer still on its way
    this.pending = undefined;
    this.show(undefined);
  }
}
