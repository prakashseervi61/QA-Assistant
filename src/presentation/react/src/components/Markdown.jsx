import { useMemo, useState } from 'react';
import { FiCheck, FiCopy } from 'react-icons/fi';

const ESCAPES = {
  '\\*': '*',
  '\\_': '_',
  '\\`': '`',
  '\\[': '[',
  '\\]': ']',
  '\\(': '(',
  '\\)': ')',
  '\\~': '~',
  '\\#': '#',
  '\\-': '-',
  '\\+': '+',
  '\\>': '>',
  '\\|': '|',
  '\\$': '$',
};

const PLACEHOLDER = '\u0000';
const TOKEN_RE =
  /(`[^`\n]*`)|(\*\*\*([\s\S]+?)\*\*\*)|(\*\*([\s\S]+?)\*\*)|(__([\s\S]+?)__)|(\*([\s\S]+?)\*)|(_([\s\S]+?)_)|(~~([\s\S]+?)~~)|(!?\[[^\]]*\]\([^)\s]+(?:\s+["'][^"']*["'])?\))/g;

let keySeq = 0;
const nextKey = () => ++keySeq;

function replaceEscapes(text) {
  const saved = [];
  const out = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\\' && i + 1 < text.length && ESCAPES[text.slice(i, i + 2)]) {
      saved.push(text[i + 1]);
      out.push(`${PLACEHOLDER}${saved.length - 1}${PLACEHOLDER}`);
      i++;
    } else {
      out.push(text[i]);
    }
  }
  return { text: out.join(''), saved };
}

function restore(text, saved) {
  return text.replace(new RegExp(`${PLACEHOLDER}(\\d+)${PLACEHOLDER}`, 'g'), (_, n) => {
    const value = saved[Number(n)];
    return value === undefined ? '' : value;
  });
}

function pushText(out, text, saved) {
  const restored = restore(text, saved);
  if (restored) out.push(restored);
}

const CODE_CLASS =
  'rounded bg-paper-200 px-1 py-0.5 font-mono text-[0.85em] text-ink-secondary';

function renderLink(token, saved) {
  const match = token.match(/^(!?)\[([^\]]*)\]\(([^)\s]+)(?:\s+["']([^"']*)["'])?\)$/);
  if (!match) return restore(token, saved);
  const isImage = match[1] === '!';
  const label = match[2];
  const url = match[3];
  // Only allow safe schemes; anything else (javascript:, data:, vbscript:)
  // is rendered as plain text instead of an anchor.
  const isSafeHref =
    /^(https?:|mailto:)/i.test(url) || url.startsWith('/') || url.startsWith('#');
  if (!isSafeHref) return restore(label, saved);
  const external = /^https?:/i.test(url);
  return (
    <a
      key={nextKey()}
      href={url}
      title={match[4] || undefined}
      target={external ? '_blank' : undefined}
      rel={external ? 'noopener noreferrer' : undefined}
      className="text-brand-600 underline decoration-brand-300 underline-offset-2 transition-colors hover:text-brand-700"
    >
      {isImage ? `${restore(label, saved)} ↗` : parseInline(label)}
    </a>
  );
}

export function parseInline(raw) {
  const { text, saved } = replaceEscapes(raw == null ? '' : String(raw));
  const out = [];
  let cursor = 0;
  for (const match of text.matchAll(TOKEN_RE)) {
    const [
      full,
      code,
      ,
      strongItalicInner,
      ,
      boldInner,
      ,
      underlineInner,
      ,
      italicInner,
      ,
      underscoreInner,
      ,
      strikeInner,
      link,
    ] = match;
    if (match.index > cursor) pushText(out, text.slice(cursor, match.index), saved);
    cursor = match.index + full.length;
    if (code) {
      out.push(
        <code key={nextKey()} className={CODE_CLASS}>
          {restore(code.slice(1, -1), saved)}
        </code>,
      );
    } else if (strongItalicInner) {
      out.push(
        <strong key={nextKey()}>
          <em>{parseInline(strongItalicInner)}</em>
        </strong>,
      );
    } else if (boldInner) {
      out.push(<strong key={nextKey()}>{parseInline(boldInner)}</strong>);
    } else if (underlineInner) {
      out.push(<strong key={nextKey()}>{parseInline(underlineInner)}</strong>);
    } else if (italicInner) {
      out.push(<em key={nextKey()}>{parseInline(italicInner)}</em>);
    } else if (underscoreInner) {
      out.push(<em key={nextKey()}>{parseInline(underscoreInner)}</em>);
    } else if (strikeInner) {
      out.push(<del key={nextKey()}>{parseInline(strikeInner)}</del>);
    } else if (link) {
      out.push(renderLink(link, saved));
    }
  }
  if (cursor < text.length) pushText(out, text.slice(cursor), saved);
  return out;
}

function Heading({ level, text }) {
  const sizes = {
    1: 'font-editorial text-2xl font-semibold',
    2: 'font-editorial text-xl font-semibold',
    3: 'font-editorial text-lg font-semibold',
    4: 'text-base font-semibold',
    5: 'text-sm font-semibold text-ink-secondary',
    6: 'text-sm font-medium text-ink-muted',
  };
  const Tag = { 1: 'h1', 2: 'h2', 3: 'h3', 4: 'h4', 5: 'h5', 6: 'h6' }[level] ?? 'h3';
  return (
    <Tag className={`text-ink leading-snug ${sizes[level] ?? sizes[3]}`}>{parseInline(text)}</Tag>
  );
}

function CopyButton({ code }) {
  const [copied, setCopied] = useState(false);
  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = code;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand('copy');
      } finally {
        document.body.removeChild(textarea);
      }
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }
  return (
    <button
      type="button"
      onClick={copyCode}
      aria-label="Copy code block"
      title="Copy code"
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
        copied ? 'text-brand-400' : 'text-stone-400 hover:bg-white/10 hover:text-stone-200'
      }`}
    >
      {copied ? (
        <FiCheck className="h-3 w-3" aria-hidden="true" />
      ) : (
        <FiCopy className="h-3 w-3" aria-hidden="true" />
      )}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function CodeBlock({ language, code }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-stone-800 bg-stone-900 text-left shadow-subtle">
      <div className="flex items-center justify-between gap-2 border-b border-stone-800 bg-stone-950/60 px-3 py-1.5">
        <span className="truncate font-mono text-[11px] uppercase tracking-wider text-stone-400">
          {language || 'code'}
        </span>
        <CopyButton code={code} />
      </div>
      <code className="block px-3.5 py-2.5 font-mono text-[12.5px] leading-relaxed text-stone-100">
        {code}
      </code>
    </pre>
  );
}

