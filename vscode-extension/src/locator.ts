import * as vscode from 'vscode';
import { Block, findBlock } from './textUtils';

/** Where a function lives in a document. Uses the language server if it has symbols, else a text search. */
export async function locateBlock(doc: vscode.TextDocument, qualified: string): Promise<Block | undefined> {
  const parts = qualified.split('.');
  try {
    const symbols = await vscode.commands.executeCommand<vscode.DocumentSymbol[]>('vscode.executeDocumentSymbolProvider', doc.uri);
    let level: vscode.DocumentSymbol[] | undefined = symbols;
    let found: vscode.DocumentSymbol | undefined;
    for (const part of parts) {
      found = level?.find((s) => s.name === part || s.name.startsWith(`${part}(`));
      if (!found) {
        break;
      }
      level = found.children;
    }
    if (found && found.selectionRange) {
      const defLine = found.selectionRange.start.line;
      let endLine = found.range.end.line;
      if (found.range.end.character === 0 && endLine > defLine) {
        endLine -= 1;
      }
      return { defLine, endLine };
    }
  } catch {
    /* language server not ready: fall through */
  }
  return findBlock(doc.getText().split(/\r?\n/), qualified);
}
