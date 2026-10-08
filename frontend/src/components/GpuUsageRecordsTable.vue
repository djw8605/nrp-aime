<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <SelectButton
        v-model="selectedStatuses"
        :options="statusOptions"
        optionLabel="label"
        optionValue="value"
        multiple
        :allowEmpty="false"
        size="small"
        aria-label="Filter by status"
      />
      <Button
        icon="pi pi-refresh"
        label="Refresh"
        severity="secondary"
        size="small"
        outlined
        :loading="loading"
        @click="loadRecords"
      />
    </div>

    <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

    <DataTable
      :value="records"
      dataKey="id"
      :loading="loading"
      stripedRows
      size="small"
      tableStyle="min-width: 40rem"
      responsiveLayout="scroll"
    >
      <template #empty>No GPU usage records with the selected status.</template>
      <Column header="Date">
        <template #body="{ data }">{{ data.usage_date }}</template>
      </Column>
      <Column v-if="!projectId" header="Project">
        <template #body="{ data }">
          <router-link
            :to="{ name: 'project-detail', params: { id: data.project_id } }"
            class="text-sky-700 no-underline hover:underline"
          >
            {{ data.project_name }}
          </router-link>
          <p v-if="data.site_project_id" class="m-0 font-mono text-xs text-slate-500">
            {{ data.site_project_id }}
          </p>
        </template>
      </Column>
      <Column header="Username">
        <template #body="{ data }">
          <span class="font-mono text-xs">{{ data.username || '—' }}</span>
        </template>
      </Column>
      <Column header="Attribution">
        <template #body="{ data }">{{ data.attribution }}</template>
      </Column>
      <Column header="GPU hours">
        <template #body="{ data }">{{ formatHours(data.gpu_hours) }}</template>
      </Column>
      <Column header="Status">
        <template #body="{ data }">
          <Tag :value="data.status" :severity="statusSeverity(data.status)" rounded />
        </template>
      </Column>
      <Column header="Attempts">
        <template #body="{ data }">{{ data.attempts }}</template>
      </Column>
      <Column header="Last error">
        <template #body="{ data }">
          <span class="whitespace-pre-wrap break-words text-xs">{{ data.last_error || '—' }}</span>
        </template>
      </Column>
      <Column header="Submitted">
        <template #body="{ data }">{{ formatDateTime(data.submitted_at) }}</template>
      </Column>
    </DataTable>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import { fetchGpuUsageRecords } from '../api/gpuUsage'

const props = defineProps({
  projectId: { type: String, default: null },
})

const statusOptions = [
  { label: 'Failed', value: 'failed' },
  { label: 'Pending', value: 'pending' },
  { label: 'Submitted', value: 'submitted' },
  { label: 'Loaded', value: 'loaded' },
]

const selectedStatuses = ref(['failed'])
const records = ref([])
const loading = ref(false)
const error = ref(null)

function statusSeverity(status) {
  if (status === 'failed') return 'danger'
  if (status === 'submitted') return 'info'
  if (status === 'loaded') return 'success'
  return 'secondary'
}

function formatHours(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function formatDateTime(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

async function loadRecords() {
  loading.value = true
  error.value = null
  try {
    records.value = await fetchGpuUsageRecords({
      statuses: selectedStatuses.value,
      projectId: props.projectId,
    })
  } catch (err) {
    records.value = []
    error.value = err?.response?.data?.detail || err?.message || 'Failed to load GPU usage records.'
  } finally {
    loading.value = false
  }
}

onMounted(loadRecords)
watch(selectedStatuses, loadRecords)
watch(() => props.projectId, loadRecords)
</script>
