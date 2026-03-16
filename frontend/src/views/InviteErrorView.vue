<template>
  <div class="mx-auto max-w-xl">
    <Card class="border border-rose-200 bg-rose-50/40 shadow-sm">
      <template #title>
        <span class="text-xl font-semibold text-rose-800">Invite Error</span>
      </template>
      <template #content>
        <p class="m-0 text-rose-900">{{ displayMessage }}</p>
        <p class="m-0 mt-3 text-sm text-rose-900">
          <strong>Error Code:</strong> {{ code || 'unknown' }}
        </p>
        <p class="m-0 mt-2">If this issue continues, ask an administrator for a new invite link.</p>

        <div class="mt-6">
          <router-link :to="{ name: 'projects' }" class="no-underline">
            <Button label="Back to Portal" icon="pi pi-home" />
          </router-link>
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'

const route = useRoute()
const code = computed(() => String(route.query.code || '').trim())
const explicitMessage = computed(() => String(route.query.message || '').trim())

const messages = {
  invalid_invite: 'This invitation link is invalid or no longer available.',
  invite_used: 'This invitation link has already been used.',
  invite_expired: 'This invitation link has expired.',
  invite_revoked: 'This invitation link has been revoked.',
  invalid_state: 'The sign-in state is invalid or expired. Please try the invite link again.',
  invite_email_mismatch: 'The authenticated email does not match the invited email.',
  internal_error: 'An unexpected error occurred while processing this invite.',
}

const displayMessage = computed(() => {
  if (explicitMessage.value) return explicitMessage.value
  if (messages[code.value]) return messages[code.value]
  return 'Unable to complete invite flow.'
})
</script>
