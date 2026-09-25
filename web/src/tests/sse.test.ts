import { afterEach, describe, expect, it, vi } from 'vitest'
import { openSse } from '@/api/sse'

describe('SSE client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('parses events split across chunks and sends the authentication token', async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: progress\ndata: first'))
        controller.enqueue(encoder.encode(' line\ndata: second\n\nevent: ping\ndata: heartbeat\n\n'))
        controller.close()
      }
    })
    const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const events: Array<{ event: string; data: string }> = []
    const closed = new Promise<void>((resolve) => {
      openSse('/api/jobs/1/events', { onEvent: (event) => events.push(event), onClose: resolve }, { token: 'secret' })
    })

    await closed

    expect(events).toEqual([{ event: 'progress', data: 'first line\nsecond' }])
    expect(fetchMock.mock.calls[0][0]).toBe('/api/jobs/1/events')
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
      Accept: 'text/event-stream',
      Authorization: 'Bearer secret'
    })
  })
})
