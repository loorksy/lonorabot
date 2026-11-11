export const meta = {
  name: 'ref37-fix-package',
  description: 'Implement one package of reference-37 fidelity gaps step by step: implement, two reviews, fix',
  phases: [
    { title: 'Implement', detail: 'one implementer per step, in the package worktree', model: 'opus' },
    { title: 'Review', detail: 'a browser reviewer and a code reviewer per step', model: 'sonnet' },
    { title: 'Fix', detail: 'answer the review findings', model: 'opus' },
  ],
}

const P = args
const FX = '/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx'
const WT = `/home/user/wt/${P.pkg}`
const BASE = 'ccr-9c66a289-3283wb'

const common = `Package: ${P.pkg} (${P.title}).
Worktree: ${WT} on branch fx/${P.pkg}. Work only there.
Read first, completely: ${FX}/BRIEF.md. Then read ${FX}/${P.pkg}/package.json: it lists what this package owns and, for each step, the lead's notes and the full audit entry of every gap (reference evidence, app evidence, what the owner sees, the auditor's suggested fix, the verifier's note).`

const GAP_RESULT = {
  type: 'array',
  items: {
    type: 'object',
    required: ['id', 'status', 'summary'],
    properties: {
      id: { type: 'string' },
      status: { type: 'string', enum: ['done', 'partial', 'not_done', 'not_a_gap'] },
      summary: { type: 'string', description: 'what the owner now sees and how you verified it' },
      tests: { type: 'array', items: { type: 'string' } },
      remaining: { type: 'string', description: 'what is missing, when not done' },
    },
  },
}
const CHECKS = {
  type: 'object',
  properties: {
    lint: { type: 'string' },
    typecheck: { type: 'string' },
    unit: { type: 'string' },
    playwright: { type: 'string' },
    i18n: { type: 'string' },
  },
}
const IMPL_SCHEMA = {
  type: 'object',
  required: ['base_sha', 'head_sha', 'gaps', 'checks'],
  properties: {
    base_sha: { type: 'string' },
    head_sha: { type: 'string' },
    gaps: GAP_RESULT,
    reference_issues: { type: 'array', items: { type: 'string' } },
    checks: CHECKS,
    cross_package: {
      type: 'array',
      items: { type: 'string' },
      description: 'edits in files another package owns, and anything another package must know',
    },
    notes_for_lead: { type: 'array', items: { type: 'string' } },
  },
}
const REVIEW_SCHEMA = {
  type: 'object',
  required: ['findings'],
  properties: {
    gap_verdicts: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'verdict'],
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['fixed', 'partly', 'not_fixed', 'regressed', 'not_checked'] },
          note: { type: 'string' },
        },
      },
    },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'problem', 'evidence'],
        properties: {
          gap_id: { type: 'string' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          problem: { type: 'string' },
          evidence: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
      },
    },
    not_checked: { type: 'array', items: { type: 'string' } },
  },
}
const FIX_SCHEMA = {
  type: 'object',
  required: ['head_sha', 'findings', 'checks'],
  properties: {
    head_sha: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['problem', 'action', 'note'],
        properties: {
          problem: { type: 'string' },
          action: { type: 'string', enum: ['fixed', 'rejected', 'deferred'] },
          note: { type: 'string' },
        },
      },
    },
    gaps: GAP_RESULT,
    checks: CHECKS,
    notes_for_lead: { type: 'array', items: { type: 'string' } },
  },
}

const implementPrompt = (step, index) => `You are implementing one step of a package of UI fidelity fixes in the Lonora web app (React in a pnpm monorepo, with a FastAPI backend).

${common}

Your step: "${step.name}" (step ${index + 1} of ${P.steps.length}). Its gaps: ${step.gaps.join(', ')}.
${index > 0 ? `Earlier steps of this package (${P.steps.slice(0, index).map((s) => s.name).join(', ')}) are already committed on this branch. Read \`git log --oneline ${BASE}..HEAD\` first, so that you build on them and do not redo them.` : ''}

How to work

