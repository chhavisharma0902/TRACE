const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const { findBlock, parseSuggestion, applyDiffToLines } = require('../out/textUtils.js');
const { relativeUnix, isIgnoredPath } = require('../out/pathCore.js');

const SRC = `import os

class Flask:
    def send_static_file(self, filename):
        if not self.has_static_folder:
            raise RuntimeError('no static folder')
        max_age = self.get_send_file_max_age(filename)
        return send_from_directory(self.static_folder, filename, max_age=max_age)

    def other(
        self,
        a,
    ):
        return a  # trailing comment with ( paren

    async def fetch(self): return 1

def top(x): return x
y = 1
`.split('\n');

test('findBlock: method, multi-line signature, one-liner, async, missing', () => {
  assert.deepStrictEqual(findBlock(SRC, 'Flask.send_static_file'), { defLine: 3, endLine: 7 });
  assert.deepStrictEqual(findBlock(SRC, 'Flask.other'), { defLine: 9, endLine: 13 });
  assert.deepStrictEqual(findBlock(SRC, 'Flask.fetch'), { defLine: 15, endLine: 15 });
  assert.deepStrictEqual(findBlock(SRC, 'top'), { defLine: 17, endLine: 17 });
  assert.strictEqual(findBlock(SRC, 'Flask.nope'), undefined);
  assert.strictEqual(findBlock(SRC, 'Nope.send_static_file'), undefined);
});

test('parseSuggestion: no-change, diff block, plain advice', () => {
  assert.strictEqual(parseSuggestion('NO_CHANGE_NEEDED It is independent.').kind, 'nochange');
  const d = parseSuggestion('Add a guard.\n```diff\n-a\n+b\n```');
  assert.strictEqual(d.kind, 'diff');
  assert.strictEqual(d.explanation, 'Add a guard.');
  assert.strictEqual(d.diff, '-a\n+b');
  assert.strictEqual(parseSuggestion('Check the callers.').kind, 'advice');
  assert.strictEqual(parseSuggestion('Fix:\n```\n-a\n+b\n```').kind, 'diff'); // fence without a language tag
});

test('applyDiffToLines: applies by matching text, ignores wrong line numbers, keeps file whitespace', () => {
  const fn = SRC.slice(3, 8);
  const diff = '--- a/x.py\n+++ b/x.py\n@@ -99,3 +99,5 @@\n         max_age = self.get_send_file_max_age(filename)\n-        return send_from_directory(self.static_folder, filename, max_age=max_age)\n+        if max_age is None:\n+            max_age = 0\n+        return send_from_directory(self.static_folder, filename, max_age=max_age)';
  const out = applyDiffToLines(fn, diff);
  assert.ok(out);
  assert.strictEqual(out.length, 7); // 5 lines - 1 removed + 3 added
  assert.ok(out.includes('            max_age = 0'));
});

test('applyDiffToLines: refuses instead of guessing', () => {
  const fn = SRC.slice(3, 8);
  assert.strictEqual(applyDiffToLines(fn, '@@\n-nonexistent line\n+new'), undefined); // cannot locate
  assert.strictEqual(applyDiffToLines(fn, '@@\n+only an insertion'), undefined); // nothing to anchor on
  assert.strictEqual(applyDiffToLines(fn, ''), undefined);
  assert.strictEqual(applyDiffToLines(fn, '@@\n ' + fn[0]), undefined); // context only: no change
});

test('applyDiffToLines: two hunks apply in order', () => {
  const lines = ['def f():', '    a = 1', '    b = 2', '    c = 3', '    return a'];
  const out = applyDiffToLines(lines, '@@\n-    a = 1\n+    a = 10\n@@\n-    c = 3\n+    c = 30');
  assert.deepStrictEqual(out, ['def f():', '    a = 10', '    b = 2', '    c = 30', '    return a']);
});

test('relativeUnix: Windows and POSIX paths become forward-slash relative paths', () => {
  assert.strictEqual(relativeUnix('C:\\proj', 'C:\\proj\\src\\main.py', path.win32), 'src/main.py');
  assert.strictEqual(relativeUnix('C:\\proj', 'c:\\proj\\src\\main.py', path.win32), 'src/main.py'); // drive letter case
  assert.strictEqual(relativeUnix('/home/me/proj', '/home/me/proj/src/main.py', path.posix), 'src/main.py');
  assert.strictEqual(relativeUnix('C:\\proj', 'D:\\other\\a.py', path.win32), undefined); // different drive
  assert.strictEqual(relativeUnix('/home/me/proj', '/home/me/other/a.py', path.posix), undefined);
  assert.strictEqual(relativeUnix('/home/me/proj', '/home/me/proj', path.posix), undefined);
});

test('isIgnoredPath: skips virtualenvs and third-party code, keeps your code', () => {
  for (const p of ['.venv/lib/x.py', 'venv/a.py', 'pkg/site-packages/y.py', 'node_modules/z.py', 'src/__pycache__/a.py']) {
    assert.ok(isIgnoredPath(p), p);
  }
  for (const p of ['src/app.py', 'src/environment.py', 'tests/venv_utils.py', 'src/envs/a.py']) {
    assert.ok(!isIgnoredPath(p), p);
  }
});
