// Pure text helpers (no vscode import) so they can be unit-tested.

export interface Block {
  defLine: number; // zero-based line of the `def` / `class`
  endLine: number; // zero-based last line of the body
}

const indentOf = (line: string): number => line.length - line.trimStart().length;

function stripComment(line: string): string {
  let quote = '';
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quote) {
      if (ch === quote && line[i - 1] !== '\\') {
        quote = '';
      }
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === '#') {
      return line.slice(0, i);
    }
  }
  return line;
}

/** Finds "Flask.send_static_file" in Python source by walking class -> method. */
export function findBlock(lines: string[], qualified: string): Block | undefined {
  const parts = qualified.split('.');
  let from = 0;
  let defLine = -1;
  for (const part of parts) {
    const safe = part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`^\\s*(async\\s+def|def|class)\\s+${safe}\\b`);
    let hit = -1;
    for (let i = from; i < lines.length; i++) {
      if (re.test(lines[i])) {
        hit = i;
        break;
      }
    }
    if (hit === -1) {
      return undefined;
    }
    defLine = hit;
    from = hit + 1;
  }

  // Skip a multi-line signature: it ends on the first line where brackets are balanced.
  let depth = 0;
  let sigEnd = defLine;
  for (let i = defLine; i < lines.length; i++) {
    for (const ch of stripComment(lines[i])) {
      if ('([{'.includes(ch)) {
        depth++;
      } else if (')]}'.includes(ch)) {
        depth--;
      }
    }
    if (depth <= 0) {
      sigEnd = i;
      break;
    }
  }

  const defIndent = indentOf(lines[defLine]);
  let endLine = sigEnd;
  for (let j = sigEnd + 1; j < lines.length; j++) {
    if (lines[j].trim() === '') {
      continue;
    }
    if (indentOf(lines[j]) <= defIndent) {
      break;
    }
    endLine = j;
  }
  return { defLine, endLine };
}

export type ParsedSuggestion =
  | { kind: 'nochange'; explanation: string }
  | { kind: 'diff'; explanation: string; diff: string }
  | { kind: 'advice'; explanation: string };

/** The backend prompt makes the model answer NO_CHANGE_NEEDED, or text + a ```diff block, or plain advice. */
export function parseSuggestion(text: string): ParsedSuggestion {
  const t = text.trim();
  if (/^NO_CHANGE_NEEDED/.test(t)) {
    return { kind: 'nochange', explanation: t.replace(/^NO_CHANGE_NEEDED[:\s.\-]*/, '').trim() };
  }
  const m = /```(?:diff|patch)?[ \t]*\r?\n([\s\S]*?)```/.exec(t);
  if (m) {
    const explanation = (t.slice(0, m.index) + t.slice(m.index + m[0].length)).trim();
    return { kind: 'diff', explanation, diff: m[1].replace(/\s+$/, '') };
  }
  return { kind: 'advice', explanation: t };
}

interface Op {
  t: ' ' | '-' | '+';
  text: string;
}

function parseHunks(diff: string): Op[][] {
  const hunks: Op[][] = [];
  let cur: Op[] | undefined;
  const hasHunkHeader = /^@@/m.test(diff);
  if (!hasHunkHeader) {
    cur = [];
    hunks.push(cur);
  }
  for (const raw of diff.split(/\r?\n/)) {
    if (raw.startsWith('@@')) {
      cur = [];
      hunks.push(cur);
      continue;
    }
    if (!cur) {
      continue; // file headers before the first hunk
    }
    if (cur.length === 0 && (raw.startsWith('--- ') || raw.startsWith('+++ '))) {
      continue;
    }
    if (raw.startsWith('\\')) {
      continue; // "\ No newline at end of file"
    }
    const c = raw[0];
    if (c === '+' || c === '-' || c === ' ') {
      cur.push({ t: c, text: raw.slice(1) });
    } else {
      cur.push({ t: ' ', text: raw });
    }
  }
  return hunks.filter((h) => h.length > 0);
}

/**
 * Applies a model-written diff to the lines of ONE function. Line numbers in the diff are ignored:
 * each hunk is located by matching its context + removed lines (whitespace-trimmed).
 * Returns undefined when any hunk can't be located, so we never guess.
 */
export function applyDiffToLines(lines: string[], diff: string): string[] | undefined {
  const hunks = parseHunks(diff);
  if (hunks.length === 0) {
    return undefined;
  }
  let work = [...lines];
  let searchFrom = 0;
  let changed = false;

  for (const ops of hunks) {
    const old = ops.filter((o) => o.t !== '+').map((o) => o.text.trim());
    if (old.length === 0 || old.every((l) => l === '')) {
      return undefined;
    }
    let idx = -1;
    for (let i = searchFrom; i + old.length <= work.length; i++) {
      if (old.every((l, k) => work[i + k].trim() === l)) {
        idx = i;
        break;
      }
    }
    if (idx === -1) {
      return undefined;
    }
    const replacement: string[] = [];
    let ptr = idx;
    for (const op of ops) {
      if (op.t === ' ') {
        replacement.push(work[ptr++]); // keep the file's own exact line
      } else if (op.t === '-') {
        ptr++;
        changed = true;
      } else {
        replacement.push(op.text);
        changed = true;
      }
    }
    work = [...work.slice(0, idx), ...replacement, ...work.slice(idx + old.length)];
    searchFrom = idx + replacement.length;
  }
  return changed ? work : undefined;
}
