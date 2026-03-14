<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">Packet Log</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Full stream of received packets with processing status.
        </p>
      </div>
      <Button
        icon="pi pi-refresh"
        label="Refresh"
        :loading="loading"
        severity="secondary"
        @click="loadPackets"
      />
    </div>

    <Message v-if="error" severity="error" :closable="false">
      {{ error }}
    </Message>

    <Card class="border border-slate-200/80 shadow-sm">
      <template #content>
        <div class="mb-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto]">
          <InputText
            v-model="searchInput"
            placeholder="Search packet type, IDs, status, or raw payload..."
            @keyup.enter="applyFilters"
          />
          <select
            v-model="statusFilter"
            class="h-[42px] rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-700"
          >
            <option value="">All statuses</option>
            <option value="processed">Processed</option>
            <option value="unprocessed">Unprocessed</option>
            <option value="error">Error</option>
            <option value="received">Received</option>
          </select>
          <div class="flex gap-2">
            <Button label="Apply" icon="pi pi-search" @click="applyFilters" />
            <Button label="Clear" severity="secondary" outlined @click="clearFilters" />
          </div>
        </div>

        <DataTable
          :value="packets"
          dataKey="id"
          stripedRows
          size="small"
          responsiveLayout="scroll"
          tableStyle="min-width: 78rem"
          paginator
          lazy
          :rows="pageSize"
          :totalRecords="totalRecords"
          :rowsPerPageOptions="[25, 50, 100, 200]"
          :first="firstRow"
          :loading="loading"
          :sortField="sortBy"
          :sortOrder="primeSortOrder"
          @page="onPage"
          @sort="onSort"
        >
          <Column field="received_at" header="Received" sortable>
            <template #body="{ data }">
              {{ formatDate(data.received_at) }}
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
          <Column field="packet_type" header="Type" sortable />
          <Column field="packet_rec_id" header="Packet Rec ID" sortable />
          <Column field="trans_rec_id" header="Trans Rec ID" sortable />
          <Column field="transaction_id" header="Transaction ID" sortable />
          <Column field="processed_at" header="Processed At" sortable>
            <template #body="{ data }">
              {{ formatDate(data.processed_at) }}
            </template>
          </Column>
          <Column header="Processed">
            <template #body="{ data }">
              <Tag
                :value="data.processed ? 'Yes' : 'No'"
                :severity="data.processed ? 'success' : 'warning'"
                rounded
              />
            </template>
          </Column>
          <Column header="Error">
            <template #body="{ data }">
              <span class="line-clamp-2 text-sm text-slate-700">{{ data.processing_error || '—' }}</span>
            </template>
          </Column>
          <Column header="Packet Contents">
            <template #body="{ data }">
              <div class="space-y-1">
                <p class="m-0 max-w-[30rem] truncate font-mono text-xs text-slate-700">
                  {{ packetPreview(data.raw_packet) }}
                </p>
                <Button
                  icon="pi pi-eye"
                  label="View"
                  size="small"
                  text
                  @click="openPacket(data)"
                />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>

    <Dialog
      v-model:visible="packetDialogVisible"
      modal
      header="Packet Contents"
      :style="{ width: '85vw', maxWidth: '1000px' }"
    >
      <div v-if="selectedPacket" class="space-y-3">
        <div class="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
          <p class="m-0"><strong>Type:</strong> {{ selectedPacket.packet_type || 'unknown' }}</p>
          <p class="m-0"><strong>Status:</strong> {{ selectedPacket.processing_status }}</p>
          <p class="m-0"><strong>Packet Rec ID:</strong> {{ selectedPacket.packet_rec_id ?? '—' }}</p>
          <p class="m-0"><strong>Received:</strong> {{ formatDate(selectedPacket.received_at) }}</p>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-950 p-3">
          <pre class="m-0 overflow-auto text-xs leading-relaxed text-slate-100">{{ prettyPacket(selectedPacket.raw_packet) }}</pre>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { fetchPacketLogs } from '../api/packets'

const packets = ref([])
const totalRecords = ref(0)
const loading = ref(false)
const error = ref(null)
const packetDialogVisible = ref(false)
const selectedPacket = ref(null)

const page = ref(1)
const pageSize = ref(100)
const sortBy = ref('received_at')
const sortOrder = ref('desc')
const searchInput = ref('')
const searchValue = ref('')
const statusFilter = ref('')
const statusValue = ref('')

const firstRow = computed(() => (page.value - 1) * pageSize.value)
const primeSortOrder = computed(() => (sortOrder.value === 'asc' ? 1 : -1))

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function prettyPacket(packet) {
  try {
    return JSON.stringify(packet, null, 2)
  } catch {
    return String(packet)
  }
}

function packetPreview(packet) {
  try {
    const text = JSON.stringify(packet)
    return text.length > 180 ? `${text.slice(0, 180)}...` : text
  } catch {
    return String(packet)
  }
}

function statusSeverity(status) {
  if (status === 'processed') return 'success'
  if (status === 'unprocessed') return 'warning'
  if (status === 'error') return 'danger'
  return 'info'
}

function openPacket(packet) {
  selectedPacket.value = packet
  packetDialogVisible.value = true
}

async function loadPackets() {
  loading.value = true
  error.value = null
  try {
    const result = await fetchPacketLogs({
      page: page.value,
      pageSize: pageSize.value,
      sortBy: sortBy.value,
      sortOrder: sortOrder.value,
      q: searchValue.value,
      status: statusValue.value,
    })
    packets.value = result.items || []
    totalRecords.value = result.total || 0
    page.value = result.page || page.value
    pageSize.value = result.page_size || pageSize.value
  } catch {
    error.value = 'Failed to load packet logs.'
  } finally {
    loading.value = false
  }
}

function onPage(event) {
  page.value = event.page + 1
  pageSize.value = event.rows
  loadPackets()
}

function onSort(event) {
  sortBy.value = event.sortField || 'received_at'
  sortOrder.value = event.sortOrder === 1 ? 'asc' : 'desc'
  page.value = 1
  loadPackets()
}

function applyFilters() {
  searchValue.value = searchInput.value.trim()
  statusValue.value = statusFilter.value
  page.value = 1
  loadPackets()
}

function clearFilters() {
  searchInput.value = ''
  statusFilter.value = ''
  searchValue.value = ''
  statusValue.value = ''
  page.value = 1
  loadPackets()
}

onMounted(async () => {
  await loadPackets()
})
</script>
