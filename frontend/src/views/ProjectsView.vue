<template>
  <div>
    <h1 class="text-2xl font-bold text-gray-800 mb-6">Projects</h1>
    <div v-if="loading" class="text-center text-gray-500 py-16">Loading projects…</div>
    <div v-else-if="error" class="text-red-600 bg-red-50 border border-red-200 rounded p-4">
      {{ error }}
    </div>
    <ProjectList v-else :projects="projects" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ProjectList from '../components/ProjectList.vue'
import { fetchProjects } from '../api/projects'

const projects = ref([])
const loading = ref(false)
const error = ref(null)

onMounted(async () => {
  loading.value = true
  try {
    projects.value = await fetchProjects()
  } catch (err) {
    error.value = 'Failed to load projects. Please try again later.'
  } finally {
    loading.value = false
  }
})
</script>
