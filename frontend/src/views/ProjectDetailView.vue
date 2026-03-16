<template>
  <div class="space-y-5">
    <router-link :to="{ name: 'projects' }" class="inline-block">
      <Button
        icon="pi pi-arrow-left"
        label="Back to Projects"
        severity="secondary"
        variant="text"
        size="small"
        class="!pl-0"
      />
    </router-link>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <ProgressSpinner style="width: 2.8rem; height: 2.8rem" strokeWidth="5" />
    </div>
    <Message v-else-if="error" severity="error" :closable="false">
      {{ error }}
    </Message>

    <template v-else-if="project">
      <ProjectDetail :project="project" />
      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="m-0 text-lg font-semibold text-slate-800">Project Provisioning</h2>
            <p class="m-0 mt-1 text-sm text-slate-600">
              Provisioning state:
              <span class="font-semibold">{{ provisioningStateLabel }}</span>
            </p>
          </div>
          <Button
            icon="pi pi-cloud-upload"
            :label="provisionButtonLabel"
            :disabled="!canProvision"
            :loading="provisioningActionLoading"
            @click="onProvisionInfrastructure"
          />
        </div>
        <Message
          v-if="provisioningSuccess"
          severity="success"
          :closable="false"
          class="mt-3"
        >
          {{ provisioningSuccess }}
        </Message>
        <Message
          v-if="provisioningError"
          severity="error"
          :closable="false"
          class="mt-3"
        >
          {{ provisioningError }}
        </Message>
      </section>

      <div class="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section class="space-y-3">
          <h2 class="m-0 flex items-center gap-2 text-xl font-semibold text-slate-700">
            <i class="pi pi-users text-base text-sky-600"></i>
            Users
          </h2>
          <Message severity="info" :closable="false">
            Invite links are managed per person on the People page.
          </Message>
          <UserList :users="users" :loading="usersLoading" />
        </section>
        <section class="space-y-3">
          <h2 class="m-0 flex items-center gap-2 text-xl font-semibold text-slate-700">
            <i class="pi pi-chart-line text-base text-emerald-600"></i>
            CPU/GPU Usage (Optional)
          </h2>
          <UsageDisplay :usage="usage" :loading="usageLoading" />
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import {
  fetchProject,
  fetchProjectUsage,
  fetchProjectUsers,
  provisionProjectInfrastructure,
} from '../api/projects'
import ProjectDetail from '../components/ProjectDetail.vue'
import UsageDisplay from '../components/UsageDisplay.vue'
import UserList from '../components/UserList.vue'

const props = defineProps({ id: { type: String, required: true } })

const project = ref(null)
const users = ref([])
const usage = ref(null)
const loading = ref(false)
const usersLoading = ref(false)
const usageLoading = ref(false)
const provisioningActionLoading = ref(false)
const provisioningSuccess = ref('')
const provisioningError = ref('')
const error = ref(null)

const provisioningStateLabel = computed(() => {
  const state = String(project.value?.provisioning_state || 'received')
    .trim()
    .toLowerCase()
  if (state === 'received') return 'Received (awaiting admin action)'
  if (state === 'provisioning') return 'Provisioning in progress'
  if (state === 'ready') return 'Ready'
  if (state === 'failed') return 'Failed'
  return state || 'Unknown'
})

const canProvision = computed(() => {
  const current = project.value
  if (!current) return false
  const state = String(current.provisioning_state || '').trim().toLowerCase()
  if (state === 'provisioning') return false
  if (state === 'received' || state === 'failed') return true
  if (!current.kubernetes_namespace || !current.authentik_group_name) return true
  return false
})

const provisionButtonLabel = computed(() => {
  const state = String(project.value?.provisioning_state || '').trim().toLowerCase()
  if (state === 'failed') return 'Retry Provisioning'
  return 'Create Namespace + Authentik Group'
})

async function loadProject() {
  loading.value = true
  try {
    project.value = await fetchProject(props.id)
  } catch (err) {
    error.value = 'Failed to load project.'
  } finally {
    loading.value = false
  }
}

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await fetchProjectUsers(props.id)
  } catch {
    users.value = []
  } finally {
    usersLoading.value = false
  }
}

async function loadUsage() {
  usageLoading.value = true
  try {
    usage.value = await fetchProjectUsage(props.id)
  } catch {
    usage.value = null
  } finally {
    usageLoading.value = false
  }
}

async function onProvisionInfrastructure() {
  if (!project.value) return
  provisioningActionLoading.value = true
  provisioningSuccess.value = ''
  provisioningError.value = ''
  try {
    const result = await provisionProjectInfrastructure(project.value.id)
    if (result?.ok) {
      provisioningSuccess.value = 'Project infrastructure provisioning completed successfully.'
    } else {
      provisioningError.value =
        result?.provisioning_last_error || 'Provisioning failed. Check backend logs for details.'
    }
  } catch (err) {
    provisioningError.value =
      err?.response?.data?.detail || 'Failed to trigger project provisioning.'
  } finally {
    provisioningActionLoading.value = false
    await loadProject()
  }
}

onMounted(async () => {
  await loadProject()
  await loadUsers()
  await loadUsage()
})
</script>
