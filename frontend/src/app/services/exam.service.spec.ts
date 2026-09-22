import { describe, expect, it } from 'vitest';
import {
  Question,
  classifyQuestionType,
  formatClock,
  formatDuration,
  httpErrorDetail,
  isAnswerCorrect,
  kindFromType,
  parseServerDate,
  progressPercent,
  questionKindCounts,
  shuffle,
  shuffleQuestionOptions,
  applyOptionOrder,
} from './exam.service';

/** Minimal question builder for grading tests. */
function q(
  type: string,
  answer: Question['answer'],
  options: Question['options'] = null,
): Question {
  return { id: 1, topic: 't', type, question: 'q', options, answer };
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

describe('questionKindCounts', () => {
  const many = (type: string, n: number): Question[] =>
    Array.from({ length: n }, () => q(type, 'A', letters));

  it('omits kinds the exam does not contain', () => {
    expect(questionKindCounts([...many('MCQ', 2), ...many('SATA', 1)])).toEqual([
      { kind: 'MCQ', count: 2 },
      { kind: 'SATA', count: 1 },
    ]);
    expect(questionKindCounts([])).toEqual([]);
  });

  it('keeps canonical order at four kinds or fewer', () => {
    const kinds = questionKindCounts([...many('MATRIX', 9), ...many('MCQ', 1), ...many('SATA', 5)]);
    expect(kinds.map((k) => k.kind)).toEqual(['MCQ', 'SATA', 'MATRIX']);
  });

  it('sorts by count descending past four kinds, canonical order breaking ties', () => {
    const kinds = questionKindCounts([
      ...many('MCQ', 1),
      ...many('SATA', 2),
      ...many('FIB', 7),
      ...many('MATRIX', 2),
      ...many('CLOZE', 4),
    ]);
    expect(kinds).toEqual([
      { kind: 'FIB', count: 7 },
      { kind: 'CLOZE', count: 4 },
      { kind: 'SATA', count: 2 },
      { kind: 'MATRIX', count: 2 },
      { kind: 'MCQ', count: 1 },
    ]);
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

  it('parseServerDate treats naive API timestamps as UTC', () => {
    expect(parseServerDate('2026-09-22T18:00:00')).toBe(Date.parse('2026-09-22T18:00:00Z'));
    expect(parseServerDate('2026-09-22T18:00:00Z')).toBe(Date.parse('2026-09-22T18:00:00Z'));
    expect(Number.isNaN(parseServerDate(null))).toBe(true);
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

  it('shuffleQuestionOptions permutes MCQ choices and leaves highlight tokens', () => {
    const mcq = q('MCQ', 'A', ['A. One', 'B. Two', 'C. Three', 'D. Four']);
    const shuffled = shuffleQuestionOptions(mcq);
    expect(mcq.options).toEqual(['A. One', 'B. Two', 'C. Three', 'D. Four']);
    expect([...(shuffled.options as string[])].sort()).toEqual(
      ['A. One', 'B. Two', 'C. Three', 'D. Four'].sort(),
    );

    const highlight = q('HIGHLIGHT', [0], { tokens: ['keep', 'this', 'order'] });
    expect(shuffleQuestionOptions(highlight).options).toEqual(highlight.options);
  });

  it('applyOptionOrder overlays a frozen permutation by question id', () => {
    const questions = [q('MCQ', 'A', ['A', 'B']), { ...q('MCQ', 'B', ['C', 'D']), id: 2 }];
    const out = applyOptionOrder(questions, { '2': ['D', 'C'] });
    expect(out[0]!.options).toEqual(['A', 'B']);
    expect(out[1]!.options).toEqual(['D', 'C']);
  });
});

describe('httpErrorDetail', () => {
  it('reads a FastAPI string detail', () => {
    expect(httpErrorDetail({ error: { detail: 'Exam not found' } })).toBe('Exam not found');
  });

  it('joins Pydantic 422 loc/msg objects instead of printing [object Object]', () => {
    expect(
      httpErrorDetail({
        error: {
          detail: [
            { loc: ['body', 'password'], msg: 'String should have at least 8 characters' },
            { loc: ['body', 'email'], msg: 'value is not a valid email address' },
          ],
        },
      }),
    ).toBe(
      'password: String should have at least 8 characters email: value is not a valid email address',
    );
  });

  it('falls back to empty so callers can supply their own message', () => {
    expect(httpErrorDetail({ error: { detail: [{ loc: ['body'] }] } }) || 'Sign in failed.').toBe(
      'Sign in failed.',
    );
    expect(httpErrorDetail(undefined)).toBe('');
  });
});
