import { describe, expect, it } from 'vitest';
import { allocateSectionDraws, expectedDraw } from './question-draft';

describe('expectedDraw', () => {
  it('matches the server: round(size * percent / 100) clamped to the section', () => {
    expect(expectedDraw(10, 50)).toBe(5);
    expect(expectedDraw(3, 50)).toBe(2);
    expect(expectedDraw(1, 1)).toBe(0);
    expect(expectedDraw(0, 100)).toBe(0);
    expect(expectedDraw(5, 50)).toBe(2); // 2.5 ties-to-even, matching Python
  });
});

describe('allocateSectionDraws', () => {
  it('splits an exam length across sections and spills leftover seats', () => {
    expect(allocateSectionDraws(10, [100, 100], [50, 50])).toEqual([5, 5]);
    expect(allocateSectionDraws(10, [100, 100], [70, 30])).toEqual([7, 3]);
    expect(allocateSectionDraws(10, [5, 100], [70, 30])).toEqual([5, 5]);
    expect(allocateSectionDraws(null, [5, 10], [50, 100])).toEqual([2, 10]);
    expect(allocateSectionDraws(1, [10, 10], [50, 50])).toEqual([1, 0]);
  });
});
