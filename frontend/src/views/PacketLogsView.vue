<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">Packet Log</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Full stream of received packets with processing status.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button
          :icon="threaded ? 'pi pi-list' : 'pi pi-sitemap'"
          :label="threaded ? 'Flat View' : 'Threaded View'"
          :severity="threaded ? 'primary' : 'secondary'"
          outlined
          @click="toggleThreaded"
        />
        <Button
          icon="pi pi-refresh"
          label="Refresh"
          :loading="loading"
          severity="secondary"
          @click="loadPackets"
        />
      </div>
    </div>

    <Message v-if="error" severity="error" :closable="false">
      {{ error }}
    </Message>
    <Message v-if="message" severity="success" :closable="false">
      {{ message }}
    </Message>

    <Card class="border border-slate-200/80 shadow-sm">
      <template #content>
        <div class="mb-4 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto_auto]">
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
          <select
            v-model="directionFilter"
            class="h-[42px] rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-700"
          >
            <option value="">All directions</option>
            <option value="incoming">Incoming</option>
            <option value="outgoing">Outgoing</option>
          </select>
          <div class="flex gap-2">
            <Button label="Apply" icon="pi pi-search" @click="applyFilters" />
            <Button label="Clear" severity="secondary" outlined @click="clearFilters" />
          </div>
        </div>

        <DataTable
          :value="displayPackets"
          dataKey="id"
          :stripedRows="!threaded"
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
          :sortField="threaded ? null : sortBy"
          :sortOrder="threaded ? null : primeSortOrder"
          @page="onPage"
          @sort="onSort"
          :rowClass="threadRowClass"
        >
          <Column v-if="threaded" header="Thread" style="width: 3rem">
            <template #body="{ data }">
              <div
                v-if="data._threadInfo"
                class="flex items-center gap-1"
              >
                <span
                  class="inline-block h-full w-1 rounded"
                  :style="{ backgroundColor: data._threadInfo.color, minHeight: '24px' }"
                ></span>
                <span
                  v-if="data._threadInfo.isFirst"
                  class="text-xs font-semibold"
                  :style="{ color: data._threadInfo.color }"
                >
                  {{ data._threadInfo.size }} pkt{{ data._threadInfo.size > 1 ? 's' : '' }}
                </span>
              </div>
            </template>
          </Column>
          <Column field="received_at" header="Received" :sortable="!threaded">
            <template #body="{ data }">
              {{ formatDate(data.received_at) }}
            </template>
          </Column>
          <Column field="processing_status" header="Status" :sortable="!threaded">
            <template #body="{ data }">
              <Tag
                :value="data.processing_status"
                :severity="statusSeverity(data.processing_status)"
                rounded
              />
            </template>
          </Column>
          <Column field="outgoing_flag" header="Direction">
            <template #body="{ data }">
              <Tag
                :value="data.outgoing_flag ? 'Outgoing' : 'Incoming'"
                :severity="data.outgoing_flag ? 'warning' : 'info'"
                rounded
              />
            </template>
          </Column>
          <Column field="packet_type" header="Type" :sortable="!threaded" />
          <Column field="packet_rec_id" header="Packet Rec ID" :sortable="!threaded" />
          <Column field="trans_rec_id" header="Trans Rec ID" :sortable="!threaded">
            <template #body="{ data }">
              <Button
                v-if="data.trans_rec_id"
                :label="String(data.trans_rec_id)"
                text
                size="small"
                @click="filterByTransRecId(data.trans_rec_id)"
              />
              <span v-else>—</span>
            </template>
          </Column>
          <Column field="transaction_id" header="Transaction ID" :sortable="!threaded">
            <template #body="{ data }">
              <Button
                v-if="data.transaction_id"
                :label="String(data.transaction_id)"
                text
                size="small"
                @click="openTransaction(data.transaction_id)"
              />
              <span v-else>—</span>
            </template>
          </Column>
          <Column field="processed_at" header="Processed At" :sortable="!threaded">
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
                <Button
                  icon="pi pi-refresh"
                  label="Re-ingest"
                  size="small"
                  text
                  :loading="reingestInProgressId === data.id"
                  @click="handleReingest(data.id)"
                />
                <Button
                  icon="pi pi-pencil"
                  label="Manual Input"
                  size="small"
                  text
                  @click="openManualInput(data)"
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
          <p class="m-0"><strong>Direction:</strong> {{ selectedPacket.outgoing_flag ? 'Outgoing' : 'Incoming' }}</p>
          <p class="m-0"><strong>Packet Rec ID:</strong> {{ selectedPacket.packet_rec_id ?? '—' }}</p>
          <p class="m-0"><strong>Trans Rec ID:</strong> {{ selectedPacket.trans_rec_id ?? '—' }}</p>
          <p class="m-0"><strong>Transaction ID:</strong> {{ selectedPacket.transaction_id ?? '—' }}</p>
          <p class="m-0"><strong>Received:</strong> {{ formatDate(selectedPacket.received_at) }}</p>
        </div>
        <div class="rounded-lg border border-slate-200 bg-slate-950 p-3">
          <pre class="m-0 overflow-auto text-xs leading-relaxed text-slate-100">{{ prettyPacket(selectedPacket.raw_packet) }}</pre>
        </div>
        <div class="flex justify-end">
          <Button
            icon="pi pi-pencil"
            label="Use For Manual Input"
            @click="openManualInput(selectedPacket)"
          />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { fetchPacketLogs, reingestPacket } from '../api/packets'

const router = useRouter()
const route = useRoute()

