import { expect, test } from '@playwright/test'

const emptyPage = { items: [], total: 0, page: 1, page_size: 20 }
test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    let json: unknown = emptyPage
    if (path === '/api/auth/presence') return route.fulfill({ status: 204 })
    if (path === '/api/auth/me') json = { id: 1, username: 'Admin', role: 'admin', display_name: 'Administrador' }
    if (path === '/api/health/ready') json = { degraded: false }
    if (path === '/api/admin/dashboard') json = { cards: { attendances: 0, distinct_customers: 0, resolved_by_ai: 0, escalated: 0, blocked: 0, waiting: 0, in_progress: 0, average_response_ms: 0, input_tokens: 0, output_tokens: 0, cost: 0 }, attendances_by_day: [], routes: [], escalation_rate: 0, technicians: [], connected_customers: [] }
    if (path === '/api/admin/users') json = [{ id: 1, username: 'Admin', role: 'admin', display_name: 'Administrador', is_active: true }]
    if (path === '/api/admin/customers') json = { ...emptyPage, total: 1, items: [{ id: 'blue', username: 'azul', nome: 'Casa Azul', email: 'contato@example.com', is_active: true, terminal_count: 1 }] }
    if (path === '/api/admin/rag/documents') json = { ...emptyPage, total: 1, items: [{ id: 1, title: 'Manual oficial Get Smart', source: 'https://site.getnet.com.br/manual-get-smart.pdf', content: 'Orientações para configurar a conexão da maquininha e atender dúvidas do cliente.', origin: 'crawler', status_embedding: 'indexed', review_required: false, poisoning_flags: [], chunk_count: 15, updated_at: '2026-10-06T12:00:00Z' }] }
    if (path === '/api/admin/logs') json = { ...emptyPage, total: 1, items: [{ id: 'run-1', request_id: 'request-readability', user_id: 'azul', route: 'knowledge', agents_used: ['Router', 'Knowledge'], status: 'ok', latency_ms: 250, tokens: { input_tokens: 150, output_tokens: 50 }, cost: .01, error: null, created_at: '2026-10-06T12:00:00Z', tool_calls: [{ id: 1, tool_name: 'rag.retrieve', success: true, latency_ms: 20, input_summary: 'Conexão da máquina', output_summary: 'Dois trechos relevantes encontrados.' }] }] }
    if (path === '/api/admin/audit') json = { ...emptyPage, total: 1, items: [{ id: 1, action: 'customer.updated', actor_name: 'Administrador', entity: 'customer', entity_id: 'blue', diff: { nome: 'Casa Azul' }, created_at: '2026-10-06T12:00:00Z' }] }
    if (path === '/api/admin/agents') json = { read_only: true, model: 'gpt-4.1-mini', embedding_model: 'text-embedding-3-small', scope: 'Atendimento Getnet e câmbio.', handoff: 'Encaminhamento humano com aceite.', languages: 'Português, inglês e espanhol.', agents: [{ name: 'ROUTER', description: 'Escolhe os agentes', prompt: 'Classifique a mensagem do cliente e selecione a rota.' }], guardrails: [], limits: { tool_timeout_seconds: 8, chat_requests_per_minute: 20 } }
    return route.fulfill({ json })
  })
})

test('Admin abre e recarrega no Dashboard; todas as páginas ficam legíveis e contidas', async ({ page }) => {
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/admin')
    await expect(page.locator('.admin-main>header h1')).toHaveText('Dashboard')
    await expect(page.getByRole('button', { name: 'Dashboard', exact: true })).toHaveAttribute('aria-current', 'page')
    for (const section of ['Usuários', 'Clientes', 'Máquinas', 'Base de conhecimento', 'Logs', 'Agentes e segurança']) {
      const menu = page.getByRole('navigation', { name: 'Menu administrativo' })
      const button = menu.getByRole('button', { name: section, exact: true })
      await button.click()
      await expect(page.locator('.admin-main>header h1')).toHaveText(section)
      await expect(button).toHaveAttribute('aria-current', 'page')
      const sizes = await page.evaluate(() => ({ width: document.body.scrollWidth, viewport: innerWidth, navFont: parseFloat(getComputedStyle(document.querySelector('.admin-nav nav button')!).fontSize), navHeight: document.querySelector('.admin-nav nav button')!.getBoundingClientRect().height, bodyFont: parseFloat(getComputedStyle(document.querySelector('.admin-panel')!).fontSize) }))
      expect(sizes.width, `${section} em ${width}px`).toBeLessThanOrEqual(sizes.viewport)
      expect(sizes.navFont).toBeGreaterThanOrEqual(14)
      expect(sizes.navHeight).toBeGreaterThanOrEqual(44)
      expect(sizes.bodyFont).toBeGreaterThanOrEqual(16)
      if (section === 'Usuários') {
        await expect(page.getByRole('cell', { name: 'Admin', exact: true })).toBeVisible()
        expect(await page.locator('td').first().evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(15)
        await page.getByRole('button', { name: 'Novo usuário', exact: true }).click()
        await expect(page.getByLabel('Nome de exibição')).toBeVisible()
        expect(await page.getByLabel('Nome de exibição').evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16)
        await page.locator('.modal-x').click()
      }
      if (section === 'Logs') {
        await page.locator('.run-summary').click()
        await expect(page.getByText('Dois trechos relevantes encontrados.')).toBeVisible()
        expect(await page.locator('.run-detail pre').first().evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(14)
        await page.getByRole('button', { name: 'Auditoria administrativa' }).click()
        await expect(page.getByText('Registro de auditoria')).toBeVisible()
      }
      if (section === 'Agentes e segurança') {
        await page.locator('summary').click()
        await expect(page.locator('.agent-source pre')).toBeVisible()
      }
      expect(await page.evaluate(() => document.body.scrollWidth), `${section} expandido em ${width}px`).toBeLessThanOrEqual(width)
      if (width === 1440 || width === 390) await page.screenshot({ path: `../docs/evidence/admin-readability/${width}-${section.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replaceAll(' ', '-').toLowerCase()}.png`, fullPage: true })
    }
    await page.reload()
    await expect(page.locator('.admin-main>header h1')).toHaveText('Dashboard')
  }
})
