import { createI18n } from 'vue-i18n'
import sk from './sk'
import en from './en'

export const i18n = createI18n({
  legacy: false,
  locale: 'sk',
  fallbackLocale: 'en',
  messages: { sk, en },
})
