<template>
  <div class="min-h-screen bg-slate-100">
    <Toolbar
      v-if="!isPublicInviteRoute"
      class="!rounded-none border-0 border-b border-slate-200 bg-white/90 backdrop-blur"
    >
      <template #start>
        <router-link :to="{ name: 'projects' }" class="flex items-center gap-3 text-slate-800 no-underline">
          <span class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-sky-600 text-white">
            <i class="pi pi-server text-sm"></i>
          </span>
          <div class="leading-tight">
            <p class="m-0 text-xs uppercase tracking-wide text-slate-500">National Research Platform</p>
            <p class="m-0 text-base font-semibold">AIME Allocation Manager</p>
          </div>
        </router-link>
      </template>
      <template #end>
        <div class="flex items-center gap-2">
          <router-link :to="{ name: 'projects' }" class="no-underline">
            <Button label="Projects" size="small" text>
              <template v-if="pendingCount > 0" #icon>
                <Badge :value="pendingCount" severity="warn" />
              </template>
            </Button>
          </router-link>
          <router-link :to="{ name: 'people' }" class="no-underline">
            <Button
              label="People"
              icon="pi pi-user"
              size="small"
              severity="secondary"
              outlined
            />
          </router-link>
          <router-link :to="{ name: 'admin' }" class="no-underline">
            <Button
              label="Admin"
              icon="pi pi-cog"
              size="small"
              severity="secondary"
              outlined
            />
          </router-link>
          <router-link :to="{ name: 'packet-logs' }" class="no-underline">
            <Button
              label="Packet Log"
              icon="pi pi-list-check"
              size="small"
              severity="contrast"
              outlined
            />
          </router-link>
          <router-link :to="{ name: 'manual-packet-input' }" class="no-underline">
            <Button
              label="Manual Packet Input"
              icon="pi pi-pencil"
              size="small"
              severity="secondary"
              outlined
            />
          </router-link>
          <Tag
            v-if="showAuthControls"
            severity="info"
            :value="principalLabel"
            rounded
          />
          <Button
            v-if="showAuthControls"
            label="Sign Out"
            icon="pi pi-sign-out"
            size="small"
            severity="secondary"
            outlined
            @click="signOut"
          />
        </div>
      </template>
    </Toolbar>

    <main :class="mainContainerClass">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Badge from 'primevue/badge'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Toolbar from 'primevue/toolbar'

import { fetchAuthSession, logoutPortal } from './api/auth'
import { fetchPendingActions } from './api/ops'
import { clearAuthSessionCache } from './router'

const route = useRoute()
const session = ref({ authenticated: false })
const pendingCount = ref(0)

const isPublicInviteRoute = computed(() => Boolean(route.meta.publicRoute))

const mainContainerClass = computed(() => {
  if (isPublicInviteRoute.value) {
    return 'mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8'
  }
  return 'mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8'
})

const showAuthControls = computed(
  () => !isPublicInviteRoute.value && Boolean(session.value?.authenticated),
)

const principalLabel = computed(() => {
  if (!showAuthControls.value) return ''
  return session.value?.name || session.value?.email || 'Authenticated'
})

async function refreshSession() {
  if (isPublicInviteRoute.value) {
    session.value = { authenticated: false }
    pendingCount.value = 0
    return
  }
  try {
    session.value = await fetchAuthSession()
    if (session.value?.authenticated) {
      try {
        const actions = await fetchPendingActions()
        pendingCount.value = actions?.total_pending_count || 0
      } catch {
        pendingCount.value = 0
      }
    }
  } catch {
    session.value = { authenticated: false }
    pendingCount.value = 0
  }
}

async function signOut() {
  try {
    await logoutPortal()
  } finally {
    clearAuthSessionCache()
    session.value = { authenticated: false }
    window.location.assign('/')
  }
}

watch(
  () => route.fullPath,
  () => {
    void refreshSession()
  },
)

onMounted(() => {
  void refreshSession()
})
</script>
