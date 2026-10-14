import * as nodePath from 'path';

/**
 * Absolute file path -> workspace-relative path with forward slashes (what the backend stores).
 * Returns undefined when the file is outside the root (including a different Windows drive).
 */
export function relativeUnix(root: string, file: string, p: typeof nodePath = nodePath): string | undefined {
  const rel = p.relative(root, file);
  if (!rel || p.isAbsolute(rel) || rel === '..' || rel.startsWith('..' + p.sep) || rel.startsWith('../')) {
    return undefined;
  }
  return rel.split(p.sep).join('/').replace(/\\/g, '/').replace(/^\.\//, '');
}

// Third-party and generated folders the backend never indexes: asking about them would only produce errors.
const IGNORED = /(^|\/)(\.venv|venv|env|node_modules|site-packages|__pycache__|\.git|\.tox|\.mypy_cache|\.pytest_cache)(\/|$)/;

export function isIgnoredPath(rel: string): boolean {
  return IGNORED.test(rel);
}
