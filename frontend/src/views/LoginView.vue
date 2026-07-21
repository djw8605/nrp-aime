<template>
  <section class="mx-auto flex min-h-[70vh] max-w-md items-center py-12">
    <Card class="w-full">
      <template #title>
        <div class="flex items-center gap-3">
          <span class="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-sky-100 bg-white p-1 shadow-sm">
            <img
              src="/branding/nrp-access-integration-icon-512.png"
              alt="NRP and ACCESS integration icon"
              class="h-full w-full object-contain"
            />
          </span>
          <span>Administrator Sign In</span>
        </div>
      </template>
      <template #subtitle>
        Sign in to manage projects, people, and operations.
      </template>
      <template #content>
        <div class="space-y-5">
          <Button
            label="Sign In as Admin"
            icon="pi pi-sign-in"
            class="w-full"
            :loading="checkingSession"
            @click="startLogin"
          />

          <p class="m-0 text-center text-sm text-slate-600">
            You'll return to
            <code>{{ nextPath }}</code>
            after signing in.
          </p>

          <p class="m-0 text-center text-xs text-slate-500">
            Invite links are public and do not require administrator login.
          </p>
        </div>
      </template>
    </Card>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'

import { buildPortalLoginUrl, fetchAuthSession } from '../api/auth'
import { clearAuthSessionCache } from '../router'

const route = useRoute()
const router = useRouter()
const checkingSession = ref(true)

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

const nextPath = computed(() =>
  normalizeNextPath(typeof route.query.next === 'string' ? route.query.next : '/projects'),
)

async function refreshSession() {
  checkingSession.value = true
  try {
    const session = await fetchAuthSession()
    if (session?.authenticated) {
      await router.replace(nextPath.value)
      return
    }
  } catch {
    clearAuthSessionCache()
  } finally {
    checkingSession.value = false
  }
}

function startLogin() {
  window.location.assign(buildPortalLoginUrl(nextPath.value))
}

onMounted(() => {
  void refreshSession()
})
</script>
