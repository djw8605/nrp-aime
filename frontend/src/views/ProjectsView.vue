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
import ProjectList from '../components/ProjectList.vue'

const projects = ref([])
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
    const [projectsResponse, summaryResponse] = await Promise.allSettled([
      fetchProjects(showDebug.value),
      fetchProjectsSummary(),
    ])

    if (projectsResponse.status === 'fulfilled') {
      projects.value = projectsResponse.value
    } else {
      throw projectsResponse.reason
    }

    if (summaryResponse.status === 'fulfilled') {
      summary.value = summaryResponse.value
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
