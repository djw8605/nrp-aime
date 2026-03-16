<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">People</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Manage individual accounts and invite links per person.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <InputText
          v-model="searchText"
          placeholder="Search people"
          class="w-64"
        />
        <Tag :value="`${filteredPeople.length} people`" severity="contrast" rounded />
      </div>
    </div>

    <Card class="border border-slate-200 shadow-sm">
      <template #content>
        <div v-if="loading" class="flex items-center justify-center py-16">
          <ProgressSpinner style="width: 2.8rem; height: 2.8rem" strokeWidth="5" />
        </div>
        <Message v-else-if="error" severity="error" :closable="false">
          {{ error }}
        </Message>
        <Message v-else-if="people.length === 0" severity="info" :closable="false">
          No people are available yet.
        </Message>
        <Message v-else-if="filteredPeople.length === 0" severity="info" :closable="false">
          No people matched the search.
        </Message>
        <DataTable
          v-else
          :value="filteredPeople"
          dataKey="id"
          stripedRows
          size="small"
          paginator
          :rows="50"
          :rowsPerPageOptions="[25, 50, 100]"
          responsiveLayout="scroll"
        >
          <Column field="name" header="Name" sortable>
            <template #body="{ data }">
              <router-link
                :to="{ name: 'person-detail', params: { id: data.id } }"
                class="text-sky-700 no-underline hover:underline"
              >
                {{ data.name }}
              </router-link>
            </template>
          </Column>
          <Column header="Email" sortable>
            <template #body="{ data }">
              {{ data.email || '—' }}
            </template>
          </Column>
          <Column field="project_count" header="Projects" sortable>
            <template #body="{ data }">
              <Tag :value="String(data.project_count || 0)" severity="info" rounded />
              <p class="m-0 mt-1 text-xs text-slate-500">
                {{ (data.project_names || []).slice(0, 2).join(', ') || '—' }}
              </p>
            </template>
          </Column>
          <Column header="Person ID" sortable>
            <template #body="{ data }">
              <span class="font-mono text-xs">{{ data.person_id || '—' }}</span>
            </template>
          </Column>
          <Column header="Source Site" sortable>
            <template #body="{ data }">
              <span class="font-mono text-xs">{{ data.source_site_name || '—' }}</span>
            </template>
          </Column>
          <Column header="Service Units" sortable>
            <template #body="{ data }">
              <span class="font-mono text-xs">{{ formatUnits(data.service_units_allocated) }}</span>
            </template>
          </Column>
          <Column header="User State" sortable>
            <template #body="{ data }">
              <Tag
                :value="data.is_active ? 'Active' : 'Inactive'"
                :severity="data.is_active ? 'success' : 'danger'"
                rounded
              />
            </template>
          </Column>
          <Column header="Actions">
            <template #body="{ data }">
              <router-link :to="{ name: 'person-detail', params: { id: data.id } }" class="no-underline">
                <Button size="small" icon="pi pi-user" label="Open Person" />
              </router-link>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import { fetchUsers } from '../api/users'

const people = ref([])
const loading = ref(false)
const error = ref(null)
const searchText = ref('')

const filteredPeople = computed(() => {
  const query = searchText.value.trim().toLowerCase()
  if (!query) return people.value

  return people.value.filter((person) => {
    const projectNames = Array.isArray(person.project_names)
      ? person.project_names.join(' ')
      : ''
    return [
      person.name,
      person.email,
      person.person_id,
      person.global_id,
      projectNames,
      person.source_site_name,
      person.service_units_allocated,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query))
  })
})

function formatUnits(value) {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

async function loadPeople() {
  loading.value = true
  error.value = null
  try {
    people.value = await fetchUsers()
  } catch {
    error.value = 'Failed to load people. Please try again later.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadPeople()
})
</script>
