#!/usr/bin/env node
// render.mjs — review.json + template.html → out.html
// usage: node render.mjs <review.json> <template.html> <out.html>
//
// Zero deps. Self-contained static HTML.
//
// Side effects beyond writing <out.html>:
//   - Reads the most-recent previous pr-{N}-*.json in the same dir to compute
//     a per-comment delta (new / edited / outdated_new / new replies / missing).
//   - Creates pr-{N}-latest.html and pr-{N}-latest.json symlinks pointing at
//     the just-rendered pair, so a browser tab on the latest URL can be refreshed
//     to see updates from subsequent runs.

import fs from 'node:fs';
import path from 'node:path';

const [, , reviewPath, tmplPath, outPath] = process.argv;
if (!reviewPath || !tmplPath || !outPath) {
  console.error('usage: render.mjs <review.json> <template.html> <out.html>');
  process.exit(2);
}

const review = JSON.parse(fs.readFileSync(reviewPath, 'utf8'));
const template = fs.readFileSync(tmplPath, 'utf8');

// ── helpers ─────────────────────────────────────────────────────────────────

const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

const attr = (s) => esc(s);

const VALIDITY_ICON = {
  valid: '✅', partial: '⚠️', unclear: '🤔', invalid: '❌',
};
const VALIDITY_LABEL = {
  valid: '수정 필요', partial: '부분 반영', unclear: '추가 논의', invalid: '반박 권장',
};
const TAG_LABEL = {
  blocking: '🔴 blocking',
  suggestion: '💡 suggestion',
  question: '❓ question',
  note: '💬 note',
};
const STATE_LABEL = {
  OPEN: 'OPEN', MERGED: 'MERGED', CLOSED: 'CLOSED',
};

const TS_REGEX = /^pr-(\d+)-(\d{8}-\d{6})\.json$/;

function vscodeHref(repoRoot, p, line) {
  if (!repoRoot || !p) return '';
  const abs = path.isAbsolute(p) ? p : path.join(repoRoot, p);
  const suffix = line != null ? `:${line}` : '';
  return `vscode://file/${abs}${suffix}`;
}

function locHtml(repoRoot, p, line) {
  const label = line != null ? `${p}:${line}` : p;
  const href = vscodeHref(repoRoot, p, line);
  if (href) return `<a href="${attr(href)}"><code>${esc(label)}</code></a>`;
  return `<code>${esc(label)}</code>`;
}

function truncate(text, max) {
  if (!text) return '';
  if (text.length <= max) return text;
  return text.slice(0, max - 1) + '…';
}

function prettyTs(name) {
  // pr-101-20260517-101200.json → 2026-05-17 10:12:00
  const m = name.match(TS_REGEX);
  if (!m) return name;
  const [_, , ts] = m;
  return `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`;
}

// ── delta: load previous review.json for the same PR ────────────────────────

function loadPrevious(currentJsonPath) {
  const dir = path.dirname(currentJsonPath);
  const currentName = path.basename(currentJsonPath);
  const m = currentName.match(TS_REGEX);
  if (!m) return null;
  const prNum = m[1];
  const pattern = new RegExp(`^pr-${prNum}-\\d{8}-\\d{6}\\.json$`);
  let entries;
  try { entries = fs.readdirSync(dir); } catch { return null; }
  const candidates = entries
    .filter((f) => pattern.test(f) && f !== currentName)
    .sort();
  if (!candidates.length) return null;
  const prevName = candidates[candidates.length - 1];
  try {
    const prev = JSON.parse(fs.readFileSync(path.join(dir, prevName), 'utf8'));
    return { prev, prevName };
  } catch {
    return null;
  }
}

