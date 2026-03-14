<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">Projects</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Includes cross-service lifecycle and consistency tracking.
        </p>
      </div>
      <div class="flex items-center gap-3">
        <Tag :value="`${summary.total_projects} total`" severity="contrast" rounded />
        <Button
          icon="pi pi-send"
          label="Send Demo Packet"
          severity="success"
          :loading="demoLoading"
          class="font-semibold"
          @click="handleSendDemoPacket"
        />
        <Button
          icon="pi pi-shield"
          label="Run Audit"
          severity="warning"
          :loading="auditLoading"
          class="font-semibold"
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

    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <Card
        v-for="kpi in kpis"
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

    <div v-if="loading" class="flex items-center justify-center py-20">
      <ProgressSpinner style="width: 2.8rem; height: 2.8rem" strokeWidth="5" />
    </div>
    <Message v-else-if="error" severity="error" :closable="false">
      {{ error }}
    </Message>
    <ProjectList v-else :projects="projects" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import { fetchProjects, fetchProjectsSummary, runAudit, sendDemoPacket } from '../api/projects'
import ProjectList from '../components/ProjectList.vue'

const projects = ref([])
const summary = ref({
  total_projects: 0,
  active_projects: 0,
  total_users: 0,
  active_users: 0,
  total_cpu_used: 0,
  total_gpu_used: 0,
})
const loading = ref(false)
const error = ref(null)
const auditLoading = ref(false)
const auditError = ref(null)
const auditReport = ref(null)
const demoLoading = ref(false)
const demoError = ref(null)
const demoMessage = ref(null)

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

async function loadDashboard() {
  loading.value = true
  error.value = null
  try {
    const [projectsResponse, summaryResponse] = await Promise.allSettled([
      fetchProjects(),
      fetchProjectsSummary(),
    ])
    if (projectsResponse.status === 'fulfilled') {
      projects.value = projectsResponse.value
    } else {
      throw projectsResponse.reason
    }

    if (summaryResponse.status === 'fulfilled') {
      summary.value = summaryResponse.value
    } else {
      summary.value.total_projects = projects.value.length
    }
  } catch {
    error.value = 'Failed to load projects. Please try again later.'
  } finally {
    loading.value = false
  }
}

async function handleSendDemoPacket() {
  demoLoading.value = true
  demoError.value = null
  demoMessage.value = null
  try {
    const result = await sendDemoPacket('project_and_account')
    demoMessage.value = `${result.message} (transaction ${result.trans_rec_id})`
    await loadDashboard()
  } catch {
    demoError.value = 'Failed to send demo packet. Please try again later.'
  } finally {
    demoLoading.value = false
  }
}

const kpis = computed(() => [
  {
    label: 'Projects Registered',
    value: summary.value.total_projects.toLocaleString(),
    icon: 'pi-folder',
    iconClass: 'text-sky-600',
  },
  {
    label: 'Active Projects',
    value: summary.value.active_projects.toLocaleString(),
    icon: 'pi-check-circle',
    iconClass: 'text-emerald-600',
  },
  {
    label: 'Total Users',
    value: summary.value.total_users.toLocaleString(),
    icon: 'pi-users',
    iconClass: 'text-cyan-600',
  },
  {
    label: 'Active Users',
    value: summary.value.active_users.toLocaleString(),
    icon: 'pi-user-plus',
    iconClass: 'text-teal-600',
  },
  {
    label: 'CPU Usage (cores)',
    value: formatUsage(summary.value.total_cpu_used),
    icon: 'pi-desktop',
    iconClass: 'text-indigo-600',
  },
  {
    label: 'GPU Usage',
    value: formatUsage(summary.value.total_gpu_used),
    icon: 'pi-bolt',
    iconClass: 'text-amber-600',
  },
])

onMounted(async () => {
  await loadDashboard()
})
</script>
