import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, setAuthToken } from '@/api/client'

describe('API client', () => {
  afterEach(() => {
    setAuthToken(null)
    vi.unstubAllGlobals()
  })

  it('encodes novel names and sends the authentication token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ name: 'A/B' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    setAuthToken('secret')

    await api.getNovel('A/B')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/novels/A%2FB')
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
      Accept: 'application/json',
      Authorization: 'Bearer secret'
    })
  })

  it('sends translated chapter edits as JSON with the target language', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ content: 'Edited' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await api.putChapterContent('A/B', 2, 'Edited', 'translation', 'vi')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/novels/A%2FB/chapters/2?view=translation&target=vi')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PUT')
    expect(JSON.parse(String(init.body))).toEqual({ content: 'Edited' })
  })

  it('returns structured API errors for failed requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: { code: 'conflict', message: 'Chapter changed', details: { chapter: 2 } } }),
      { status: 409 }
    )))

    await expect(api.getNovel('book')).rejects.toMatchObject({
      message: 'Chapter changed',
      code: 'conflict',
      status: 409,
      details: { chapter: 2 }
    })
  })
})
