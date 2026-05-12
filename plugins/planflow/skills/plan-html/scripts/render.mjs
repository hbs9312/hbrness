#!/usr/bin/env node
// render.mjs — plan.json + template.html → index.html
// usage: node render.mjs <plan.json> <template.html> <out.html> <helperPort>
//
// Zero deps. Validates plan against schema.json (loaded sibling to template).

import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));

const [, , planPath, tmplPath, outPath, helperPortRaw] = process.argv;
if (!planPath || !tmplPath || !outPath) {
  console.error('usage: render.mjs <plan.json> <template.html> <out.html> [helperPort]');
  process.exit(2);
}
const helperPort = helperPortRaw || '0';

const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
const template = fs.readFileSync(tmplPath, 'utf8');
const lang = plan.lang === 'en' ? 'en' : 'ko';

// ── i18n helpers ─────────────────────────────────────────────────────────────
const T = {
  ko: {
    overview: '개요', goal: '목표', scope_in: '포함 범위', scope_out: '제외 범위',
    success: '성공 기준', risks: '리스크',
    phases: '단계', files: '변경 파일', files_other: '기타 변경 파일', diagrams: '다이어그램', decisions: '결정사항',
    round: '라운드', answered: '답변 완료', active: '답변 대기', pending: '대기',
    required: '필수', no_questions: '질문 없음', depends_on: '선행', tasks: '할 일',
    type: { add: 'ADD', modify: 'MODIFY', delete: 'DELETE', rename: 'RENAME' },
    status: { draft: '초안', review: '검토중', approved: '승인됨' },
  },
  en: {
    overview: 'Overview', goal: 'Goal', scope_in: 'In Scope', scope_out: 'Out of Scope',
    success: 'Success Criteria', risks: 'Risks',
    phases: 'Phases', files: 'Files', files_other: 'Other Files', diagrams: 'Diagrams', decisions: 'Decisions',
    round: 'Round', answered: 'Answered', active: 'Active', pending: 'Pending',
    required: 'required', no_questions: 'No questions', depends_on: 'depends on', tasks: 'Tasks',
    type: { add: 'ADD', modify: 'MODIFY', delete: 'DELETE', rename: 'RENAME' },
    status: { draft: 'Draft', review: 'Review', approved: 'Approved' },
  },
};
const t = T[lang];

const i18n = (val) => {
  if (val == null) return '';
  if (typeof val === 'string') return val;
  if (typeof val === 'object') return val[lang] ?? val.ko ?? val.en ?? '';
  return String(val);
};

const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const attr = (s) => esc(s);

// ── Section builders ─────────────────────────────────────────────────────────

function buildOverview() {
  const o = plan.overview;
  if (!o || Object.keys(o).length === 0) return '';
  const list = (arr, anchorPrefix) => (arr && arr.length)
    ? `<ul class="ov-list">${arr.map((x, i) => `<li data-anchor-id="${attr(anchorPrefix + '.' + i)}">${esc(i18n(x))}</li>`).join('')}</ul>`
    : `<div class="empty">—</div>`;

  const block = (klass, title, body) =>
    `<div class="ov-block ${klass}"><h3 class="ov-title">${esc(title)}</h3><div class="ov-body">${body}</div></div>`;

  const parts = [];
  if (o.goal) parts.push(block('goal', t.goal, `<p class="ov-text" data-anchor-id="overview.goal">${esc(i18n(o.goal))}</p>`));
  if (o.scope_in) parts.push(block('scope-in', t.scope_in, list(o.scope_in, 'overview.scope_in')));
  if (o.scope_out) parts.push(block('scope-out', t.scope_out, list(o.scope_out, 'overview.scope_out')));
  if (o.success_criteria) parts.push(block('criteria', t.success, list(o.success_criteria, 'overview.success_criteria')));
  if (o.risks) parts.push(block('risks', t.risks, list(o.risks, 'overview.risks')));

  return `
<section id="overview">
  <h2>${esc(t.overview)}</h2>
  <div class="overview-stack">${parts.join('')}</div>
</section>`;
}

