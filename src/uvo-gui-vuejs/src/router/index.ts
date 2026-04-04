import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('../pages/DashboardPage.vue') },
    { path: '/contracts', component: () => import('../pages/ContractsPage.vue') },
    { path: '/suppliers', component: () => import('../pages/SuppliersPage.vue') },
    { path: '/suppliers/:ico', component: () => import('../pages/SupplierDetailPage.vue') },
    { path: '/procurers', component: () => import('../pages/ProcurersPage.vue') },
    { path: '/procurers/:ico', component: () => import('../pages/ProcurerDetailPage.vue') },
    { path: '/costs', component: () => import('../pages/CostAnalysisPage.vue') },
    { path: '/search', component: () => import('../pages/SearchPage.vue') },
  ],
})

export default router
