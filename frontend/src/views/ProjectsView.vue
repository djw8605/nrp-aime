<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">Projects</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Focused view of projects with resource allocations.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button
          :icon="showDebug ? 'pi pi-eye-slash' : 'pi pi-eye'"
          :label="showDebug ? 'Hide Debug' : 'Show Debug'"
          severity="secondary"
          outlined
          @click="toggleDebugVisibility"
        />
        <router-link :to="{ name: 'admin' }" class="no-underline">
          <Button
            icon="pi pi-cog"
            label="Admin Dashboard"
            severity="secondary"
            outlined
          />
        </router-link>
      </div>
    </div>

    <!-- Pending Admin Actions -->
    <div
      v-if="pendingActions && pendingActions.total_pending_count > 0"
      class="rounded-2xl border border-amber-300 bg-amber-50 p-4 shadow-sm"
    >
      <div class="mb-3 flex items-center gap-2">
        <i class="pi pi-exclamation-triangle text-lg text-amber-600"></i>
        <h2 class="m-0 text-lg font-semibold text-amber-800">
          Pending Admin Actions
          <Tag :value="pendingActions.total_pending_count" severity="warn" rounded class="ml-2" />
        </h2>
      </div>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <!-- Projects needing provisioning -->
        <div v-if="pendingActions.projects_pending_provisioning.length > 0">
          <p class="m-0 mb-2 text-sm font-semibold text-slate-700">
            <i class="pi pi-server mr-1 text-sky-600"></i>
            Projects Needing Provisioning
            <Tag :value="pendingActions.projects_pending_provisioning.length" severity="warn" rounded class="ml-1" />
          </p>
          <ul class="m-0 list-none space-y-1 p-0">
            <li
              v-for="item in pendingActions.projects_pending_provisioning"
              :key="item.project_id"
              class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <router-link
                :to="{ name: 'project-detail', params: { id: item.project_id } }"
                class="font-medium text-sky-700 no-underline hover:underline"
              >
                {{ item.project_name }}
              </router-link>
              <Tag :value="item.lifecycle_state" severity="warn" rounded class="ml-2 text-xs" />
            </li>
          </ul>
        </div>

        <!-- Projects with provisioning failures -->
        <div v-if="pendingActions.projects_provisioning_failed.length > 0">
          <p class="m-0 mb-2 text-sm font-semibold text-slate-700">
            <i class="pi pi-times-circle mr-1 text-red-600"></i>
            Projects With Provisioning Failures
            <Tag :value="pendingActions.projects_provisioning_failed.length" severity="danger" rounded class="ml-1" />
          </p>
          <ul class="m-0 list-none space-y-1 p-0">
            <li
              v-for="item in pendingActions.projects_provisioning_failed"
              :key="item.project_id"
              class="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm"
            >
              <router-link
                :to="{ name: 'project-detail', params: { id: item.project_id } }"
                class="font-medium text-red-700 no-underline hover:underline"
              >
                {{ item.project_name }}
              </router-link>
              <Tag value="provisioning_failed" severity="danger" rounded class="ml-2 text-xs" />
            </li>
          </ul>
        </div>

        <!-- Users needing email invite -->
        <div v-if="pendingActions.users_pending_email_invite.length > 0">
          <p class="m-0 mb-2 text-sm font-semibold text-slate-700">
            <i class="pi pi-envelope mr-1 text-amber-600"></i>
            Users Needing Email Invite
            <Tag :value="pendingActions.users_pending_email_invite.length" severity="warn" rounded class="ml-1" />
          </p>
          <ul class="m-0 list-none space-y-1 p-0">
            <li
              v-for="item in pendingActions.users_pending_email_invite"
              :key="item.project_user_id"
              class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <router-link
                :to="{ name: 'project-detail', params: { id: item.project_id } }"
                class="font-medium text-sky-700 no-underline hover:underline"
              >
                {{ item.user_name }}
              </router-link>
              <span class="ml-1 text-slate-500">in {{ item.project_name }}</span>
            </li>
          </ul>
        </div>

        <!-- Users needing AIME notification -->
        <div v-if="pendingActions.users_pending_aime_notification.length > 0">
          <p class="m-0 mb-2 text-sm font-semibold text-slate-700">
            <i class="pi pi-check-circle mr-1 text-emerald-600"></i>
            Users Awaiting AIME Notification
            <Tag :value="pendingActions.users_pending_aime_notification.length" severity="info" rounded class="ml-1" />
          </p>
          <ul class="m-0 list-none space-y-1 p-0">
            <li
              v-for="item in pendingActions.users_pending_aime_notification"
              :key="item.project_user_id"
              class="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <router-link
                :to="{ name: 'project-detail', params: { id: item.project_id } }"
                class="font-medium text-sky-700 no-underline hover:underline"
              >
                {{ item.user_name }}
              </router-link>
              <span class="ml-1 text-slate-500">in {{ item.project_name }}</span>
              <Tag value="oauth complete" severity="success" rounded class="ml-2 text-xs" />
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
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

    <Message
      v-if="showDebug"
      severity="info"
      :closable="false"
    >
      Debug projects are visible below, but dashboard totals continue to exclude debug-tagged projects and users.
    </Message>

    <Message
      v-if="projects.length > 0 && projectsWithAllocations.length === 0"
      severity="info"
      :closable="false"
    >
      No projects currently have service-unit allocation data. Showing all projects.
    </Message>

    <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 class="m-0 text-lg font-semibold text-slate-800">Projects With Service Units</h2>
        <div class="flex items-center gap-2">
          <InputText
            v-model="allocationSearch"
            placeholder="Search project name or tag"
            class="w-64"
          />
          <Tag
            :value="`${filteredProjects.length} shown`"
            severity="contrast"
            rounded
          />
        </div>
      </div>
      <div v-if="loading" class="flex items-center justify-center py-20">
        <ProgressSpinner style="width: 2.8rem; height: 2.8rem" strokeWidth="5" />
      </div>
      <Message v-else-if="error" severity="error" :closable="false">
        {{ error }}
      </Message>
      <Message
        v-else-if="filteredProjects.length === 0"
        severity="info"
        :closable="false"
      >
        No projects matched the allocation name search.
      </Message>
      <ProjectList v-else :projects="filteredProjects" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import { fetchProjects, fetchProjectsSummary } from '../api/projects'