function renderFileRows(files, anchorPrefix) {
  return files.map((f) => {
    const ct = f.change_type || 'modify';
    const summary = i18n(f.summary);
    const aid = `${anchorPrefix}.${f.path}`;
    return `<li class="phase-file" data-anchor-id="${attr(aid)}">
      <span class="change-chip" data-type="${attr(ct)}">${esc(t.type[ct])}</span>
      <span class="path">${esc(f.path)}</span>${summary ? `<span class="summary">— ${esc(summary)}</span>` : ''}
    </li>`;
  }).join('');
}

function buildPhases() {
  if (!plan.phases || !plan.phases.length) return '';
  const items = plan.phases.map((p, i) => {
    const tasks = (p.tasks && p.tasks.length)
      ? `<div class="phase-sub-title">${esc(t.tasks)}</div><ul class="phase-tasks">${p.tasks.map((tk, ti) => `<li data-anchor-id="${attr('phase.' + p.id + '.task.' + ti)}">${esc(i18n(tk))}</li>`).join('')}</ul>` : '';
    const files = (p.files && p.files.length)
      ? `<div class="phase-sub-title phase-sub-title-files">${esc(t.files)}</div><ul class="phase-files">${renderFileRows(p.files, 'phase.' + p.id + '.file')}</ul>` : '';
    const deps = (p.depends_on && p.depends_on.length)
      ? `<div class="phase-deps">${esc(t.depends_on)}: ${p.depends_on.map(esc).join(', ')}</div>` : '';
    return `
      <div class="phase card">
        <div class="phase-marker">${i + 1}</div>
        <div class="phase-content">
          <div class="phase-name" data-anchor-id="${attr('phase.' + p.id + '.name')}">${esc(i18n(p.name))} <span class="badge" style="margin-left:6px">${esc(p.id)}</span></div>
          ${deps}
          ${tasks}
          ${files}
        </div>
        <div class="phase-duration">${esc(p.duration || '')}</div>
      </div>`;
  }).join('');
  return `
<section id="phases">
  <h2>${esc(t.phases)} <span class="count">${plan.phases.length}</span></h2>
  <div class="phases-list">${items}</div>
</section>`;
}

function buildFiles() {
  // top-level files_touched: optional fallback for files that don't fit a phase.
  // phases[].files is preferred for per-phase impact.
  if (!plan.files_touched || !plan.files_touched.length) return '';
  return `
<section id="files">
  <h2>${esc(t.files_other)} <span class="count">${plan.files_touched.length}</span></h2>
  <div class="card">
    <ul class="phase-files">${renderFileRows(plan.files_touched, 'files')}</ul>
  </div>
</section>`;
}

function buildDiagrams() {
  if (!plan.diagrams || !plan.diagrams.length) return '';
  const items = plan.diagrams.map((d, i) => {
    const title = d.title ? `<div class="diagram-title">${esc(i18n(d.title))}</div>` : '';
    const aid = `diagram.${i}`;
    if (d.type === 'mermaid') {
      return `<div class="diagram" data-anchor-id="${attr(aid)}">${title}<div class="mermaid">${esc(d.code || '')}</div></div>`;
    }
    if (d.type === 'image') {
      return `<div class="diagram" data-anchor-id="${attr(aid)}">${title}<img src="${attr(d.src || '')}" alt="${attr(i18n(d.alt))}" /></div>`;
    }
    return '';
  }).join('');
  return `
<section id="diagrams">
  <h2>${esc(t.diagrams)} <span class="count">${plan.diagrams.length}</span></h2>
  <div class="card">${items}</div>
</section>`;
}

// ── Question rendering ───────────────────────────────────────────────────────