function computeDelta(current, prev) {
  if (!prev) return { hasPrev: false, perComment: new Map(), missing: [] };
  const prevById = new Map();
  for (const c of prev.comments || []) {
    if (c.database_id) prevById.set(c.database_id, c);
  }
  const currentIds = new Set();
  const perComment = new Map();
  for (const c of current.comments || []) {
    if (!c.database_id) continue;
    currentIds.add(c.database_id);
    const prevC = prevById.get(c.database_id);
    const flags = {};
    if (!prevC) {
      flags.is_new = true;
    } else {
      // Edited: any of body change, last_edited_at advance, or updated_at advance.
      if (
        (c.last_edited_at && c.last_edited_at !== prevC.last_edited_at) ||
        (c.body !== prevC.body)
      ) flags.is_edited = true;
      if (!prevC.is_outdated && c.is_outdated) flags.outdated_new = true;
      const prevReplyIds = new Set(
        (prevC.replies || []).map((r) => r.database_id).filter(Boolean)
      );
      const newReplies = (c.replies || [])
        .filter((r) => r.database_id && !prevReplyIds.has(r.database_id)).length;
      // If prev had no IDs at all on replies, fall back to count diff.
      const lenDiff = (c.replies || []).length - (prevC.replies || []).length;
      flags.new_reply_count = Math.max(newReplies, lenDiff > 0 ? lenDiff : 0);
    }
    perComment.set(c.database_id, flags);
  }
  const missing = [];
  for (const c of prev.comments || []) {
    if (c.database_id && !currentIds.has(c.database_id)) missing.push(c);
  }
  return { hasPrev: true, perComment, missing };
}

// ── header / pr meta ────────────────────────────────────────────────────────

const pr = review.pr || {};
const reviews = review.reviews || {};
const repoRoot = review.repo_root || '';
const comments = (review.comments || []).slice();

const totalComments = comments.length;
const totalReviewers = (reviews.by_reviewer || []).length;

const prevInfo = loadPrevious(reviewPath);
const delta = computeDelta(review, prevInfo?.prev);

const draftBadge = pr.is_draft ? `<span class="badge badge-draft">DRAFT</span>` : '';
const prUrlLink = pr.url
  ? `<a class="icon-btn" href="${attr(pr.url)}" target="_blank" rel="noopener" title="Open on GitHub">↗ GitHub</a>`
  : '';

// ── pr body excerpt ─────────────────────────────────────────────────────────

const prBody = pr.body || '';
const prBodyEmpty = prBody.trim() === '';

// ── delta badges html ───────────────────────────────────────────────────────

function deltaBadgesHtml(c, opts = { compact: false }) {
  const f = delta.perComment.get(c.database_id);
  if (!f) return '';
  const out = [];
  if (f.is_new) out.push(`<span class="delta-badge new" title="이전 호출 이후 새로 달림">${opts.compact ? '🆕' : '🆕 NEW'}</span>`);
  if (f.is_edited) out.push(`<span class="delta-badge edited" title="본문 수정됨">${opts.compact ? '✏️' : '✏️ EDITED'}</span>`);
  if (f.outdated_new) out.push(`<span class="delta-badge outdated" title="새 커밋으로 diff outdated">${opts.compact ? '⏱' : '⏱ OUTDATED'}</span>`);
  if (f.new_reply_count > 0) out.push(`<span class="delta-badge reply-new" title="새 답글 ${f.new_reply_count}개">↳ +${f.new_reply_count}</span>`);
  return out.join(' ');
}

// ── github link icon ────────────────────────────────────────────────────────

const GH_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M7.775 3.275a.75.75 0 001.06 1.06l1.25-1.25a2 2 0 112.83 2.83l-2.5 2.5a2 2 0 01-2.83 0 .75.75 0 00-1.06 1.06 3.5 3.5 0 004.95 0l2.5-2.5a3.5 3.5 0 00-4.95-4.95l-1.25 1.25zm-4.69 9.64a2 2 0 010-2.83l2.5-2.5a2 2 0 012.83 0 .75.75 0 001.06-1.06 3.5 3.5 0 00-4.95 0l-2.5 2.5a3.5 3.5 0 004.95 4.95l1.25-1.25a.75.75 0 00-1.06-1.06l-1.25 1.25a2 2 0 01-2.83 0z"/></svg>`;

function ghLinkHtml(url) {
  if (!url) return '';
  return `<a class="gh-link" href="${attr(url)}" target="_blank" rel="noopener" title="Open on GitHub">${GH_SVG}</a>`;
}

// ── stats strip ─────────────────────────────────────────────────────────────

