/** Turns "src/auth.py::login" or "src/app.py::<module>" into something readable. */
export function friendlyName(functionId: string): { title: string; subtitle: string } {
  const sep = functionId.indexOf('::');
  if (sep === -1) {
    return { title: functionId, subtitle: '' };
  }
  const file = functionId.slice(0, sep);
  const name = functionId.slice(sep + 2);
  const base = file.split('/').pop() ?? file;
  if (name === '<module>') {
    return { title: `Top-level code in ${base}`, subtitle: file };
  }
  return { title: `${name}()`, subtitle: file };
}
