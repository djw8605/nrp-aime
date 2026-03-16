<template>
  <section class="mx-auto max-w-2xl py-12">
    <Card>
      <template #title>
        <div class="flex items-center gap-3">
          <span class="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-sky-600 text-white">
            <i class="pi pi-shield text-base"></i>
          </span>
          <span>Administrator Sign In</span>
        </div>
      </template>
      <template #subtitle>
        Sign in to access project administration, people, and operations tools.
      </template>
      <template #content>
        <div class="space-y-5">
          <Message v-if="hasError" severity="error" :closable="false">
            <p class="m-0 font-semibold">{{ errorTitle }}</p>
            <p class="mt-1 mb-0">{{ errorSummary }}</p>
            <p v-if="errorReason" class="mt-2 mb-0">
              Determination: {{ errorReason }}
            </p>
          </Message>

          <Message severity="info" :closable="false">
            Invite links are public and do not require administrator login.
          </Message>

          <div class="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
            <p class="m-0 font-medium">How login failures are classified</p>
            <ul class="mt-2 mb-0 list-disc space-y-1 pl-5">
              <li><code>invalid_state</code>: callback state failed signature/expiry/purpose checks</li>
              <li><code>missing_code</code>: callback did not include an authorization code</li>
              <li><code>missing_email_claim</code>: callback identity did not include an email</li>
              <li><code>idp_error</code>: identity provider returned an explicit OAuth error</li>
              <li><code>login_failed</code>: unexpected callback validation failure</li>
            </ul>
          </div>

          <div class="flex flex-wrap items-center gap-3">
            <Button
              label="Sign In as Admin"
              icon="pi pi-sign-in"
              :loading="checkingSession"
              @click="startLogin"
            />
            <p class="m-0 text-sm text-slate-600">
              Next route after login:
              <code>{{ nextPath }}</code>
            </p>
          </div>
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
import Message from 'primevue/message'

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

const errorCode = computed(() =>
  String(
    typeof route.query.auth_error === 'string' ? route.query.auth_error : '',
  ).trim(),
)
const errorReason = computed(() =>
  String(
    typeof route.query.auth_error_reason === 'string' ? route.query.auth_error_reason : '',
  ).trim(),
)
const hasError = computed(() => errorCode.value.length > 0)

const errorMeta = {
  invalid_state: {
    title: 'Login blocked by invalid state token',
    summary:
      'The callback state could not be verified. This usually means the login state expired, was tampered, or did not match this auth flow.',
  },
  missing_code: {
    title: 'Login callback missing authorization code',
    summary:
      'The identity provider redirected back without an OAuth authorization code, so authentication cannot be completed.',
  },
  missing_email_claim: {
    title: 'Login callback missing email claim',
    summary:
      'The callback identity payload did not include an email claim required for an administrator session.',
  },
  idp_error: {
    title: 'Identity provider returned an OAuth error',
    summary:
      'The external identity provider reported an authentication/authorization error during callback.',
  },
  login_failed: {
    title: 'Login callback validation failed',
    summary:
      'An unexpected error occurred while validating the authentication callback.',
  },
}

const errorTitle = computed(() => errorMeta[errorCode.value]?.title || 'Login failed')
const errorSummary = computed(
  () =>
    errorMeta[errorCode.value]?.summary ||
    'Authentication was not completed. Please try again.',
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
