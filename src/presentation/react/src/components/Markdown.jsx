import { memo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlightSubset from '../plugins/rehypeHighlightSubset';
import { Check, Copy } from 'lucide-react';

/** Flatten a React node tree into its literal text (for copy buttons). */
function nodeToText(node) {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(nodeToText).join('');
  const { children } = node.props || {};
  return nodeToText(children);
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
      className={`nb-btn !rounded !px-2 !py-0.5 !text-[10px] !font-bold uppercase !tracking-wider ${
        copied ? '!bg-pastel-green' : '!bg-paper-surface hover:!bg-accent-yellow'
      }`}
    >
      {copied ? (
        <Check className="h-3 w-3" aria-hidden="true" />
      ) : (
        <Copy className="h-3 w-3" aria-hidden="true" />
      )}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

// H1/H2 are uppercased globally in index.css — display type is never
// lowercase in this system. Only the weights and sizes need stating here.
const headingClasses = {
  1: 'text-2xl font-black uppercase leading-tight text-ink',
  2: 'text-xl font-black uppercase leading-tight text-ink',
  3: 'text-lg font-extrabold uppercase leading-snug text-ink',
  4: 'text-base font-extrabold leading-snug text-ink',
  5: 'text-sm font-bold uppercase leading-snug text-ink-secondary',
  6: 'text-sm font-bold uppercase leading-snug text-ink-muted',
};

/**
 * Build a heading renderer for one level.
 * @param {number} level 1-6, indexing headingClasses.
 */
function heading(level) {
  const Tag = `h${level}`;
  const className = headingClasses[level];
  return function Heading({ node, children, ...props }) {
    return (
      <Tag {...props} className={className}>
        {children}
      </Tag>
    );
  };
}

/**
 * Markdown — renders model output safely.
 *
 * Uses react-markdown (synchronous, CommonMark + GFM via remark-gfm) with
 * `rehype-highlight` for fenced-code syntax highlighting. Raw HTML from the
 * model is never injected (react-markdown treats it as text); links are
 * sanitized by react-markdown's default safe-scheme url transform; code
 * blocks get a copy control. Streaming-tolerant: unterminated emphasis
 * stays literal.
 */
export default memo(function Markdown({ content }) {
  return (
    <div className="space-y-2.5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlightSubset]}
        components={{
          a({ node, href, children, ...props }) {
            const external = /^https?:/i.test(href || '');
            return (
              <a
                href={href}
                {...props}
                className="font-bold text-ink underline decoration-4 decoration-accent-cyan underline-offset-2 hover:decoration-accent-magenta"
                {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
              >
                {children}
              </a>
            );
          },
          // ponytail: h1-h6 were six near-identical overrides whose only
          // difference was the headingClasses[n] lookup. One factory instead.
          h1: heading(1),
          h2: heading(2),
          h3: heading(3),
          h4: heading(4),
          h5: heading(5),
          h6: heading(6),
          // Fenced + indented code blocks: wrap the highlighted <code> (which
          // react-markdown passes through the `code` override) with a header
          // bar carrying the language label and copy control.
          pre({ children }) {
            const codeNode = Array.isArray(children) ? children[0] : children;
            const className = codeNode?.props?.className || '';
            const langMatch = className.match(/language-([\w-]+)/);
            const language = langMatch ? langMatch[1] : undefined;
            return (
              <pre className="overflow-x-auto rounded border-[3px] border-nb-line bg-paper-subtle text-left shadow-brutal-sm">
                <div className="flex items-center justify-between gap-2 border-b-[3px] border-nb-line bg-accent-yellow px-3 py-1.5">
                  <span className="nb-label truncate !text-ink-on-accent">
                    {language || 'code'}
                  </span>
                  <CopyButton code={nodeToText(children)} />
                </div>
                {children}
              </pre>
            );
          },
          // Inline code vs block: rehype-highlight tags block code with hljs,
          // so only style as an inline span when it's not a block code. Keep
          // the incoming classes so the `pre` override can read `language-*`.
          code({ node, className, children, ...props }) {
            const isBlock = className && (className.includes('hljs') || className.startsWith('language-'));
            if (isBlock) {
              return (
                <code
                  {...props}
                  className={`${className || ''} block overflow-x-auto px-3.5 py-2.5 font-mono text-[12.5px] leading-relaxed text-ink-primary`}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                {...props}
                className="rounded border-2 border-nb-line bg-paper-muted px-1.5 py-0.5 font-mono text-[0.85em] font-bold text-ink"
              >
                {children}
              </code>
            );
          },
          blockquote({ node, children, ...props }) {
            return (
              <blockquote {...props} className="border-l-[3px] border-nb-line bg-paper-subtle py-1 pl-3 font-medium text-ink-secondary">
                {children}
              </blockquote>
            );
          },
          ul({ node, children, ...props }) {
            return (
              <ul {...props} className="my-1 list-disc space-y-1.5 pl-5 marker:text-ink">
                {children}
              </ul>
            );
          },
          ol({ node, children, ...props }) {
            return (
              <ol {...props} className="my-1 list-decimal space-y-1.5 pl-5 marker:font-black marker:text-ink">
                {children}
              </ol>
            );
          },
          hr() {
            return <hr className="mt-4 border-0 border-t-[3px] border-nb-line" />;
          },
          table({ node, children, ...props }) {
            return (
              <div className="my-3 overflow-x-auto rounded border-[3px] border-nb-line shadow-brutal-sm">
                <table {...props} className="w-full border-collapse text-sm">
                  {children}
                </table>
              </div>
            );
          },
          th({ node, children, ...props }) {
            return (
              <th
                {...props}
                className="border-b-[3px] border-r-[3px] border-nb-line bg-paper-muted px-3 py-2 text-left font-mono text-[11px] font-bold uppercase tracking-wider text-ink last:border-r-0"
              >
                {children}
              </th>
            );
          },
          td({ node, children, ...props }) {
            return (
              <td {...props} className="border-b-2 border-r-2 border-nb-line px-3 py-2 font-medium text-ink-secondary last:border-r-0">
                {children}
              </td>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});