function renderQuestion(q) {
  const isAnswered = q.answer !== undefined;
  const required = q.required ? `<span class="q-required" title="${esc(t.required)}">*</span>` : '';
  const group = q.group ? `<span class="q-group">${esc(i18n(q.group))}</span>` : '';
  const ctx = q.context ? `<div class="q-context">${esc(i18n(q.context))}</div>` : '';

  let inputHtml = '';
  switch (q.type) {
    case 'text':
      inputHtml = `<input class="input" type="text" name="${attr(q.id)}" placeholder="${attr(i18n(q.placeholder))}" value="${attr(q.default ?? '')}" />`;
      break;
    case 'textarea':
      inputHtml = `<textarea class="textarea" name="${attr(q.id)}" placeholder="${attr(i18n(q.placeholder))}">${esc(q.default ?? '')}</textarea>`;
      break;
    case 'number':
      inputHtml = `<input class="input" type="number" name="${attr(q.id)}" placeholder="${attr(i18n(q.placeholder))}" ${q.min!=null?`min="${attr(q.min)}"`:''} ${q.max!=null?`max="${attr(q.max)}"`:''} ${q.step!=null?`step="${attr(q.step)}"`:''} value="${attr(q.default ?? '')}" />`;
      break;
    case 'date':
      inputHtml = `<input class="input" type="date" name="${attr(q.id)}" value="${attr(q.default ?? '')}" />`;
      break;
    case 'slider': {
      const min = q.min ?? 0, max = q.max ?? 100, step = q.step ?? 1;
      const def = q.default ?? min;
      inputHtml = `<div class="slider-wrap">
        <input class="slider" type="range" name="${attr(q.id)}" min="${attr(min)}" max="${attr(max)}" step="${attr(step)}" value="${attr(def)}" data-unit="${attr(q.unit || '')}" />
        <span class="slider-val"></span>
      </div>`;
      break;
    }
    case 'select': {
      const opts = (q.options || []).map((o) =>
        `<option value="${attr(o.value)}" ${q.default === o.value ? 'selected' : ''}>${esc(i18n(o.label) || o.value)}</option>`
      ).join('');
      inputHtml = `<select class="select" name="${attr(q.id)}"><option value="">—</option>${opts}</select>`;
      break;
    }
    case 'radio': {
      const opts = (q.options || []).map((o, i) =>
        `<label class="opt"><input type="radio" name="${attr(q.id)}" value="${attr(o.value)}" ${q.default === o.value ? 'checked' : ''} /><span class="opt-label">${esc(i18n(o.label) || o.value)}</span></label>`
      ).join('');
      inputHtml = `<div class="opt-group">${opts}</div>`;
      break;
    }
    case 'checkbox': {
      const defaults = Array.isArray(q.default) ? q.default : [];
      const opts = (q.options || []).map((o) =>
        `<label class="opt"><input type="checkbox" name="${attr(q.id)}" value="${attr(o.value)}" ${defaults.includes(o.value) ? 'checked' : ''} /><span class="opt-label">${esc(i18n(o.label) || o.value)}</span></label>`
      ).join('');
      inputHtml = `<div class="opt-group">${opts}</div>`;
      break;
    }
    case 'toggle':
      inputHtml = `<div class="toggle-row">
        <div class="toggle"><input type="checkbox" name="${attr(q.id)}" ${q.default ? 'checked' : ''} /></div>
        <span class="q-label" style="font-weight:400;color:var(--c-text-muted)">${esc(i18n(q.placeholder))}</span>
      </div>`;
      break;
    case 'tag-input':
      inputHtml = `<div class="tags tag-input-wrap">
        <input type="hidden" name="${attr(q.id)}" value='${esc(JSON.stringify(Array.isArray(q.default) ? q.default : []))}' />
        <input type="text" class="tag-input-field" placeholder="${attr(i18n(q.placeholder))}" />
      </div>`;
      break;
    default:
      inputHtml = `<div class="empty">unknown type: ${esc(q.type)}</div>`;
  }

  const answerDisplay = isAnswered
    ? `<div class="q-answer-display">${esc(formatAnswer(q.answer))}</div>` : '';

  return `<div class="q" data-qid="${attr(q.id)}" data-type="${attr(q.type)}" data-required="${q.required ? 'true' : 'false'}" data-readonly="${isAnswered ? 'true' : 'false'}">
    <div class="q-label">${group}<span>${esc(i18n(q.label))}</span>${required}</div>
    ${ctx}
    <div class="q-input">${inputHtml}</div>
    ${answerDisplay}
  </div>`;
}

function formatAnswer(a) {
  if (Array.isArray(a)) return a.join(', ');
  if (typeof a === 'boolean') return a ? '✓' : '✗';
  return String(a);
}

// ── Rounds ──────────────────────────────────────────────────────────────────

