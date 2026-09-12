import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import Markdown from '../components/Markdown';

function html(source) {
  return renderToStaticMarkup(<Markdown content={source} />);
}

describe('Markdown', () => {
  it('renders bold and italic inline emphasis', () => {
    const out = html('**bold** and *italic*');
    expect(out).toContain('<strong>bold</strong>');
    expect(out).toContain('<em>italic</em>');
  });

  it('renders inline code spans', () => {
    const out = html('use `fetchJSON(url)`');
    expect(out).toMatch(/<code[^>]*>fetchJSON\(url\)<\/code>/);
  });

  it('renders strikethrough', () => {
    expect(html('~~removed~~')).toContain('<del>removed</del>');
  });

  it('renders links for safe schemes only', () => {
    expect(html('[docs](https://example.com)')).toContain('href="https://example.com"');
    expect(html('[bad](javascript:alert(1))')).not.toContain('href="javascript:');
    expect(html('[bad](javascript:alert(1))')).toContain('bad');
  });

  it('renders headings at the right level', () => {
    expect(html('## Section')).toMatch(/<h2[^>]*>Section<\/h2>/);
    expect(html('### Sub')).toMatch(/<h3[^>]*>Sub<\/h3>/);
  });

  it('renders fenced code blocks with a copy control', () => {
    const out = html('```js\nconst x = 1;\n```');
    expect(out).toContain('<pre');
    expect(out).toContain('const x = 1;');
    expect(out).toContain('Copy');
    expect(out).toContain('aria-label="Copy code block"');
  });

  it('renders ordered and unordered lists', () => {
    const ul = html('- one\n- two');
    expect(ul).toContain('<ul');
    expect(ul).toContain('<li>one</li>');
    expect(ul).toContain('<li>two</li>');
    const ol = html('1. first\n2. second');
    expect(ol).toContain('<ol');
    expect(ol).toContain('<li>first</li>');
  });

  it('renders blockquotes', () => {
    expect(html('> quoted note')).toContain('<blockquote');
    expect(html('> quoted note')).toContain('quoted note');
  });

  it('keeps unterminated emphasis literal while streaming', () => {
    const out = html('The answer is **almost');
    expect(out).toContain('**almost');
    expect(out).not.toContain('<strong>');
  });

  it('escapes raw HTML from the model output', () => {
    expect(html('<script>alert(1)</script>')).not.toContain('<script>');
  });

  it('handles an empty or undefined source', () => {
    expect(html('')).toBe('<div class="space-y-2.5"></div>');
    expect(html(null)).toBe('<div class="space-y-2.5"></div>');
  });

  it('renders nested emphasis without overflowing the stack', () => {
    const out = html('**outer *inner* tail**');
    expect(out).toContain('<strong>');
    expect(out).toContain('<em>inner</em>');
    expect(out).toContain('</strong>');
  });
});