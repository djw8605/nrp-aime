<template>
  <div>
    <!-- Back link -->
    <router-link to="/" class="text-blue-600 hover:underline text-sm mb-4 inline-block">
      ← Back to Projects
    </router-link>

    <div v-if="loading" class="text-center text-gray-500 py-16">Loading project…</div>
    <div v-else-if="error" class="text-red-600 bg-red-50 border border-red-200 rounded p-4">
      {{ error }}
    </div>

    <template v-else-if="project">
      <ProjectDetail
        :project="project"
        @send-email="handleSendEmail"
      />

      <!-- Notification -->
      <Notification :message="notification" @dismiss="notification = null" />

      <div class="mt-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 class="text-lg font-semibold text-gray-700 mb-3">Users</h2>
          <UserList :users="users" :loading="usersLoading" />
        </div>
        <div>
          <h2 class="text-lg font-semibold text-gray-700 mb-3">Resource Usage</h2>
          <UsageDisplay :usage="usage" :loading="usageLoading" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ProjectDetail from '../components/ProjectDetail.vue'
import UserList from '../components/UserList.vue'
import UsageDisplay from '../components/UsageDisplay.vue'
import Notification from '../components/Notification.vue'
import { fetchProject, fetchProjectUsers, fetchProjectUsage, sendAccountEmail } from '../api/projects'

const props = defineProps({ id: { type: String, required: true } })

const project = ref(null)
const users = ref([])
const usage = ref(null)
const loading = ref(false)
const usersLoading = ref(false)
const usageLoading = ref(false)
const error = ref(null)
const notification = ref(null)

async function handleSendEmail() {
  try {
    await sendAccountEmail(props.id)
    notification.value = 'Account creation emails queued successfully!'
  } catch (err) {
    notification.value = 'Failed to send emails. Please try again.'
  }
}

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
