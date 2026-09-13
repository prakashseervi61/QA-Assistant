import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  GlassCard,
  GradientButton,
  PipelineStepper,
  WaveformOrb,
  CitationPill,
  MessageBubble,
} from '../components/ui';
import { getSourceTitle } from '../components/utils/getSourceTitle';

function render(element) {
  return renderToStaticMarkup(element);
}

describe('GlassCard', () => {
  it('renders children inside a glass surface', () => {
    const out = render(<GlassCard>Hello</GlassCard>);
    expect(out).toContain('class="glass');
    expect(out).toContain('Hello');
  });

  it('supports the strong glass modifier', () => {
    expect(render(<GlassCard strong>Hi</GlassCard>)).toContain('glass-strong');
  });
});

describe('GradientButton', () => {
  it('renders an accessible button', () => {
    const out = render(<GradientButton>Send</GradientButton>);
    expect(out).toContain('type="button"');
    expect(out).toContain('Send');
  });

  it('is disabled while loading', () => {
    const out = render(<GradientButton loading>Send</GradientButton>);
    expect(out).toContain('disabled');
    expect(out).toContain('aria-busy="true"');
  });
});

describe('PipelineStepper', () => {
  it('renders all four stages', () => {
    const out = render(<PipelineStepper currentStage="retrieve" />);
    expect(out).toContain('Rewriting query');
    expect(out).toContain('Retrieving context');
    expect(out).toContain('Reranking sources');
    expect(out).toContain('Generating answer');
    expect(out).toContain('aria-live="polite"');
  });
});

describe('WaveformOrb', () => {
  it('exposes listening state via aria-pressed', () => {
    expect(render(<WaveformOrb listening />)).toContain('aria-pressed="true"');
    expect(render(<WaveformOrb />)).toContain('aria-pressed="false"');
    expect(render(<WaveformOrb />)).toContain('aria-label="Voice input"');
  });
});

describe('CitationPill', () => {
  it('renders a superscript number tied to a safe source title', () => {
    const out = render(
      <CitationPill index={2} title="Manual.pdf" source={{ metadata: { filename: 'Manual.pdf', page: 4 } }} />,
    );
    expect(out).toContain('3');
    expect(out).toContain('p.4');
  });

  it('never renders a javascript: href', () => {
    const out = render(
      <CitationPill index={0} title="Bad" source={{ metadata: { url: 'javascript:alert(1)' } }} />,
    );
    expect(out).not.toContain('href="javascript:');
  });
});

describe('MessageBubble', () => {
  it('renders a user message as a gradient bubble', () => {
    const out = render(<MessageBubble role="user" content="My question" />);
    expect(out).toContain('bg-bioluminescent');
    expect(out).toContain('My question');
  });

  it('renders the sources section when citations are provided', () => {
    const out = render(
      <MessageBubble role="assistant" content="Answer." sources={[{ metadata: { filename: 'A.pdf' } }]} />,
    );
    expect(out).toContain('Sources');
  });

  it('renders an error callout when error is set', () => {
    expect(render(<MessageBubble role="assistant" error />)).toContain('Something went wrong');
  });
});

describe('getSourceTitle', () => {
  it('falls back to a numbered label', () => {
    expect(getSourceTitle({ metadata: {} }, 0)).toBe('Source 1');
    expect(getSourceTitle({ metadata: { filename: 'Doc.pdf' } }, 2)).toBe('Doc.pdf');
  });
});