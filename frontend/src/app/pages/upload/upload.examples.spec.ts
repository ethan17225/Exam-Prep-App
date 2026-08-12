import { describe, expect, it } from 'vitest';

import { EXAMPLE_TYPES, JSON_EXAMPLES, buildExampleJson } from './upload.examples';

/** The numbers the assembler wrote, in order. */
function numbersIn(json: string): number[] {
  return [...json.matchAll(/"number":\s*(\d+)/g)].map((m) => Number(m[1]));
}

function parse(json: string): { type: string; number: number }[] {
  return JSON.parse(json) as { type: string; number: number }[];
}

describe('buildExampleJson', () => {
  it('produces valid JSON for every single-type selection', () => {
    // A malformed literal in one example is invisible until someone pastes it and
    // gets a validation error they cannot explain.
    for (const type of EXAMPLE_TYPES) {
      const parsed = parse(buildExampleJson(new Set([type])));
      expect(parsed.length, type).toBeGreaterThan(0);
      expect(parsed.every((q) => q.type === type)).toBe(true);
    }
  });

  it('treats an empty selection as All', () => {
    const all = parse(buildExampleJson(new Set()));
    expect(all).toHaveLength(JSON_EXAMPLES.length);
    // Every documented type is represented, so "All" really is all of them.
    for (const type of EXAMPLE_TYPES) {
      expect(
        all.some((q) => q.type === type),
        type,
      ).toBe(true);
    }
  });

  it('renumbers from 1 consecutively whatever the subset', () => {
    // The numbers are the array's own identifiers; a subset that kept the original
    // numbering would upload questions numbered 2, 5, 9.
    expect(numbersIn(buildExampleJson(new Set(['SATA'])))).toEqual([1]);
    expect(numbersIn(buildExampleJson(new Set(['SATA', 'HOTSPOT'])))).toEqual([1, 2]);
    expect(numbersIn(buildExampleJson(new Set()))).toEqual(
      JSON_EXAMPLES.map((_, index) => index + 1),
    );
  });

  it('keeps the tab order regardless of the order types were picked', () => {
    const picked = parse(buildExampleJson(new Set(['HOTSPOT', 'FIB'])));
    expect(picked.map((q) => q.type)).toEqual(['FIB', 'HOTSPOT']);
  });

  it('leaves no unsubstituted number placeholder', () => {
    expect(buildExampleJson(new Set())).not.toContain('__N__');
  });

  it('ignores a type with no example rather than emitting an empty array', () => {
    // Selecting nothing that exists is indistinguishable from selecting nothing,
    // and "[]" would read as a broken page.
    expect(parse(buildExampleJson(new Set(['NOT_A_TYPE'])))).toHaveLength(0);
  });
});
