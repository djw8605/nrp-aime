<template>
  <div class="bg-white rounded-xl shadow border border-gray-100 overflow-hidden">
    <div v-if="loading" class="p-6 text-center text-gray-400">Loading users…</div>
    <div v-else-if="users.length === 0" class="p-6 text-center text-gray-400">
      No users assigned.
    </div>
    <table v-else class="min-w-full text-sm">
      <thead class="bg-gray-50 border-b border-gray-100">
        <tr>
          <th class="text-left px-4 py-3 text-gray-500 font-medium">Name</th>
          <th class="text-left px-4 py-3 text-gray-500 font-medium">Email</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="user in users"
          :key="user.id"
          class="border-b border-gray-50 hover:bg-gray-50 transition-colors"
        >
          <td class="px-4 py-3 font-medium text-gray-700">{{ user.name }}</td>
          <td class="px-4 py-3 text-gray-500">{{ user.email }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({
  users: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})
</script>