function buildRounds() {
  const questions = plan.questions || [];
  if (!questions.length) return `<div class="empty">${esc(t.no_questions)}</div>`;

  // group by round (default 1)
  const byRound = new Map();
  for (const q of questions) {
    const r = q.round || 1;
    if (!byRound.has(r)) byRound.set(r, []);
    byRound.get(r).push(q);
  }
  const rounds = [...byRound.keys()].sort((a, b) => a - b);

  // determine state per round
  const roundState = new Map();
  for (const r of rounds) {
    const qs = byRound.get(r);
    const allAnswered = qs.every((q) => q.answer !== undefined);
    roundState.set(r, allAnswered ? 'answered' : 'active');
  }
  // only one "active" — the lowest-numbered un-answered round
  let activeMarked = false;
  for (const r of rounds) {
    if (roundState.get(r) === 'active') {
      if (activeMarked) roundState.set(r, 'pending');
      else activeMarked = true;
    }
  }

  return rounds.map((r) => {
    const state = roundState.get(r);
    const qs = byRound.get(r);
    const stateLabel = state === 'answered' ? `${t.answered} ✓`
                      : state === 'active' ? `${t.active} ●`
                      : t.pending;
    const open = state === 'active' ? 'true' : (state === 'answered' ? 'false' : 'false');
    const inner = qs.map(renderQuestion).join('');
    const submitRow = state === 'active'
      ? `<div class="submit-row"><button class="btn btn-primary" data-submit-round="${r}">${esc(lang === 'ko' ? '이 라운드 제출' : 'Submit this round')}</button></div>`
      : '';
    return `<div class="round" data-round="${r}" data-state="${state}" data-open="${open}">
      <div class="round-header">
        <svg class="round-chevron" viewBox="0 0 16 16" fill="currentColor"><path d="M6 4l4 4-4 4z"/></svg>
        <div class="round-title">${esc(t.round)} ${r}</div>
        <span class="round-status" data-state="${state}">${esc(stateLabel)}</span>
      </div>
      <div class="round-body">${inner}${submitRow}</div>
    </div>`;
  }).join('');
}

// ── TOC ─────────────────────────────────────────────────────────────────────

function buildToc() {
  const items = [];
  if (plan.overview && Object.keys(plan.overview).length) items.push(['overview', t.overview]);
  if (plan.phases && plan.phases.length) items.push(['phases', t.phases]);
  if (plan.files_touched && plan.files_touched.length) items.push(['files', t.files]);
  if (plan.diagrams && plan.diagrams.length) items.push(['diagrams', t.diagrams]);
  items.push(['decisions', t.decisions]);
  items.push(['ask', lang === 'ko' ? '질문하기' : 'Ask Claude']);
  return items.map(([id, label]) => `<a href="#${id}">${esc(label)}</a>`).join('');
}

// ── Compose ─────────────────────────────────────────────────────────────────

const totalQuestions = (plan.questions || []).filter((q) => q.answer === undefined).length
  + (plan.questions || []).filter((q) => q.answer !== undefined).length; // all questions count
const statusLabel = t.status[plan.status || 'draft'];

const subs = {
  TITLE: esc(plan.title || ''),
  STATUS: esc(plan.status || 'draft'),
  STATUS_LABEL: esc(statusLabel),
  LANG: esc(lang),
  CREATED_AT: esc(plan.created_at || ''),
  HELPER_PORT: esc(helperPort),
  PLAN_SLUG: esc(plan.slug || path.basename(path.dirname(planPath))),
  TOTAL_QUESTIONS: String(totalQuestions),

  TOC_HTML: buildToc(),
  OVERVIEW_HTML: buildOverview(),
  PHASES_HTML: buildPhases(),
  FILES_HTML: buildFiles(),
  DIAGRAMS_HTML: buildDiagrams(),
  ROUNDS_HTML: buildRounds(),
};

// Comments serialized for client-side decoration.
// Safe JSON embedding: replace </ with <\/ to prevent script tag breakout.
const commentsJson = JSON.stringify(plan.comments || []).replace(/</g, '\\u003c');
subs.COMMENTS_JSON = commentsJson;

let html = template;
// {{{NAME}}} — raw HTML
html = html.replace(/\{\{\{([A-Z_]+)\}\}\}/g, (_, k) => subs[k] ?? '');
// {{NAME}} — already escaped strings
html = html.replace(/\{\{([A-Z_]+)\}\}/g, (_, k) => subs[k] ?? '');

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, html, 'utf8');
console.log(`rendered → ${outPath} (${totalQuestions} questions, ${(plan.comments || []).length} comments)`);