function buildStatsStrip() {
  if (totalComments === 0 && (review.resolved_hidden_count || 0) === 0) return '';
  const counts = { valid: 0, partial: 0, unclear: 0, invalid: 0 };
  comments.forEach((c) => { counts[c.validity] = (counts[c.validity] || 0) + 1; });
  const unresolvedCnt = comments.filter((c) => !c.resolved).length;
  const issueCnt = comments.filter((c) => c.recommendation === '이슈 생성').length;
  const hidden = review.resolved_hidden_count || 0;

  // Cross-call new comment count for the strip.
  let newCnt = 0;
  for (const c of comments) {
    if (delta.perComment.get(c.database_id)?.is_new) newCnt++;
  }

  const chips = [
    `<span class="stat-chip valid"><span class="num">${counts.valid}</span><span class="label">✅ Valid</span></span>`,
    `<span class="stat-chip partial"><span class="num">${counts.partial}</span><span class="label">⚠️ Partial</span></span>`,
    `<span class="stat-chip unclear"><span class="num">${counts.unclear}</span><span class="label">🤔 Unclear</span></span>`,
    `<span class="stat-chip invalid"><span class="num">${counts.invalid}</span><span class="label">❌ Invalid</span></span>`,
    `<span class="stat-chip"><span class="num">${unresolvedCnt}</span><span class="label">미해결 스레드</span></span>`,
  ];
  if (issueCnt > 0) {
    chips.push(`<span class="stat-chip"><span class="num">${issueCnt}</span><span class="label">이슈 분리 제안</span></span>`);
  }
  if (hidden > 0) {
    chips.push(`<span class="stat-chip"><span class="num">${hidden}</span><span class="label">resolved 숨김</span></span>`);
  }
  if (delta.hasPrev && newCnt > 0) {
    chips.push(`<span class="stat-chip"><span class="num">${newCnt}</span><span class="label">🆕 신규</span></span>`);
  }
  return `<div class="stats-strip">${chips.join('')}</div>`;
}

// ── missing strip (delta) ───────────────────────────────────────────────────

function buildMissingStrip() {
  if (!delta.hasPrev || !delta.missing.length) return '';
  const items = delta.missing.slice(0, 12).map((c) => {
    const resolvedNote = c.resolved_by ? ` <span class="related-note">resolved by @${esc(c.resolved_by)}</span>` : '';
    return `<li>
      <span class="miss-num">이전 #${esc(c.number ?? '?')}</span>
      ${locHtml(repoRoot, c.path, c.line)} — ${esc(c.summary || truncate(c.body, 30) || '(요약 없음)')}${resolvedNote}
    </li>`;
  }).join('');
  const moreNote = delta.missing.length > 12 ? `<li class="related-note">… 외 ${delta.missing.length - 12}건</li>` : '';
  const prevTs = prevInfo?.prevName ? prettyTs(prevInfo.prevName) : '';
  return `<div class="missing-strip">
    <div class="missing-strip-title">
      <span>⚠️ 이전 호출 이후 ${delta.missing.length}건이 사라졌습니다 (resolved · 숨김 · 삭제)</span>
      <span class="prev-ts">prev: ${esc(prevTs)}</span>
    </div>
    <ul>${items}${moreNote}</ul>
  </div>`;
}

// ── filter bar ──────────────────────────────────────────────────────────────

function buildFilterBar() {
  if (totalComments === 0) return '';
  const counts = { valid: 0, partial: 0, unclear: 0, invalid: 0 };
  comments.forEach((c) => { counts[c.validity] = (counts[c.validity] || 0) + 1; });
  return `<div class="filter-bar">
    <span class="filter-label">Filter</span>
    <span class="filter-chip active" data-filter="all">전체 <span class="chip-count">${totalComments}</span></span>
    <span class="filter-chip" data-filter="valid">✅ <span class="chip-count">${counts.valid}</span></span>
    <span class="filter-chip" data-filter="partial">⚠️ <span class="chip-count">${counts.partial}</span></span>
    <span class="filter-chip" data-filter="unclear">🤔 <span class="chip-count">${counts.unclear}</span></span>
    <span class="filter-chip" data-filter="invalid">❌ <span class="chip-count">${counts.invalid}</span></span>
    <input class="filter-search" type="search" placeholder="검색 (경로/요약/리뷰어)" />
  </div>`;
}

