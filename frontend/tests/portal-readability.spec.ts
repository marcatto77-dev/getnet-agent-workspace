import { expect, test } from '@playwright/test'

const messages = [{ id: 'm1', sender_type: 'customer', content: 'Minha máquina não conecta à internet.' }, { id: 'm2', sender_type: 'technician', content: 'Vamos verificar a conexão Wi-Fi juntos.' }]
const handoff = { id: 'h1', conversation_id: 'c1', customer_name: 'Casa Azul', terminal_name: 'Get Smart', reason: 'cliente_pediu', summary: { problem: 'Cliente pediu ajuda para conectar a máquina.' }, status: 'assigned', technician_name: 'Técnico Plantão', waiting_since: '2026-10-06T12:00:00Z', assigned_at: '2026-10-06T12:05:00Z', closed_at: '2026-10-06T12:20:00Z', close_category: 'resolvido', resolution_note: 'Conexão Wi-Fi restabelecida.' }
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { class Socket { onopen?: () => void; onclose?: () => void; constructor() { setTimeout(() => this.onopen?.(), 0) } close() {} send() {} }; (window as any).WebSocket = Socket })
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    let json: unknown = []
    if (path === '/api/auth/presence') return route.fulfill({ status: 204 })
    if (path === '/api/auth/me') json = page.url().includes('/tecnico') ? { id: 2, role: 'tecnico', display_name: 'Técnico Plantão' } : { id: 6, role: 'cliente', username: 'azul', display_name: 'Casa Azul', must_change_password: false }
    if (path === '/api/chat/current') json = { conversation_id: 'c1', status: 'with_technician', messages }
    if (path === '/api/customer/terminals') json = [{ id: 't1', model: 'Get Smart', apelido: 'Caixa principal', serial_number: 'A1B2C3', connection_status: 'online', updated_at: '2026-10-06T12:00:00Z' }]
    if (path === '/api/customer/profile') json = { nome: 'Casa Azul', email: 'contato@example.com', telefone: '(11) 99999-0000' }
    if (path === '/api/tech/service-center/summary') json = { queue: 1, mine: 1, others: 1, closed: 1 }
    if (['/api/tech/queue', '/api/tech/handoffs/mine', '/api/tech/handoffs/others'].includes(path)) json = [handoff]
    if (path === '/api/tech/handoffs/closed') json = { items: [handoff], total: 1, page: 1, page_size: 10 }
    if (path === '/api/tech/technicians') json = [{ id: 2, display_name: 'Técnico Plantão', status: 'online', active_chats: 1 }, { id: 3, display_name: 'Segundo técnico', status: 'online', active_chats: 0 }]
    if (path === '/api/tech/handoffs/h1/preview') json = { ...handoff, messages }
    if (path === '/api/tech/conversations/c1') json = { id: 'c1', handoff_id: 'h1', handoff_status: 'assigned', nome: 'Casa Azul', external_id: 'azul', summary: handoff.summary, messages, customer: { nome: 'Casa Azul', contato: 'Contato demonstrativo' }, terminals: [{ model: 'Get Smart', connection_status: 'online' }] }
    return route.fulfill({ json })
  })
})

test('cliente: chat, máquinas, conta e logo legíveis em quatro larguras', async ({ page }) => {
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const [path, label] of [['/', 'chat'], ['/minhas-maquinas', 'maquinas'], ['/conta', 'conta']]) {
      await page.goto(path)
      await expect(page.locator('.public-shell')).toBeVisible()
      await expect(page.locator('.customer-nav a[aria-current="page"]')).toHaveCount(1)
      await expect(page.locator('.customer-nav a[aria-current="page"]')).toHaveAttribute('href', path)
      await expect(page.getByRole('img', { name: 'Getnet', exact: true })).toBeVisible()
      const logo = await page.getByRole('img', { name: 'Getnet', exact: true }).evaluate((el: HTMLImageElement) => ({ loaded: el.complete && el.naturalWidth > 0, src: el.src }))
      expect(logo.loaded).toBe(true)
      expect(logo.src).toMatch(/^data:image\/png;base64,/)
      if (path === '/') {
        await expect(page.getByText('Vamos verificar a conexão Wi-Fi juntos.')).toBeVisible()
        await expect(page.locator('.chat-heading small')).toBeVisible()
        if (width >= 1024) {
          const card = await page.locator('.chat-card').boundingBox()
          expect(card!.width).toBeGreaterThan(width * 0.9)
          const header = await page.locator('.public-header').boundingBox()
          expect(header!.height).toBeLessThan(90)
        }
        expect(await page.locator('.public-message p').first().evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16)
      } else if (path === '/conta') {
        await expect(page.getByLabel('Senha atual')).toBeVisible()
        expect(await page.getByLabel('Senha atual').evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBe(16)
      } else await expect(page.getByText('Caixa principal')).toBeVisible()
      expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(width)
      if (width === 1440 || width === 390) await page.screenshot({ path: `../docs/evidence/portal-readability/${width}-cliente-${label}.png`, fullPage: true })
    }
  }
})

