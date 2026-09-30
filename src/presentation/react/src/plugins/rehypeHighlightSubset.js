/**
 * A minimal syntax-highlighting rehype plugin.
 *
 * `rehype-highlight` statically imports lowlight's `common` bundle, which
 * pulls all 37 of its grammars into the build no matter which languages an
 * app actually uses. This project only ever highlights a short list, so we
 * register just those grammars with lowlight directly and skip the rest.
 *
 * Output is identical to rehype-highlight for the languages we register:
 * the `hljs` class lands on the `<code>` element and tokens come back as
 * `<span class="hljs-*">`, which is what the theme in `index.css` styles.
 */

import { createLowlight } from 'lowlight';
import { visit } from 'unist-util-visit';

import bash from 'highlight.js/lib/languages/bash';
import css from 'highlight.js/lib/languages/css';
import diff from 'highlight.js/lib/languages/diff';
import go from 'highlight.js/lib/languages/go';
import graphql from 'highlight.js/lib/languages/graphql';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import python from 'highlight.js/lib/languages/python';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';

/** The only grammars we bundle. Everything else renders unhighlighted. */
const languages = {
  bash,
  css,
  diff,
  go,
  graphql,
  javascript,
  json,
  markdown,
  python,
  sql,
  typescript,
  xml,
  yaml,
};

/** Common fence aliases mapped onto the registered grammar names. */
const ALIASES = {
  cjs: 'javascript',
  js: 'javascript',
  mjs: 'javascript',
  html: 'xml',
  md: 'markdown',
  py: 'python',
  sh: 'bash',
  shell: 'bash',
  ts: 'typescript',
  yml: 'yaml',
  zsh: 'bash',
};

const lowlight = createLowlight(languages);

/** Concatenate the literal text inside a hast node tree. */
function nodeText(node) {
  if (node.type === 'text') return node.value;
  if (Array.isArray(node.children)) return node.children.map(nodeText).join('');
  return '';
}

/** Resolve the language a `<code>` node declares, if any. */
function detectLanguage(node) {
  const classNames = node.properties?.className;
  if (!Array.isArray(classNames)) return null;
  for (const className of classNames) {
    if (typeof className !== 'string') continue;
    const match = /^language-(.+)$/.exec(className);
    if (!match) continue;
    const name = match[1].toLowerCase();
    const resolved = ALIASES[name] || name;
    return lowlight.registered(resolved) ? resolved : null;
  }
  return null;
}

/**
 * Highlight fenced code blocks whose language we support.
 *
 * Code in an unknown language is left exactly as-is rather than throwing,
 * matching rehype-highlight's `ignoreMissing` behaviour.
 */
export default function rehypeHighlightSubset() {
  return function transformer(tree) {
    visit(tree, 'element', (node) => {
      if (node.tagName !== 'code') return;

      const language = detectLanguage(node);
      if (!language) return;

      let highlighted;
      try {
        highlighted = lowlight.highlight(language, nodeText(node));
      } catch {
        return; // Unknown grammar — render the code block unhighlighted.
      }

      node.children = highlighted.children;
      node.properties.className = [
        ...(Array.isArray(node.properties.className) ? node.properties.className : []),
        'hljs',
      ];
    });
  };
}
