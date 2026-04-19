import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useCommandPalette } from './useCommandPalette'

const GOTO: Record<string, string> = {
  d: '/',
  c: '/contracts',
  s: '/suppliers',
  p: '/procurers',
  x: '/costs',
  '/': '/search',
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

export function useHotkeys() {
  const router = useRouter()
  const palette = useCommandPalette()

  let pendingChord: 'g' | null = null
  let chordTimer: number | undefined

  function clearChord() {
    pendingChord = null
    if (chordTimer) { window.clearTimeout(chordTimer); chordTimer = undefined }
  }

  function onKeydown(e: KeyboardEvent) {
    // ⌘K / Ctrl+K always open palette
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      palette.toggle()
      clearChord()
      return
    }

    // Esc always closes palette
    if (e.key === 'Escape') {
      if (palette.isOpen.value) {
        e.preventDefault()
        palette.close()
      }
      clearChord()
      return
    }

    if (isTypingTarget(e.target)) return
    if (e.metaKey || e.ctrlKey || e.altKey) return

    if (pendingChord === 'g') {
      const target = GOTO[e.key.toLowerCase()]
      if (target) {
        e.preventDefault()
        router.push(target)
      }
      clearChord()
      return
    }

    if (e.key === 'g') {
      pendingChord = 'g'
      chordTimer = window.setTimeout(clearChord, 1200)
      return
    }

    if (e.key === '/') {
      e.preventDefault()
      router.push('/search')
      return
    }

    if (e.key === '?') {
      e.preventDefault()
      palette.open()
      return
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))
}
