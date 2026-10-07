import { expect, test } from '@playwright/test'

const snapshot = {
  cards: { attendances: 120, distinct_customers: 85, resolved_by_ai: 90, escalated: 30, blocked: 7, waiting: 2, in_progress: 4, average_response_ms: 1850, input_tokens: 12000, output_tokens: 4000, cost: .4321 },
  attendances_by_day: [{ day: '2026-10-05', total: 50 }, { day: '2026-10-06', total: 70 }],
  routes: [{ route: 'knowledge', total: 140 }, { route: 'support', total: 60 }, { route: 'knowledge_support', total: 25 }],
  escalation_rate: 25,
  technicians: [{ id: 2, display_name: 'Técnico Plantão', status: 'online', active_chats: 4, attended: 12 }],
}
test.beforeEach(async ({ page }) => {
  await page.route('**/api/auth/me', route => route.fulfill({ json: { id: 1, username: 'Admin', role: 'admin', display_name: 'Administrador' } }))
  await page.route('**/api/health/ready', route => route.fulfill({ json: { degraded: false } }))
  await page.route('**/api/admin/users', route => route.fulfill({ json: [] }))
  await page.route('**/api/auth/presence', route => route.fulfill({ status: 204 }))
  await page.route('**/api/admin/dashboard/details**', route => route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 10 } }))
})
test('indicadores, gráficos e equipe abrem detalhes; teclado mantém foco no modal', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/admin/dashboard?**', route => route.fulfill({ json: snapshot }))
  await page.setViewportSize({ width: 1440, height: 1050 })
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  const tokens = page.getByRole('button', { name: 'Ver detalhes: Tokens utilizados', exact: true })
  await tokens.focus()
  await page.keyboard.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Tokens utilizados', exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('12.000', { exact: true })).toBeVisible()
  await expect(dialog.getByText('R$ 0.4321', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Fechar detalhes' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: 'Voltar ao dashboard' })).toBeFocused()
  await page.screenshot({ path: '../docs/evidence/dashboard/dashboard-detalhes.png', fullPage: true })
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(tokens).toBeFocused()
  await page.getByRole('button', { name: 'Ver detalhes: Conversas sem handoff' }).click()
  await expect(page.getByRole('dialog').getByText(/Não confirma resolução/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '06/10: 70 conversas' }).click()
  await expect(page.getByRole('dialog', { name: 'Conversas em 06/10' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Ver rota: Conhecimento', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('140', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Ver detalhes de Técnico Plantão' }).click()
  await expect(page.getByRole('dialog').getByText('12', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.screenshot({ path: '../docs/evidence/dashboard/dashboard-desktop.png', fullPage: true })
  expect(errors).toEqual([])
})
test('troca de período, atualização e estado vazio', async ({ page }) => {
  const periods: string[] = []
  await page.route('**/api/admin/dashboard?**', route => {
    periods.push(new URL(route.request().url()).searchParams.get('period')!)
    return route.fulfill({ json: periods.at(-1) === '30d' ? { ...snapshot, attendances_by_day: [], routes: [], technicians: [] } : snapshot })
  })
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ver detalhes: Em fila agora' })).toBeVisible()
  await page.getByLabel('Período do dashboard').selectOption('30d')
  await expect(page.getByText('Nenhuma conversa iniciada no período.')).toBeVisible()
  await expect(page.getByText('Nenhuma execução registrada no período.')).toBeVisible()
  await expect(page.getByText('Nenhum técnico cadastrado.')).toBeVisible()
  const before = periods.length
  await page.getByRole('button', { name: 'Atualizar', exact: true }).click()
  await expect.poll(() => periods.length).toBeGreaterThan(before)
  expect(periods).toContain('30d')
})
test('erro formatado e recuperação por tentar novamente', async ({ page }) => {
  let available = false
  await page.route('**/api/admin/dashboard?**', route => available ? route.fulfill({ json: snapshot }) : route.fulfill({ status: 503, json: { detail: { message: 'Indicadores temporariamente indisponíveis' } } }))
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Tentar novamente' })).toBeVisible()
  await expect(page.getByText('[object Object]', { exact: false })).toHaveCount(0)
  available = true
  await page.getByRole('button', { name: 'Tentar novamente' }).click()
  await expect(page.getByRole('button', { name: 'Ver detalhes: Conversas iniciadas' })).toBeVisible()
  await expect(page.locator('.admin-alert')).toHaveCount(0)
})
test('atualização automática mantém o modal aberto e informa falha sem perder a última leitura', async ({ page }) => {
  await page.clock.install()
  let calls = 0
  let available = true
  await page.route('**/api/admin/dashboard?**', route => {
    calls++
    return available ? route.fulfill({ json: snapshot }) : route.fulfill({ status: 503, json: { detail: 'Falha temporária' } })
  })
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ver detalhes: Tokens utilizados' })).toBeVisible()
  await page.getByRole('button', { name: 'Ver detalhes: Tokens utilizados' }).click()
  const before = calls
  await page.clock.fastForward(30_000)
  await expect.poll(() => calls).toBeGreaterThan(before)
  await expect(page.getByRole('dialog', { name: 'Tokens utilizados', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  available = false
  await page.clock.fastForward(30_000)
  await expect(page.getByText(/Exibindo a última leitura/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ver detalhes: Conversas iniciadas' })).toBeVisible()
  available = true
  await page.clock.fastForward(30_000)
  await expect(page.getByText(/Exibindo a última leitura/)).toHaveCount(0)
})
test('layout responsivo sem overflow da página e modal opaco', async ({ page }) => {
  await page.route('**/api/admin/dashboard?**', route => route.fulfill({ json: snapshot }))
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ver detalhes: Conversas iniciadas' })).toBeVisible()
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const labelSize = await page.locator('.dashboard-metric-label').first().evaluate(element => parseFloat(getComputedStyle(element).fontSize))
    expect(labelSize).toBeGreaterThanOrEqual(16)
  }
  await page.getByRole('button', { name: 'Ver detalhes: Conversas iniciadas' }).click()
  const modal = page.getByRole('dialog')
  await expect(modal).toBeVisible()
  expect(await modal.evaluate(element => getComputedStyle(element).backgroundColor)).toBe('rgb(255, 255, 255)')
  const box = await modal.boundingBox()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(390)
  await page.screenshot({ path: '../docs/evidence/dashboard/dashboard-mobile-modal.png', fullPage: true })
})

test('bloqueios reais do contrato, paginação, seleção de dia e presença separada', async ({ page }) => {
  const queries: string[] = []
  await page.route('**/api/admin/dashboard?**', route => {
    queries.push(route.request().url())
    return route.fulfill({ json: {
      ...snapshot,
      recent_conversations_by_day: Array.from({ length: 7 }, (_, i) => ({ day: '2026-10-' + String(i + 1).padStart(2, '0'), total: i === 5 ? 70 : 0 })),
      technicians: [{ ...snapshot.technicians[0], status: 'offline', availability: 'online', connected: false }],
      connected_customers: [{ id: 3, display_name: 'Cliente conectado', last_seen_at: '2026-10-06T15:00:00Z' }],
    } })
  })
  await page.route('**/api/admin/dashboard/details**', route => {
    const url = new URL(route.request().url())
    const kind = url.searchParams.get('kind'), requestedPage = Number(url.searchParams.get('page'))
    queries.push(route.request().url())
    return route.fulfill({ json: { items: kind === 'blocked' ? [{ id: String(requestedPage), rule: 'command_execution_request', layer: 'input', severity: 'high', sample: '<svg>texto não executável</svg>', created_at: '2026-10-06T15:00:00Z' }] : [{ id: 'chat-1', customer_name: 'Café Aurora', status: 'with_technician', handoff_status: 'assigned', technician_name: 'Técnico Plantão', message_count: 4, started_at: '2026-10-06T15:00:00Z' }], total: kind === 'blocked' ? 11 : 1, page: requestedPage, page_size: 10 } })
  })
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByText('0 técnicos disponíveis', { exact: true })).toBeVisible()
  await expect(page.getByText('1 clientes conectados', { exact: true })).toBeVisible()
  await expect(page.getByText('Cliente conectado', { exact: true })).toBeVisible()
  await expect(page.locator('.dashboard-bar-chart > button')).toHaveCount(7)
  await page.getByRole('button', { name: 'Ver detalhes: Eventos bloqueados' }).click()
  let dialog = page.getByRole('dialog')
  await expect(dialog.getByText('Tentativa de executar comando', { exact: true })).toBeVisible()
  await expect(dialog.locator('svg')).toHaveCount(1) // Only the close icon; event text is not HTML.
  await dialog.getByRole('button', { name: 'Próxima' }).click()
  await expect(dialog.getByText('Página 2 de 2')).toBeVisible()
  await dialog.getByLabel('Data dos detalhes').fill('2026-10-04')
  await expect.poll(() => queries.some(url => url.includes('date=2026-10-04') && url.includes('page=1'))).toBe(true)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Ver rota: Encaminhamento humano' }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByText(/Escalation: agente de IA/)).toBeVisible()
  await expect(dialog.getByText(/Técnico Plantão/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Ver conversas', exact: true }).click()
  await expect(page.getByRole('dialog').getByText('Café Aurora', { exact: true })).toBeVisible()
  expect(queries.some(url => url.includes('kind=conversations') && url.includes('period=7d'))).toBe(true)
  await page.keyboard.press('Escape')
  await page.getByLabel('Dia do dashboard').fill('2026-10-04')
  await expect.poll(() => queries.some(url => url.includes('/dashboard?') && url.includes('date=2026-10-04'))).toBe(true)
})
