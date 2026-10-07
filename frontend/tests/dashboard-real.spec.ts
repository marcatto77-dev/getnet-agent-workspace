import { expect, test } from '@playwright/test'

test.skip(!process.env.REAL_E2E, 'Requer o Docker local com banco de demonstração.')
test('dashboard real: métricas do banco, detalhes e troca de período sem erros', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/login')
  await page.getByLabel('Usuário').fill(process.env.E2E_ADMIN_USERNAME || 'Admin')
  await page.getByLabel('Senha').fill(process.env.E2E_ADMIN_PASSWORD || 'Admin')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page).toHaveURL(/\/admin$/)
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Ver detalhes: Conversas iniciadas' })).toBeVisible()
  await expect(page.locator('.admin-alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Ver detalhes: Tokens utilizados' }).click()
  await expect(page.getByRole('dialog', { name: 'Tokens utilizados', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').getByText('Tokens de entrada')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Ver detalhes: Eventos bloqueados' }).click()
  await expect(page.getByRole('dialog').getByText(/registro\(s\) encontrado/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Ver conversas', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'Conversas dos últimos 7 dias', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').getByText(/registro\(s\) encontrado/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByLabel('Período do dashboard').selectOption('30d')
  await expect(page.getByRole('button', { name: 'Ver detalhes: Conversas iniciadas' })).toBeVisible()
  await expect(page.locator('.admin-alert')).toHaveCount(0)
  await expect(page.getByText('[object Object]', { exact: false })).toHaveCount(0)
  await page.screenshot({ path: '../docs/evidence/dashboard/dashboard-real.png', fullPage: true })
  expect(errors).toEqual([])
})

test('presença real separa cliente de técnico e remove a sessão encerrada', async ({ browser }) => {
  const adminContext = await browser.newContext(), customerContext = await browser.newContext(), techContext = await browser.newContext()
  try {
    const admin = await adminContext.newPage(), customer = await customerContext.newPage(), tech = await techContext.newPage()
    for (const [page, username, password, url] of [
      [admin, process.env.E2E_ADMIN_USERNAME || 'Admin', process.env.E2E_ADMIN_PASSWORD || 'Admin', /\/admin$/],
      [customer, 'cliente1988', '123', /\/$/],
      [tech, 'Tecnico', 'Tecnico', /\/tecnico\/atendimento$/],
    ] as const) {
      await page.goto('/login')
      await page.getByLabel('Usuário').fill(username)
      await page.getByLabel('Senha').fill(password)
      await page.getByRole('button', { name: 'Entrar', exact: true }).click()
      await expect(page).toHaveURL(url)
    }
    const technician = await (await tech.request.get('/api/auth/me')).json()
    const client = await (await customer.request.get('/api/auth/me')).json()
    const snapshot = async () => (await admin.request.get('/api/admin/dashboard')).json()
    await expect.poll(async () => (await snapshot()).connected_customers.some((row: any) => row.id === client.id)).toBe(true)
    await expect.poll(async () => (await snapshot()).technicians.find((row: any) => row.id === technician.id)?.status).toBe('online')
    await tech.getByRole('button', { name: 'Sair', exact: true }).click()
    await expect(tech).toHaveURL(/\/login$/)
    await expect.poll(async () => (await snapshot()).technicians.find((row: any) => row.id === technician.id)?.connected).toBe(false)
    expect((await snapshot()).connected_customers.some((row: any) => row.id === client.id)).toBe(true)
    // Logout invalidates the session deterministically. Pagehide/beacon alone is
    // best effort and may require lease expiry when the browser drops the request.
    await customer.getByRole('button', { name: 'Sair', exact: true }).click()
    await expect(customer.getByRole('heading', { name: 'Entre para ser atendido' })).toBeVisible()
    await expect.poll(async () => (await snapshot()).connected_customers.some((row: any) => row.id === client.id)).toBe(false)
  } finally {
    await adminContext.close(); await customerContext.close(); await techContext.close()
  }
})

test('sair do técnico e entrar pelo portal registra o cliente no mesmo navegador', async ({ browser }) => {
  const adminContext = await browser.newContext(), normalContext = await browser.newContext()
  try {
    const admin = await adminContext.newPage(), normal = await normalContext.newPage()
    await admin.goto('/login')
    await admin.getByLabel('Usuário').fill(process.env.E2E_ADMIN_USERNAME || 'Admin')
    await admin.getByLabel('Senha').fill(process.env.E2E_ADMIN_PASSWORD || 'Admin')
    await admin.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(admin).toHaveURL(/\/admin$/)
    await normal.goto('/login')
    await normal.getByLabel('Usuário').fill('Tecnico')
    await normal.getByLabel('Senha').fill('Tecnico')
    await normal.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(normal).toHaveURL(/\/tecnico\/atendimento$/)
    await normal.getByRole('button', { name: 'Sair', exact: true }).click()
    await expect(normal).toHaveURL(/\/login$/)
    await normal.goto('/')
    await normal.getByLabel('Usuário').fill(process.env.E2E_CUSTOMER_USERNAME || 'cliente1988')
    await normal.getByLabel('Senha').fill(process.env.E2E_CUSTOMER_PASSWORD || '123')
    await normal.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(normal.getByRole('heading', { name: 'Como podemos ajudar?' })).toBeVisible()
    const client = await (await normal.request.get('/api/auth/me')).json()
    expect(client.role).toBe('cliente')
    await expect.poll(async () => {
      const snapshot = await (await admin.request.get('/api/admin/dashboard')).json()
      return snapshot.connected_customers.some((row: any) => row.id === client.id)
    }).toBe(true)
    await admin.getByRole('button', { name: 'Dashboard', exact: true }).click()
    await admin.getByRole('button', { name: 'Atualizar', exact: true }).click()
    await expect(admin.locator('.dashboard-customer-presence').getByText(client.display_name, { exact: true })).toBeVisible()
    await normal.getByRole('button', { name: 'Sair', exact: true }).click()
    await expect(normal.getByRole('heading', { name: 'Entre para ser atendido' })).toBeVisible()
    await expect.poll(async () => {
      const snapshot = await (await admin.request.get('/api/admin/dashboard')).json()
      return snapshot.connected_customers.some((row: any) => row.id === client.id)
    }).toBe(false)
  } finally {
    await adminContext.close(); await normalContext.close()
  }
})

test('Admin real inicia no Dashboard e navega por todas as páginas com a nova tipografia', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/login')
  await page.getByLabel('Usuário').fill(process.env.E2E_ADMIN_USERNAME || 'Admin')
  await page.getByLabel('Senha').fill(process.env.E2E_ADMIN_PASSWORD || 'Admin')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.locator('.admin-main>header h1')).toHaveText('Dashboard')
  await expect(page.getByRole('heading', { name: 'Visão do atendimento' })).toBeVisible()
  for (const section of ['Usuários', 'Clientes', 'Máquinas', 'Base de conhecimento', 'Logs', 'Agentes e segurança']) {
    const endpoint: Record<string, string> = { 'Usuários': '/api/admin/users', 'Clientes': '/api/admin/customers', 'Máquinas': '/api/admin/machines', 'Base de conhecimento': '/api/admin/rag/documents', 'Logs': '/api/admin/logs', 'Agentes e segurança': '/api/admin/agents' }
    const responsePromise = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === endpoint[section] && (section !== 'Máquinas' || url.searchParams.get('kind') === 'terminal')
    })
    await page.getByRole('navigation', { name: 'Menu administrativo' }).getByRole('button', { name: section, exact: true }).click()
    const response = await responsePromise
    expect(response.ok()).toBe(true)
    const payload = await response.json()
    await expect(page.locator('.admin-main>header h1')).toHaveText(section)
    await expect(page.locator('.admin-alert')).toHaveCount(0)
    if (section === 'Agentes e segurança') await expect(page.getByText('Configuração em execução', { exact: false })).toBeVisible()
    else await expect(page.locator('.admin-panel')).toBeVisible()
    if (section !== 'Agentes e segurança') {
      const count = Array.isArray(payload) ? payload.length : payload.items.length
      if (section === 'Logs') await expect(page.locator('.runs-list>article')).toHaveCount(count)
      else if (count) await expect(page.locator('.admin-panel tbody tr')).toHaveCount(count)
    }
    expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(1440)
    await page.screenshot({ path: `../docs/evidence/admin-readability/real-${section.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replaceAll(' ', '-').toLowerCase()}.png` })
  }
  await page.reload()
  await expect(page.locator('.admin-main>header h1')).toHaveText('Dashboard')
  expect(errors).toEqual([])
})
