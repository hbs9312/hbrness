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
    summary: '요약', current_state: '현재 파악', proposed_approach: '접근 방향',
    review_focus: '검토 포인트', success: '성공 기준', risks: '리스크',
    phases: '단계', files: '변경 파일', files_other: '기타 변경 파일', diagrams: '다이어그램', decisions: '질문 라운드',
    answer_review: '답변 확인', answer_review_help: '질문 라운드에서 선택한 답변을 펼쳐 확인합니다.',
    asks: 'Q&A', asks_toggle: 'Q&A', asks_pending: '답변 대기', asks_answered: '답변 완료',
    asks_help: 'UI 에서 보낸 자유 질문과 Claude 의 답변. 채팅에는 카운트만 표시되고 본문은 여기 누적됩니다.',
    asks_empty: '아직 질문이 없습니다.',
    asks_no_answer: '답변 대기 중',
    asks_answered_by: '답변자',
    asks_sent_at: '보낸 시각',
    asks_answered_at: '답변 시각',
    round: '라운드', answered: '답변 완료', active: '답변 대기', pending: '대기',
    required: '필수', no_questions: '질문 없음', depends_on: '선행', tasks: '할 일',
    evidence: '확인한 근거', recommendation: '추천', tradeoffs: '트레이드오프',
    other: '직접 입력',
    other_placeholder: '원하는 답변 입력',
    type: { add: 'ADD', modify: 'MODIFY', delete: 'DELETE', rename: 'RENAME' },
    status: { draft: '초안', review: '검토중', approved: '승인됨' },
  },
  en: {
    overview: 'Overview', goal: 'Goal', scope_in: 'In Scope', scope_out: 'Out of Scope',
    summary: 'Summary', current_state: 'Current State', proposed_approach: 'Approach',
    review_focus: 'Review Focus', success: 'Success Criteria', risks: 'Risks',
    phases: 'Phases', files: 'Files', files_other: 'Other Files', diagrams: 'Diagrams', decisions: 'Question Rounds',
    answer_review: 'Answer Review', answer_review_help: 'Expand to review the answers selected during question rounds.',
    asks: 'Q&A', asks_toggle: 'Q&A', asks_pending: 'Awaiting answer', asks_answered: 'Answered',
    asks_help: 'Free-form questions sent from the UI and Claude\'s answers. The chat shows only a count; full bodies accumulate here.',
    asks_empty: 'No questions yet.',
    asks_no_answer: 'Awaiting answer',
    asks_answered_by: 'Answered by',
    asks_sent_at: 'Sent at',
    asks_answered_at: 'Answered at',
    round: 'Round', answered: 'Answered', active: 'Active', pending: 'Pending',
    required: 'required', no_questions: 'No questions', depends_on: 'depends on', tasks: 'Tasks',
    evidence: 'Evidence', recommendation: 'Recommendation', tradeoffs: 'Tradeoffs',
    other: 'Other',
    other_placeholder: 'Enter a custom answer',
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

  // Render prose with paragraph breaks (\n\n) and bullet detection.
  // Each blank-line-separated block becomes its own <p>, <ul>, or <ol>.
  const proseHtml = (text) => {
    const blocks = String(text || '').split(/\n[ \t]*\n+/).map((b) => b.trim()).filter(Boolean);
    if (!blocks.length) return '';
    return blocks.map((b) => {
      const lines = b.split('\n').map((l) => l.trim()).filter(Boolean);
      if (lines.length > 1 && lines.every((l) => /^[-*]\s+/.test(l))) {
        const items = lines.map((l) => `<li>${esc(l.replace(/^[-*]\s+/, ''))}</li>`).join('');
        return `<ul class="ov-bullets">${items}</ul>`;
      }
      if (lines.length > 1 && lines.every((l) => /^(\(\d+\)|\d+[.)])\s+/.test(l))) {
        const items = lines.map((l) => `<li>${esc(l.replace(/^(\(\d+\)|\d+[.)])\s+/, ''))}</li>`).join('');
        return `<ol class="ov-bullets">${items}</ol>`;
      }
      return `<p class="ov-text">${esc(lines.join(' '))}</p>`;
    }).join('');
  };

  // Anchor is placed on the outer block so existing comments anchored to
  // "overview.<key>" keep resolving even after we split prose into paragraphs.
  const block = (klass, title, body, anchorId) => {
    const anchorAttr = anchorId ? ` data-anchor-id="${attr(anchorId)}"` : '';
    return `<div class="ov-block ${klass}"${anchorAttr}><h3 class="ov-title">${esc(title)}</h3><div class="ov-body">${body}</div></div>`;
  };
  const prose = (key, title, klass) =>
    o[key] ? block(`prose ${klass}`, title, proseHtml(i18n(o[key])), `overview.${key}`) : '';

  const parts = [];
  const proseParts = [
    prose('summary', t.summary, 'summary'),
    prose('current_state', t.current_state, 'current-state'),
    prose('proposed_approach', t.proposed_approach, 'proposed-approach'),
  ].filter(Boolean);
  parts.push(...proseParts);
  if (o.goal) parts.push(block('goal', t.goal, proseHtml(i18n(o.goal)), 'overview.goal'));
  if (o.review_focus) parts.push(block('review-focus', t.review_focus, list(o.review_focus, 'overview.review_focus')));
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
  const hint = lang === 'en' ? 'Click to zoom' : '클릭하면 확대';
  const items = plan.diagrams.map((d, i) => {
    const title = d.title ? `<div class="diagram-title">${esc(i18n(d.title))}</div>` : '';
    const aid = `diagram.${i}`;
    const zoomHint = `<span class="diagram-zoom-hint">🔍 ${esc(hint)}</span>`;
    if (d.type === 'mermaid') {
      return `<div class="diagram" data-anchor-id="${attr(aid)}">${title}${zoomHint}<div class="mermaid">${esc(d.code || '')}</div></div>`;
    }
    if (d.type === 'image') {
      return `<div class="diagram" data-anchor-id="${attr(aid)}">${title}${zoomHint}<img src="${attr(d.src || '')}" alt="${attr(i18n(d.alt))}" /></div>`;
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

function optionLabel(q, value) {
  const match = ((q && q.options) || []).find((o) => Object.is(o.value, value));
  return match ? (i18n(match.label) || String(match.value)) : String(value);
}

function optionValues(q) {
  return new Set((q.options || []).map((o) => String(o.value)));
}

function renderOtherControl(q, kind, defaultOtherValue) {
  if (!q.allow_other) return '';
  const label = i18n(q.other_label) || t.other;
  const placeholder = i18n(q.other_placeholder) || t.other_placeholder;
  const checked = defaultOtherValue ? 'checked' : '';
  const inputValue = defaultOtherValue ? ` value="${attr(defaultOtherValue)}"` : '';
  const input = `<input class="input opt-other-input" type="text" data-other-input placeholder="${attr(placeholder)}"${inputValue} />`;
  if (kind === 'radio') {
    return `<label class="opt opt-other"><input type="radio" name="${attr(q.id)}" value="__other__" data-other-radio ${checked} /><span class="opt-label">${esc(label)}</span>${input}</label>`;
  }
  return `<label class="opt opt-other"><input type="checkbox" name="${attr(q.id)}" value="__other__" data-other-checkbox ${checked} /><span class="opt-label">${esc(label)}</span>${input}</label>`;
}

function renderQuestionMeta(q) {
  const blocks = [];
  if (Array.isArray(q.evidence) && q.evidence.length) {
    const items = q.evidence.map((ev, i) => {
      const pathHtml = ev.path ? `<span class="q-evidence-path">${esc(ev.path)}</span>` : '';
      return `<li data-anchor-id="${attr('question.' + q.id + '.evidence.' + i)}">${pathHtml}<span>${esc(i18n(ev.summary))}</span></li>`;
    }).join('');
    blocks.push(`<div class="q-meta-block q-evidence">
      <div class="q-meta-title">${esc(t.evidence)}</div>
      <ul class="q-evidence-list">${items}</ul>
    </div>`);
  }
  if (q.recommendation) {
    blocks.push(`<div class="q-meta-block q-recommendation" data-anchor-id="${attr('question.' + q.id + '.recommendation')}">
      <div class="q-meta-title">${esc(t.recommendation)}</div>
      <p>${esc(i18n(q.recommendation))}</p>
    </div>`);
  }
  if (Array.isArray(q.tradeoffs) && q.tradeoffs.length) {
    const items = q.tradeoffs.map((tr, i) => {
      const valueHtml = tr.value !== undefined ? `<span class="q-tradeoff-value">${esc(optionLabel(q, tr.value))}</span>` : '';
      return `<li data-anchor-id="${attr('question.' + q.id + '.tradeoff.' + i)}">${valueHtml}<span>${esc(i18n(tr.impact))}</span></li>`;
    }).join('');
    blocks.push(`<div class="q-meta-block q-tradeoffs">
      <div class="q-meta-title">${esc(t.tradeoffs)}</div>
      <ul class="q-tradeoff-list">${items}</ul>
    </div>`);
  }
  return blocks.length ? `<div class="q-meta">${blocks.join('')}</div>` : '';
}

function renderQuestion(q) {
  const isAnswered = q.answer !== undefined;
  const required = q.required ? `<span class="q-required" title="${esc(t.required)}">*</span>` : '';
  const group = q.group ? `<span class="q-group">${esc(i18n(q.group))}</span>` : '';
  const ctx = q.context ? `<div class="q-context">${esc(i18n(q.context))}</div>` : '';
  const meta = renderQuestionMeta(q);

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
      const values = optionValues(q);
      const defaultOther = q.default != null && !values.has(String(q.default)) ? String(q.default) : '';
      const opts = (q.options || []).map((o, i) =>
        `<label class="opt"><input type="radio" name="${attr(q.id)}" value="${attr(o.value)}" ${q.default === o.value ? 'checked' : ''} /><span class="opt-label">${esc(i18n(o.label) || o.value)}</span></label>`
      ).join('');
      inputHtml = `<div class="opt-group">${opts}${renderOtherControl(q, 'radio', defaultOther)}</div>`;
      break;
    }
    case 'checkbox': {
      const defaults = Array.isArray(q.default) ? q.default : [];
      const values = optionValues(q);
      const defaultOther = defaults.filter((v) => !values.has(String(v))).map(String).join(', ');
      const opts = (q.options || []).map((o) =>
        `<label class="opt"><input type="checkbox" name="${attr(q.id)}" value="${attr(o.value)}" ${defaults.includes(o.value) ? 'checked' : ''} /><span class="opt-label">${esc(i18n(o.label) || o.value)}</span></label>`
      ).join('');
      inputHtml = `<div class="opt-group">${opts}${renderOtherControl(q, 'checkbox', defaultOther)}</div>`;
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
    ? `<div class="q-answer-display">${esc(formatAnswer(q, q.answer))}</div>` : '';

  return `<div class="q" data-qid="${attr(q.id)}" data-type="${attr(q.type)}" data-required="${q.required ? 'true' : 'false'}" data-readonly="${isAnswered ? 'true' : 'false'}">
    <div class="q-label">${group}<span data-anchor-id="${attr('question.' + q.id + '.label')}">${esc(i18n(q.label))}</span>${required}</div>
    ${ctx}
    ${meta}
    <div class="q-input">${inputHtml}</div>
    ${answerDisplay}
  </div>`;
}

function formatAnswer(q, a) {
  if (Array.isArray(a)) return a.map((v) => optionLabel(q, v)).join(', ');
  if (q && Array.isArray(q.options) && q.options.length && a != null) return optionLabel(q, a);
  if (typeof a === 'boolean') return a ? '✓' : '✗';
  return String(a);
}

function formatReviewAnswer(q) {
  const answer = q.answer;
  return formatAnswer(q, answer);
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

function buildDecisionSection() {
  return `
<section id="decisions">
  <h2>${esc(t.decisions)} <span class="count">${(plan.questions || []).length}</span></h2>
  ${buildRounds()}
</section>`;
}

function buildPlanSections() {
  return [
    buildOverview(),
    buildPhases(),
    buildFiles(),
    buildDiagrams(),
  ].filter(Boolean).join('\n');
}

function buildAnswerReview() {
  const answered = (plan.questions || []).filter((q) => q.answer !== undefined);
  if (!answered.length) return '';

  const byRound = new Map();
  for (const q of answered) {
    const r = q.round || 1;
    if (!byRound.has(r)) byRound.set(r, []);
    byRound.get(r).push(q);
  }

  const rounds = [...byRound.keys()].sort((a, b) => a - b).map((r) => {
    const items = byRound.get(r).map((q) => {
      const group = q.group ? `<div class="answer-group">${esc(i18n(q.group))}</div>` : '';
      return `<li class="answer-item">
        ${group}
        <div class="answer-label">${esc(i18n(q.label))}</div>
        <div class="answer-value">${esc(formatReviewAnswer(q))}</div>
      </li>`;
    }).join('');
    return `<div class="answer-round">
      <div class="answer-round-title">${esc(t.round)} ${r}</div>
      <ul class="answer-list">${items}</ul>
    </div>`;
  }).join('');

  return `<p class="answer-review-help">${esc(t.answer_review_help)}</p>${rounds}`;
}

function buildAsksReview() {
  const asks = Array.isArray(plan.asks) ? plan.asks : [];
  if (!asks.length) return `<p class="answer-review-help">${esc(t.asks_help)}</p><div class="empty">${esc(t.asks_empty)}</div>`;

  const items = asks.map((a) => {
    const isAnswered = a.answer != null && String(a.answer).length > 0;
    const stateLabel = isAnswered ? t.asks_answered : t.asks_pending;
    const stateClass = isAnswered ? 'answered' : 'pending';
    const answerHtml = isAnswered
      ? `<div class="ask-answer">${esc(a.answer)}</div>
         <div class="ask-meta">${esc(t.asks_answered_by)}: ${esc(a.answered_by || 'claude')} · ${esc(t.asks_answered_at)}: ${esc(a.answered_at || '')}</div>`
      : `<div class="ask-answer ask-answer-empty">${esc(t.asks_no_answer)}</div>`;
    return `<li class="ask-item" data-state="${stateClass}" data-ask-id="${attr(a.id)}">
      <div class="ask-header">
        <span class="ask-id">${esc(a.id)}</span>
        <span class="ask-state" data-state="${stateClass}">${esc(stateLabel)}</span>
      </div>
      <div class="ask-question">${esc(a.text || '')}</div>
      <div class="ask-meta">${esc(t.asks_sent_at)}: ${esc(a.ts || '')}</div>
      ${answerHtml}
    </li>`;
  }).join('');

  return `<p class="answer-review-help">${esc(t.asks_help)}</p><ul class="ask-list">${items}</ul>`;
}

// ── TOC ─────────────────────────────────────────────────────────────────────

function buildToc() {
  const items = [];
  if (flowState === 'questions') {
    items.push(['decisions', t.decisions]);
  } else {
    if (plan.overview && Object.keys(plan.overview).length) items.push(['overview', t.overview]);
    if (plan.phases && plan.phases.length) items.push(['phases', t.phases]);
    if (plan.files_touched && plan.files_touched.length) items.push(['files', t.files]);
    if (plan.diagrams && plan.diagrams.length) items.push(['diagrams', t.diagrams]);
  }
  return items.map(([id, label]) => `<a href="#${id}">${esc(label)}</a>`).join('');
}

// ── Compose ─────────────────────────────────────────────────────────────────

const questions = plan.questions || [];
const totalQuestions = questions.length;
const answeredQuestions = questions.filter((q) => q.answer !== undefined).length;
const unansweredQuestions = totalQuestions - answeredQuestions;
const flowState = unansweredQuestions > 0 ? 'questions' : 'plan';
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
  ANSWERED_QUESTIONS: String(answeredQuestions),
  UNANSWERED_QUESTIONS: String(unansweredQuestions),
  FLOW_STATE: esc(flowState),
  ASKS_TOTAL: String((plan.asks || []).length),
  ASKS_PENDING: String((plan.asks || []).filter((a) => !a.answer).length),
  ASKS_PENDING_EMPTY: ((plan.asks || []).filter((a) => !a.answer).length === 0) ? 'true' : 'false',

  TOC_HTML: buildToc(),
  DECISIONS_SECTION_HTML: flowState === 'questions' ? buildDecisionSection() : '',
  PLAN_SECTIONS_HTML: flowState === 'plan' ? buildPlanSections() : '',
  ANSWERS_SIDEBAR_HTML: buildAnswerReview(),
  ASKS_SIDEBAR_HTML: buildAsksReview(),
};

// Comments serialized for client-side decoration.
// Safe JSON embedding: replace </ with <\/ to prevent script tag breakout.
const commentsJson = JSON.stringify(plan.comments || []).replace(/</g, '\\u003c');
subs.COMMENTS_JSON = commentsJson;
subs.ANSWERS_JSON = JSON.stringify(Object.fromEntries(
  questions.filter((q) => q.answer !== undefined).map((q) => [q.id, q.answer])
)).replace(/</g, '\\u003c');

let html = template;
// {{{NAME}}} — raw HTML
html = html.replace(/\{\{\{([A-Z_]+)\}\}\}/g, (_, k) => subs[k] ?? '');
// {{NAME}} — already escaped strings
html = html.replace(/\{\{([A-Z_]+)\}\}/g, (_, k) => subs[k] ?? '');

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, html, 'utf8');
console.log(`rendered → ${outPath} (${totalQuestions} questions, ${(plan.comments || []).length} comments)`);