test('chat amplo mantém leitura confortável em resposta longa e compositor acessível', async ({ page }) => {
  await page.route('**/api/chat/current', route => route.fulfill({ json: {
    conversation_id: 'c1', status: 'with_technician', messages: [
      { id: 'long1', sender_type: 'customer', content: 'Quando recebo o dinheiro das vendas de ontem?' },
      { id: 'long2', sender_type: 'ai', content: [
        'Os prazos de recebimento dependem do seu plano contratado. Você pode consultar os lançamentos e as datas previstas no portal Minha Conta.',
        'Para conferir, abra a área de recebimentos e selecione a data das vendas. Verifique também o tipo de pagamento: débito, crédito à vista ou parcelado.',
        'Se houver antecipação contratada, o prazo pode ser diferente. A informação geral não confirma um depósito individual: consulte a agenda de recebíveis para verificar sua venda.',
        'Caso não encontre o lançamento esperado, podemos verificar os dados disponíveis para o seu cadastro ou encaminhar o atendimento a um técnico quando você solicitar.',
      ].join('\n\n') },
    ],
  } }))
  for (const width of [1875, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/')
    await expect(page.getByText('Os prazos de recebimento', { exact: false })).toBeVisible()
    await expect(page.getByLabel('Sua mensagem')).toBeVisible()
    const font = await page.locator('.public-message.ai p').evaluate(el => getComputedStyle(el).fontSize)
    expect(font).toBe('16px')
    const card = await page.locator('.chat-card').boundingBox()
    if (width > 700) expect(card!.width).toBeGreaterThan(1400)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width)
    await page.screenshot({ path: `../docs/evidence/portal-readability/${width}-cliente-chat-ux.png`, fullPage: true })
  }
})

test('técnico: fila, prévia, conversa, contexto, encaminhamento e encerrados legíveis', async ({ page }) => {
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/tecnico/atendimento')
    await expect(page.getByRole('heading', { name: 'Atendimentos aguardando um técnico' })).toBeVisible()
    await page.getByRole('button', { name: 'Ver chat', exact: true }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('dialog').getByText('Vamos verificar a conexão Wi-Fi juntos.')).toBeVisible()
    await page.getByRole('button', { name: 'Fechar prévia' }).click()
    await page.getByRole('button', { name: /Meus atendimentos/ }).click()
    await page.locator('.center-list>button').click()
    await expect(page.getByLabel('Mensagem ao cliente')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Contexto', exact: true })).toBeVisible()
    expect(await page.locator('.tech-messages p').first().evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThanOrEqual(16)
    await page.getByRole('button', { name: 'Encaminhar', exact: true }).click()
    await expect(page.getByLabel('Destino')).toBeVisible()
    await page.getByRole('button', { name: 'Cancelar', exact: true }).click()
    expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(width)
    if (width === 1440 || width === 390) await page.screenshot({ path: `../docs/evidence/portal-readability/${width}-tecnico-conversa.png`, fullPage: true })
    await page.getByRole('button', { name: /Encerrados/ }).first().click()
    await expect(page.getByText('Conexão Wi-Fi restabelecida.')).toBeVisible()
    await page.getByRole('button', { name: 'Ver histórico' }).click()
    await expect(page.locator('.tech-messages')).toBeVisible()
    await expect(page.getByLabel('Mensagem ao cliente')).toHaveCount(0)
    expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(width)
  }
})

test('login e troca de senha usam logo original e campos ampliados', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  for (const path of ['/login', '/change-password']) {
    await page.goto(path)
    await expect(page.getByRole('img', { name: 'Getnet' })).toBeVisible()
    const input = page.locator('input').first()
    expect(await input.evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBe(16)
    expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(390)
  }
})
