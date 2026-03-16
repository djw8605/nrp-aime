<template>
  <div class="mx-auto max-w-5xl">
    <section
      class="overflow-hidden rounded-3xl border border-sky-200 bg-gradient-to-br from-sky-50 via-white to-emerald-50 p-6 shadow-sm sm:p-10"
    >
      <div v-if="loading" class="flex items-center justify-center py-20">
        <ProgressSpinner style="width: 2.8rem; height: 2.8rem" strokeWidth="5" />
      </div>

      <Message v-else-if="error" severity="error" :closable="false">
        {{ error }}
      </Message>

      <div v-else-if="preview" class="space-y-7">
        <div class="space-y-3">
          <p class="m-0 text-xs font-semibold uppercase tracking-[0.16em] text-sky-700">
            National Research Platform
          </p>
          <h1 class="m-0 text-3xl font-bold text-slate-900 sm:text-4xl">Complete Your Account Sign-In</h1>
          <p class="m-0 max-w-3xl text-base leading-relaxed text-slate-700">
            Thanks for requesting an account with the National Research Platform
            (<a href="https://nrp.ai" target="_blank" rel="noreferrer" class="font-semibold text-sky-700 underline">
              https://nrp.ai
            </a>).
            Please follow the link below to login and it will automatically create your account.
          </p>
        </div>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
          <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-slate-500">Invited Email</p>
            <p class="m-0 mt-2 text-base font-semibold text-slate-800">
              {{ preview.invited_email_masked || 'hidden' }}
            </p>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-slate-500">Invite Expires</p>
            <p class="m-0 mt-2 text-base font-semibold text-slate-800">
              {{ formatDate(preview.expires_at) }}
            </p>
          </article>
          <article class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-slate-500">Projects Included</p>
            <p class="m-0 mt-2 text-base font-semibold text-slate-800">
              {{ preview.project_count || 0 }}
            </p>
          </article>
        </div>

        <div v-if="(preview.project_names || []).length" class="space-y-3">
          <p class="m-0 text-sm font-semibold text-slate-700">Project Access Summary</p>
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
            <article
              v-for="projectName in preview.project_names"
              :key="projectName"
              class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4"
            >
              <p class="m-0 text-sm font-semibold text-emerald-800">{{ projectName }}</p>
            </article>
          </div>
        </div>

        <div class="rounded-2xl border border-sky-300 bg-sky-100/70 p-4">
          <Button
            label="Continue to Secure Sign-In"
            icon="pi pi-sign-in"
            class="w-full !text-base"
            @click="continueToAuth"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { buildInviteAcceptStartUrl, previewInvite } from '../api/invites'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref(null)
const preview = ref(null)
const token = ref('')

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function gotoError(code, message = '') {
  router.replace({
    name: 'invite-error',
    query: { code, message },
  })
}

async function loadPreview() {
  token.value = String(route.query.token || '').trim()
  if (!token.value) {
    gotoError('invalid_invite', 'Invite token is missing.')
    return
  }

  loading.value = true
  error.value = null
  try {
    const result = await previewInvite(token.value)
    if (!result.valid) {
      gotoError(result.status || 'invalid_invite', result.message)
      return
    }
    preview.value = result
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to validate invite.'
  } finally {
    loading.value = false
  }
}

function continueToAuth() {
  if (!token.value) return
  window.location.assign(buildInviteAcceptStartUrl(token.value))
}

onMounted(async () => {
  await loadPreview()
})
</script>
