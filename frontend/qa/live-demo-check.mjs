// Live PostgreSQL browser verification. No fixtures, interception, or fabricated responses.
// Uses the installed Chromium CDP endpoint; no browser/dependency download.
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:5175'
const batch = process.env.QA_BATCH
if (!batch) throw new Error('Use backend/scripts/verify_demo.py to create an isolated QA batch.')
const cdp = process.env.QA_CDP_URL || 'http://127.0.0.1:9223'
const out = fileURLToPath(new URL('../../docs/screenshots/live-demo/', import.meta.url))
await mkdir(out, { recursive: true })
const page = await (await fetch(cdp + '/json/new?about:blank', { method: 'PUT' })).json()
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
const credentials = JSON.parse(
  await readFile(process.env.QA_CREDENTIALS_FILE || '/tmp/sentinel-live-credentials.json', 'utf8'),
)
const apiBase = process.env.QA_API_URL || 'http://127.0.0.1:8002/api/v1'
const checks = []
function assert(value, message) {
  if (!value) throw new Error(message)
  checks.push(message)
}
async function clickText(text, selector = 'button') {
  await waitFor(
    `[...document.querySelectorAll(${JSON.stringify(selector)})].some(e => e.textContent.trim() === ${JSON.stringify(text)})`,
  )
  await evaluate(
    `[...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.textContent.trim() === ${JSON.stringify(text)}).click()`,
  )
}
async function fill(selector, value) {
  await evaluate(
    `(() => {const e=document.querySelector(${JSON.stringify(selector)}); const setter=Object.getOwnPropertyDescriptor(e instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,'value').set; setter.call(e,${JSON.stringify(value)}); e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));})()`,
  )
}
async function go(path) {
  await call('Page.navigate', { url: base + path })
  await waitFor(
    "document.querySelector('h1') && !document.body.innerText.includes('Loading workspace…')",
  )
}
async function api(path, options = {}) {
  return evaluate(
    `(async () => {const r=await fetch(${JSON.stringify(apiBase + path)}, { ...${JSON.stringify(options)},headers:{'Authorization':'Bearer '+sessionStorage.getItem('sentinelai-token'),'Content-Type':'application/json'}}); if(!r.ok)throw new Error('API '+r.status); return r.json()})()`,
  )
}
async function screenshot(name) {
  await delay(300)
  const image = await call('Page.captureScreenshot', { format: 'png' })
  await writeFile(out + name + '.png', Buffer.from(image.data, 'base64'))
}
async function layout(name, width, height) {
  await call('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await delay(300)
  const result = await evaluate(
    `({viewport: innerWidth, body:document.body.scrollWidth, main:document.querySelector('main').scrollWidth, mainWidth:document.querySelector('main').clientWidth, h1:document.querySelectorAll('h1').length, controls:[...document.querySelectorAll('input,textarea,select')].filter(e=>!e.labels?.length && !e.getAttribute('aria-label')).length})`,
  )
  if (result.main > result.mainWidth + 1) {
    console.log(
      'Overflow',
      result,
      await evaluate(
        `[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth).slice(0,15).map(e=>({tag:e.tagName, cls:e.className,text:e.textContent.slice(0,60),width:e.getBoundingClientRect().width}))`,
      ),
    )
    await screenshot('overflow-debug')
  }
  assert(
    result.body <= result.viewport + 1 && result.main <= result.mainWidth + 1,
    name + ': no page-level horizontal overflow',
  )
  assert(result.h1 >= 1 && result.controls === 0, name + ': headings and named form controls')
  await screenshot(name)
}
try {
  await call('Runtime.enable')
  await call('Page.enable')
  await call('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await go('/login')
  await fill('#email', credentials.email)
  await fill('#password', credentials.password)
  await clickText('Sign in')
  await waitFor("document.querySelector('h1')?.textContent === 'Dashboard'")
  await waitFor("document.body.innerText.includes('Transactions monitored')")
  const dashboard = await api('/workspace/dashboard')
  assert(
    await evaluate(
      `document.body.innerText.includes(${JSON.stringify(dashboard.transactions.toLocaleString())})`,
    ),
    'Dashboard count matches real API',
  )
  const navigation = await evaluate(
    `[...document.querySelector('[aria-label="Primary navigation"]').querySelectorAll('a')].map(a=>a.textContent.trim())`,
  )
  assert(
    JSON.stringify(navigation) ===
      JSON.stringify(['Dashboard', 'Alerts', 'Investigations', 'Transactions']),
    'Only four primary destinations',
  )
  await evaluate("document.querySelector('#explore-demo').open=true")
  const scenarios = (await api('/demo/scenarios')).items.filter((s) => s.batch === batch)
  assert(scenarios.length === 5, 'Five stored isolated QA scenarios')
  await screenshot('dashboard-desktop')
  // Each scenario is followed from its rendered link, not a manually entered UUID.
  for (const scenario of scenarios) {
    await go('/')
    await waitFor("document.querySelector('#explore-demo')")
    await evaluate("document.querySelector('#explore-demo').open=true")
    await waitFor(
      `document.querySelector('a[href="/transactions/${scenario.transaction_id}?connected=${scenario.account_id}"]')`,
    )
    await evaluate(
      `document.querySelector('a[href="/transactions/${scenario.transaction_id}?connected=${scenario.account_id}"]').click()`,
    )
    await waitFor("document.body.innerText.includes('What influenced the model score?')")
    await waitFor("document.querySelector('[role=img]')")
    assert(
      await evaluate(`location.pathname.endsWith(${JSON.stringify(scenario.transaction_id)})`),
      scenario.key + ': scenario opens the stored transaction',
    )
    const item = await api('/workspace/transactions/' + scenario.transaction_id)
    assert(
      item.risk?.explanation?.contributions.length > 0,
      scenario.key + ': persisted model and SHAP assessment',
    )
    const graph = await api(
      `/graph/accounts/${scenario.account_id}?hops=2&as_of_step=${item.transaction.step + 1}`,
    )
    assert(
      graph.nodes.length > 1 && graph.edges.length > 0,
      scenario.key + ': actual connected accounts and transfers',
    )
    if (scenario.key === 'redistribution') await screenshot('redistribution-graph')
  }
  await go('/alerts')
  await waitFor("document.querySelector('tbody tr')")
  assert(
    await evaluate("document.body.innerText.includes('Demonstration rule')"),
    'Inbox labels scenario rules separately',
  )
  await screenshot('alert-inbox')
  // Complete the linked-activity scenario with all five supporting payments.
  const linked = scenarios.find((s) => s.key === 'linked')
  await go(`/transactions/${linked.transaction_id}`)
  await waitFor("document.body.innerText.includes('What influenced the model score?')")
  if (
    await evaluate(
      "[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Investigate')",
    )
  )
    await clickText('Investigate')
  else await clickText('Open investigation →', 'a')
  await waitFor(
    "location.pathname.startsWith('/cases/') && document.body.innerText.includes('Supporting evidence')",
  )
  const caseId = await evaluate("location.pathname.split('/').pop()")
  const linkedContext = await api(`/workspace/cases/${caseId}`)
  assert(linkedContext.activities.length === 5, 'Linked case contains five actual payments')
  await evaluate("document.querySelector('#activity select').focus()")
  await call('Input.dispatchKeyEvent', {
    type: 'keyDown',
    key: 'End',
    code: 'End',
    windowsVirtualKeyCode: 35,
  })
  await call('Input.dispatchKeyEvent', {
    type: 'keyUp',
    key: 'End',
    code: 'End',
    windowsVirtualKeyCode: 35,
  })
  const lastAmount = Number(linkedContext.activities.at(-1).transaction.amount).toLocaleString(
    'en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 },
  )
  await waitFor(
    `document.querySelector('#activity h2')?.textContent.includes(${JSON.stringify(lastAmount)})`,
  )
  assert(true, 'Keyboard payment selection updates the transaction context')
  const again = await api(`/workspace/alerts/${linked.alert_id}/investigate`, { method: 'POST' })
  assert(again.case_id === caseId && !again.created, 'Repeated Investigate reuses the case')
  await waitFor("document.querySelector('[role=img]')")
  await layout('workspace-desktop', 1440, 1000)
  await layout('workspace-tablet', 768, 1024)
  await layout('workspace-mobile', 390, 844)
  await evaluate('document.querySelector(\'[aria-label="Open navigation"]\').click()')
  await waitFor("document.querySelector('[role=dialog]')")
  assert(
    await evaluate("document.querySelector('[role=dialog]').contains(document.activeElement)"),
    'Mobile navigation traps keyboard focus',
  )
  await call('Input.dispatchKeyEvent', {
    type: 'keyDown',
    key: 'Escape',
    code: 'Escape',
    windowsVirtualKeyCode: 27,
  })
  await call('Input.dispatchKeyEvent', {
    type: 'keyUp',
    key: 'Escape',
    code: 'Escape',
    windowsVirtualKeyCode: 27,
  })
  await call('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  })
  await clickText('Save connected accounts')
  await waitFor("document.querySelector('#supporting').innerText.includes('Connected accounts')")
  await clickText('Save account history')
  await waitFor("document.querySelector('#supporting').innerText.includes('Account history')")
  await fill(
    '#analyst-note',
    'Synthetic linked transfers reviewed with stored account and network evidence.',
  )
  await clickText('Save note')
  await waitFor(
    "document.querySelector('#supporting').innerText.includes('Synthetic linked transfers reviewed')",
  )
  const evidence = await api(`/cases/${caseId}/evidence?limit=100`)
  const graphEvidence = evidence.items.find((e) => e.evidence_type === 'graph_neighborhood')
  assert(
    graphEvidence?.evidence_payload.as_of_step ===
      Math.max(...linkedContext.activities.map((a) => a.transaction.step)) + 1,
    'Saved network evidence uses the same event cutoff as the workspace',
  )
  assert(
    evidence.items.some((e) => e.evidence_type === 'historical_stats') &&
      evidence.items.some((e) => e.evidence_type === 'analyst_note'),
    'Account history and analyst note persist as linked evidence',
  )
  const existing = await api(`/workspace/cases/${caseId}`)
  assert(existing.case.status === 'investigating', 'Fresh QA case is awaiting investigation')
  if (!existing.run_id) await clickText('Start AI investigation')
  await waitFor("document.body.innerText.includes('Mock AI report')")
  await waitFor(
    "document.body.innerText.includes('Approve report') || document.body.innerText.includes('Reviewed report')",
  )
  const context = await api(`/workspace/cases/${caseId}`)
  const repeated = await api(`/workspace/cases/${caseId}/report`, { method: 'POST' })
  assert(context.run_id === repeated.run_id, 'Repeated report start reuses the run')
  let run = await api('/investigations/' + context.run_id)
  assert(run.model_provider === 'mock', 'Mock AI provider is explicit in the real response')
  if (run.status === 'awaiting_approval') {
    await clickText('Approve report')
    await clickText('Confirm report approval')
    await waitFor("document.body.innerText.includes('Reviewed report')")
  }
  const before = await api(`/cases/${caseId}`)
  assert(before.status === 'investigating', 'Report approval does not resolve the case')
  await evaluate("document.querySelector('#report').scrollIntoView()")
  await screenshot('reviewed-mock-report')
  await evaluate("document.querySelector('#decision').scrollIntoView()")
  // Choose Dismissed with the actual accessible select and confirmation dialog.
  await evaluate('document.querySelector(\'[aria-label="Case decision"]\').click()')
  await waitFor(
    "[...document.querySelectorAll('[role=option]')].some(e=>e.textContent==='Dismissed')",
  )
  await evaluate(
    "[...document.querySelectorAll('[role=option]')].find(e=>e.textContent==='Dismissed').click()",
  )
  await fill(
    '#rationale',
    'Synthetic demonstration reviewed during live browser verification; this pattern is not proof of crime.',
  )
  await clickText('Review decision')
  await waitFor("document.querySelector('[role=dialog]')")
  await clickText('Record decision')
  await waitFor("!document.querySelector('#rationale')")
  const after = await api(`/cases/${caseId}`)
  assert(after.status === 'resolved', 'Separate authorized human decision resolves the case')
  await screenshot('human-case-decision')
  assert(errors.length === 0, 'No browser runtime exceptions')
  await writeFile(
    out + 'verification.json',
    JSON.stringify(
      {
        date: new Date().toISOString(),
        source: 'Real PostgreSQL backend; no API fixtures',
        batch,
        dashboard,
        checks,
        browserErrors: errors,
        caseId,
        runId: context.run_id,
      },
      null,
      2,
    ),
  )
  console.log(
    JSON.stringify(
      { passed: checks.length, screenshots: out, transactions: dashboard.transactions, checks },
      null,
      2,
    ),
  )
} finally {
  await fetch(cdp + '/json/close/' + page.id)
  ws.close()
}
