// Lightweight fetch-based SSE client. Native EventSource cannot attach
// Authorization headers, which the API needs in remote mode.

export interface SseEvent {
  event: string
  data: string
}

export interface SseHandlers {
  onEvent?: (event: SseEvent) => void
  onError?: (error: Event | Error) => void
  onOpen?: () => void
  onClose?: () => void
}

export interface SseClient {
  close: () => void
}

export function openSse(
  url: string,
  handlers: SseHandlers,
  init: { token?: string | null; signal?: AbortSignal } = {}
): SseClient {
  const controller = new AbortController()
  if (init.signal) {
    init.signal.addEventListener('abort', () => controller.abort())
  }

  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (init.token) {
    headers.Authorization = `Bearer ${init.token}`
  }

  let closed = false
  fetch(url, { method: 'GET', headers, signal: controller.signal })
    .then(async (response) => {
      if (!response.ok || !response.body) {
        handlers.onError?.(new Error(`SSE failed: ${response.status}`))
        return
      }
      handlers.onOpen?.()
      const reader = response.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      while (!closed) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }
        buffer += decoder.decode(value, { stream: true })
        let separator: RegExpMatchArray | null
        while ((separator = buffer.match(/\r\n\r\n|\n\n|\r\r/)) !== null) {
          const idx = separator.index ?? 0
          const raw = buffer.slice(0, idx)
          buffer = buffer.slice(idx + separator[0].length)
          const event: SseEvent = { event: 'message', data: '' }
          const dataLines: string[] = []
          for (const line of raw.split(/\r\n|\r|\n/)) {
            if (line.startsWith('event:')) {
              event.event = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trimStart())
            }
          }
          event.data = dataLines.join('\n')
          if (event.event === 'ping' || event.data === '') {
            continue
          }
          handlers.onEvent?.(event)
        }
      }
      handlers.onClose?.()
    })
    .catch((error) => {
      if (!closed) {
        handlers.onError?.(error instanceof Error ? error : new Error(String(error)))
      }
    })

  return {
    close: () => {
      closed = true
      controller.abort()
    }
  }
}