import { fetchPendingActions } from '../api/ops'
import ProjectList from '../components/ProjectList.vue'

const projects = ref([])
const pendingActions = ref(null)
const summary = ref({
  active_projects: 0,
  total_service_units_allocated: 0,
})
const loading = ref(false)
const error = ref(null)
const allocationSearch = ref('')
const showDebug = ref(false)

function formatUsage(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

const projectsWithAllocations = computed(() =>
  projects.value.filter(
    (project) =>
      Number(project.service_units_allocated || 0) > 0 ||
      Boolean(project.allocated_resource || project.resource_type),
  ),
)

const displayProjects = computed(() => {
  const base =
    projectsWithAllocations.value.length > 0
      ? projectsWithAllocations.value
      : projects.value
  return [...base].sort((a, b) => {
    const aTotal = Number(a.service_units_allocated || 0)
    const bTotal = Number(b.service_units_allocated || 0)
    return bTotal - aTotal
  })
})

const filteredProjects = computed(() => {
  const query = allocationSearch.value.trim().toLowerCase()
  if (!query) return displayProjects.value
  return displayProjects.value.filter((project) => {
    const haystack = [
      project.name,
      project.aime_allocation_id,
      project.site_project_id,
      project.source_site_name,
      Array.isArray(project.tags) ? project.tags.join(' ') : '',
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(query)
  })
})

const kpis = computed(() => [
  {
    label: 'Projects With SU Data',
    value: projectsWithAllocations.value.length.toLocaleString(),
    icon: 'pi-briefcase',
    iconClass: 'text-sky-600',
  },
  {
    label: 'Total Service Units',
    value: formatUsage(summary.value.total_service_units_allocated),
    icon: 'pi-database',
    iconClass: 'text-indigo-600',
  },
  {
    label: 'Active Projects',
    value: formatUsage(summary.value.active_projects),
    icon: 'pi-th-large',
    iconClass: 'text-emerald-600',
  },
])

async function loadProjects() {
  loading.value = true
  error.value = null
  try {
    const [projectsResponse, summaryResponse, pendingResponse] = await Promise.allSettled([
      fetchProjects(showDebug.value),
      fetchProjectsSummary(),
      fetchPendingActions(),
    ])

    if (projectsResponse.status === 'fulfilled') {
      projects.value = projectsResponse.value
    } else {
      throw projectsResponse.reason
    }

    if (summaryResponse.status === 'fulfilled') {
      summary.value = summaryResponse.value
    }

    if (pendingResponse.status === 'fulfilled') {
      pendingActions.value = pendingResponse.value
    }
  } catch {
    error.value = 'Failed to load projects. Please try again later.'
  } finally {
    loading.value = false
  }
}

async function toggleDebugVisibility() {
  showDebug.value = !showDebug.value
  await loadProjects()
}

onMounted(async () => {
  await loadProjects()
})
</script>
