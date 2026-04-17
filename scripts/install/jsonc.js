/**
 * Minimal JSONC (JSON with comments + trailing commas) parser.
 *
 * Claude Code writes some of its config files with trailing commas and
 * occasional comments. Strict JSON.parse on those throws, so we run the
 * raw text through a lightweight comment/trailing-comma stripper first.
 */

function stripComments(text) {
  const out = [];
  let i = 0;
  const n = text.length;
  let inString = false;
  let quote = '';

  while (i < n) {
    const ch = text[i];
    const next = i + 1 < n ? text[i + 1] : '';

    if (inString) {
      out.push(ch);
      if (ch === '\\' && i + 1 < n) {
        out.push(text[i + 1]);
        i += 2;
        continue;
      }
      if (ch === quote) inString = false;
      i += 1;
      continue;
    }

    if (ch === '"' || ch === "'") {
      inString = true;
      quote = ch;
      out.push(ch);
      i += 1;
      continue;
    }

    if (ch === '/' && next === '/') {
      // line comment — skip until newline (keep the newline so line numbers stay)
      while (i < n && text[i] !== '\n') i += 1;
      continue;
    }
    if (ch === '/' && next === '*') {
      // block comment
      i += 2;
      while (i < n - 1 && !(text[i] === '*' && text[i + 1] === '/')) i += 1;
      i += 2;
      continue;
    }

    out.push(ch);
    i += 1;
  }
  return out.join('');
}

function stripTrailingCommas(text) {
  return text.replace(/,(\s*[\]}])/g, '$1');
}

function parseJsonc(text) {
  if (typeof text !== 'string') throw new TypeError('parseJsonc expects a string');
  const noComments = stripComments(text);
  const noTrailing = stripTrailingCommas(noComments);
  return JSON.parse(noTrailing);
}

module.exports = { parseJsonc, stripComments, stripTrailingCommas };
