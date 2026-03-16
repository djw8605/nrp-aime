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
            Resource Usage
          </h2>
          <UsageDisplay :usage="usage" :loading="usageLoading" />
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { fetchProject, fetchProjectUsage, fetchProjectUsers } from '../api/projects'
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
const error = ref(null)

onMounted(async () => {
  loading.value = true
  try {
    project.value = await fetchProject(props.id)
  } catch (err) {
    error.value = 'Failed to load project.'
  } finally {
    loading.value = false
  }

  usersLoading.value = true
  try {
    users.value = await fetchProjectUsers(props.id)
  } catch {
    users.value = []
  } finally {
    usersLoading.value = false
  }

  usageLoading.value = true
  try {
    usage.value = await fetchProjectUsage(props.id)
  } catch {
    usage.value = null
  } finally {
    usageLoading.value = false
  }
})
</script>
