# Trace for VS Code

**Predictive code impact analysis, inside your editor.**
Save a Python file and Trace shows which *other* functions are likely to need attention, based on what calls what (static analysis) and what has historically changed together (git history).

This folder is **Member 5 (Frontend Track)** of the TRACE project. It talks to the FastAPI backend in `backend/`.

---

## What you get

| Section in the Trace sidebar | What it shows | Backend call |
|---|---|---|
| **Status** | Backend online / offline, live or mock data, function count | `GET /` |
| **Editing** | The function your cursor is in | `GET /api/recommend` |
| **Suggested fix** | The model's explanation and a colored diff, with Accept / Review diff / Dismiss | `POST /api/suggest-fix` |
| **Related functions** | Ranked list with score bar. Badges: **calls** (blue), **changes together** (orange) | `GET /api/recommend` |
| **Mind-tree** | Graph centered on your function. Blue solid arrow = calls, orange dashed = changes together | `GET /api/ego-graph` |

### How it behaves

| You do | Trace does |
|---|---|
| Save a `.py` file, or switch to another Python tab | After a short pause (default 700 ms) it asks the backend, then fills the table and graph |
| Click a row in the table | Opens that function's file |
| Click **Suggest fix** on a row | Reads your uncommitted `git diff`, sends it with that function's source, and shows the answer |
| Click a graph node | Re-centers the table and graph on that function |
| Double-click a graph node | Opens the file and jumps to the function's `def` line |
| Press **Accept** on a suggestion | Applies it to the file (not saved) |

### Safety rules

These come from the backend contract and are enforced in code:

- **Nothing is ever applied automatically.** Only the Accept button edits a file, and Accept refuses if the file changed after the suggestion was made.
- **Suggestions are only requested on a button click**, never on save.
- A diff Trace cannot match to the current code is shown **read-only** with Accept disabled. Trace never guesses where to apply a change.
- Applied changes are left **unsaved**, so you can review them and press Ctrl+Z.

---

## Requirements

| Need | Notes |
|---|---|
| VS Code 1.85 or newer | |
| Node.js 18 or newer | For building the extension |
| Trace backend running | See below |
| A git repository | Only for **Suggest fix** (it reads `git diff`) |
| Python extension (Pylance) | Optional. Makes jump-to-function more precise. Without it Trace searches the file text instead |

---

## Quick start

### 1. Start the backend

In `backend/` (see `backend/README.md` for the data files):

```bash
# real data (needs unified_graph.json and best_weights.json)
uvicorn src.main:app --port 8000

# or, without the data files
TRACE_USE_MOCK=1 uvicorn src.main:app --port 8000      # macOS / Linux
$env:TRACE_USE_MOCK=1; uvicorn src.main:app --port 8000  # Windows PowerShell
```

Open `http://localhost:8000`. You should see JSON with `"mode": "real"` or `"mock"`.

For **Suggest fix**, put `GEMINI_API_KEY` in `backend/.env`.

### 2. Build and run the extension

```bash
cd vscode-extension
npm install
npm run compile
code --extensionDevelopmentPath="$PWD" "/path/to/a/python/project"
```

(PowerShell: use `$PWD` the same way. cmd: `%cd%`.)

Or open this folder in VS Code and press **F5**. The included `.vscode/launch.json` starts an Extension Development Host.

> The project you open in that window must be the one your graph was built from. Graph data for Flask will not recommend anything for a different repository.

### 3. Use it

1. Click the **Trace** icon in the Activity Bar.
2. Open a Python file from the analysed project, put the cursor inside a function, and **save**.
3. Read the table and graph. Try **Suggest fix**.

---

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `trace.backendUrl` | `http://localhost:8000` | Where the backend runs. `localhost:8000` also works (http is added) |
| `trace.debounceMs` | `700` | Wait this long after the last save or tab switch (300 to 3000) |
| `trace.requestTimeoutMs` | `5000` | Give up on table, graph and health requests after this long. Suggest fix always allows 60 s |
| `trace.mockFunctionId` | empty | Dev only: always query this function id, for example `src/auth.py::login` |

## Commands

| Command | Does |
|---|---|
| `Trace: Refresh Recommendations` | Re-runs the analysis for the active file |
| `Trace: Check Backend Connection` | Re-checks the backend. Clicking the status bar item does the same |

---

## How it works

```
 VS Code event (save / tab switch)
        |  debounce 700 ms
        v
 absolute path -> workspace-relative, forward slashes      (pathCore.ts)
 cursor line + 1  (VS Code counts from 0, backend from 1)
        |
        +--> GET /api/recommend  --> ranked table
        +--> GET /api/ego-graph  --> mind-tree (vis-network)
        |
 Suggest fix click
        +--> git diff (your edit) + function source
        +--> POST /api/suggest-fix --> explanation + diff
        +--> match diff to the code --> VS Code diff tab --> Accept / Dismiss
```

