/* Code Quiz: lists the subjects, runs a quiz and remembers progress in
   localStorage. Quiz data comes from an embedded <script id="quiz-data">
   (the single-file build) or from quizzes.json (python quiz.py serve). */
(() => {
  'use strict';

  const STORAGE_KEY = 'code-quiz:v1';
  const COUNTS = [10, 20, 30, 0]; // 0 means every matching question
  const LEVELS = ['easy', 'medium', 'hard'];
  const POOLS = [['all', 'All'], ['new', 'Not seen yet'], ['missed', 'Missed last time']];
  const KEYS = 'ABCDEF';
  const DEFAULTS = { excluded: [], count: 20, difficulty: 'all', pool: 'all' };

  const app = document.getElementById('app');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const announcer = document.createElement('div');
  announcer.className = 'sr-only';
  announcer.setAttribute('aria-live', 'polite');
  document.body.append(announcer);

  let subjects = [];
  let current = { view: 'loading', subject: null };
  let session = null;
  let confirmingReset = false;
  const saved = readSaved();

  /* ---------- saved progress and settings (a convenience, never required) ---------- */

  function readSaved() {
    try {
      const value = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (value && typeof value === 'object') {
        return { progress: value.progress || {}, settings: value.settings || {} };
      }
    } catch { /* storage blocked or unreadable */ }
    return { progress: {}, settings: {} };
  }

  function writeSaved() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); } catch { /* storage blocked */ }
  }

  function settingsFor(subject) {
    const settings = { ...DEFAULTS, ...saved.settings[subject.id] };
    if (!hasLevels(subject)) settings.difficulty = 'all';
    return settings;
  }

  function saveSettings(subject, settings) {
    saved.settings[subject.id] = settings;
    writeSaved();
  }

  function progressFor(subject) {
    return saved.progress[subject.id] || {};
  }

  function record(subject, question, correct) {
    const progress = (saved.progress[subject.id] ||= {});
    const entry = (progress[question.id] ||= { c: 0, w: 0 });
    if (correct) entry.c += 1; else entry.w += 1;
    entry.last = correct ? 1 : 0;
    writeSaved();
  }

  /* ---------- question pools ---------- */

  function itemsOf(subject) {
    return subject.topics.flatMap((topic) => topic.questions.map((q) => ({ q, topic })));
  }

  /** Difficulty is optional; subjects without it get no difficulty filter. */
  function hasLevels(subject) {
    return itemsOf(subject).some(({ q }) => q.difficulty);
  }

  function tally(subject, items) {
    const progress = progressFor(subject);
    let mastered = 0;
    let missed = 0;
    for (const { q } of items) {
      const entry = progress[q.id];
      if (entry && entry.last) mastered += 1;
      else if (entry) missed += 1;
    }
    return { total: items.length, mastered, missed };
  }

  function matching(subject, settings, overrides = {}) {
    const { difficulty, pool } = { ...settings, ...overrides };
    const progress = progressFor(subject);
    return itemsOf(subject).filter(({ q, topic }) => {
      if (settings.excluded.includes(topic.id)) return false;
      if (difficulty !== 'all' && q.difficulty !== difficulty) return false;
      const entry = progress[q.id];
      if (pool === 'new') return !entry;
      if (pool === 'missed') return Boolean(entry) && !entry.last;
      return true;
    });
  }

  function shuffle(list) {
    for (let i = list.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [list[i], list[j]] = [list[j], list[i]];
    }
    return list;
  }

  /* ---------- text: escaping, inline markdown, syntax highlighting ---------- */

  const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ESCAPES[c]);
  const words = (list) => new Set(list.split(' '));

  const LANGUAGES = {
    python: {
      pattern: /(#[^\n]*)|((?:\b[rRbBfFuU]{1,2})?(?:'''[\s\S]*?'''|"""[\s\S]*?"""|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"))|(\b\d[\d_]*(?:\.\d*)?(?:[eE][+-]?\d+)?j?\b)|([A-Za-z_]\w*)/g,
      keywords: words('False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'),
      builtins: words('abs all any bool dict enumerate filter float int isinstance len list map max min open print range repr round set sorted str sum tuple type zip'),
    },
    sql: {
      pattern: /(--[^\n]*)|('(?:''|[^'])*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)/g,
      keywords: words('select from where group by order having limit offset join left right inner outer full cross on as and or not in is null like ilike between case when then else end distinct union all insert into values update set delete create table view with over partition asc desc exists cast'),
      builtins: words('count sum avg min max coalesce row_number rank dense_rank lag lead date_trunc extract nullif round'),
      caseless: true,
    },
  };

  function highlight(code, language) {
    const rules = LANGUAGES[language];
    if (!rules) return esc(code);
    let html = '';
    let last = 0;
    for (const match of code.matchAll(rules.pattern)) {
      const [text, comment, string, number, word] = match;
      let kind = '';
      if (comment) kind = 'c';
      else if (string) kind = 's';
      else if (number) kind = 'n';
      else {
        const key = rules.caseless ? word.toLowerCase() : word;
        const isCall = code[match.index + text.length] === '(';
        if (code[match.index - 1] === '.') kind = isCall ? 'f' : ''; // methods and attributes
        else if (rules.keywords.has(key)) kind = 'k';
        else if (rules.builtins.has(key)) kind = 'b';
        else if (isCall) kind = 'f';
      }
      html += esc(code.slice(last, match.index));
      html += kind ? `<span class="t-${kind}">${esc(text)}</span>` : esc(text);
      last = match.index + text.length;
    }
    return html + esc(code.slice(last));
  }

  const CODE_SPAN = /(`+)(?!`)([\s\S]*?[^`])\1(?!`)/g;
  const FENCE = /```(\w*)\n([\s\S]*?)\n```/g;

  /** `code`, **bold** and line breaks; everything else is escaped. */
  function inline(text, language) {
    let html = '';
    let last = 0;
    for (const match of text.matchAll(CODE_SPAN)) {
      let code = match[2];
      if (code.length > 2 && code.startsWith(' ') && code.endsWith(' ')) code = code.slice(1, -1);
      html += prose(text.slice(last, match.index)) + `<code>${highlight(code, language)}</code>`;
      last = match.index + match[0].length;
    }
    return html + prose(text.slice(last));
  }

  function prose(text) {
    return esc(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
  }

  /** Paragraphs split by blank lines, plus ``` fenced code blocks. */
  function blocks(text, language) {
    let html = '';
    let last = 0;
    for (const match of text.matchAll(FENCE)) {
      html += paragraphs(text.slice(last, match.index), language);
      html += `<pre><code>${highlight(match[2], match[1] || language)}</code></pre>`;
      last = match.index + match[0].length;
    }
    return html + paragraphs(text.slice(last), language);
  }

  function paragraphs(text, language) {
    return text.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean)
      .map((part) => `<p>${inline(part, language)}</p>`).join('');
  }

  /** Options with line breaks (printed DataFrames, for instance) keep their layout. */
  function optionHtml(text, language) {
    if (!text.includes('\n')) return inline(text, language);
    const fence = text.match(/^```(\w*)\n([\s\S]*?)\n?```$/);
    const body = fence ? highlight(fence[2], fence[1] || language) : esc(text);
    return `<span class="option-pre">${body}</span>`;
  }

  function cell(code, language, number) {
    const prompt = language === 'python' ? `In [${number}]:` : esc(language.toUpperCase());
    return `<div class="cell">
      <span class="cell-prompt" aria-hidden="true">${prompt}</span>
      <pre tabindex="0"><code>${highlight(code, language)}</code></pre>
    </div>`;
  }

  function badge(subject, large = false) {
    const text = subject.badge || subject.title.slice(0, 2).toLowerCase();
    return `<span class="badge${large ? ' large' : ''}" aria-hidden="true">${esc(text)}</span>`;
  }

  function meter(fraction, label) {
    const width = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
    return `<span class="meter" role="img" aria-label="${esc(label)}"><span style="width:${width}%"></span></span>`;
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  /* ---------- views ---------- */

  function show(view, subject, html, { top = true } = {}) {
    current = { view, subject };
    app.innerHTML = html;
    if (top) {
      app.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
  }

  function route() {
    session = null;
    confirmingReset = false;
    const id = decodeURIComponent(location.hash.slice(1));
    const subject = subjects.find((s) => s.id === id);
    if (subject) renderSetup(subject);
    else renderHome();
  }

  function renderHome() {
    document.title = 'Code Quiz';
    const categories = [];
    for (const subject of subjects) {
      let group = categories.find(([name]) => name === subject.category);
      if (!group) categories.push((group = [subject.category, []]));
      group[1].push(subject);
    }
    const list = categories.map(([name, group], i) => `
      <section class="category" aria-labelledby="category-${i}">
        <h2 class="eyebrow" id="category-${i}">${esc(name)}</h2>
        <ul class="subject-list">${group.map(subjectCard).join('')}</ul>
      </section>`).join('');
    show('home', null, `<div class="view">
      <section class="group">
        <h1>Pick a subject</h1>
        <p class="lede">Short multiple-choice rounds with an explanation after every answer. The app remembers what you've mastered and what you missed.</p>
      </section>
      ${list || '<p class="status">No subjects yet. Add a folder with a quiz.json under quizzes/.</p>'}
    </div>`);
  }

  function subjectCard(subject) {
    const t = tally(subject, itemsOf(subject));
    return `<li><a class="subject-card" href="#${encodeURIComponent(subject.id)}">
      ${badge(subject)}
      <span class="subject-body">
        <span class="subject-title">${esc(subject.title)}</span>
        ${subject.description ? `<span class="subject-desc">${inline(subject.description, subject.language)}</span>` : ''}
        ${meter(t.total ? t.mastered / t.total : 0, `${t.mastered} of ${t.total} mastered`)}
        <span class="subject-meta">${plural(t.total, 'question')} · ${plural(subject.topics.length, 'topic')} · ${t.mastered} mastered</span>
      </span>
      <span class="go" aria-hidden="true">→</span>
    </a></li>`;
  }

  function pill(name, value, label, checked, extra = '') {
    const id = `${name}-${value}`;
    return `<label class="pill" for="${id}">
      <input type="radio" name="${name}" id="${id}" value="${value}"${checked ? ' checked' : ''}>
      <span>${label}${extra}</span>
    </label>`;
  }

  function renderSetup(subject, { focusId } = {}) {
    document.title = `${subject.title} · Code Quiz`;
    const settings = settingsFor(subject);
    const pool = matching(subject, settings);
    const count = settings.count ? Math.min(settings.count, pool.length) : pool.length;
    const totals = tally(subject, itemsOf(subject));
    const language = subject.language;

    const topics = subject.topics.map((topic) => {
      const t = tally(subject, topic.questions.map((q) => ({ q, topic })));
      const id = `topic-${topic.id}`;
      return `<label class="topic" for="${esc(id)}">
        <input type="checkbox" id="${esc(id)}" data-topic="${esc(topic.id)}"${settings.excluded.includes(topic.id) ? '' : ' checked'}>
        <span class="topic-name">${esc(topic.title)}</span>
        <span class="topic-meta">${plural(t.total, 'question')} · ${t.mastered} mastered</span>
      </label>`;
    }).join('');

    const counts = COUNTS.map((n) => pill('count', n, n ? String(n) : 'All', settings.count === n,
      n ? '' : ` <small>${pool.length}</small>`)).join('');
    const levels = ['all', ...LEVELS].map((level) => pill('difficulty', level,
      level[0].toUpperCase() + level.slice(1), settings.difficulty === level,
      ` <small>${matching(subject, settings, { difficulty: level }).length}</small>`)).join('');
    const pools = POOLS.map(([key, label]) => pill('pool', key, label, settings.pool === key,
      ` <small>${matching(subject, settings, { pool: key }).length}</small>`)).join('');

    let hint = `${plural(pool.length, 'question')} match`;
    if (!pool.length) {
      if (settings.excluded.length === subject.topics.length) hint = 'Select at least one topic.';
      else if (settings.pool === 'missed') hint = 'Nothing missed here yet. Choose All to practice.';
      else if (settings.pool === 'new') hint = 'You have seen every question here. Choose All or Missed last time.';
      else hint = 'No questions match. Try another difficulty.';
    }

    const reset = confirmingReset
      ? `<p>Clear your answers for ${esc(subject.title)}? Mastered and missed counts start over.</p>
         <button type="button" class="btn danger" id="reset-confirm" data-action="reset-confirm">Clear progress</button>
         <button type="button" class="btn quiet" id="reset-cancel" data-action="reset-cancel">Cancel</button>`
      : `<p>${totals.mastered} of ${totals.total} mastered · ${totals.missed} missed last time</p>
         <button type="button" class="btn quiet" id="reset-open" data-action="reset">Reset progress</button>`;

    show('setup', subject, `<div class="view">
      <p class="crumbs"><a href="#">← All subjects</a></p>
      <section class="subject-head">
        ${badge(subject, true)}
        <div>
          <p class="eyebrow">${esc(subject.category)}</p>
          <h1>${esc(subject.title)}</h1>
          ${subject.description ? `<p class="lede">${inline(subject.description, language)}</p>` : ''}
        </div>
      </section>
      ${subject.note ? `<p class="note">${inline(subject.note, language)}</p>` : ''}
      <div class="setup">
        <div class="group" role="group" aria-labelledby="topics-label">
          <div class="group-head">
            <span class="label" id="topics-label">Topics</span>
            <span class="group-tools">
              <button type="button" class="btn quiet" id="topics-all" data-action="topics-all">Select all</button>
              <button type="button" class="btn quiet" id="topics-none" data-action="topics-none">Clear</button>
            </span>
          </div>
          <div class="topic-list">${topics}</div>
        </div>
        <div class="group" role="radiogroup" aria-labelledby="count-label">
          <span class="label" id="count-label">Questions per round</span>
          <div class="pills">${counts}</div>
        </div>
        ${hasLevels(subject) ? `<div class="group" role="radiogroup" aria-labelledby="difficulty-label">
          <span class="label" id="difficulty-label">Difficulty</span>
          <div class="pills">${levels}</div>
        </div>` : ''}
        <div class="group" role="radiogroup" aria-labelledby="pool-label">
          <span class="label" id="pool-label">Questions to draw from</span>
          <div class="pills">${pools}</div>
        </div>
        <div class="start-row">
          <button type="button" class="btn primary" id="start" data-action="start"${count ? '' : ' disabled'}>Start ${plural(count, 'question')}</button>
          <span class="hint">${hint}</span>
        </div>
      </div>
      ${totals.mastered + totals.missed ? `<div class="reset">${reset}</div>` : ''}
    </div>`, { top: !focusId });
    if (focusId) document.getElementById(focusId)?.focus();
  }

  function startQuiz(subject, items) {
    session = {
      subject,
      items: shuffle(items.slice()).map(({ q, topic }) => {
        const order = q.options.map((_, i) => i);
        return { q, topic, order: q.shuffle === false ? order : shuffle(order) };
      }),
      index: 0,
      answers: [],
    };
    renderQuestion();
  }

  function renderQuestion({ top = true } = {}) {
    const { subject, items, index, answers } = session;
    const { q, topic, order } = items[index];
    const language = subject.language;
    const answer = answers[index];
    const answeredCount = answers.filter(Boolean).length;
    const score = answers.filter((a) => a && a.correct).length;
    const correctKey = KEYS[order.indexOf(q.answer)];
    const isLast = index === items.length - 1;

    const options = order.map((original, pos) => {
      let state = '';
      let verdict = '';
      if (answer) {
        if (original === q.answer) {
          state = 'is-correct';
          verdict = answer.correct ? '✓ Correct' : '✓ Answer';
        } else if (original === answer.choice) {
          state = 'is-wrong';
          verdict = '✗ Your pick';
        } else {
          state = 'is-muted';
        }
      }
      return `<li><button type="button" class="option ${state}" data-action="choose" data-pos="${pos}"${answer ? ' disabled' : ''}>
        <span class="key" aria-hidden="true">${KEYS[pos]}</span>
        <span class="option-body"><span class="sr-only">${KEYS[pos]}: </span>${optionHtml(q.options[original], language)}</span>
        <span class="verdict">${verdict}</span>
      </button></li>`;
    }).join('');

    let after;
    if (answer) {
      const title = answer.correct
        ? '✓ Correct'
        : answer.choice === -1 ? `The answer is ${correctKey}` : `✗ Not quite. The answer is ${correctKey}.`;
      after = `<div class="feedback ${answer.correct ? 'ok' : 'bad'}" id="feedback">
          <p class="feedback-title">${title}</p>
          <div class="explanation">${blocks(q.explanation, language)}</div>
        </div>
        <div class="actions">
          <button type="button" class="btn primary" id="next" data-action="next">${isLast ? 'See results' : 'Next question'} <kbd>Enter</kbd></button>
        </div>`;
    } else {
      after = `<div class="actions">
          <button type="button" class="btn quiet" data-action="reveal">I don't know, show me</button>
          <span class="kbd-hint">Keys 1–${order.length} or A–${KEYS[order.length - 1]} pick an answer</span>
        </div>`;
    }

    const level = q.difficulty
      ? `<div class="q-head"><span class="chip"><span class="dots" aria-hidden="true">${'●'.repeat(LEVELS.indexOf(q.difficulty) + 1).padEnd(3, '○')}</span>${q.difficulty}</span></div>`
      : '';
    show('quiz', subject, `<div class="view">
      <div class="quiz-top">
        <div class="quiz-meta">
          <span>${esc(subject.title)} · ${esc(topic.title)}</span>
          <span>Question <strong>${index + 1}</strong> of ${items.length} · ${score} correct</span>
        </div>
        <div class="progress" role="progressbar" aria-label="Answered" aria-valuemin="0" aria-valuemax="${items.length}" aria-valuenow="${answeredCount}">
          <span style="width:${Math.round((answeredCount / items.length) * 100)}%"></span>
        </div>
      </div>
      <article class="question" aria-labelledby="question-text">
        ${level}
        <p class="prompt" id="question-text">${inline(q.question, language)}</p>
        ${q.code ? cell(q.code, language, index + 1) : ''}
        <ol class="options" aria-label="Answers">${options}</ol>
        ${after}
      </article>
      <p class="crumbs"><button type="button" class="btn quiet" data-action="end">End quiz and see results</button></p>
    </div>`, { top });
  }

  function choose(pos) {
    const item = session.items[session.index];
    if (session.answers[session.index]) return;
    const choice = pos === -1 ? -1 : item.order[pos];
    const correct = choice === item.q.answer;
    session.answers[session.index] = { choice, correct };
    record(session.subject, item.q, correct);
    renderQuestion({ top: false });
    const key = KEYS[item.order.indexOf(item.q.answer)];
    announce(correct ? 'Correct.' : `Not quite. The answer is ${key}.`);
    document.getElementById('next')?.focus({ preventScroll: true });
    document.getElementById('feedback')?.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  function next() {
    if (session.index < session.items.length - 1) {
      session.index += 1;
      renderQuestion();
    } else {
      renderResults();
    }
  }

  function renderResults() {
    const { subject, items, answers } = session;
    const language = subject.language;
    const done = items.map((item, i) => ({ ...item, number: i + 1, answer: answers[i] })).filter((x) => x.answer);
    if (!done.length) {
      session = null;
      renderSetup(subject);
      return;
    }
    const correct = done.filter((x) => x.answer.correct).length;
    const missed = done.filter((x) => !x.answer.correct);
    session.missed = missed;
    const pct = Math.round((correct / done.length) * 100);
    let message = 'A tough round. Read the explanations below, then retry the ones you missed.';
    if (pct === 100) message = 'Every answer right.';
    else if (pct >= 80) message = 'Solid. Review the few you missed below.';
    else if (pct >= 50) message = 'Getting there. Each miss is explained below.';

    const byTopic = new Map();
    for (const x of done) {
      const row = byTopic.get(x.topic.id) || { title: x.topic.title, total: 0, right: 0 };
      row.total += 1;
      if (x.answer.correct) row.right += 1;
      byTopic.set(x.topic.id, row);
    }
    const rows = [...byTopic.values()].map((row) => `<tr>
        <td>${esc(row.title)}</td>
        <td class="num">${row.right}/${row.total}</td>
        <td class="num">${meter(row.right / row.total, `${Math.round((row.right / row.total) * 100)}% correct`)}</td>
      </tr>`).join('');

    const review = missed.map((x) => `<li class="review-item">
        <p class="eyebrow">${esc(x.topic.title)}</p>
        <p class="prompt">${inline(x.q.question, language)}</p>
        ${x.q.code ? cell(x.q.code, language, x.number) : ''}
        <div class="answer-line"><span class="tag bad">Your answer</span>
          <div>${x.answer.choice === -1 ? '<em>Skipped</em>' : optionHtml(x.q.options[x.answer.choice], language)}</div></div>
        <div class="answer-line"><span class="tag ok">Correct answer</span>
          <div>${optionHtml(x.q.options[x.q.answer], language)}</div></div>
        <div class="explanation">${blocks(x.q.explanation, language)}</div>
      </li>`).join('');

    show('results', subject, `<div class="view">
      <section class="group">
        <p class="eyebrow">${esc(subject.title)} · results</p>
        <div class="score">
          <span class="score-big">${correct}<small>/${done.length}</small></span>
          <p class="score-line">${pct}% correct. ${message}</p>
        </div>
      </section>
      <div class="actions">
        ${missed.length ? `<button type="button" class="btn primary" data-action="retry">Retry ${plural(missed.length, 'missed question')}</button>` : ''}
        <button type="button" class="btn${missed.length ? '' : ' primary'}" data-action="again">New round</button>
        <a class="btn quiet" href="#">All subjects</a>
      </div>
      <section class="group">
        <h2>By topic</h2>
        <div class="table-wrap"><table class="breakdown">
          <thead><tr><th scope="col">Topic</th><th scope="col" class="num">Score</th><th scope="col"><span class="sr-only">Share correct</span></th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </section>
      ${missed.length ? `<section class="group"><h2>What you missed</h2><ol class="review">${review}</ol></section>` : ''}
    </div>`);
  }

  function announce(text) {
    announcer.textContent = '';
    window.setTimeout(() => { announcer.textContent = text; }, 50);
  }

  /* ---------- events ---------- */

  app.addEventListener('click', (event) => {
    const el = event.target.closest('[data-action]');
    if (!el) return;
    const subject = current.subject;
    switch (el.dataset.action) {
      case 'choose': choose(Number(el.dataset.pos)); break;
      case 'reveal': choose(-1); break;
      case 'next': next(); break;
      case 'end': renderResults(); break;
      case 'retry': startQuiz(subject, session.missed); break;
      case 'again':
        session = null;
        renderSetup(subject);
        break;
      case 'start': {
        const settings = settingsFor(subject);
        const pool = shuffle(matching(subject, settings));
        const count = settings.count ? Math.min(settings.count, pool.length) : pool.length;
        if (count) startQuiz(subject, pool.slice(0, count));
        break;
      }
      case 'topics-all':
      case 'topics-none': {
        const settings = settingsFor(subject);
        settings.excluded = el.dataset.action === 'topics-all' ? [] : subject.topics.map((t) => t.id);
        saveSettings(subject, settings);
        renderSetup(subject, { focusId: el.id });
        break;
      }
      case 'reset':
        confirmingReset = true;
        renderSetup(subject, { focusId: 'reset-confirm' });
        break;
      case 'reset-confirm':
        delete saved.progress[subject.id];
        writeSaved();
        confirmingReset = false;
        renderSetup(subject, { focusId: 'start' });
        break;
      case 'reset-cancel':
        confirmingReset = false;
        renderSetup(subject, { focusId: 'reset-open' });
        break;
      default:
    }
  });

  app.addEventListener('change', (event) => {
    const input = event.target;
    const subject = current.subject;
    if (current.view !== 'setup' || !input.matches('input')) return;
    const settings = settingsFor(subject);
    if (input.dataset.topic) {
      const excluded = new Set(settings.excluded);
      if (input.checked) excluded.delete(input.dataset.topic); else excluded.add(input.dataset.topic);
      settings.excluded = [...excluded];
    } else if (input.name === 'count') {
      settings.count = Number(input.value);
    } else if (input.name === 'difficulty' || input.name === 'pool') {
      settings[input.name] = input.value;
    }
    saveSettings(subject, settings);
    renderSetup(subject, { focusId: input.id });
  });

  document.addEventListener('keydown', (event) => {
    if (current.view !== 'quiz' || !session || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target.closest('input, select, textarea')) return;
    const item = session.items[session.index];
    if (!session.answers[session.index]) {
      const key = event.key.length === 1 ? event.key.toUpperCase() : '';
      const pos = /[1-6]/.test(key) ? Number(key) - 1 : key ? KEYS.indexOf(key) : -1;
      if (pos >= 0 && pos < item.order.length) {
        event.preventDefault();
        choose(pos);
      }
    } else if (event.key === 'Enter' && !event.target.closest('button, a')) {
      event.preventDefault();
      next();
    }
  });

  /* ---------- start ---------- */

  async function loadData() {
    const embedded = document.getElementById('quiz-data');
    if (embedded) return JSON.parse(embedded.textContent);
    const response = await fetch('quizzes.json', { cache: 'no-store' });
    const body = await response.text();
    if (!response.ok) throw new Error(body || `The server answered ${response.status}.`);
    return JSON.parse(body);
  }

  loadData().then((data) => {
    subjects = data.subjects || [];
    window.addEventListener('hashchange', route);
    route();
  }).catch((error) => {
    const fromDisk = location.protocol === 'file:';
    show('error', null, `<div class="error" role="alert">
      <h1>The quizzes didn't load</h1>
      <p>${fromDisk
        ? 'This page needs its quiz data. Run <code>python quiz.py</code> and open the address it prints, or open the single file made by <code>python quiz.py build</code>.'
        : 'Fix the problems below in the quiz files, then reload this page.'}</p>
      <pre>${esc(error.message)}</pre>
    </div>`);
  });
})();