// ── dashboard table ─────────────────────────────────────────────────────────

function buildDashboardTable() {
  if (totalComments === 0) {
    return `<div class="empty-state">아직 인라인 코멘트가 없습니다.</div>`;
  }
  const rows = comments.map((c) => {
    const v = c.validity;
    const summary = c.summary || truncate(c.body, 30) || '(요약 없음)';
    const searchText = [c.path, c.summary, c.body, c.reviewer].join(' ').toLowerCase();
    const badges = deltaBadgesHtml(c, { compact: true });
    return `<tr data-comment-num="${attr(c.number)}" data-db-id="${attr(c.database_id || '')}" data-thread-id="${attr(c.thread_id || '')}" data-validity="${attr(v)}" data-search-text="${attr(searchText)}" class="${c.resolved ? 'resolved' : ''}">
      <td class="dash-num"><a href="#c${attr(c.number)}">#${esc(c.number)}</a>${badges ? ' ' + badges : ''}</td>
      <td class="dash-validity"><span class="v-icon" title="${esc(VALIDITY_LABEL[v] || v)}">${VALIDITY_ICON[v] || '·'}</span></td>
      <td class="dash-tag"><span class="tag-chip" data-tag="${attr(c.tag)}">${esc(TAG_LABEL[c.tag] || c.tag)}</span></td>
      <td class="dash-loc">${locHtml(repoRoot, c.path, c.line)}</td>
      <td class="dash-summary">${esc(summary)}</td>
      <td class="dash-rec"><span class="rec-chip" data-rec="${attr(c.recommendation)}">${esc(c.recommendation)}</span></td>
    </tr>`;
  }).join('');
  return `<div class="card dash-card">
    <table class="dash-table">
      <thead>
        <tr>
          <th>#</th><th>판정</th><th>태그</th><th>위치</th><th>요약</th><th>권장</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// ── processing order ────────────────────────────────────────────────────────

function buildProcOrder() {
  const order = review.processing_order || [];
  if (!order.length) return '';
  const pills = order.map((n) =>
    `<a class="proc-pill" href="#c${attr(n)}">#${esc(n)}</a>`
  ).join('<span class="proc-arrow">→</span>');
  return `<div class="proc-order">
    <span class="proc-label">처리 순서 제안:</span>
    ${pills}
  </div>`;
}

// ── diff hunk rendering ─────────────────────────────────────────────────────

function buildDiff(hunk) {
  if (!hunk) return '';
  const lines = hunk.split('\n');
  const MAX = 30;
  const shown = lines.slice(0, MAX);
  const more = lines.length - MAX;
  const html = shown.map((line) => {
    let cls = 'ctx';
    if (line.startsWith('@@')) cls = 'hunk';
    else if (line.startsWith('+')) cls = 'add';
    else if (line.startsWith('-')) cls = 'del';
    return `<span class="diff-line ${cls}">${esc(line) || '&nbsp;'}</span>`;
  }).join('');
  const trunc = more > 0 ? `<div class="diff-trunc">… (+${more} lines)</div>` : '';
  return `<div class="diff"><pre>${html}</pre>${trunc}</div>`;
}

// ── comment card ────────────────────────────────────────────────────────────