| File | Role |
|---|---|
| `src/extension.ts` | Entry point: events, debounce, status bar, orchestration |
| `src/sidebarProvider.ts` | The webview (table, suggestion card, graph) |
| `src/backendClient.ts` | `fetch` with timeouts and friendly error messages |
| `src/suggestFlow.ts` | Suggest-fix lifecycle: git diff, request, preview, Accept |
| `src/textUtils.ts` | Pure logic: find a function in source, parse model output, apply a diff safely |
| `src/pathCore.ts`, `pathUtils.ts` | Windows/Unix path handling, multi-root workspaces, ignored folders |
| `src/locator.ts` | Function location via the language server, with text-search fallback |
| `src/names.ts` | `src/app.py::<module>` becomes "Top-level code in app.py" |
| `media/vendor/vis-network.min.js` | Graph library, bundled because webviews cannot load CDNs |

---

## Edge cases handled

| Situation | Behavior |
|---|---|
| Backend off, crashed or slow | Status bar and sidebar show **Backend Offline** with a Retry button. Requests time out, so the editor never freezes |
| Autosave or rapid tab switching | Debounced. Older responses that arrive late are ignored |
| Windows paths (`C:\proj\src\a.py`) | Converted to `src/a.py`. Drive-letter case differences and files on another drive are handled |
| Multi-root workspaces | Paths are relative to the folder the file belongs to, and that folder is used for opening files and running git |
| Files in `.venv`, `site-packages`, `node_modules`, ... | Skipped with a short message instead of an error |
| Cursor outside any function | "Your cursor isn't inside a function" |
| Function missing from the graph (new file) | Explains that the graph may need rebuilding |
| `::<module>` results | Shown as "Top-level code in file.py" |
| Large graphs | Top 25 nodes shown, with "Showing 25 of N functions" |
| `suggest-fix` rate limit (429) | Shows the backend's "retry in Ns" message |
| LLM not configured (503) | Shows the backend's message. The Suggest fix button is hidden when the backend reports no key |
| No uncommitted changes, git missing, not a repo | Clear message, nothing is sent |
| Very large diffs or functions | Trimmed to stay under the backend's size limits |
| Model returns plain advice or `NO_CHANGE_NEEDED` | Shown as text. There is nothing to apply |
| Restricted Mode (untrusted workspace) | Suggest fix is disabled (it runs git). Everything else works |
| Webview hidden and shown again | State is restored from the extension |
| Unexpected error in the analysis | Logged to the Trace output panel, the sidebar shows a calm message |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot find module '.../out/extension.js'` | Run `npm install` then `npm run compile` first |
| `'tsc' is not recognized` | `npm install` did not run in this folder |
| Select debugger list appears on F5 | You opened the wrong folder. Open `vscode-extension` itself, so `.vscode/launch.json` is at its root |
| **Trace offline** in the status bar | Start the backend, then click the status bar item. Check `trace.backendUrl` |
| Table says "No related functions" | You are on mock data (only 4 fake functions), or the file is not in the graph |
| Suggest fix button missing | Backend has no `GEMINI_API_KEY`, or it is offline |
| "No uncommitted changes" | Suggest fix compares against git. Edit and save first, and do not commit |
| Blank sidebar with a loading bar | The extension failed to activate. Open **Help > Toggle Developer Tools** and **View > Output > Log (Extension Host)** |
| Debug console shows errors from other extensions | Launch with `--disable-extensions` to see only Trace |

Logs: **View > Output > Trace**.

---

## Development

```bash
npm run watch      # recompile on change
npm test           # compile, then run the unit tests in test/
npm run vendor     # re-copy vis-network into media/vendor after upgrading it
npm run package    # build a .vsix (uses @vscode/vsce)
```

The unit tests cover the logic most likely to break: finding functions, parsing model output, applying diffs (including refusing bad ones), and Windows/Unix path conversion. The UI itself is tested by hand against the checkpoints below.

### Checkpoints (from the work distribution)

| Checkpoint | How to verify |
|---|---|
| 5.1 | Save a `.py` file. **Output > Trace** shows `saved src/x.py (line N)` |
| 5.2 | With the backend running, the sidebar shows the status card, a populated table and the mind-tree |
| 5.3 | Save a real file, see live recommendations, and click a row or node to open it. Then try Suggest fix, Review diff and Accept |

---

## Known limitations

- One analysed file at a time. The table follows the most recently saved or focused Python file.
- Suggest fix needs the project to be a git repository, and compares against uncommitted changes.
- Jump-to-function relies on the Python language server or a text search, so unusual formatting can land a few lines off.
- Recommendation quality depends on the backend's graph. The extension only displays it.
