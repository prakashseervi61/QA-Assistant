import { memo, useState } from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
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
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[11px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
        copied ? 'text-brand-400' : 'text-ink-faint hover:bg-paper-200 hover:text-ink-secondary'
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

const headingClasses = {
  1: 'font-editorial text-2xl font-semibold leading-snug text-ink',
  2: 'font-editorial text-xl font-semibold leading-snug text-ink',
  3: 'font-editorial text-lg font-semibold leading-snug text-ink',
  4: 'text-base font-semibold leading-snug text-ink',
  5: 'text-sm font-semibold leading-snug text-ink-secondary',
  6: 'text-sm font-medium leading-snug text-ink-muted',
};

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
        rehypePlugins={[[rehypeHighlight, { ignoreMissing: true }]]}
        urlTransform={defaultUrlTransform}
        components={{
          a({ node, href, children, ...props }) {
            const external = /^https?:/i.test(href || '');
            return (
              <a
                href={href}
                {...props}
                className="text-brand-600 underline decoration-brand-300 underline-offset-2 transition-colors hover:text-brand-700"
                {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
              >
                {children}
              </a>
            );
          },
          h1({ node, children, ...props }) {
            return (
              <h1 {...props} className={headingClasses[1]}>
                {children}
              </h1>
            );
          },
          h2({ node, children, ...props }) {
            return (
              <h2 {...props} className={headingClasses[2]}>
                {children}
              </h2>
            );
          },
          h3({ node, children, ...props }) {
            return (
              <h3 {...props} className={headingClasses[3]}>
                {children}
              </h3>
            );
          },
          h4({ node, children, ...props }) {
            return (
              <h4 {...props} className={headingClasses[4]}>
                {children}
              </h4>
            );
          },
          h5({ node, children, ...props }) {
            return (
              <h5 {...props} className={headingClasses[5]}>
                {children}
              </h5>
            );
          },
          h6({ node, children, ...props }) {
            return (
              <h6 {...props} className={headingClasses[6]}>
                {children}
              </h6>
            );
          },
          // Fenced + indented code blocks: wrap the highlighted <code> (which
          // react-markdown passes through the `code` override) with a header
          // bar carrying the language label and copy control.
          pre({ children }) {
            const codeNode = Array.isArray(children) ? children[0] : children;
            const className = codeNode?.props?.className || '';
            const langMatch = className.match(/language-([\w-]+)/);
            const language = langMatch ? langMatch[1] : undefined;
            return (
              <pre className="overflow-x-auto rounded-lg border border-strong bg-paper-100 text-left shadow-subtle">
                <div className="flex items-center justify-between gap-2 border-b border-strong bg-paper-200 px-3 py-1.5">
                  <span className="truncate font-mono text-[11px] uppercase tracking-wider text-ink-faint">
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
              <code {...props} className="rounded bg-paper-200 px-1 py-0.5 font-mono text-[0.85em] text-ink-secondary">
                {children}
              </code>
            );
          },
          blockquote({ node, children, ...props }) {
            return (
              <blockquote {...props} className="border-l-2 border-brand-300 pl-3 text-ink-secondary">
                {children}
              </blockquote>
            );
          },
          ul({ node, children, ...props }) {
            return (
              <ul {...props} className="my-1 list-disc space-y-1.5 pl-5 marker:text-brand-600">
                {children}
              </ul>
            );
          },
          ol({ node, children, ...props }) {
            return (
              <ol {...props} className="my-1 list-decimal space-y-1.5 pl-5 marker:text-brand-600">
                {children}
              </ol>
            );
          },
          hr() {
            return <hr className="border-border" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});