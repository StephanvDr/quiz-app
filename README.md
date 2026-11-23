# Code Quiz

Private app for training skills within different domains.

It starts with multiple-choice syntax drills for coding subjects. Each question shows a
snippet and asks what it prints, or which call does the job, then explains the answer
either way.

The first subject is **pandas**: 183 questions across 14 topics, aimed at data engineering
and LLM work. 171 of them are checked by actually running the code, so the marked answers
are what pandas really does.

The second subject is **ML pitfalls** (category Machine Learning): 104 questions across 7
topics on supervised-learning terminology and common mistakes, based on the DAT lesson of
19-11-2026 (ML-valkuilen). 25 of them are scikit-learn snippets checked by running the code.

| Topic | Questions |
| --- | ---: |
| Workflow and basics | 14 |
| Algorithms | 14 |
| Pitfalls 1: data quality and preprocessing | 16 |
| Pitfalls 2: model choice and training | 15 |
| Pitfalls 3a: classification metrics | 15 |
| Pitfalls 3b: regression metrics and validation | 17 |
| Pitfalls 4: implementation in practice | 13 |

| Topic | Questions |
| --- | ---: |
| Series and DataFrames | 13 |
| Selecting with `[]`, `loc` and `iloc` | 13 |
| Filtering rows | 13 |
| Creating and changing columns | 13 |
| Missing values and duplicates | 13 |
| Sorting and ranking | 10 |
| GroupBy and aggregation | 15 |
| Merging and concatenating | 13 |
| Reshaping: pivot, melt and stack | 12 |
| Text with the `.str` accessor | 12 |
| Dates and time series | 15 |
| Reading and writing files | 13 |
| Dtypes, memory and performance | 14 |
| JSON and text for LLM pipelines | 14 |

## Run it

```bash
python quiz.py
```

This serves the app at <http://localhost:8000> and opens your browser. It needs Python 3.10
or newer and nothing else: no packages, no Node, no build step. Edits to the quiz files show
up when you reload the page.

To share the quiz without Python, build a single self-contained HTML file:

```bash
python quiz.py build
```

`dist/index.html` holds the app and every question. Open it straight from disk, send it to
someone, or host it on any static host (GitHub Pages, Netlify, S3).

## Using the quiz

- Pick the topics, the round size (10, 20, 30 or all), a difficulty, and which questions to
  draw from: all of them, ones you haven't seen yet, or ones you got wrong last time.
- Answer options are shuffled every time. Press `1`–`6` or `A`–`F` to answer and `Enter` to
  continue. "I don't know, show me" reveals the answer and counts it as missed.
- The results page breaks the score down by topic, lists every miss with its explanation, and
  can start a new round with just the questions you missed.
- Progress is stored in your browser's `localStorage`, per subject. Nothing is sent anywhere.

## Adding questions and subjects

Every folder under `quizzes/` that contains a `quiz.json` is a subject. The folders above it
are just for organizing:

```
quizzes/
└── python/
    └── pandas/
        ├── quiz.json                      the subject
        ├── 01-series-and-dataframes.json  one file per topic, shown in file-name order
        ├── 02-selecting-data.json
        └── ...
```

To add a subject, say SQL, create `quizzes/sql/postgres/quiz.json` plus a topic file, run
`python quiz.py validate`, and reload the page.

### quiz.json

```json
{
  "title": "Pandas",
  "category": "Python",
  "badge": "pd",
  "language": "python",
  "description": "Read pandas code and predict the result, or pick the call that does the job.",
  "note": "Every snippet assumes `import pandas as pd` and `import numpy as np`.",
  "prelude": ["import pandas as pd", "import numpy as np"]
}
```

| Field | | |
| --- | --- | --- |
| `title`, `category` | required | Subjects are grouped under their category on the home page. |
| `badge` | optional | Short text on the subject's tile, such as the import alias `pd`. |
| `language` | optional | Syntax highlighting: `python` or `sql`. Other values show plain code. |
| `description`, `note` | optional | Shown on the subject page. `note` is a good place for assumptions. |
| `prelude` | optional | Code that `verify` runs before every snippet. It isn't shown in questions. |

### Topic files

```json
{
  "topic": "GroupBy and aggregation",
  "questions": [
    {
      "id": "groupby-sum-dict",
      "difficulty": "easy",
      "question": "What does this print?",
      "code": [
        "df = pd.DataFrame({'k': ['a', 'b', 'a'], 'v': [1, 2, 3]})",
        "print(df.groupby('k')['v'].sum().to_dict())"
      ],
      "options": ["`{'a': 4, 'b': 2}`", "`{'a': 1, 'b': 2}`", "`{'a': 3, 'b': 2}`"],
      "answer": 0,
      "explanation": "Rows with the same key are summed: `a` is 1 + 3 = 4 and `b` is 2.",
      "check": "output"
    }
  ]
}
```

| Field | | |
| --- | --- | --- |
| `id` | required | Lowercase words joined by hyphens, unique within the subject. Progress is saved per id, so keep it stable. |
| `difficulty` | required | `easy`, `medium` or `hard`. |
| `question`, `explanation` | required | Text with `` `code` `` and `**bold**`. Explanations can also have paragraphs (blank lines) and fenced code blocks. |
| `code` | optional | The snippet, as a string or a list of lines. |
| `options` | required | 2 to 6 answers. An option containing a line break is shown as preformatted text, which suits printed DataFrames. |
| `answer` | required | Index of the correct option. The app shuffles options, so it can always be `0`. |
| `check` | optional | How `verify` tests the question; see below. |
| `expect` | optional | With `"check": "options"`: a Python expression the answer must equal. |
| `shuffle` | optional | `false` keeps the options in file order. |

### Checked answers

`python quiz.py verify` runs the questions of Python subjects that have a `check`:

- `"check": "output"` runs `code`. What it prints, or the name of the exception it raises, must
  equal the correct option (backticks removed), and must not equal any other option.
- `"check": "options"` runs `code` as setup, then evaluates each option as a Python expression.
  The answer must run, and every other option must raise or return something different.

Either check also fails when the answer triggers a `DeprecationWarning` or `FutureWarning`, so
the quiz doesn't teach syntax that's on its way out. Questions without a `check` (concepts,
and file or database I/O) are validated for structure only, so review them by hand.

## Commands

| Command | |
| --- | --- |
| `python quiz.py` | Serve the app on port 8000 (or the next free one). Add `serve --port 9000 --no-open` to change that. |
| `python quiz.py build [--out DIR]` | Write the single-file app to `dist/index.html`. |
| `python quiz.py validate` | Check every quiz file's structure: required fields, unique ids, valid answer indexes. |
| `python quiz.py verify [SUBJECT]` | Run the checked questions. Needs `pip install -r requirements-dev.txt`. |
| `python -m unittest discover -s tests` | Tests for `quiz.py`. |

GitHub Actions runs all of these on every push (`.github/workflows/ci.yml`).

## pandas versions

Answers are verified against pandas 3.1. Almost all of them are the same on pandas 2.x. The
few that cover pandas 3 changes (the `str` dtype, Copy-on-Write, removed APIs and the new
frequency aliases) say "In pandas 3" and explain the 2.x behavior. After a pandas upgrade,
run `python quiz.py verify` to see which answers changed.

## Layout

```
quiz.py              serve, build, validate and verify (standard library only)
app/                 the web app: index.html, styles.css, app.js (no dependencies)
quizzes/             the questions
tests/test_quiz.py   unit tests for quiz.py
```
