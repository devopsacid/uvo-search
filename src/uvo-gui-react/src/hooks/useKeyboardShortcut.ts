import { useEffect } from 'react'

export function useKeyboardShortcut(key: string, callback: () => void) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Skip when focus is inside an input/textarea/select/contenteditable
      const target = e.target as HTMLElement
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target.isContentEditable
      ) {
        return
      }
      if (e.key === key && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault()
        callback()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [key, callback])
}