1. Record \`git rev-parse HEAD\` as your base.
2. Look before you change. For each gap, find the surface in the reference (grep it, then run it with openRef) and in the app (openApp on your server). The audit entry says where. The auditor's suggested fix was written before anyone tried it: check it against the reference and the code, and take a better design when you see one. Several entries can describe one defect; fix a defect once.
3. Where behaviour changes, write the test first and watch it fail.
4. Implement, following the rules in the brief.
5. Rebuild with serve.sh and look at the result at phone and desktop size, dark and light, next to the reference. For motion, measure it (sample rects or computed styles over frames) instead of guessing. Save before and after screenshots for visual gaps.
6. Commit each logical change.
7. Before you finish, run lint, the full type check, the unit tests and the Playwright specs that cover what you changed, and the catalog extraction with no missing Arabic. Fix what you broke.

Do not fake a fix. If a gap cannot be done properly in this step (the audit was wrong, an owner decision or a money-safety rule forbids it, or it needs a server change too large for this step), leave it and say exactly why. Report a partly done gap as partial, with what is missing.

Your final message is data for the lead, not prose for a person: return the structured result. base_sha and head_sha are full commit hashes. In checks, give each command's real outcome (for example "pass", or the failing test names).`

const stepFacts = (step, impl) => `Step under review: "${step.name}". Its gaps: ${step.gaps.join(', ')}.
The step's commits, in the worktree: \`git log --oneline ${impl.base_sha}..${impl.head_sha}\`.
The implementer's report (claims to verify, not facts):
${JSON.stringify({ gaps: impl.gaps, reference_issues: impl.reference_issues, cross_package: impl.cross_package, notes_for_lead: impl.notes_for_lead, checks: impl.checks })}`

const browserReviewPrompt = (step, impl) => `You are reviewing one step of a package of UI fidelity fixes in the Lonora web app. You check the result in the browser against the reference prototype. You do not edit code and you do not commit.

${common}

${stepFacts(step, impl)}

What to do

1. Run \`${FX}/serve.sh ${P.pkg}\` so the server serves the current code.
2. For every gap in the step, whatever status the implementer claims: open the surface in the reference and in the app, at phone (390x844) and desktop (1280x800) size, dark and light where the look is involved. Compare containers, spacing, radii, colours, type, Arabic wording, the order of items, what a tap does, where Back goes, and motion (measure durations and easing: sample over frames, or read the computed transition and animation). Try the obvious edge cases: English as well as Arabic, the keyboard (Tab, Enter, Esc), reduced motion, an empty state, a long name.
3. Look for regressions beside the change: the other controls of the same screen, and neighbouring screens that share the component.
4. Check that the owner decisions hold (the brief lists what must not come back) and that nothing invented is shown (fake data, placeholder numbers).

Be specific and sceptical: a claim counts only if you saw it. If you could not check something, list it under not_checked; do not guess. Where the result matches the reference, or is clearly better and clean, do not report matters of taste. The reference can be wrong: if the app deliberately does the sound thing where the reference has a bug, that is not a finding.

Save evidence screenshots in ${FX}/${P.pkg}/shots/ with a \`review-\` prefix and name them in the evidence.

Return the structured result: a verdict for every gap of the step, and the findings (each with what is wrong, the evidence, and what would fix it).`

const codeReviewPrompt = (step, impl) => `You are reviewing the code of one step of a package of UI fidelity fixes in the Lonora web app. You read the diff and the code around it. You do not edit code and you do not commit. Another reviewer is checking the result in the browser at the same time: do not start or restart the server and do not run Playwright. You may run lint, type checks and node unit tests.

${common}

${stepFacts(step, impl)}

Read \`git diff ${impl.base_sha}..${impl.head_sha}\` and enough of the surrounding code to judge it. Check, in this order:

1. Correctness: logic errors, races, leaks (listeners, timers or observers that are not cleaned up), state that can go stale, broken RTL or LTR, broken keyboard or focus handling, anything that breaks when the data is empty, long or slow to arrive.
2. Money safety and owner decisions, as listed in the brief. Any change that touches trading, authority, approvals or the brake gets a careful read: its behaviour must be unchanged unless the gap says otherwise.
3. Cleanliness, as the brief defines it: code copied or transliterated from the reference prototype; hex colours, one-off sizes, Tailwind utilities, \`.legacy-surface\`, shadcn or Base UI primitives, or lucide in new code; logic duplicated where a helper exists; speculative options or abstractions; dead code, unused imports, CSS rules or catalog strings left behind; comments that narrate the change; changes that no gap in this step explains.
4. Text: every owner-visible string goes through Lingui, the Arabic is present and uses the reference's wording, and no msgid carries two meanings.
5. Tests: is there a test that fails without the change? Was any test skipped, deleted or weakened?
6. Server changes, if any: validation, authorisation (owner-only routes stay owner-only), no secrets in responses or logs, pytest coverage.

Report only what you can point to: the file and line, and why it is wrong. No style opinions that Biome and the surrounding code do not back.

Return the structured result: the findings, and a verdict per gap where the code alone lets you judge it.`

