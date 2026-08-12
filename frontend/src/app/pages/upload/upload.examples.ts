/**
 * The JSON examples shown on the upload page, one entry per illustrated question
 * type. Kept out of the component because it is ~150 lines of literal data.
 *
 * `body` is the object exactly as it should appear inside the array, indented two
 * spaces, with `__N__` where the question number goes — the numbers have to be
 * consecutive in whatever subset the user picked, so they cannot be hardcoded.
 */
export interface JsonExample {
  /** The type tab this example appears under. Not unique: MCQ has two. */
  type: string;
  body: string;
}

/** Tab order. Simple types first, then the Next-Gen structured ones. */
export const EXAMPLE_TYPES = [
  'MCQ',
  'SATA',
  'FIB',
  'MATRIX',
  'CLOZE',
  'BOWTIE',
  'RANKING',
  'HIGHLIGHT',
  'HOTSPOT',
] as const;

export const JSON_EXAMPLES: JsonExample[] = [
  {
    type: 'MCQ',
    body: `  {
    "number": __N__,
    "topic": "Pharmacology",
    "type": "MCQ",
    "question": "Which medication is a beta-blocker?",
    "options": [
      "A. Metoprolol",
      "B. Lisinopril",
      "C. Amlodipine",
      "D. Losartan"
    ],
    "answer": "A",
    "rationale": "Metoprolol is a selective beta-1 blocker."
  }`,
  },
  {
    type: 'SATA',
    body: `  {
    "number": __N__,
    "topic": "Infection Control",
    "type": "SATA",
    "question": "Which are standard precautions? Select all that apply.",
    "options": [
      "A. Hand hygiene",
      "B. Use of PPE",
      "C. Reverse isolation",
      "D. Safe injection practices"
    ],
    "answer": ["A", "B", "D"],
    "rationale": "Standard precautions include hand hygiene, PPE, and safe injection practices."
  }`,
  },
  {
    type: 'FIB',
    body: `  {
    "number": __N__,
    "topic": "Anatomy",
    "type": "FIB",
    "question": "The largest organ of the human body is the ____.",
    "answer": "skin",
    "rationale": "The skin is the largest organ by surface area."
  }`,
  },
  {
    type: 'MATRIX',
    body: `  {
    "number": __N__,
    "topic": "Endocrine",
    "type": "MATRIX",
    "question": "For each finding, check the matching diabetes type.",
    "options": {
      "rows": ["HgA1C 6.8%", "BMI 35.9"],
      "columns": ["Type 1 Diabetes", "Type 2 Diabetes"]
    },
    "answer": { "0": ["Type 1 Diabetes", "Type 2 Diabetes"], "1": ["Type 2 Diabetes"] },
    "rationale": "Answer keys map row index to the correct column(s)."
  }`,
  },
  {
    type: 'CLOZE',
    body: `  {
    "number": __N__,
    "topic": "Diabetes",
    "type": "CLOZE",
    "question": "The client should be instructed to [1] and [2] if the blood sugar is 60 mg/dL.",
    "options": {
      "blanks": [
        { "label": "Dropdown 1", "choices": ["fast", "drink orange juice", "call 911"] },
        { "label": "Dropdown 2", "choices": ["continue to monitor symptoms", "drink four glasses of water"] }
      ]
    },
    "answer": ["drink orange juice", "continue to monitor symptoms"],
    "rationale": "One answer per blank, in order."
  }`,
  },
  {
    type: 'BOWTIE',
    body: `  {
    "number": __N__,
    "topic": "Newborn",
    "type": "BOWTIE",
    "question": "Drag one condition and two interventions.",
    "options": {
      "categories": [
        { "name": "Potential Condition", "count": 1, "choices": ["Acrocyanosis", "Meconium aspiration syndrome"] },
        { "name": "Potential Interventions", "count": 2, "choices": ["Suctioning", "Oxygen therapy", "Phototherapy"] }
      ]
    },
    "answer": {
      "Potential Condition": ["Meconium aspiration syndrome"],
      "Potential Interventions": ["Suctioning", "Oxygen therapy"]
    },
    "rationale": "Answer keys map category name to the correct choice(s)."
  }`,
  },
  {
    type: 'RANKING',
    body: `  {
    "number": __N__,
    "topic": "Urinary",
    "type": "RANKING",
    "question": "Rank from highest risk to lowest risk for UTI.",
    "options": ["Older males", "School-age female", "Older females", "Adolescent males"],
    "answer": ["Older females", "Older males", "School-age female", "Adolescent males"],
    "rationale": "Options is the display order; answer is the correct order."
  }`,
  },
  {
    type: 'HIGHLIGHT',
    body: `  {
    "number": __N__,
    "topic": "Assessment",
    "type": "HIGHLIGHT",
    "question": "Click to highlight the findings that require follow-up.",
    "options": {
      "tokens": ["Blood pressure 160/100 mm Hg", "Heart rate 88 beats/min", "BMI 35.9 kg/m2"]
    },
    "answer": [0, 2],
    "rationale": "Answer is the list of correct token indices (0-based)."
  }`,
  },
  {
    type: 'HOTSPOT',
    body: `  {
    "number": __N__,
    "topic": "Pediatrics",
    "type": "HOTSPOT",
    "question": "Click the location where the nurse should pull the pinna.",
    "options": {
      "regions": [
        { "id": "r1", "label": "Up and back", "x": 55, "y": 5, "w": 40, "h": 30 },
        { "id": "r2", "label": "Down and back", "x": 55, "y": 60, "w": 40, "h": 30 }
      ]
    },
    "answer": "r2",
    "rationale": "Region coordinates are percentages of the image. Upload the image afterwards via Edit Questions."
  }`,
  },
  // Filed under MCQ so that picking MCQ still demonstrates `sections`: they are
  // valid on every type, and hiding this behind a tab of its own meant most
  // people never saw the case-study format at all.
  {
    type: 'MCQ',
    body: `  {
    "number": __N__,
    "topic": "Hypoglycemia Management",
    "type": "MCQ",
    "question": "The client is alert and able to swallow. Which action should the nurse take first?",
    "sections": [
      {
        "title": "Nurses' Notes",
        "blocks": [
          { "type": "text", "text": "1030: Client reports feeling shaky and sweaty. Skin cool and diaphoretic. Last meal at 0700." },
          { "type": "list", "items": ["Alert and oriented x3", "Able to swallow without difficulty", "Fine tremor of both hands"] }
        ]
      },
      {
        "title": "Laboratory Results",
        "blocks": [
          {
            "type": "table",
            "caption": "Point-of-care glucose",
            "headers": ["Lab Test", "0800", "1030", "Reference Range"],
            "rows": [
              ["Blood glucose", "101 mg/dL", "58 mg/dL", "74-140 mg/dL"],
              ["Hemoglobin A1C", "7.2%", "-", "Less than 5.7%"]
            ]
          }
        ]
      }
    ],
    "options": [
      "A. Give 15 g of a fast-acting carbohydrate and recheck in 15 minutes.",
      "B. Administer 1 mg of glucagon intramuscularly.",
      "C. Hold the next dose of insulin and notify the provider.",
      "D. Provide a peanut butter sandwich and whole milk."
    ],
    "answer": "A",
    "rationale": "Sections are optional on any question type. Two or more sections render as tabs above the question."
  }`,
  },
];

/**
 * Assembles the example array for the chosen types, renumbering from 1.
 *
 * An empty selection means "All" — the same output as before this was filterable,
 * so the default view is unchanged.
 */
export function buildExampleJson(selected: ReadonlySet<string>): string {
  const chosen = selected.size ? JSON_EXAMPLES.filter((e) => selected.has(e.type)) : JSON_EXAMPLES;
  const bodies = chosen.map((e, index) => e.body.replace('__N__', String(index + 1)));
  return `[\n${bodies.join(',\n')}\n]`;
}
