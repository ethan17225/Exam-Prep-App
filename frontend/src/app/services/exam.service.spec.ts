import { describe, expect, it } from 'vitest';
import {
  Question,
  classifyQuestionType,
  formatClock,
  formatDuration,
  isAnswerCorrect,
  kindFromType,
  progressPercent,
  shuffle,
} from './exam.service';

/** Minimal question builder for grading tests. */
function q(
  type: string,
  answer: Question['answer'],
  options: Question['options'] = null,
): Question {
  return { number: 1, topic: 't', type, question: 'q', options, answer };
}

const letters = ['A. One', 'B. Two', 'C. Three'];

// isAnswerCorrect mirrors backend/src/grading/service.py — these cases pin the
// semantics that used to diverge between client and server.
describe('isAnswerCorrect', () => {
  it('grades MCQ with trimmed string equality', () => {
    expect(isAnswerCorrect(q('MCQ', 'A', letters), ' A ')).toBe(true);
    expect(isAnswerCorrect(q('MCQ', 'A', letters), 'B')).toBe(false);
    expect(isAnswerCorrect(q('MCQ', 'A', letters), null)).toBe(false);
  });

  it('grades SATA as an unordered set, accepting comma-string expected answers', () => {
    expect(isAnswerCorrect(q('SATA', ['A', 'B'], letters), ['B', 'A'])).toBe(true);
    expect(isAnswerCorrect(q('SATA', 'A, B', letters), ['B', 'A'])).toBe(true);
    expect(isAnswerCorrect(q('SATA', ['A', 'B'], letters), ['A'])).toBe(false);
  });

  it('grades HIGHLIGHT as normalized string sets (numbers and strings agree)', () => {
    const question = q('HIGHLIGHT', [0, 2], { tokens: ['a', 'b', 'c'] });
    expect(isAnswerCorrect(question, ['0', '2'])).toBe(true);
    expect(isAnswerCorrect(question, [2, 0])).toBe(true);
    expect(isAnswerCorrect(question, [0])).toBe(false);
  });

  it('never grades HOTSPOT correct on an empty answer, even if expected is empty', () => {
    const regions = { regions: [{ id: 'r1', label: 'x', x: 0, y: 0, w: 1, h: 1 }] };
    expect(isAnswerCorrect(q('HOTSPOT', 'r1', regions), 'r1')).toBe(true);
    expect(isAnswerCorrect(q('HOTSPOT', '', regions), '')).toBe(false);
    expect(isAnswerCorrect(q('HOTSPOT', 'r1', regions), null)).toBe(false);
  });

  it('grades CLOZE ordered and case-insensitively', () => {
    const question = q('CLOZE', ['Juice', 'Water'], { blanks: [] });
    expect(isAnswerCorrect(question, ['juice', 'WATER'])).toBe(true);
    expect(isAnswerCorrect(question, ['water', 'juice'])).toBe(false);
    expect(isAnswerCorrect(question, ['juice'])).toBe(false);
  });

  it('grades RANKING ordered and case-sensitively', () => {
    const question = q('RANKING', ['a', 'b'], ['b', 'a']);
    expect(isAnswerCorrect(question, ['a', 'b'])).toBe(true);
    expect(isAnswerCorrect(question, ['b', 'a'])).toBe(false);
  });

  it('grades MATRIX/BOWTIE as grouped sets, ignoring empty selections', () => {
    const question = q(
      'MATRIX',
      { '0': ['X'], '1': ['Y', 'Z'] },
      { rows: ['r0', 'r1'], columns: ['X', 'Y', 'Z'] },
    );
    expect(isAnswerCorrect(question, { '0': ['X'], '1': ['Z', 'Y'] })).toBe(true);
    expect(isAnswerCorrect(question, { '0': ['X'], '1': ['Z', 'Y'], '2': [] })).toBe(true);
    expect(isAnswerCorrect(question, { '0': ['X'] })).toBe(false);
  });

  it('grades FIB with float equality then fuzzy substring (len >= 3)', () => {
    expect(isAnswerCorrect(q('FIB', '2'), '2.0')).toBe(true);
    expect(isAnswerCorrect(q('FIB', 'the skin'), 'skin')).toBe(true);
    expect(isAnswerCorrect(q('FIB', 'abc'), 'ab')).toBe(false);
    expect(isAnswerCorrect(q('FIB', 'Skin'), 'skin')).toBe(true);
  });

  it('returns false when the question has no answer key', () => {
    expect(isAnswerCorrect(q('MCQ', undefined, letters), 'A')).toBe(false);
  });
});

describe('classifyQuestionType / kindFromType', () => {
  it('classifies by normalized type string', () => {
    expect(classifyQuestionType({ type: 'sata', options: letters })).toBe('SATA');
    expect(classifyQuestionType({ type: 'MATRIX', options: null })).toBe('MATRIX');
    expect(classifyQuestionType({ type: 'Fill-in-the-blank', options: null })).toBe('FIB');
  });

  it('falls back to FIB when options are missing, MCQ otherwise', () => {
    expect(classifyQuestionType({ type: 'MCQ', options: null })).toBe('FIB');
    expect(classifyQuestionType({ type: 'MCQ', options: letters })).toBe('MCQ');
  });

  it('kindFromType trusts the type string alone (editor semantics)', () => {
    expect(kindFromType('MCQ')).toBe('MCQ');
    expect(kindFromType('fib')).toBe('FIB');
    expect(kindFromType(' bowtie ')).toBe('BOWTIE');
    expect(kindFromType('unknown')).toBe('MCQ');
  });
});

describe('formatting helpers', () => {
  it('formatDuration picks the two most significant units', () => {
    expect(formatDuration(3900)).toBe('1h 5m');
    expect(formatDuration(303)).toBe('5m 3s');
    expect(formatDuration(42)).toBe('42s');
    expect(formatDuration(0)).toBe('0s');
  });

  it('formatClock renders HH:MM:SS', () => {
    expect(formatClock(3661)).toBe('01:01:01');
    expect(formatClock(0)).toBe('00:00:00');
  });

  it('progressPercent rounds and survives zero totals', () => {
    expect(progressPercent({ answered_count: 1, total_questions: 3 })).toBe(33);
    expect(progressPercent({ answered_count: 0, total_questions: 0 })).toBe(0);
  });

  it('shuffle preserves elements and does not mutate its input', () => {
    const input = [1, 2, 3, 4, 5];
    const out = shuffle(input);
    expect(input).toEqual([1, 2, 3, 4, 5]);
    expect([...out].sort()).toEqual([1, 2, 3, 4, 5]);
  });
});
