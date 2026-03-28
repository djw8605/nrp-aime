<template>
  <Card class="border border-slate-200 shadow-sm">
    <template #content>
      <div v-if="loading" class="space-y-3 p-2">
        <Skeleton v-for="n in 4" :key="n" height="2.5rem" borderRadius="0.5rem" />
      </div>
      <Message v-else-if="users.length === 0" severity="info" :closable="false">
        No users assigned.
      </Message>
      <DataTable
        v-else
        :value="users"
        dataKey="project_user_id"
        stripedRows
        size="small"
        tableStyle="min-width: 20rem"
        responsiveLayout="scroll"
      >
        <Column header="Name">
          <template #body="{ data }">
            <div class="flex flex-wrap items-center gap-2">
              <router-link
                :to="{ name: 'person-detail', params: { id: data.id } }"
                class="text-sky-700 no-underline hover:underline"
              >
                {{ data.name }}
              </router-link>
              <Tag
                v-if="data.is_project_pi"
                value="PI"
                severity="warn"
                rounded
              />
              <Tag
                v-for="tag in data.tags || []"
                :key="tag"
                :value="tag"
                severity="contrast"
                rounded
              />
            </div>
          </template>
        </Column>
        <Column header="Person ID">
          <template #body="{ data }">
            <span class="font-mono text-xs">{{ data.person_id || '—' }}</span>
          </template>
        </Column>
        <Column header="Email">
          <template #body="{ data }">
            {{ data.email || '—' }}
          </template>
        </Column>
        <Column header="Account">
          <template #body="{ data }">
            <Tag
              :value="data.account_is_active ? 'Active' : 'Inactive'"
              :severity="data.account_is_active ? 'success' : 'danger'"
              rounded
            />
          </template>
        </Column>
        <Column header="Lifecycle">
          <template #body="{ data }">
            <Tag
              :value="data.account_state"
              :severity="accountStateSeverity(data.account_state)"
              rounded
            />
          </template>
        </Column>
        <Column header="User">
          <template #body="{ data }">
            <Tag
              :value="data.user_is_active ? 'Active' : 'Inactive'"
              :severity="data.user_is_active ? 'success' : 'danger'"
              rounded
            />
          </template>
        </Column>
        <Column header="Role">
          <template #body="{ data }">
            <Tag
              v-if="data.is_project_pi"
              value="PI"
              severity="warn"
              rounded
            />
            <span v-else>{{ data.role || '—' }}</span>
          </template>
        </Column>
        <Column header="Resource">
          <template #body="{ data }">
            <span class="font-mono text-xs">{{ data.resource || '—' }}</span>
          </template>
        </Column>
        <Column header="Allocated Resource">
          <template #body="{ data }">
            <span class="font-mono text-xs">{{ data.allocated_resource || '—' }}</span>
          </template>
        </Column>
        <Column header="SU Allocated">
          <template #body="{ data }">
            <span class="font-mono text-xs">{{ formatUnits(data.membership_service_units_allocated) }}</span>
          </template>
        </Column>
        <Column header="SU Remaining">
          <template #body="{ data }">
            <span class="font-mono text-xs">{{ formatUnits(data.membership_service_units_remaining) }}</span>
          </template>
        </Column>
        <Column header="Organization">
          <template #body="{ data }">
            {{ data.organization || '—' }}
          </template>
        </Column>
        <Column header="Department">
          <template #body="{ data }">
            {{ data.department || '—' }}
          </template>
        </Column>
        <Column header="NSF Status">
          <template #body="{ data }">
            {{ data.nsf_status_code || '—' }}
          </template>
        </Column>
        <Column header="DNs">
          <template #body="{ data }">
            {{ (data.dn_list || []).length }}
          </template>
        </Column>
        <Column header="AIME Confirmed">
          <template #body="{ data }">
            <Tag
              :value="confirmationTagValue(data)"
              :severity="confirmationTagSeverity(data)"
              rounded
            />
          </template>
        </Column>
        <Column v-if="showDebugActions" header="Debug">
          <template #body="{ data }">
            <Button
              v-if="canDebugComplete(data.account_state)"
              icon="pi pi-bolt"
              label="Mock OAuth"
              severity="help"
              outlined
              size="small"
              @click="$emit('debug-complete-account', data.project_user_id)"
            />
            <span v-else class="text-xs text-slate-400">--</span>
          </template>
        </Column>
      </DataTable>
    </template>
  </Card>
</template>

<script setup>
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'

function accountStateSeverity(state) {
  if (state === 'aime_notified' || state === 'covered_by_project_notification') return 'success'
  if (state === 'user_completed_oauth') return 'success'
  if (state === 'email_invite_sent') return 'info'
  if (state === 'received') return 'warning'
  // Legacy states
  if (state === 'account_made') return 'success'
  if (state === 'sent_email') return 'info'
  if (state === 'not_sent_email_invite') return 'warning'
  if (state === 'just_received_packet') return 'warning'
  return 'secondary'
}

function formatUnits(value) {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function confirmationTagValue(membership) {
  if (membership?.account_confirmation_required === false) {
    return membership?.aime_confirmation_sent_at
      ? 'Covered by Project Create'
      : 'Project Notify Pending'
  }
  return membership?.aime_confirmation_sent_at ? 'Sent' : 'Pending'
}

function confirmationTagSeverity(membership) {
  if (membership?.account_confirmation_required === false) {
    return membership?.aime_confirmation_sent_at ? 'info' : 'warning'
  }
  return membership?.aime_confirmation_sent_at ? 'success' : 'warning'
}

function canDebugComplete(state) {
  return state === 'received' || state === 'email_invite_sent'
}

defineProps({
  users: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  showDebugActions: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['debug-complete-account'])
</script>
