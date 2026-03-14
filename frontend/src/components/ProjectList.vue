<template>
  <Message v-if="projects.length === 0" severity="info" :closable="false">
    No projects found.
  </Message>

  <DataView v-else :value="projects" dataKey="id" layout="list" class="project-list-view">
    <template #list="slotProps">
      <div class="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
        <ProjectCard
          v-for="project in slotProps.items"
          :key="project.id"
          :project="project"
        />
      </div>
    </template>
  </DataView>
</template>

<script setup>
import DataView from 'primevue/dataview'
import Message from 'primevue/message'
import ProjectCard from './ProjectCard.vue'

defineProps({
  projects: {
    type: Array,
    required: true,
  },
})
</script>

<style scoped>
.project-list-view :deep(.p-dataview),
.project-list-view :deep(.p-dataview-content) {
  background: transparent;
  border: 0;
}

.project-list-view :deep(.p-dataview-content) {
  padding: 0;
}
</style>
