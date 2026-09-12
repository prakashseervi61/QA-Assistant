import { describe, expect, it } from 'vitest';
import { parseSSEEvent, parseSSELine } from '../api';

describe('parseSSELine', () => {
  it('classifies a blank line', () => {
    expect(parseSSELine('')).toEqual({ kind: 'blank' });
  });

  it('classifies a comment line', () => {
    expect(parseSSELine(': keep-alive')).toEqual({ kind: 'comment' });
  });

  it('ignores non-data fields', () => {
    expect(parseSSELine('event: chunk')).toEqual({ kind: 'ignored' });
    expect(parseSSELine('id: 42')).toEqual({ kind: 'ignored' });
    expect(parseSSELine('retry: 1000')).toEqual({ kind: 'ignored' });
  });

  it('strips the optional single space after "data:"', () => {
    expect(parseSSELine('data: {"a":1}')).toEqual({ kind: 'data', value: '{"a":1}' });
    expect(parseSSELine('data:{"a":1}')).toEqual({ kind: 'data', value: '{"a":1}' });
  });

  it('recognises the [DONE] marker', () => {
    expect(parseSSELine('data: [DONE]')).toEqual({ kind: 'done' });
  });

  it('keeps JSON content intact when it contains spaces', () => {
    expect(parseSSELine('data: {"content":"hello world"}')).toEqual({
      kind: 'data',
      value: '{"content":"hello world"}',
    });
  });
});

describe('parseSSEEvent', () => {
  it('returns null for an empty block', () => {
    expect(parseSSEEvent([])).toBeNull();
    expect(parseSSEEvent([''])).toBeNull();
  });

  it('returns end for the [DONE] marker', () => {
    expect(parseSSEEvent(['data: [DONE]'])).toEqual({ type: 'end' });
  });

  it('dispatches on the payload type field', () => {
    expect(parseSSEEvent(['data: {"type":"chunk","content":"hi"}'])).toEqual({
      type: 'chunk',
      data: { type: 'chunk', content: 'hi' },
    });
  });

  it('passes RAG stage trace events through on their type', () => {
    expect(
      parseSSEEvent(['data: {"type":"stage","stage":"retrieving","detail":"Searching documents"}']),
    ).toEqual({
      type: 'stage',
      data: { type: 'stage', stage: 'retrieving', detail: 'Searching documents' },
    });
  });

  it('falls back to type "json" when there is no type field', () => {
    expect(parseSSEEvent(['data: {"answer":"hi"}'])).toEqual({
      type: 'json',
      data: { answer: 'hi' },
    });
  });

  it('joins multiple data lines before parsing', () => {
    expect(parseSSEEvent(['data: {"type":"json","n":', 'data: 5}'])).toEqual({
      type: 'json',
      data: { type: 'json', n: 5 },
    });
  });

  it('returns null for non-JSON payloads', () => {
    expect(parseSSEEvent(['data: not-json'])).toBeNull();
  });

  it('treats [DONE] as end even alongside data lines', () => {
    expect(parseSSEEvent(['data: {"type":"chunk"}', 'data: [DONE]'])).toEqual({
      type: 'end',
    });
  });
});