export function renderBlocks(source) {
  const lines = String(source ?? '').replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed === '') {
      i++;
      continue;
    }

    const fence = trimmed.match(/^```([\w\-. ]*)$/);
    if (fence) {
      const code = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) {
        code.push(lines[i]);
        i++;
      }
      i++;
      blocks.push(
        <CodeBlock key={nextKey()} language={fence[1].trim()} code={code.join('\n')} />,
      );
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      i++;
      blocks.push(<Heading key={nextKey()} level={heading[1].length} text={heading[2]} />);
      continue;
    }

    if (/^([-*_])\1{2,}\s*$/.test(trimmed)) {
      i++;
      blocks.push(<hr key={nextKey()} className="border-border" />);
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^>\s?/, ''));
        i++;
      }
      blocks.push(
        <blockquote key={nextKey()} className="border-l-2 border-brand-300 pl-3 text-ink-secondary">
          {parseInline(quote.join('\n'))}
        </blockquote>,
      );
      continue;
    }

    if (/^\s*(?:[-*+]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items = [];
      while (i < lines.length) {
        const itemMatch = lines[i].match(/^\s*(?:[-*+]|\d+[.)])\s+(.*)$/);
        if (itemMatch) {
          items.push(itemMatch[1]);
          i++;
        } else if (lines[i].trim() === '') {
          i++;
          break;
        } else {
          break;
        }
      }
      const List = ordered ? 'ol' : 'ul';
      blocks.push(
        <List
          key={nextKey()}
          className={`my-1 space-y-1.5 pl-5 marker:text-brand-600 ${ordered ? 'list-decimal' : 'list-disc'}`}
        >
          {items.map(item => (
            <li key={nextKey()}>{parseInline(item)}</li>
          ))}
        </List>,
      );
      continue;
    }

    const paragraph = [line];
    i++;
    while (i < lines.length) {
      const next = lines[i];
      if (
        next.trim() === '' ||
        /^```/.test(next) ||
        /^#{1,6}\s/.test(next) ||
        /^>\s?/.test(next) ||
        /^\s*(?:[-*+]|\d+[.)])\s+/.test(next) ||
        /^([-*_])\1{2,}\s*$/.test(next.trim())
      ) {
        break;
      }
      paragraph.push(next);
      i++;
    }
    blocks.push(
      <p key={nextKey()} className="whitespace-pre-line">
        {parseInline(paragraph.join('\n'))}
      </p>,
    );
  }
  return blocks;
}

export default function Markdown({ content }) {
  const blocks = useMemo(() => renderBlocks(content), [content]);
  return <div className="space-y-2.5">{blocks}</div>;
}