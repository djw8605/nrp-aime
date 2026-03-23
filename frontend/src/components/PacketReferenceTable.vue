<template>
  <Card class="border border-slate-200 shadow-sm">
    <template #content>
      <div v-if="loading" class="space-y-3 p-2">
        <Skeleton v-for="n in 4" :key="n" height="2.5rem" borderRadius="0.5rem" />
      </div>
      <Message v-else-if="packets.length === 0" severity="info" :closable="false">
        {{ emptyMessage }}
      </Message>
      <DataTable
        v-else
        :value="packets"
        dataKey="id"
        stripedRows
        size="small"
        responsiveLayout="scroll"
        tableStyle="min-width: 64rem"
      >
        <Column field="packet_type" header="Type" sortable />
        <Column field="packet_rec_id" header="Packet" sortable>
          <template #body="{ data }">
            <router-link
              v-if="data.packet_rec_id"
              :to="{ name: 'packet-logs', query: { q: String(data.packet_rec_id) } }"
              class="text-sky-700 no-underline hover:underline"
            >
              {{ data.packet_rec_id }}
            </router-link>
            <span v-else>—</span>
          </template>
        </Column>
        <Column field="trans_rec_id" header="Trans Rec ID" sortable>
          <template #body="{ data }">
            <router-link
              v-if="data.trans_rec_id"
              :to="{ name: 'packet-logs', query: { q: String(data.trans_rec_id) } }"
              class="text-sky-700 no-underline hover:underline"
            >
              {{ data.trans_rec_id }}
            </router-link>
            <span v-else>—</span>
          </template>
        </Column>
        <Column field="transaction_id" header="Transaction" sortable>
          <template #body="{ data }">
            <router-link
              v-if="data.transaction_id"
              :to="{ name: 'transaction-detail', params: { transactionId: String(data.transaction_id) } }"
              class="text-sky-700 no-underline hover:underline"
            >
              {{ data.transaction_id }}
            </router-link>
            <span v-else>—</span>
          </template>
        </Column>
        <Column field="processing_status" header="Status" sortable>
          <template #body="{ data }">
            <Tag
              :value="data.processing_status"
              :severity="statusSeverity(data.processing_status)"
              rounded
            />
          </template>
        </Column>
        <Column field="ingest_source" header="Source" sortable />
        <Column header="Matched On">
          <template #body="{ data }">
            <div class="flex flex-wrap gap-2">
              <Tag
                v-for="reason in data.matched_on || []"
                :key="reason"
                :value="reason"
                severity="secondary"
                rounded
              />
            </div>
          </template>
        </Column>
        <Column field="received_at" header="Received" sortable>
          <template #body="{ data }">
            {{ formatDate(data.received_at) }}
          </template>
        </Column>
        <Column field="processed_at" header="Processed" sortable>
          <template #body="{ data }">
            {{ formatDate(data.processed_at) }}
          </template>
        </Column>
        <Column header="Error">
          <template #body="{ data }">
            <span class="line-clamp-2 text-sm text-slate-700">{{ data.processing_error || '—' }}</span>
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

defineProps({
  packets: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  emptyMessage: {
    type: String,
    default: 'No related packets found.',
  },
})

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function statusSeverity(status) {
  if (status === 'processed') return 'success'
  if (status === 'unprocessed') return 'warning'
  if (status === 'error') return 'danger'
  return 'info'
}
</script>
