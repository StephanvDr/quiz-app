# Code Quiz

A multiple-choice quiz app for practising data and machine-learning skills. Each question
explains its answer, whether you got it right or not, so you learn from every miss.

## Subjects

**Pandas** (Python): 183 questions in 14 topics. Read a snippet and predict what it prints,
or pick the call that does the job. The code answers are checked by running them on pandas
3.1; where pandas 2.x behaves differently, the explanation says so.

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

**ML pitfalls** (Machine Learning): 104 questions in 7 topics on supervised-learning
terminology and common mistakes, with Dutch terms where the course slides use them.

| Topic | Questions |
| --- | ---: |
| Workflow and basics | 14 |
| Algorithms | 14 |
| Pitfalls 1: data quality and preprocessing | 16 |
| Pitfalls 2: model choice and training | 15 |
| Pitfalls 3a: classification metrics | 15 |
| Pitfalls 3b: regression metrics and validation | 17 |
| Pitfalls 4: implementation in practice | 13 |

## Start the quiz

You need Python 3.10 or newer; nothing else to install. In the project folder, run:

```bash
python quiz.py
```

The quiz opens in your browser at <http://localhost:8000>. Press Ctrl+C in the terminal to
stop it.

### Without Python

Build a single HTML file that holds the whole app and every question:

```bash
python quiz.py build
```

Open `dist/index.html` straight from disk, send it to someone, or put it on any static host
such as GitHub Pages.

## How it works

- **Pick a round**: choose topics, a round size (10, 20, 30 or all), a difficulty, and which
  questions to draw from: all, ones you haven't seen yet, or ones you got wrong last time.
- **Answer**: click an option, or press `1`–`6` or `A`–`F`, then `Enter` to continue.
  Options are shuffled every time. "I don't know, show me" reveals the answer and counts it
  as missed.
- **Review**: the results page shows your score per topic, lists every miss with its
  explanation, and can start a new round with just the questions you missed.
- **Progress** is saved in your browser, per subject. Nothing is sent anywhere, so it stays
  on the device and browser you used.

## Adding questions

Want to add questions or a new subject? See [CONTRIBUTING.md](CONTRIBUTING.md).
