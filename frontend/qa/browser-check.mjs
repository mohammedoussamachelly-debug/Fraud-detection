// Browser-only synthetic fixtures. Never imported by application code or bundled.
// Uses the installed Chromium CDP endpoint; no browser/dependency download.
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:5174'
const out = fileURLToPath(new URL('../../docs/screenshots/', import.meta.url))
await mkdir(out, { recursive: true })
const page = await (
  await fetch('http://127.0.0.1:9223/json/new?about:blank', { method: 'PUT' })
).json()
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
let id = 0
const pending = new Map()
const errors = []
ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const p = pending.get(message.id)
    pending.delete(message.id)
    message.error ? p.reject(message.error) : p.resolve(message.result)
  }
  if (message.method === 'Runtime.exceptionThrown')
    errors.push(
      message.params.exceptionDetails.text +
        ': ' +
        (message.params.exceptionDetails.exception?.description || ''),
    )
})
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const key = ++id
    const timeout = setTimeout(() => {
      pending.delete(key)
      reject(new Error('CDP timed out: ' + method))
    }, 25000)
    pending.set(key, {
      resolve: (value) => {
        clearTimeout(timeout)
        resolve(value)
      },
      reject: (error) => {
        clearTimeout(timeout)
        reject(error)
      },
    })
    ws.send(JSON.stringify({ id: key, method, params }))
  })
}
const delay = (ms) => new Promise((r) => setTimeout(r, ms))
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (result.exceptionDetails)
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text)
  return result.result.value
}
async function waitFor(expression) {
  for (let i = 0; i < 100; i++) {
    if (await evaluate(`Boolean(${expression})`)) return
    await delay(100)
  }
  throw new Error('Timed out: ' + expression)
}
function fixtureSetup() {
  const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
  const stamp = '2026-11-07T10:30:00Z'
  const user = {
    id: uuid(1),
    email: 'qa-analyst@sentinelai.test',
    role: 'senior_analyst',
    is_active: true,
  }
  const alerts = Array.from({ length: 31 }, (_, i) => ({
    id: uuid(i + 10),
    transaction_id: uuid(100),
    risk_score_id: uuid(200),
    alert_type: i % 2 ? 'rule_threshold' : 'model_threshold',
    severity: ['critical', 'high', 'medium', 'low'][i % 4],
    status: 'open',
    created_at: stamp,
  }))
  const cases = [
    {
      id: uuid(300),
      status: 'pending_review',
      priority: 'high',
      assigned_analyst_id: user.id,
      created_at: stamp,
      updated_at: stamp,
      closed_at: null,
      alerts: [{ alert_id: uuid(10), linked_at: stamp }],
    },
  ]
  const transaction = {
    id: uuid(100),
    external_ref: 'QA-PAYSIM-001',
    step: 42,
    occurred_at: stamp,
    type: 'TRANSFER',
    amount: '128450.50',
    origin_account_id: uuid(400),
    dest_account_id: uuid(401),
    origin_balance_before: '130000.00',
    origin_balance_after: '1549.50',
    dest_balance_before: '0',
    dest_balance_after: '128450.50',
  }
  const accounts = [
    {
      id: uuid(400),
      external_ref: 'QA-ORIGIN',
      account_type: 'customer',
      first_seen_at: stamp,
      created_at: stamp,
    },
    {
      id: uuid(401),
      external_ref: 'QA-RECIPIENT',
      account_type: 'customer',
      first_seen_at: stamp,
      created_at: stamp,
    },
  ]
  const explanation = {
    base_value: -1.4,
    contributions: [
      { feature: 'amount', value: 128450.5, shap_contribution: 0.7, direction: 'increases_risk' },
      {
        feature: 'origin_balance_after',
        value: 1549.5,
        shap_contribution: -0.2,
        direction: 'decreases_risk',
      },
    ],
  }
  const score = {
    id: uuid(200),
    transaction_id: transaction.id,
    risk_score: 0.94,
    risk_level: 'high',
    model_version: 'qa-fixture-v1',
    threshold_used: 0.8,
    explanation,
    scored_at: stamp,
  }
  const evidence = [
    {
      id: uuid(500),
      case_id: uuid(300),
      evidence_type: 'transaction',
      source_reference: `transaction:${transaction.id}`,
      evidence_payload: transaction,
      created_at: stamp,
    },
  ]
  const disclaimer = 'Structural signals only; these are not proof of fraud.'
  const report = {
    summary: 'Synthetic QA fixture report for interface verification.',
    hypotheses: [
      {
        text: 'Review this synthetic transfer.',
        confidence: 'medium',
        evidence_refs: [evidence[0].source_reference],
      },
    ],
    uncertainties: ['Synthetic scenario only.'],
    recommended_next_step: 'Review transaction evidence.',
    model_provider: 'mock',
    model_name: 'mock-deterministic-v1',
    is_mock: true,
    evidence_refs: [evidence[0].source_reference],
  }
  const run = {
    run_id: uuid(600),
    case_id: uuid(300),
    started_by_user_id: user.id,
    status: 'awaiting_approval',
    model_provider: 'mock',
    model_name: 'mock-deterministic-v1',
    prompt_version: 'v1',
    revision_count: 0,
    review_feedback: [],
    draft_report: report,
    final_report: null,
    error: null,
    started_at: stamp,
    completed_at: stamp,
    steps: [
      {
        id: uuid(700),
        node_name: 'evidence_collection',
        attempt: 1,
        status: 'completed',
        tool_calls: [
          {
            tool: 'get_transaction',
            args_summary: { id: transaction.id },
            result_ref: evidence[0].source_reference,
            duration_ms: 12,
          },
        ],
        output: { evidence_count: 1 },
        error: null,
        started_at: stamp,
        completed_at: stamp,
      },
    ],
    evidence_refs: [
      {
        id: uuid(800),
        evidence_type: 'transaction',
        source_reference: evidence[0].source_reference,
        summary: 'Synthetic transfer.',
        collected_by_node: 'evidence_collection',
        created_at: stamp,
      },
    ],
  }
  window.__qa = {
    uuid,
    alerts,
    cases,
    transaction,
    accounts,
    evidence,
    run,
    requests: [],
    mode: sessionStorage.getItem('qa-mode') || 'normal',
  }
  const paginate = (items, q) => ({
    items: items.slice(
      Number(q.get('offset') || 0),
      Number(q.get('offset') || 0) + Number(q.get('limit') || 25),
    ),
    total: items.length,
    limit: Number(q.get('limit') || 25),
    offset: Number(q.get('offset') || 0),
  })
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.origin)
    if (!url.pathname.startsWith('/api/v1')) return originalFetch(input, init)
    const p = url.pathname.slice('/api/v1'.length),
      q = url.searchParams,
      method = init?.method || 'GET'
    window.__qa.requests.push({ path: p, query: url.search, method })
    const response = (data, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(data), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    if (window.__qa.mode === 'unauthorized' && p !== '/auth/me')
      return response({ detail: 'QA expired session' }, 401)
    if (window.__qa.mode === 'error' && p !== '/auth/me')
      return response({ detail: 'QA simulated service outage' }, 503)
    if (window.__qa.mode === 'loading' && p !== '/auth/me') return new Promise(() => {})
    if (p === '/auth/login')
      return response({
        access_token: 'synthetic-qa-token',
        token_type: 'bearer',
        expires_in: 1800,
      })
    if (p === '/auth/me') return response(user)
    if (p === '/alerts')
      return response(
        paginate(
          window.__qa.mode === 'empty'
            ? []
            : alerts.filter(
                (a) =>
                  (!q.get('status') || a.status === q.get('status')) &&
                  (!q.get('severity') || a.severity === q.get('severity')) &&
                  (!q.get('created_from') || a.created_at.slice(0, 10) >= q.get('created_from')) &&
                  (!q.get('created_to') || a.created_at.slice(0, 10) <= q.get('created_to')),
              ),
          q,
        ),
      )
    if (p.startsWith('/alerts/')) {
      const a = alerts.find((a) => a.id === p.split('/')[2])
      if (method === 'PATCH') Object.assign(a, JSON.parse(init.body))
      return response(a)
    }
    if (p === '/transactions') return response(paginate([transaction], q))
    if (p.endsWith('/risk-score')) return response(score)
    if (p.endsWith('/explanation')) return response(explanation)
    if (p.startsWith('/transactions/')) return response(transaction)
    if (p === '/accounts')
      return response(
        paginate(
          accounts.filter(
            (a) => !q.get('external_ref') || a.external_ref === q.get('external_ref'),
          ),
          q,
        ),
      )
    if (p.startsWith('/accounts/')) return response(accounts.find((a) => a.id === p.split('/')[2]))
    if (p.startsWith('/graph/accounts/')) {
      const accountId = p.split('/')[3],
        as_of_step = q.has('as_of_step') ? Number(q.get('as_of_step')) : null
      if (p.endsWith('/metrics'))
        return response({
          account_id: accountId,
          as_of_step,
          incoming_transaction_count: 0,
          outgoing_transaction_count: 1,
          unique_senders: 0,
          unique_recipients: 1,
          fan_in_pattern: false,
          fan_out_pattern: false,
          velocity_window_steps: 24,
          velocity_count: 1,
          truncated: false,
          disclaimer,
        })
      if (p.endsWith('/fund-flow'))
        return response({
          source_account_id: accountId,
          as_of_step,
          max_hops: 3,
          max_branches: 5,
          paths: [
            {
              steps: [
                {
                  transaction_id: transaction.id,
                  transaction_external_ref: transaction.external_ref,
                  from_account_id: accounts[0].id,
                  to_account_id: accounts[1].id,
                  amount: transaction.amount,
                  step: 42,
                },
              ],
            },
          ],
          truncated: false,
          disclaimer,
        })
      if (p.endsWith('/transactions'))
        return response({ ...paginate([{ ...transaction, direction: 'outgoing' }], q), as_of_step })
      return response({
        center_account_id: accountId,
        hops: Number(q.get('hops') || 2),
        as_of_step,
        nodes: accounts,
        edges: [
          {
            source: accounts[0].id,
            target: accounts[1].id,
            transaction_id: transaction.id,
            external_ref: transaction.external_ref,
            amount: transaction.amount,
            step: 42,
            type: 'TRANSFER',
          },
        ],
        cycles: [],
        truncated: false,
        disclaimer,
      })
    }
    if (p === '/cases') {
      if (method === 'POST') return response(cases[0], 201)
      return response(
        paginate(
          cases.filter((c) => !q.get('status') || c.status === q.get('status')),
          q,
        ),
      )
    }
    if (p.endsWith('/evidence')) {
      if (method === 'POST') {
        const body = JSON.parse(init.body)
        evidence.push({
          id: uuid(501),
          case_id: cases[0].id,
          evidence_type: body.evidence_type,
          source_reference: 'analyst_note:qa',
          evidence_payload: { body: body.body },
          created_at: stamp,
        })
        return response(evidence.at(-1), 201)
      }
      return response(paginate(evidence, q))
    }
    if (p.endsWith('/decision')) {
      if (method === 'POST') {
        window.__qa.decision = {
          id: uuid(900),
          case_id: cases[0].id,
          decided_by_user_id: user.id,
          ...JSON.parse(init.body),
          decided_at: stamp,
        }
        cases[0].status = 'resolved'
        return response(window.__qa.decision, 201)
      }
      return window.__qa.decision
        ? response(window.__qa.decision)
        : response({ detail: 'No decision recorded' }, 404)
    }
    if (p.endsWith('/investigations') && p.startsWith('/cases/'))
      return method === 'POST'
        ? response({ run_id: run.run_id, status: run.status }, 202)
        : response(paginate([run], q))
    if (p.startsWith('/cases/')) {
      if (method === 'PATCH') Object.assign(cases[0], JSON.parse(init.body))
      return response(cases[0])
    }
    if (p.startsWith('/investigations/')) {
      if (p.endsWith('/approve')) {
        run.status = 'approved'
        run.final_report = report
      }
      if (p.endsWith('/reject')) run.status = 'rejected'
      if (p.endsWith('/request-revision')) {
        run.review_feedback.push(JSON.parse(init.body).feedback)
        run.revision_count++
      }
      return response(run)
    }
    return response({ detail: 'No QA fixture for ' + p }, 404)
  }
  document.addEventListener('DOMContentLoaded', () => {
    const label = document.createElement('div')
    label.textContent = 'BROWSER QA · SYNTHETIC FIXTURES'
    label.style.cssText =
      'position:fixed;bottom:0;right:0;z-index:9999;background:#17212b;color:white;font:10px monospace;padding:3px 8px;pointer-events:none'
    document.body.append(label)
  })
}
await call('Page.enable')
await call('Runtime.enable')
const injected = await call('Page.addScriptToEvaluateOnNewDocument', {
  source: `(${fixtureSetup.toString()})()`,
})
async function go(path) {
  await call('Page.navigate', { url: base + path })
  await waitFor("document.querySelector('h1') && !document.querySelector('vite-error-overlay')")
  await delay(450)
}
async function capture(name, width, path) {
  await call('Emulation.setDeviceMetricsOverride', {
    width,
    height: 950,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await go(path)
  const layout = await evaluate(
    '({ width: innerWidth, document: document.documentElement.scrollWidth, heading: document.querySelector("h1")?.textContent })',
  )
  if (layout.document > width) throw new Error('Page overflow: ' + name + JSON.stringify(layout))
  const shot = await call('Page.captureScreenshot', { format: 'png' })
  await writeFile(resolve(out, `${name}-${width}.png`), Buffer.from(shot.data, 'base64'))
  console.log(`${name} ${width}px: ${layout.heading}, no page overflow`)
}
async function click(selector) {
  await waitFor(selector)
  const rect = await evaluate(
    `(() => { const e = ${selector}; if (!e) throw new Error('Missing click target'); e.scrollIntoView({block:'center'}); const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2} })()`,
  )
  await call('Input.dispatchMouseEvent', {
    type: 'mousePressed',
    button: 'left',
    clickCount: 1,
    ...rect,
  })
  await call('Input.dispatchMouseEvent', {
    type: 'mouseReleased',
    button: 'left',
    clickCount: 1,
    ...rect,
  })
}
const button = (text) =>
  `Array.from(document.querySelectorAll('button')).find(e => e.textContent.trim() === ${JSON.stringify(text)})`
async function fill(selector, value) {
  await evaluate(
    `(() => { const e=document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(e, ${JSON.stringify(value)}); e.dispatchEvent(new Event('input', {bubbles:true})); })()`,
  )
}
async function snap(name) {
  const shot = await call('Page.captureScreenshot', { format: 'png' })
  await writeFile(resolve(out, name + '.png'), Buffer.from(shot.data, 'base64'))
}
async function workflows() {
  await call('Emulation.setDeviceMetricsOverride', {
    width: 1280,
    height: 950,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await evaluate('sessionStorage.clear()')
  await go('/login')
  await fill('#email', 'qa-analyst@sentinelai.test')
  await fill('#password', 'qa-fixture-password')
  await click(button('Sign in'))
  await waitFor("document.querySelector('h1')?.textContent === 'Overview'")
  console.log('Browser workflow: login through form passed')
  await click(`document.querySelector('a[href="/alerts?status=open&severity=critical"]')`)
  await waitFor("document.querySelector('tbody tr[tabindex]')")
  await click(`document.querySelector('tbody tr[tabindex]')`)
  await waitFor("document.querySelector('h1')?.textContent.startsWith('Alert ')")
  await click(button('QA-PAYSIM-001'))
  await waitFor("document.querySelector('[role=dialog]')")
  await snap('transaction-panel-1280')
  await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' })
  await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape' })
  await waitFor("!document.querySelector('[role=dialog]')")
  console.log('Browser workflow: alert to transaction panel and Escape passed')
  await go('/alerts/00000000-0000-4000-8000-000000000010')
  await click(button('Create case'))
  await waitFor("document.querySelector('[role=dialog]')")
  await click(
    `Array.from(document.querySelectorAll('[role=dialog] button')).find(e => e.textContent.trim() === 'Create case')`,
  )
  await waitFor("document.querySelector('h1')?.textContent.startsWith('Case ')")
  await click(button('Attach evidence'))
  await waitFor("document.querySelector('#note-body')")
  await fill('#note-body', 'QA: reviewed the transfer and account context.')
  await click(button('Attach'))
  await waitFor(
    "!document.querySelector('[role=dialog]') && document.body.textContent.includes('QA: reviewed')",
  )
  await click(button('Investigations'))
  await waitFor(
    "Array.from(document.querySelectorAll('button')).some(e => e.textContent.trim() === 'Start investigation')",
  )
  await click(button('Start investigation'))
  await waitFor("document.querySelector('h1')?.textContent.startsWith('Investigation ')")
  await click(button('Approve report'))
  await waitFor("document.querySelector('[role=dialog]')")
  await snap('report-confirmation-1280')
  await click(button('Confirm report approval'))
  await waitFor("window.__qa.run.status === 'approved' && !document.querySelector('[role=dialog]')")
  if (
    await evaluate(
      "window.__qa.requests.some(r => r.method === 'POST' && r.path.endsWith('/decision'))",
    )
  )
    throw new Error('Report approval called the case decision endpoint')
  console.log(
    'Browser workflow: create case, add note, start run, approve report separately passed',
  )
  await click(`document.querySelector('a[href^="/cases/"]')`)
  await waitFor("document.querySelector('h1')?.textContent.startsWith('Case ')")
  await click(button('Decision'))
  await waitFor("document.querySelector('#rationale')")
  await fill('#rationale', 'QA: separate human case decision after evidence review.')
  await click(button('Review decision'))
  await waitFor("document.querySelector('[role=dialog]')")
  await snap('case-decision-confirmation-1280')
  await click(button('Record decision'))
  await waitFor(
    "window.__qa.cases[0].status === 'resolved' && !document.querySelector('[role=dialog]')",
  )
  console.log('Browser workflow: authorized final case decision passed')
  await go('/network?account=00000000-0000-4000-8000-000000000400')
  await fill('input[placeholder="All history"]', '0')
  await click(button('Explore'))
  await waitFor(
    "window.__qa.requests.filter(r => r.path.startsWith('/graph') && r.query.includes('as_of_step=0')).length >= 3",
  )
  console.log(
    'Browser workflow: temporal cutoff propagated to graph, metrics, and fund-flow passed',
  )
  for (const mode of ['empty', 'error', 'loading']) {
    await evaluate(`sessionStorage.setItem('qa-mode', '${mode}')`)
    await go('/alerts')
    if (mode === 'empty') await waitFor("document.body.textContent.includes('No alerts match')")
    if (mode === 'error')
      await waitFor("document.body.textContent.includes('QA simulated service outage')")
    if (mode === 'loading') await waitFor("document.querySelectorAll('tbody tr').length === 6")
    await snap('alerts-' + mode + '-1280')
  }
  await evaluate(
    "sessionStorage.removeItem('qa-mode'); localStorage.setItem('sentinelai-theme', 'dark')",
  )
  for (const [name, path] of [
    ['overview', '/'],
    ['network', '/network?account=00000000-0000-4000-8000-000000000400'],
    ['investigation', '/investigations/00000000-0000-4000-8000-000000000600'],
    ['cases', '/cases'],
    ['transactions', '/transactions'],
  ])
    await capture(name + '-dark', 1440, path)
  await call('Emulation.setDeviceMetricsOverride', {
    width: 390,
    height: 950,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await go('/')
  await click(`document.querySelector('button[aria-label="Open navigation"]')`)
  await waitFor("document.querySelector('[role=dialog]')")
  await snap('navigation-dark-390')
  await call('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' })
  await call('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape' })
  await waitFor("!document.querySelector('[role=dialog]')")
  await evaluate("sessionStorage.setItem('qa-mode', 'unauthorized')")
  await go('/alerts')
  await waitFor("document.querySelector('h1')?.textContent === 'Sign in'")
  console.log(
    'Browser workflow: responsive navigation, dark theme, error/empty/loading and expired-session redirect passed',
  )
  await evaluate("sessionStorage.clear(); localStorage.setItem('sentinelai-theme', 'light')")
}
try {
  await go('/login')
  await evaluate("sessionStorage.clear(); localStorage.setItem('sentinelai-theme', 'light')")
  await go('/login')
  for (const width of [1440, 1280, 768, 390]) await capture('login', width, '/login')
  await evaluate("sessionStorage.setItem('sentinelai-token', 'synthetic-qa-token')")
  const routes = process.argv.includes('--all')
    ? [
        ['overview', '/'],
        ['alerts', '/alerts'],
        ['alert-detail', '/alerts/00000000-0000-4000-8000-000000000010'],
        ['transactions', '/transactions'],
        ['transaction-detail', '/transactions/00000000-0000-4000-8000-000000000100'],
        ['cases', '/cases'],
        ['accounts', '/accounts'],
        ['account', '/accounts/00000000-0000-4000-8000-000000000400'],
        ['investigations', '/investigations'],
        ['permission-denied', '/audit-log'],
        ['case', '/cases/00000000-0000-4000-8000-000000000300'],
        ['network', '/network?account=00000000-0000-4000-8000-000000000400'],
        ['investigation', '/investigations/00000000-0000-4000-8000-000000000600'],
      ]
    : [
        ['overview', '/'],
        ['alerts', '/alerts'],
        ['alert-detail', '/alerts/00000000-0000-4000-8000-000000000010'],
      ]
  for (const [name, path] of process.argv.includes('--workflows-only') ? [] : routes)
    for (const width of [1440, 1280, 768, 390]) await capture(name, width, path)
  if (process.argv.includes('--all') || process.argv.includes('--workflows-only')) await workflows()
  if (errors.length) throw new Error(errors.join('\n'))
  console.log('Browser QA completed using explicitly labeled fixtures.')
} finally {
  await call('Page.removeScriptToEvaluateOnNewDocument', { identifier: injected.identifier }).catch(
    () => {},
  )
  ws.close()
  await fetch('http://127.0.0.1:9223/json/close/' + page.id)
}
