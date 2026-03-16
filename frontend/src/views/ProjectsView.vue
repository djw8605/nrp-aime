<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">Projects</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Focused view of projects with resource allocations.
        </p>
      </div>
      <router-link :to="{ name: 'admin' }" class="no-underline">
        <Button
          icon="pi pi-cog"
          label="Admin Dashboard"
          severity="secondary"
          outlined
        />
      </router-link>
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
      v-if="projects.length > 0 && projectsWithAllocations.length === 0"
      severity="info"
      :closable="false"
    >
      No projects currently have CPU/GPU allocations. Showing all projects.
    </Message>

    <div class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 class="m-0 text-lg font-semibold text-slate-800">Projects With Allocations</h2>
        <div class="flex items-center gap-2">
          <InputText
            v-model="allocationSearch"
            placeholder="Search allocation name"
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
  total_cpu_allocated: 0,
  total_gpu_allocated: 0,
})
const loading = ref(false)
const error = ref(null)
const allocationSearch = ref('')

function formatUsage(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

const projectsWithAllocations = computed(() =>
  projects.value.filter(
    (project) =>
      Number(project.cpu_allocated || 0) > 0 ||
      Number(project.gpu_allocated || 0) > 0,
  ),
)

const displayProjects = computed(() => {
  const base =
    projectsWithAllocations.value.length > 0
      ? projectsWithAllocations.value
      : projects.value
  return [...base].sort((a, b) => {
    const aTotal = Number(a.cpu_allocated || 0) + Number(a.gpu_allocated || 0)
    const bTotal = Number(b.cpu_allocated || 0) + Number(b.gpu_allocated || 0)
    return bTotal - aTotal
  })
})

const filteredProjects = computed(() => {
  const query = allocationSearch.value.trim().toLowerCase()
  if (!query) return displayProjects.value
  return displayProjects.value.filter((project) =>
    String(project.name || '')
      .toLowerCase()
      .includes(query),
  )
})

const kpis = computed(() => [
  {
    label: 'Projects With Allocations',
    value: projectsWithAllocations.value.length.toLocaleString(),
    icon: 'pi-briefcase',
    iconClass: 'text-sky-600',
  },
  {
    label: 'CPU Allocated (cores)',
    value: formatUsage(summary.value.total_cpu_allocated),
    icon: 'pi-server',
    iconClass: 'text-indigo-600',
  },
  {
    label: 'GPU Allocated',
    value: formatUsage(summary.value.total_gpu_allocated),
    icon: 'pi-th-large',
    iconClass: 'text-emerald-600',
  },
])

async function loadProjects() {
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
    }
  } catch {
    error.value = 'Failed to load projects. Please try again later.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadProjects()
})
</script>
