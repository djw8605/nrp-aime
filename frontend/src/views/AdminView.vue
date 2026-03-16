<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">
          Operations & Administration
        </h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Backend observability, packet operations, and audit controls.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Menu ref="debugMenu" :model="debugMenuItems" popup />
        <Button
          icon="pi pi-refresh"
          label="Refresh"
          severity="secondary"
          outlined
          :loading="loading"
          @click="loadAdminData"
        />
        <Button
          icon="pi pi-bug"
          label="Debug"
          severity="secondary"
          :loading="demoLoading"
          outlined
          @click="toggleDebugMenu"
        />
        <Button
          icon="pi pi-shield"
          label="Run Audit"
          severity="warning"
          :loading="auditLoading"
          @click="handleRunAudit"
        />
      </div>
    </div>

    <Message v-if="auditError" severity="error" :closable="false">
      {{ auditError }}
    </Message>
    <Message v-if="demoError" severity="error" :closable="false">
      {{ demoError }}
    </Message>
    <Message v-if="demoMessage" severity="success" :closable="false">
      {{ demoMessage }}
    </Message>

    <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <Card
        v-for="kpi in adminKpis"
        :key="kpi.label"
        class="border border-slate-200/80 shadow-sm"
      >
        <template #content>
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="m-0 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {{ kpi.label }}
              </p>
              <p class="mt-2 text-2xl font-semibold text-slate-800">
                {{ kpi.value }}
              </p>
            </div>
            <i :class="`pi ${kpi.icon} text-xl ${kpi.iconClass}`"></i>
          </div>
        </template>
      </Card>
    </div>

    <Card v-if="auditReport" class="border border-slate-200/80 shadow-sm">
      <template #title>
        <div class="flex items-center justify-between gap-2">
          <span class="text-lg font-semibold text-slate-800">Audit Result</span>
          <Tag
            :value="auditReport.status.toUpperCase()"
            :severity="auditSeverity(auditReport.status)"
            rounded
          />
        </div>
      </template>
      <template #content>
        <p class="m-0 mb-3 text-sm text-slate-500">
          Last checked: {{ formatCheckedAt(auditReport.checked_at) }}
        </p>
        <div class="space-y-2">
          <div
            v-for="check in auditReport.checks"
            :key="check.service"
            class="rounded-xl border border-slate-200 bg-slate-50 p-3"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <p class="m-0 text-sm font-semibold uppercase tracking-wide text-slate-700">
                {{ check.service }}
              </p>
              <Tag
                :value="check.status.toUpperCase()"
                :severity="auditSeverity(check.status)"
                rounded
              />
            </div>
            <p class="m-0 mt-1 text-sm text-slate-600">
              {{ check.summary }}
            </p>
          </div>
        </div>
      </template>
    </Card>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card class="border border-slate-200/80 shadow-sm">
        <template #title>Data Freshness</template>
        <template #content>
          <div class="space-y-1 text-sm text-slate-700">
            <p class="m-0">
              <strong>Packet Poll:</strong>
              {{ formatCheckedAt(freshness?.last_successful_packet_poll_at || freshness?.aime_worker_last_success_at) }}
            </p>
            <p class="m-0">
              <strong>Usage Export:</strong>
              {{ formatCheckedAt(freshness?.last_successful_usage_export_at || freshness?.usage_worker_last_success_at) }}
            </p>
            <p class="m-0">
              <strong>Account Confirmation Sync:</strong>
              {{ formatCheckedAt(freshness?.last_successful_account_confirmation_sync_at) }}
            </p>
          </div>
        </template>
      </Card>

      <Card class="border border-slate-200/80 shadow-sm">
        <template #title>Error Budget</template>
        <template #content>
          <div class="grid grid-cols-2 gap-2 text-sm text-slate-700">
            <p class="m-0"><strong>Total Packets:</strong> {{ errorBudget?.total_packets ?? 0 }}</p>
            <p class="m-0"><strong>Manual Ingest:</strong> {{ errorBudget?.manual_ingest_count ?? 0 }}</p>
            <p class="m-0"><strong>Unsupported:</strong> {{ errorBudget?.unsupported_packet_count ?? 0 }}</p>
            <p class="m-0"><strong>Parse Failures:</strong> {{ errorBudget?.parse_failures_total ?? 0 }}</p>
            <p class="m-0"><strong>Unprocessed:</strong> {{ errorBudget?.unprocessed_packet_count ?? 0 }}</p>
            <p class="m-0"><strong>Outbound Failures:</strong> {{ errorBudget?.outbound_failures ?? 0 }}</p>
          </div>
        </template>
      </Card>
    </div>

    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card class="border border-slate-200/80 shadow-sm">
        <template #title>Lifecycle Funnel</template>
        <template #content>
          <div class="grid grid-cols-2 gap-2 text-sm text-slate-700">
            <p class="m-0"><strong>Just Received:</strong> {{ lifecycleFunnel?.just_received_packet ?? 0 }}</p>
            <p class="m-0"><strong>Sent Email:</strong> {{ lifecycleFunnel?.sent_email ?? 0 }}</p>
            <p class="m-0"><strong>Account Made:</strong> {{ lifecycleFunnel?.account_made ?? 0 }}</p>
            <p class="m-0"><strong>Notify Sent:</strong> {{ lifecycleFunnel?.notify_account_create_sent ?? 0 }}</p>
          </div>
        </template>
      </Card>

      <Card class="border border-slate-200/80 shadow-sm">
        <template #title>Queue / Latency (seconds)</template>
        <template #content>
          <div class="grid grid-cols-1 gap-1 text-sm text-slate-700">
            <p class="m-0"><strong>Avg To Project Completion:</strong> {{ formatUsage(queueLatency?.avg_seconds_to_project_completion) }}</p>
            <p class="m-0"><strong>Avg To User Completion:</strong> {{ formatUsage(queueLatency?.avg_seconds_to_user_completion) }}</p>
            <p class="m-0"><strong>Avg To Email Sent:</strong> {{ formatUsage(queueLatency?.avg_seconds_to_email_sent) }}</p>
            <p class="m-0"><strong>Avg To Account Made:</strong> {{ formatUsage(queueLatency?.avg_seconds_to_account_made) }}</p>
            <p class="m-0"><strong>Avg To Notify Sent:</strong> {{ formatUsage(queueLatency?.avg_seconds_to_notify_account_create_sent) }}</p>
            <p class="m-0"><strong>Pending Email Queue:</strong> {{ queueLatency?.pending_email_queue ?? 0 }}</p>
            <p class="m-0"><strong>Pending Confirmation Queue:</strong> {{ queueLatency?.pending_confirmation_queue ?? 0 }}</p>
          </div>
        </template>
      </Card>
    </div>

    <Card class="border border-slate-200/80 shadow-sm">
      <template #title>Worker Observability</template>
      <template #content>
        <div v-if="!workerStatuses.length" class="text-sm text-slate-500">
          No worker status rows available yet.
        </div>
        <div v-else class="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="worker in workerStatuses"
            :key="worker.worker_name"
            class="rounded-xl border border-slate-200 bg-slate-50 p-3"
          >
            <div class="mb-1 flex items-center justify-between">
              <p class="m-0 text-sm font-semibold text-slate-800">{{ worker.worker_name }}</p>
              <Tag :value="worker.current_state" :severity="worker.current_state === 'error' ? 'danger' : 'info'" rounded />
            </div>
            <p class="m-0 text-xs text-slate-600">Active: {{ worker.is_active ? 'Yes' : 'No' }}</p>
            <p class="m-0 text-xs text-slate-600">Heartbeat Lag: {{ worker.heartbeat_lag_seconds ?? '—' }}s</p>
            <p class="m-0 text-xs text-slate-600">Last Success: {{ formatCheckedAt(worker.last_success_at) }}</p>
            <p class="m-0 text-xs text-slate-600">Last Error: {{ formatCheckedAt(worker.last_error_at) }}</p>
            <p class="m-0 mt-1 text-xs text-slate-700">{{ worker.last_error_message || worker.status_message || '—' }}</p>
          </div>
        </div>
      </template>
    </Card>

    <Card class="border border-slate-200/80 shadow-sm">
      <template #title>Outbound Packet Tracking</template>
      <template #content>
        <div v-if="!outboundPackets.length" class="text-sm text-slate-500">
          No outbound packet rows yet.
        </div>
        <div v-else class="overflow-auto">
          <table class="min-w-full border-collapse text-sm">
            <thead>
              <tr class="border-b border-slate-200 text-left text-slate-600">
                <th class="px-2 py-2">Event</th>
                <th class="px-2 py-2">Status</th>
                <th class="px-2 py-2">Ack</th>
                <th class="px-2 py-2">Retries</th>
                <th class="px-2 py-2">Source Packet</th>
                <th class="px-2 py-2">Outbound Packet</th>
                <th class="px-2 py-2">Last Error</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in outboundPackets"
                :key="row.id"
                class="border-b border-slate-100 align-top"
              >
                <td class="px-2 py-2">{{ row.event_type }}</td>
                <td class="px-2 py-2">{{ row.status }}</td>
                <td class="px-2 py-2">{{ row.ack_status }}</td>
                <td class="px-2 py-2">{{ row.retry_count }}/{{ row.max_retries }}</td>
                <td class="px-2 py-2">{{ row.source_packet_rec_id ?? '—' }}</td>
                <td class="px-2 py-2">{{ row.outbound_packet_rec_id ?? '—' }}</td>
                <td class="px-2 py-2">
                  <span class="line-clamp-2">{{ row.last_error || '—' }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Menu from 'primevue/menu'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import {
  refreshAccountingStubs,
  runAudit,
  sendDemoPacket,
  syncPortalNamespaceMemberships,
} from '../api/projects'
import {
  evaluateAlerts,
  fetchErrorBudgetMetrics,
  fetchFreshness,
  fetchLifecycleFunnelMetrics,
  fetchOutboundPacketLogs,
  fetchQueueLatencyMetrics,
  fetchWorkerStatuses,
} from '../api/ops'

const router = useRouter()
const loading = ref(false)
const auditLoading = ref(false)
const demoLoading = ref(false)
const debugMenu = ref(null)
const demoError = ref(null)
const demoMessage = ref(null)
const auditError = ref(null)
const auditReport = ref(null)
const workerStatuses = ref([])
const freshness = ref(null)
const errorBudget = ref(null)
const lifecycleFunnel = ref(null)
const queueLatency = ref(null)
const outboundPackets = ref([])

function formatUsage(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatCheckedAt(value) {
  if (!value) return 'unknown'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return value
  }
}

function auditSeverity(status) {
  if (status === 'ok') return 'success'
  if (status === 'warn') return 'warning'
  if (status === 'error') return 'danger'
  return 'contrast'
}

const staleWorkers = computed(
  () =>
    workerStatuses.value.filter((worker) => Number(worker.heartbeat_lag_seconds || 0) > 300)
      .length,
)

const adminKpis = computed(() => [
  {
    label: 'Stale Workers',
    value: staleWorkers.value.toLocaleString(),
    icon: 'pi-exclamation-triangle',
    iconClass: staleWorkers.value > 0 ? 'text-amber-600' : 'text-emerald-600',
  },
  {
    label: 'Parse Failures',
    value: Number(errorBudget.value?.parse_failures_total || 0).toLocaleString(),
    icon: 'pi-times-circle',
    iconClass: 'text-rose-600',
  },
  {
    label: 'Outbound Failures',
    value: Number(errorBudget.value?.outbound_failures || 0).toLocaleString(),
    icon: 'pi-send',
    iconClass: 'text-indigo-600',
  },
])

function toggleDebugMenu(event) {
  debugMenu.value?.toggle(event)
}

async function loadAdminData() {
  loading.value = true
  try {
    const [
      workersResponse,
      freshnessResponse,
      errorBudgetResponse,
      lifecycleResponse,
      queueLatencyResponse,
      outboundResponse,
    ] = await Promise.allSettled([
      fetchWorkerStatuses(),
      fetchFreshness(),
      fetchErrorBudgetMetrics(),
      fetchLifecycleFunnelMetrics(),
      fetchQueueLatencyMetrics(),
      fetchOutboundPacketLogs(100),
    ])
    if (workersResponse.status === 'fulfilled') {
      workerStatuses.value = workersResponse.value.workers || []
    }
    if (freshnessResponse.status === 'fulfilled') {
      freshness.value = freshnessResponse.value
    }
    if (errorBudgetResponse.status === 'fulfilled') {
      errorBudget.value = errorBudgetResponse.value
    }
    if (lifecycleResponse.status === 'fulfilled') {
      lifecycleFunnel.value = lifecycleResponse.value
    }
    if (queueLatencyResponse.status === 'fulfilled') {
      queueLatency.value = queueLatencyResponse.value
    }
    if (outboundResponse.status === 'fulfilled') {
      outboundPackets.value = outboundResponse.value.items || []
    }
  } finally {
    loading.value = false
  }
}

async function handleRunAudit() {
  auditLoading.value = true
  auditError.value = null
  try {
    auditReport.value = await runAudit()
  } catch {
    auditError.value = 'Failed to run audit. Please try again later.'
  } finally {
    auditLoading.value = false
  }
}

async function handleSendDemoPacket(scenario = 'project_and_account') {
  demoLoading.value = true
  demoError.value = null
  demoMessage.value = null
  try {
    const result = await sendDemoPacket(scenario)
    demoMessage.value = `${result.message} (transaction ${result.trans_rec_id})`
    await loadAdminData()
  } catch {
    demoError.value = 'Failed to send demo packet. Please try again later.'
  } finally {
    demoLoading.value = false
  }
}

async function handleEvaluateAlerts() {
  demoLoading.value = true
  demoError.value = null
  demoMessage.value = null
  try {
    const result = await evaluateAlerts()
    demoMessage.value = `Alert evaluation completed (${(result.results || []).length} alert actions).`
    await loadAdminData()
  } catch {
    demoError.value = 'Failed to evaluate alerts.'
  } finally {
    demoLoading.value = false
  }
}

async function handleRefreshAccountingStubs() {
  demoLoading.value = true
  demoError.value = null
  demoMessage.value = null
  try {
    const result = await refreshAccountingStubs()
    demoMessage.value = `Accounting stubs refreshed (${result.updated ?? 0} created, ${result.skipped ?? 0} skipped).`
  } catch {
    demoError.value = 'Failed to refresh accounting stubs.'
  } finally {
    demoLoading.value = false
  }
}

async function handlePortalSync(applyChanges = false) {
  demoLoading.value = true
  demoError.value = null
  demoMessage.value = null
  try {
    const result = await syncPortalNamespaceMemberships(applyChanges)
    demoMessage.value = result.summary || 'Portal namespace sync audit completed.'
    await loadAdminData()
  } catch {
    demoError.value = 'Failed to run portal namespace sync audit.'
  } finally {
    demoLoading.value = false
  }
}

const debugMenuItems = computed(() => [
  {
    label: 'Send Demo: Project + Account',
    icon: 'pi pi-send',
    command: () => handleSendDemoPacket('project_and_account'),
  },
  {
    label: 'Send Demo: Project Only',
    icon: 'pi pi-send',
    command: () => handleSendDemoPacket('project_only'),
  },
  {
    label: 'Send Demo: Account Only',
    icon: 'pi pi-send',
    command: () => handleSendDemoPacket('account_only'),
  },
  {
    separator: true,
  },
  {
    label: 'Packet Log',
    icon: 'pi pi-list',
    command: () => router.push({ name: 'packet-logs' }),
  },
  {
    label: 'Manual Packet Input',
    icon: 'pi pi-pencil',
    command: () => router.push({ name: 'manual-packet-input' }),
  },
  {
    label: 'Evaluate Alerts',
    icon: 'pi pi-bell',
    command: () => handleEvaluateAlerts(),
  },
  {
    label: 'Refresh Accounting Stubs',
    icon: 'pi pi-database',
    command: () => handleRefreshAccountingStubs(),
  },
  {
    label: 'Audit Portal Sync (Dry Run)',
    icon: 'pi pi-search',
    command: () => handlePortalSync(false),
  },
  {
    label: 'Apply Portal Sync',
    icon: 'pi pi-wrench',
    command: () => handlePortalSync(true),
  },
])

onMounted(async () => {
  await loadAdminData()
})
</script>
