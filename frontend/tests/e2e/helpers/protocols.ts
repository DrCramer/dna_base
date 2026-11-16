import { expect, type Page } from '@playwright/test'

export async function assertIsolatedProtocolBackend(page: Page) {
  expect(process.env.DNA_E2E_ISOLATED, 'Запись разрешена только в изолированную E2E-базу').toBe('1')
  const response = await page.request.get('/api/protocols/profiles')
  expect(response.ok()).toBe(true)
  const profiles = await response.json() as Array<{ instrument_config_json?: Record<string, unknown> }>
  expect(profiles.some((profile) => profile.instrument_config_json?._isolated_protocol_e2e === true), 'Backend не содержит маркер из create_protocol_concentration_e2e.py; проверьте адрес proxy').toBe(true)
}