function buildComment(c) {
  const v = c.validity;
  const replies = (c.replies || []).map((r) =>
    `<div class="reply">
      <span class="reply-author">↳ @${esc(r.author)}</span>
      <span class="reply-body">${esc(r.body) || '<em>(본문 없음)</em>'}</span>
    </div>`
  ).join('');
  const repliesHtml = replies ? `<div class="comment-replies">${replies}</div>` : '';

  const related = (c.related || []).map((r) => {
    const noteHtml = r.note ? `<span class="related-note">— ${esc(r.note)}</span>` : '';
    return `<li>${locHtml(repoRoot, r.path, r.line)}${noteHtml}</li>`;
  }).join('');
  const relatedHtml = related
    ? `<div class="meta-block"><span class="meta-icon">🔗</span><span class="meta-block-title">연관 확인</span><ul class="related-list">${related}</ul></div>`
    : '';

  const rationale = c.rationale
    ? `<div class="meta-block"><span class="meta-icon">🔍</span><span class="meta-block-title">판정 근거</span>${esc(c.rationale)}</div>`
    : '';

  const recReason = c.recommendation_reason
    ? ` — ${esc(c.recommendation_reason)}`
    : '';
  const recHtml = `<div class="meta-block"><span class="meta-icon">🛠</span><span class="meta-block-title">권장</span><span class="rec-chip" data-rec="${attr(c.recommendation)}">${esc(c.recommendation)}</span>${recReason}</div>`;

  const resolvedBadge = c.resolved ? `<span class="comment-resolved-badge">RESOLVED</span>` : '';
  const bodyContent = c.body ? esc(c.body) : '<em>(본문 없음)</em>';
  const bodyClass = c.body ? 'comment-body' : 'comment-body empty';
  const deltaBadges = deltaBadgesHtml(c);
  const ghLink = ghLinkHtml(c.url);

  return `<article id="c${attr(c.number)}" class="comment ${c.resolved ? 'resolved' : ''}" data-comment-num="${attr(c.number)}" data-db-id="${attr(c.database_id || '')}" data-thread-id="${attr(c.thread_id || '')}" data-validity="${attr(v)}">
    <header class="comment-header">
      <span class="comment-num">#${esc(c.number)}</span>
      ${deltaBadges}
      <span class="comment-loc">${locHtml(repoRoot, c.path, c.line)}</span>
      <span class="tag-chip" data-tag="${attr(c.tag)}">${esc(TAG_LABEL[c.tag] || c.tag)}</span>
      <span class="comment-reviewer">— @${esc(c.reviewer)}</span>
      ${resolvedBadge}
      ${ghLink}
    </header>
    <div class="${bodyClass}">${bodyContent}</div>
    ${repliesHtml}
    ${relatedHtml}
    ${rationale}
    ${recHtml}
    ${buildDiff(c.diff_hunk)}
  </article>`;
}

// ── detail groups (by validity) ─────────────────────────────────────────────

function buildDetailGroups() {
  if (totalComments === 0) {
    return `<div class="empty-state">아직 인라인 코멘트가 없습니다.</div>`;
  }
  const groups = [
    { v: 'valid', title: '수정 필요' },
    { v: 'partial', title: '부분 반영' },
    { v: 'unclear', title: '추가 논의' },
    { v: 'invalid', title: '반박 권장' },
  ];
  return groups.map(({ v, title }) => {
    const items = comments.filter((c) => c.validity === v);
    const inner = items.length
      ? items.map(buildComment).join('')
      : `<div class="detail-group-empty">_없음_</div>`;
    return `<div class="detail-group" data-validity="${attr(v)}">
      <div class="detail-group-header">
        <span>${VALIDITY_ICON[v]}</span><span>${esc(title)}</span>
        <span class="count" style="color:var(--c-text-muted);font-weight:400;font-size:13px;">· ${items.length}건</span>
      </div>
      ${inner}
    </div>`;
  }).join('');
}

// ── reviewer summary ────────────────────────────────────────────────────────

function reviewerInitials(login) {
  return (login || '?').slice(0, 2).toUpperCase();
}

