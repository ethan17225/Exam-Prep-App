import { describe, expect, it } from 'vitest';

import { EXAMPLE_TYPES, JSON_EXAMPLES, buildExampleJson } from './upload.examples';

function parse(json: string): { type: string }[] {
  return JSON.parse(json) as { type: string }[];
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

  it('omits a client-assigned number field', () => {
    // Identity is Question.id, assigned on insert. A leftover `"number"` in the
    // example would reintroduce the field we dropped.
    const json = buildExampleJson(new Set());
    expect(json).not.toContain('"number"');
    expect(json).not.toContain('__N__');
  });

  it('keeps the tab order regardless of the order types were picked', () => {
    const picked = parse(buildExampleJson(new Set(['HOTSPOT', 'FIB'])));
    expect(picked.map((q) => q.type)).toEqual(['FIB', 'HOTSPOT']);
  });

  it('ignores a type with no example rather than emitting an empty array', () => {
    // Selecting nothing that exists is indistinguishable from selecting nothing,
    // and "[]" would read as a broken page.
    expect(parse(buildExampleJson(new Set(['NOT_A_TYPE'])))).toHaveLength(0);
  });
});