const fixPrompt = (step, impl, reviews) => `You are finishing one step of a package of UI fidelity fixes in the Lonora web app. Two reviewers checked it: one in the browser against the reference, one by reading the code. Their findings are below.

${common}

Step: "${step.name}". Its gaps: ${step.gaps.join(', ')}.
The step's commits so far: \`git log --oneline ${impl.base_sha}..HEAD\` in the worktree.
The implementer's report:
${JSON.stringify({ gaps: impl.gaps, notes_for_lead: impl.notes_for_lead })}

Browser reviewer:
${JSON.stringify(reviews.browser)}

Code reviewer:
${JSON.stringify(reviews.code)}

For each finding, first check that it is real: reviewers make mistakes, so reproduce it or read the code. Fix every real one properly, with a test where behaviour was wrong. If a finding is wrong, or fixing it would go against the reference's behaviour, an owner decision or a rule in the brief, reject it and say why in a sentence or two. Gaps that a reviewer judged partly fixed, not fixed or regressed are yours to complete, unless the implementer's reason for leaving them still holds.

Then run the checks again (lint, the full type check, unit tests, the Playwright specs that cover the change, catalogs with no missing Arabic), rebuild, look at the result once more in the browser, and commit.

Your final message is data for the lead: return the structured result, with one entry per finding in the order given (browser reviewer first), the final status of each gap of the step, and the real outcome of each check.`

const steps = []
for (let index = 0; index < P.steps.length; index++) {
  const step = P.steps[index]
  const tag = `${P.pkg}:${step.name}`
  const impl = await agent(implementPrompt(step, index), {
    label: `${tag}:implement`,
    phase: 'Implement',
    model: 'opus',
    schema: IMPL_SCHEMA,
  })
  if (!impl) {
    log(`${tag}: the implementer returned nothing; moving on`)
    steps.push({ name: step.name, error: 'implementer returned nothing' })
    continue
  }
  const [browser, code] = await parallel([
    () => agent(browserReviewPrompt(step, impl), { label: `${tag}:review-browser`, phase: 'Review', model: 'sonnet', schema: REVIEW_SCHEMA }),
    () => agent(codeReviewPrompt(step, impl), { label: `${tag}:review-code`, phase: 'Review', model: 'sonnet', schema: REVIEW_SCHEMA }),
  ])
  const open = [browser, code].filter(Boolean)
  const needsFix =
    open.some((r) => r.findings.length > 0 || (r.gap_verdicts ?? []).some((v) => v.verdict !== 'fixed' && v.verdict !== 'not_checked')) ||
    impl.gaps.some((g) => g.status === 'partial')
  let fix = null
  if (needsFix) {
    fix = await agent(fixPrompt(step, impl, { browser, code }), {
      label: `${tag}:fix`,
      phase: 'Fix',
      model: 'opus',
      schema: FIX_SCHEMA,
    })
  }
  log(`${tag}: ${impl.gaps.filter((g) => g.status === 'done').length}/${step.gaps.length} done by the implementer, ${open.reduce((n, r) => n + r.findings.length, 0)} review findings${fix ? `, ${fix.findings.filter((f) => f.action === 'fixed').length} fixed` : ''}`)
  steps.push({ name: step.name, impl, browser, code, fix })
}
return { pkg: P.pkg, steps }