function buildReviewerList() {
  const reviewers = reviews.by_reviewer || [];
  if (!reviewers.length) {
    return `<div class="empty-state">아직 리뷰가 달리지 않았습니다.</div>`;
  }
  return `<div class="reviewer-list">${reviewers.map((r) => {
    const stateLabel = r.state === 'APPROVED' ? '✅ Approved'
      : r.state === 'CHANGES_REQUESTED' ? '🔴 Changes Requested'
      : r.state === 'COMMENTED' ? '💬 Commented'
      : r.state;
    const body = r.body || '';
    const bodyClass = body ? 'reviewer-body' : 'reviewer-body empty';
    const bodyHtml = body ? esc(body) : '(본문 없음)';
    const nums = (r.comment_numbers || []).map((n) =>
      `<a href="#c${attr(n)}">#${esc(n)}</a>`
    ).join(' ');
    const commentsHtml = nums ? `<div class="reviewer-comments">댓글 ${nums}</div>` : '';
    return `<div class="reviewer-row">
      <div class="reviewer-avatar">${esc(reviewerInitials(r.login))}</div>
      <div class="reviewer-meta">
        <span class="reviewer-name">@${esc(r.login)}</span>
        <span class="reviewer-state" data-state="${attr(r.state)}">${esc(stateLabel)}</span>
        <div class="${bodyClass}">${bodyHtml}</div>
        ${commentsHtml}
      </div>
    </div>`;
  }).join('')}</div>`;
}

// ── latest symlinks ─────────────────────────────────────────────────────────

function makeLatestSymlinks(htmlPath, jsonPath) {
  const dir = path.dirname(htmlPath);
  const htmlBase = path.basename(htmlPath);
  const jsonBase = path.basename(jsonPath);
  const m = htmlBase.match(/^pr-(\d+)-\d{8}-\d{6}\.html$/);
  if (!m) return;
  const prNum = m[1];
  const pairs = [
    [path.join(dir, `pr-${prNum}-latest.html`), htmlBase],
    [path.join(dir, `pr-${prNum}-latest.json`), jsonBase],
  ];
  for (const [link, target] of pairs) {
    try { fs.unlinkSync(link); } catch {}
    try {
      fs.symlinkSync(target, link);
    } catch (e) {
      console.warn(`latest symlink skipped (${link}): ${e.message}`);
    }
  }
}

// ── compose ─────────────────────────────────────────────────────────────────

const subs = {
  PR_NUMBER: esc(pr.number ?? ''),
  PR_TITLE: esc(pr.title || ''),
  PR_STATE: esc(pr.state || 'OPEN'),
  PR_STATE_LABEL: esc(STATE_LABEL[pr.state] || pr.state || 'OPEN'),
  DRAFT_BADGE: draftBadge,
  HEAD_BRANCH: esc(pr.branch?.head || ''),
  BASE_BRANCH: esc(pr.branch?.base || ''),
  ADDITIONS: esc(pr.changes?.additions ?? 0),
  DELETIONS: esc(pr.changes?.deletions ?? 0),
  FILES_COUNT: esc(pr.changes?.files ?? 0),
  R_APPROVED: esc(reviews.approved ?? 0),
  R_CHANGES: esc(reviews.changes_requested ?? 0),
  R_COMMENTED: esc(reviews.commented ?? 0),
  PR_URL_LINK: prUrlLink,
  PR_BODY: prBodyEmpty ? '(본문 없음)' : esc(prBody),
  PR_BODY_EMPTY_CLASS: prBodyEmpty ? ' empty' : '',
  TOTAL_COMMENTS: String(totalComments),
  TOTAL_REVIEWERS: String(totalReviewers),
  MISSING_STRIP: buildMissingStrip(),
  STATS_STRIP: buildStatsStrip(),
  FILTER_BAR: buildFilterBar(),
  DASHBOARD_TABLE: buildDashboardTable(),
  PROC_ORDER: buildProcOrder(),
  DETAIL_GROUPS: buildDetailGroups(),
  REVIEWER_LIST: buildReviewerList(),
  GENERATED_AT: esc(review.generated_at || new Date().toISOString()),
};

let html = template;
html = html.replace(/\{\{([A-Z_]+)\}\}/g, (_, k) => (k in subs ? subs[k] : ''));

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, html, 'utf8');

makeLatestSymlinks(outPath, reviewPath);

const newCnt = [...delta.perComment.values()].filter((f) => f.is_new).length;
const editedCnt = [...delta.perComment.values()].filter((f) => f.is_edited).length;
const deltaSummary = delta.hasPrev
  ? ` · delta vs ${prevInfo.prevName}: ${newCnt} new, ${editedCnt} edited, ${delta.missing.length} missing`
  : '';
console.log(`rendered → ${outPath} (${totalComments} comments, ${totalReviewers} reviewers)${deltaSummary}`);