const packets = ref([])
const totalRecords = ref(0)
const loading = ref(false)
const error = ref(null)
const message = ref(null)
const packetDialogVisible = ref(false)
const selectedPacket = ref(null)
const reingestInProgressId = ref(null)

const page = ref(1)
const pageSize = ref(100)
const sortBy = ref('received_at')
const sortOrder = ref('desc')
const searchInput = ref('')
const searchValue = ref('')
const statusFilter = ref('')
const statusValue = ref('')
const directionFilter = ref('')
const directionValue = ref('')
const threaded = ref(false)

const firstRow = computed(() => (page.value - 1) * pageSize.value)
const primeSortOrder = computed(() => (sortOrder.value === 'asc' ? 1 : -1))

// Thread colors for visual grouping (alternating palette)
const THREAD_COLORS = [
  '#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b',
  '#ef4444', '#ec4899', '#6366f1', '#14b8a6', '#f97316',
]

/**
 * Augment packet list with threading metadata when in threaded mode.
 * Each packet gets a _threadInfo with: color, isFirst, size.
 */
const displayPackets = computed(() => {
  const items = packets.value
  if (!threaded.value || !items.length) return items

  // Build thread groups by trans_rec_id
  const threadGroups = new Map()
  for (const pkt of items) {
    const key = pkt.trans_rec_id
    if (key === null || key === undefined) continue
    if (!threadGroups.has(key)) {
      threadGroups.set(key, [])
    }
    threadGroups.get(key).push(pkt.id)
  }

  // Assign colors to threads (round-robin)
  const threadColorMap = new Map()
  let colorIdx = 0
  for (const [key, ids] of threadGroups) {
    if (ids.length > 1) {
      threadColorMap.set(key, THREAD_COLORS[colorIdx % THREAD_COLORS.length])
      colorIdx++
    }
  }

  // Track which group IDs we have already marked as "first"
  const seenFirst = new Set()

  return items.map((pkt) => {
    const key = pkt.trans_rec_id
    const group = (key !== null && key !== undefined) ? threadGroups.get(key) : null
    if (!group || group.length <= 1) return pkt

    const isFirst = !seenFirst.has(key)
    if (isFirst) seenFirst.add(key)

    return {
      ...pkt,
      _threadInfo: {
        color: threadColorMap.get(key) || '#94a3b8',
        isFirst,
        size: group.length,
      },
    }
  })
})

function threadRowClass(data) {
  if (!threaded.value || !data._threadInfo) return ''
  return 'threaded-row'
}

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

function openTransaction(transactionId) {
  if (!transactionId) return
  router.push({
    name: 'transaction-detail',
    params: { transactionId: String(transactionId) },
  })
}

function filterByTransRecId(transRecId) {
  if (!transRecId) return
  searchInput.value = String(transRecId)
  applyFilters()
}

function openManualInput(packet) {
  if (!packet?.id) return
  router.push({
    name: 'manual-packet-input',
    query: { packetId: packet.id },
  })
}

function toggleThreaded() {
  threaded.value = !threaded.value
  page.value = 1
  loadPackets()
}

async function handleReingest(packetId) {
  if (!packetId) return
  reingestInProgressId.value = packetId
  error.value = null
  message.value = null
  try {
    const result = await reingestPacket(packetId)
    message.value = result.detail || `Packet ${result.packet_rec_id} re-ingested.`
    await loadPackets()
  } catch (err) {
    error.value = err?.response?.data?.detail || 'Failed to re-ingest packet.'
  } finally {
    reingestInProgressId.value = null
  }
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
      direction: directionValue.value,
      threaded: threaded.value,
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

function syncFiltersFromRoute() {
  const routeQuery = typeof route.query.q === 'string' ? route.query.q : ''
  const routeStatus = typeof route.query.status === 'string' ? route.query.status : ''
  const routeDirection = typeof route.query.direction === 'string' ? route.query.direction : ''
  const routeThreaded = route.query.threaded === 'true'
  searchInput.value = routeQuery
  searchValue.value = routeQuery
  statusFilter.value = routeStatus
  statusValue.value = routeStatus
  directionFilter.value = routeDirection
  directionValue.value = routeDirection
  threaded.value = routeThreaded
  page.value = 1
}

function onPage(event) {
  page.value = event.page + 1
  pageSize.value = event.rows
  loadPackets()
}

function onSort(event) {
  if (threaded.value) return
  sortBy.value = event.sortField || 'received_at'
  sortOrder.value = event.sortOrder === 1 ? 'asc' : 'desc'
  page.value = 1
  loadPackets()
}

function applyFilters() {
  searchValue.value = searchInput.value.trim()
  statusValue.value = statusFilter.value
  directionValue.value = directionFilter.value
  page.value = 1
  router.replace({
    query: {
      q: searchValue.value || undefined,
      status: statusValue.value || undefined,
      direction: directionValue.value || undefined,
      threaded: threaded.value ? 'true' : undefined,
    },
  })
  loadPackets()
}

function clearFilters() {
  searchInput.value = ''
  statusFilter.value = ''
  directionFilter.value = ''
  searchValue.value = ''
  statusValue.value = ''
  directionValue.value = ''
  threaded.value = false
  page.value = 1
  router.replace({ query: {} })
  loadPackets()
}

onMounted(async () => {
  syncFiltersFromRoute()
  await loadPackets()
})

watch(
  () => [route.query.q, route.query.status, route.query.direction, route.query.threaded],
  async () => {
    syncFiltersFromRoute()
    await loadPackets()
  },
)
</script>
