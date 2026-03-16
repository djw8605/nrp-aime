import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import ProjectsView from '../views/ProjectsView.vue'
import ProjectDetailView from '../views/ProjectDetailView.vue'
import PacketLogsView from '../views/PacketLogsView.vue'
import ManualPacketInputView from '../views/ManualPacketInputView.vue'
import TransactionDetailView from '../views/TransactionDetailView.vue'
import AdminView from '../views/AdminView.vue'
import InviteAcceptView from '../views/InviteAcceptView.vue'
import InviteSuccessView from '../views/InviteSuccessView.vue'
import InviteErrorView from '../views/InviteErrorView.vue'
import PeopleView from '../views/PeopleView.vue'
import PersonDetailView from '../views/PersonDetailView.vue'
import { fetchAuthSession } from '../api/auth'

const PUBLIC_ROUTE_NAMES = new Set(['login', 'invite-accept', 'invite-success', 'invite-error'])
let sessionCache = null
let sessionPromise = null

async function getAuthSession() {
  if (sessionCache) return sessionCache
  if (!sessionPromise) {
    sessionPromise = fetchAuthSession()
      .then((session) => {
        sessionCache = session
        return session
      })
      .catch(() => ({ authenticated: false }))
      .finally(() => {
        sessionPromise = null
      })
  }
  return sessionPromise
}

export function clearAuthSessionCache() {
  sessionCache = null
}

function normalizeNextPath(value) {
  const candidate = String(value || '/projects').trim()
  if (!candidate.startsWith('/')) return '/projects'
  if (candidate.startsWith('//')) return '/projects'
  if (candidate.includes('://')) return '/projects'
  const [rawPath, rawQuery] = candidate.split('?')
  const path = rawPath === '/login' || rawPath === '/' ? '/projects' : (rawPath || '/projects')
  if (!rawQuery) return path

  const params = new URLSearchParams(rawQuery)
  params.delete('next')
  params.delete('auth_error')
  params.delete('auth_error_reason')
  const cleaned = params.toString()
  return cleaned ? `${path}?${cleaned}` : path
}

const routes = [
  {
    path: '/',
    name: 'login',
    component: LoginView,
    meta: { publicRoute: true, requiresAuth: false },
  },
  {
    path: '/projects',
    name: 'projects',
    component: ProjectsView,
    meta: { requiresAuth: true },
  },
  {
    path: '/projects/:id',
    name: 'project-detail',
    component: ProjectDetailView,
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminView,
    meta: { requiresAuth: true },
  },
  {
    path: '/people',
    name: 'people',
    component: PeopleView,
    meta: { requiresAuth: true },
  },
  {
    path: '/people/:id',
    name: 'person-detail',
    component: PersonDetailView,
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/invite/accept',
    name: 'invite-accept',
    component: InviteAcceptView,
    meta: { publicRoute: true },
  },
  {
    path: '/invite/success',
    name: 'invite-success',
    component: InviteSuccessView,
    meta: { publicRoute: true },
  },
  {
    path: '/invite/error',
    name: 'invite-error',
    component: InviteErrorView,
    meta: { publicRoute: true },
  },
  {
    path: '/packets/logs',
    name: 'packet-logs',
    component: PacketLogsView,
    meta: { requiresAuth: true },
  },
  {
    path: '/packets/manual',
    name: 'manual-packet-input',
    component: ManualPacketInputView,
    meta: { requiresAuth: true },
  },
  {
    path: '/transactions/:transactionId',
    name: 'transaction-detail',
    component: TransactionDetailView,
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/packets/unprocessed',
    redirect: { name: 'packet-logs' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const routeName = String(to.name || '')
  const isPublic = PUBLIC_ROUTE_NAMES.has(routeName) || to.meta.publicRoute
  if (isPublic) {
    if (routeName !== 'login') return true
    const session = await getAuthSession()
    if (!session?.authenticated) return true

    const nextPath = normalizeNextPath(
      typeof to.query.next === 'string' ? to.query.next : '/projects',
    )
    if (nextPath === to.fullPath) return true
    return nextPath
  }

  const requiresAuth = to.meta.requiresAuth !== false
  if (!requiresAuth) return true

  const session = await getAuthSession()
  if (session?.authenticated) return true

  clearAuthSessionCache()
  return {
    name: 'login',
    query: { next: to.fullPath || '/projects' },
  }
})

export default router
