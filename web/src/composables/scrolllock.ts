import { onUnmounted, watch, type WatchSource } from 'vue'

const locks = new Set<symbol>()
let savedBodyOverflow: string | null = null
let savedDocumentOverflow: string | null = null

function lockBody(token: symbol) {
  if (locks.has(token)) return
  if (locks.size === 0 && typeof document !== 'undefined') {
    savedBodyOverflow = document.body.style.overflow
    savedDocumentOverflow = document.documentElement.style.overflow
  }
  locks.add(token)
  if (typeof document !== 'undefined') {
    document.body.style.overflow = 'hidden'
    document.documentElement.style.overflow = 'hidden'
  }
}

function unlockBody(token: symbol) {
  if (!locks.delete(token) || locks.size > 0) return
  if (typeof document !== 'undefined') {
    document.body.style.overflow = savedBodyOverflow ?? ''
    document.documentElement.style.overflow = savedDocumentOverflow ?? ''
  }
  savedBodyOverflow = null
  savedDocumentOverflow = null
}

export function useBodyScrollLock(open: WatchSource<boolean>) {
  const token = Symbol('body-scroll-lock')
  let locked = false

  const stop = watch(open, (isOpen) => {
    if (isOpen && !locked) {
      locked = true
      lockBody(token)
    } else if (!isOpen && locked) {
      locked = false
      unlockBody(token)
    }
  }, { immediate: true })

  onUnmounted(() => {
    stop()
    if (locked) {
      locked = false
      unlockBody(token)
    }
  })
}
