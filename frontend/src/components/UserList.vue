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
        dataKey="id"
        stripedRows
        size="small"
        tableStyle="min-width: 20rem"
        responsiveLayout="scroll"
      >
        <Column field="name" header="Name" />
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
            {{ data.role || '—' }}
          </template>
        </Column>
        <Column header="Resource">
          <template #body="{ data }">
            <span class="font-mono text-xs">{{ data.resource || '—' }}</span>
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
              :value="data.aime_confirmation_sent_at ? 'Sent' : 'Pending'"
              :severity="data.aime_confirmation_sent_at ? 'success' : 'warning'"
              rounded
            />
          </template>
        </Column>
      </DataTable>
    </template>
  </Card>
</template>

<script setup>
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'

function accountStateSeverity(state) {
  if (state === 'account_made') return 'success'
  if (state === 'sent_email') return 'info'
  if (state === 'just_received_packet') return 'warning'
  return 'secondary'
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
})
</script>
