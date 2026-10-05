import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ConfidenceSignal, WaveformOrb } from '../components/ui';
import { getSourceTitle } from '../components/ChatWidget';

function render(element) {
  return renderToStaticMarkup(element);
}

describe('WaveformOrb', () => {
  it('exposes listening state via aria-pressed', () => {
    expect(render(<WaveformOrb listening />)).toContain('aria-pressed="true"');
    expect(render(<WaveformOrb />)).toContain('aria-pressed="false"');
    expect(render(<WaveformOrb />)).toContain('aria-label="Voice input"');
  });
});

describe('ConfidenceSignal', () => {
  it('shows the confidence the backend computed', () => {
    const out = render(<ConfidenceSignal confidence={0.82} />);
    expect(out).toContain('Confidence');
    expect(out).toContain('82%');
  });

  it('flags a weakly grounded answer as low confidence', () => {
    const out = render(<ConfidenceSignal confidence={0.2} />);
    expect(out).toContain('Low confidence');
    expect(out).toContain('20%');
  });

  it('clamps out-of-range values instead of printing nonsense', () => {
    expect(render(<ConfidenceSignal confidence={1.4} />)).toContain('100%');
    expect(render(<ConfidenceSignal confidence={-0.2} />)).toContain('0%');
  });

  it('renders nothing when no score is available', () => {
    // Older messages loaded from history carry no stored score.
    expect(render(<ConfidenceSignal />)).toBe('');
  });
});

describe('getSourceTitle', () => {
  it('falls back to a numbered label', () => {
    expect(getSourceTitle({ metadata: {} }, 0)).toBe('Source 1');
    expect(getSourceTitle({ metadata: { filename: 'Doc.pdf' } }, 2)).toBe('Doc.pdf');
  });
});