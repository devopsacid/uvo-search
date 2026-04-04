import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

interface Company {
  ico: string
  name: string
  type: 'supplier' | 'procurer'
}

export const useFilterStore = defineStore('filter', () => {
  const ico = ref<string | null>(null)
  const name = ref<string | null>(null)
  const type = ref<'supplier' | 'procurer' | null>(null)

  const isFiltered = computed(() => ico.value !== null)
  const queryParams = computed(() =>
    isFiltered.value ? { ico: ico.value!, entity_type: type.value! } : {}
  )

  function setCompany(company: Company) {
    ico.value = company.ico
    name.value = company.name
    type.value = company.type
  }

  function clear() {
    ico.value = null
    name.value = null
    type.value = null
  }

  return { ico, name, type, isFiltered, queryParams, setCompany, clear }
})
