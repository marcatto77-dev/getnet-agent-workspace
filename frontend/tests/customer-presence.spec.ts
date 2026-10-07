import { expect, test } from '@playwright/test'

const azul = { id: 6, username: 'azul', role: 'cliente', display_name: 'Casa Azul', must_change_password: false }

test('presença do Azul começa após validar a sessão e renova ao voltar à aba', async ({ page }) => {
  let validated = false
  const requests: { validated: boolean; active: boolean }[] = []
  await page.route('**/api/auth/me', async route => {
    await new Promise(resolve => setTimeout(resolve, 200))
    validated = true
    await route.fulfill({ json: azul })
  })
  await page.route('**/api/auth/presence', async route => {
    requests.push({ validated, active: route.request().postDataJSON().active })
    await route.fulfill({ status: 204 })
  })
  await page.route('**/api/chat/current', route => route.fulfill({ json: null }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Como podemos ajudar?' })).toBeVisible()
  await expect.poll(() => requests.filter(item => item.active).length).toBeGreaterThan(0)
  expect(requests.filter(item => item.active).every(item => item.validated)).toBe(true)
  const count = requests.filter(item => item.active).length
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect.poll(() => requests.filter(item => item.active).length).toBeGreaterThan(count)
})

test('portal sem sessão não registra cliente online', async ({ page }) => {
  let presenceRequests = 0
  await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Sessão expirada.' } }))
  await page.route('**/api/auth/presence', route => { presenceRequests++; return route.fulfill({ status: 204 }) })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Entre para ser atendido' })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  expect(presenceRequests).toBe(0)
})
