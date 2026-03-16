<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">
          Transaction {{ transactionId }}
        </h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Transaction-centric packet status and replay controls.
        </p>
      </div>
      <div class="flex gap-2">
        <router-link :to="{ name: 'packet-logs' }" class="no-underline">
          <Button icon="pi pi-arrow-left" label="Back To Packet Log" severity="secondary" />
        </router-link>
        <Button
          icon="pi pi-refresh"
          label="Reload"
          severity="secondary"
          outlined
          :loading="loading"
          @click="loadTransaction"
        />
        <Button
          icon="pi pi-replay"
          label="Replay Transaction"
          :loading="replayLoading"
          @click="handleReplayTransaction"
        />
      </div>
    </div>

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
    <Message v-if="message" severity="success" :closable="false">{{ message }}</Message>

    <Card v-if="transaction" class="border border-slate-200/80 shadow-sm">
      <template #content>
        <div class="grid grid-cols-1 gap-3 text-sm md:grid-cols-4">
          <p class="m-0"><strong>State:</strong> {{ transaction.current_state }}</p>
          <p class="m-0"><strong>Packets:</strong> {{ transaction.packet_count }}</p>
          <p class="m-0"><strong>Trans Rec ID:</strong> {{ transaction.trans_rec_id ?? '—' }}</p>
          <p class="m-0"><strong>Reply Eligible:</strong> {{ transaction.reply_eligible ? 'Yes' : 'No' }}</p>
        </div>
        <div class="mt-3">
          <p class="m-0 mb-1 text-sm font-semibold text-slate-700">Pending Actions</p>
          <ul class="m-0 ml-5 text-sm text-slate-600">
            <li v-for="action in transaction.pending_actions" :key="action">{{ action }}</li>
            <li v-if="!transaction.pending_actions?.length">None</li>
          </ul>
        </div>
      </template>
    </Card>

    <Card class="border border-slate-200/80 shadow-sm">
      <template #title>Packets In Transaction</template>
      <template #content>
        <DataTable
          v-if="transaction?.packets?.length"
          :value="transaction.packets"
          dataKey="id"
          stripedRows
          size="small"
          responsiveLayout="scroll"
          tableStyle="min-width: 72rem"
        >
          <Column field="packet_rec_id" header="Packet Rec ID" />
          <Column field="packet_type" header="Type" />
          <Column field="processing_status" header="Status" />
          <Column field="received_at" header="Received">
            <template #body="{ data }">{{ formatDate(data.received_at) }}</template>
          </Column>
          <Column field="processed_at" header="Processed">
            <template #body="{ data }">{{ formatDate(data.processed_at) }}</template>
          </Column>
          <Column header="Error">
            <template #body="{ data }">
              <span class="line-clamp-2 text-sm text-slate-700">{{ data.processing_error || '—' }}</span>
            </template>
          </Column>
          <Column header="Controls">
            <template #body="{ data }">
              <div class="flex flex-wrap gap-2">
                <Button
                  icon="pi pi-refresh"
                  label="Re-ingest"
                  text
                  size="small"
                  :loading="reingestInProgressId === data.id"
                  @click="handleReingest(data.id)"
                />
                <Button
                  icon="pi pi-eye"
                  label="Raw"
                  text
                  size="small"
                  @click="openRawPacket(data)"
                />
              </div>
            </template>
          </Column>
        </DataTable>
        <Message v-else severity="info" :closable="false">
          No packets found for this transaction.
        </Message>
      </template>
    </Card>

    <Dialog
      v-model:visible="packetDialogVisible"
      modal
      header="Packet Contents"
      :style="{ width: '85vw', maxWidth: '1000px' }"
    >
      <pre class="m-0 max-h-[70vh] overflow-auto rounded-lg border border-slate-200 bg-slate-950 p-3 text-xs leading-relaxed text-slate-100">{{ selectedPacketRaw }}</pre>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import { fetchTransactionSummary, reingestPacket, replayTransaction } from '../api/packets'

const route = useRoute()
const loading = ref(false)
const replayLoading = ref(false)
const reingestInProgressId = ref(null)
const error = ref(null)
const message = ref(null)
const transaction = ref(null)
const packetDialogVisible = ref(false)
const selectedPacketRaw = ref('{}')

const transactionId = computed(() => route.params.transactionId)

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function openRawPacket(packet) {
  selectedPacketRaw.value = JSON.stringify(packet.raw_packet || {}, null, 2)
  packetDialogVisible.value = true
}

async function loadTransaction() {
  loading.value = true
  error.value = null
  try {
    transaction.value = await fetchTransactionSummary(transactionId.value)
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to load transaction.'
  } finally {
    loading.value = false
  }
}

async function handleReplayTransaction() {
  replayLoading.value = true
  error.value = null
  message.value = null
  try {
    const result = await replayTransaction(transactionId.value)
    message.value = `Replay completed: ${result.handled} handled, ${result.failed_or_skipped} failed/skipped.`
    await loadTransaction()
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to replay transaction.'
  } finally {
    replayLoading.value = false
  }
}

async function handleReingest(packetId) {
  reingestInProgressId.value = packetId
  error.value = null
  message.value = null
  try {
    const result = await reingestPacket(packetId)
    message.value = result.detail || `Re-ingest status: ${result.processing_status}`
    await loadTransaction()
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to re-ingest packet.'
  } finally {
    reingestInProgressId.value = null
  }
}

onMounted(async () => {
  await loadTransaction()
})
</script>
