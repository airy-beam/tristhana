export const meta = {
  name: 'deep-review',
  description: 'Multi-lens review of current changes (correctness, Ashtanga domain, time/privacy/i18n, architecture/security), each finding adversarially verified',
  whenToUse: 'Before merging a feature-sized change. Pass an optional target (e.g. "main...HEAD", a PR number, or file paths) as args.',
  phases: [
    { title: 'Review', detail: 'one reviewer per lens' },
    { title: 'Verify', detail: 'a skeptic tries to refute each finding' },
  ],
}

const target = (typeof args === 'string' && args.trim()) ? args.trim() : 'the uncommitted changes plus the last commit (git diff HEAD~1)'

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['blocker', 'should-fix', 'nit'] },
          summary: { type: 'string' },
          failure_scenario: { type: 'string' },
          suggested_fix: { type: 'string' },
        },
        required: ['file', 'severity', 'summary', 'failure_scenario'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reasoning: { type: 'string' },
  },
  required: ['refuted', 'reasoning'],
}

const LENSES = [
  { key: 'correctness', agentType: 'code-reviewer',
    focus: 'logic bugs, edge cases, error handling, missing or weak tests, simplicity' },
  { key: 'domain', agentType: 'ashtanga-expert',
    focus: 'Ashtanga correctness: sequences, practice-length presets, rest/moon/ladies days, progression, terminology, supportive tone' },
  { key: 'time-privacy-i18n', agentType: 'code-reviewer',
    focus: 'ONLY time zones/dates (naive datetimes, offsets, DST, local dates), privacy (ladies holiday, diary, check-ins, teacher projections, encryption, authorization policies) and i18n (hard-coded strings, en/ru keys, plurals)' },
  { key: 'architecture-security', agentType: 'code-reviewer',
    focus: 'ONLY hexagonal layering (aiogram outside bots/telegram, logic in handlers, domain I/O), API design, responsiveness (callback answered first, N+1 queries, heavy imports), and security (initData/HMAC, webhook secret, secrets, input validation)' },
]

const results = await pipeline(
  LENSES,
  lens => agent(
    `Review ${target} in this repository through the "${lens.key}" lens: ${lens.focus}. ` +
    `Report only real, specific problems with file and line. An empty list is a valid answer.`,
    { label: `review:${lens.key}`, phase: 'Review', schema: FINDINGS, agentType: lens.agentType },
  ),
  (review, lens) => parallel((review?.findings || []).map(f => () =>
    agent(
      `A reviewer claims this problem in ${f.file}${f.line ? ':' + f.line : ''} (${f.severity}): ${f.summary}\n` +
      `Failure scenario: ${f.failure_scenario}\n` +
      `Read the code and try to REFUTE it: is it real, reachable and correctly described? ` +
      `Default to refuted=true if you cannot confirm it from the code.`,
      { label: `verify:${lens.key}`, phase: 'Verify', schema: VERDICT },
    ).then(v => ({ ...f, lens: lens.key, verdict: v })),
  )),
)

const all = results.flat().filter(Boolean)
const confirmed = all.filter(f => f.verdict && !f.verdict.refuted)
const order = { blocker: 0, 'should-fix': 1, nit: 2 }
confirmed.sort((a, b) => order[a.severity] - order[b.severity])
log(`${confirmed.length} confirmed of ${all.length} reported findings`)
return { confirmed, refuted_count: all.length - confirmed.length }
