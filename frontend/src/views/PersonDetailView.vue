<template>
  <div class="space-y-5">
    <router-link :to="{ name: 'people' }" class="inline-block">
      <Button
        icon="pi pi-arrow-left"
        label="Back to People"
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

    <template v-else-if="person">
      <Message
        v-if="personMessage"
        :severity="personMessage.severity"
        :closable="true"
        @close="personMessage = null"
      >
        {{ personMessage.text }}
      </Message>

      <Card v-if="editingPerson" class="border border-slate-200 shadow-sm">
        <template #title>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 class="m-0 text-2xl font-bold text-slate-800">Edit Person Details</h1>
              <p class="m-0 mt-1 text-sm text-slate-500">
                This form updates the stored person record in the database.
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Button
                label="Cancel"
                severity="secondary"
                outlined
                :disabled="savingPerson"
                @click="cancelPersonEdit"
              />
              <Button
                icon="pi pi-save"
                label="Save Person"
                :loading="savingPerson"
                @click="savePerson"
              />
            </div>
          </div>
        </template>
        <template #content>
          <div class="space-y-6">
            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Core Identity</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Display Name</label>
                  <InputText v-model="personForm.name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Email</label>
                  <InputText v-model="personForm.email" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">First Name</label>
                  <InputText v-model="personForm.first_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Middle Name</label>
                  <InputText v-model="personForm.middle_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Last Name</label>
                  <InputText v-model="personForm.last_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Person ID</label>
                  <InputText v-model="personForm.person_id" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Global ID</label>
                  <InputText v-model="personForm.global_id" class="w-full" />
                </div>
                <div class="flex items-center gap-2 pt-6">
                  <Checkbox v-model="personForm.is_active" binary inputId="person-active" />
                  <label for="person-active" class="text-sm font-medium text-slate-700">Person is active</label>
                </div>
                <div class="flex items-center gap-2 pt-6">
                  <Checkbox v-model="personForm.is_debug" binary inputId="person-debug" />
                  <label for="person-debug" class="text-sm font-medium text-slate-700">Mark person as debug</label>
                </div>
              </div>
            </section>

            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Organization</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Organization</label>
                  <InputText v-model="personForm.organization" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Org Code</label>
                  <InputText v-model="personForm.org_code" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Department</label>
                  <InputText v-model="personForm.department" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">NSF Status Code</label>
                  <InputText v-model="personForm.nsf_status_code" class="w-full" />
                </div>
              </div>
            </section>

            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Portal and Source Details</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Remote Site Login</label>
                  <InputText v-model="personForm.remote_site_login" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Source Site</label>
                  <InputText v-model="personForm.source_site_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Service Units Allocated</label>
                  <InputNumber
                    v-model="personForm.service_units_allocated"
                    :maxFractionDigits="4"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div class="md:col-span-2 xl:col-span-4">
                  <label class="mb-1 block text-sm font-medium text-slate-600">Custom Tags</label>
                  <Textarea
                    v-model="personForm.tags_text"
                    rows="2"
                    class="w-full"
                    autoResize
                    placeholder="Comma-separated or one tag per line"
                  />
                </div>
                <div class="md:col-span-2 xl:col-span-4">
                  <label class="mb-1 block text-sm font-medium text-slate-600">Distinguished Names</label>
                  <Textarea
                    v-model="personForm.dn_list_text"
                    rows="4"
                    class="w-full"
                    autoResize
                    placeholder="One DN per line"
                  />
                </div>
              </div>
            </section>
          </div>
        </template>
      </Card>

      <Card v-else class="border border-slate-200 shadow-sm">
        <template #title>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 class="m-0 text-2xl font-bold text-slate-800">{{ person.name }}</h1>
              <p class="m-0 mt-1 text-sm text-slate-500">
                {{ person.email || 'No email on file' }}
              </p>
              <div v-if="(person.tags || []).length" class="mt-2 flex flex-wrap gap-2">
                <Tag
                  v-for="tag in person.tags"
                  :key="tag"
                  :value="tag"
                  severity="contrast"
                  rounded
                />
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Tag
                :value="person.is_active ? 'Active User' : 'Inactive User'"
                :severity="person.is_active ? 'success' : 'danger'"
                rounded
              />
              <Button icon="pi pi-pencil" label="Edit Person" @click="startPersonEdit" />
            </div>
          </div>
        </template>
        <template #content>
          <div class="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">User ID</p>
              <p class="m-0 mt-2 font-mono text-xs font-medium text-slate-700">{{ person.id }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Person ID</p>
              <p class="m-0 mt-2 font-mono font-medium text-slate-700">{{ person.person_id || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Global ID</p>
              <p class="m-0 mt-2 font-mono font-medium text-slate-700">{{ person.global_id || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Remote Site Login</p>
              <p class="m-0 mt-2 font-mono font-medium text-slate-700">{{ person.remote_site_login || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Source Site</p>
              <p class="m-0 mt-2 font-mono font-medium text-slate-700">{{ person.source_site_name || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Service Units</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ formatUnits(person.service_units_allocated) }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">First Name</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.first_name || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Middle Name</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.middle_name || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Last Name</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.last_name || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">NSF Status</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.nsf_status_code || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Organization</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.organization || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Org Code</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.org_code || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Department</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ person.department || '—' }}</p>
            </div>
            <div class="rounded-lg bg-slate-50 p-3">
              <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Created</p>
              <p class="m-0 mt-2 font-medium text-slate-700">{{ formatDate(person.created_at) }}</p>
            </div>
          </div>

          <div class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Custom Tags</p>
            <div v-if="!(person.tags || []).length" class="mt-2 text-sm text-slate-500">No custom tags set.</div>
            <div v-else class="mt-2 flex flex-wrap gap-2">
              <Tag
                v-for="tag in person.tags"
                :key="tag"
                :value="tag"
                severity="contrast"
                rounded
              />
            </div>
          </div>

          <div class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Distinguished Names (DN)</p>
            <div v-if="!(person.dn_list || []).length" class="mt-2 text-sm text-slate-500">No DNs captured.</div>
            <div v-else class="mt-2 flex flex-wrap gap-2">
              <Tag
                v-for="dn in person.dn_list"
                :key="dn"
                :value="dn"
                severity="secondary"
                rounded
              />
            </div>
          </div>
        </template>
      </Card>

      <section class="space-y-3">
        <div>
          <h2 class="m-0 flex items-center gap-2 text-xl font-semibold text-slate-700">
            <i class="pi pi-send text-base text-amber-600"></i>
            Related Packets
          </h2>
          <p class="m-0 mt-1 text-sm text-slate-500">
            Packets that created or modified this person or their account memberships.
          </p>
        </div>
        <PacketReferenceTable
          :packets="userPackets"
          :loading="userPacketsLoading"
          empty-message="No user-related packets have been linked yet."
        />
      </section>

      <Message
        v-if="inviteMessage"
        :severity="inviteMessage.severity"
        :closable="true"
        @close="inviteMessage = null"
      >
        {{ inviteMessage.text }}
        <template v-if="inviteMessage.url">
          <a
            :href="inviteMessage.url"
            target="_blank"
            class="ml-1 text-sky-700 underline"
            rel="noreferrer"
          >
            Invite link
          </a>
        </template>
      </Message>

      <Card class="border border-slate-200 shadow-sm">
        <template #title>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <span class="text-lg font-semibold text-slate-800">Project Memberships</span>
            <div class="flex flex-wrap items-center gap-2">
              <div class="flex items-center gap-2">
                <label class="text-sm text-slate-500">Invite TTL (hours)</label>
                <InputNumber
                  v-model="inviteTtlHours"
                  :min="1"
                  :max="720"
                  showButtons
                  buttonLayout="horizontal"
                  :step="1"
                  inputClass="w-20"
                />
              </div>
              <Button
                icon="pi pi-send"
                label="Send User Invite"
                size="small"
                :disabled="!person.email || memberships.length === 0"
                :loading="sendingInvite"
                @click="sendPersonInvite"
              />
            </div>
          </div>
        </template>
        <template #content>
          <Message v-if="!person.email" severity="warn" :closable="false">
            This person has no email address, so portal invite links cannot be sent.
          </Message>

          <Message v-if="memberships.length === 0" severity="info" :closable="false">
            No project memberships found for this person.
          </Message>

          <DataTable
            v-else
            :value="memberships"
            dataKey="project_user_id"
            stripedRows
            size="small"
            paginator
            :rows="20"
            :rowsPerPageOptions="[20, 50, 100]"
            responsiveLayout="scroll"
          >
            <Column field="project_name" header="Project" sortable />
            <Column header="Site Project ID" sortable>
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ data.project_site_project_id || '—' }}</span>
              </template>
            </Column>
            <Column header="Role" sortable>
              <template #body="{ data }">
                {{ data.role || '—' }}
              </template>
            </Column>
            <Column header="Resource" sortable>
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ data.resource || '—' }}</span>
              </template>
            </Column>
            <Column header="Allocated Resource" sortable>
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ data.allocated_resource || '—' }}</span>
              </template>
            </Column>
            <Column header="SU Allocated" sortable>
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ formatUnits(data.membership_service_units_allocated) }}</span>
              </template>
            </Column>
            <Column header="SU Remaining" sortable>
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ formatUnits(data.membership_service_units_remaining) }}</span>
              </template>
            </Column>
            <Column header="Project State" sortable>
              <template #body="{ data }">
                <Tag
                  :value="data.project_is_active ? 'Active' : 'Inactive'"
                  :severity="data.project_is_active ? 'success' : 'warning'"
                  rounded
                />
              </template>
            </Column>
            <Column header="Account State" sortable>
              <template #body="{ data }">
                <Tag
                  :value="data.account_state"
                  :severity="accountStateSeverity(data.account_state)"
                  rounded
                />
              </template>
            </Column>
            <Column header="Account Login" sortable>
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ data.account_remote_site_login || '—' }}</span>
              </template>
            </Column>
            <Column header="Packet Refs">
              <template #body="{ data }">
                <div class="space-y-0.5 text-xs">
                  <p class="m-0"><strong>P:</strong> {{ data.source_packet_rec_id ?? '—' }}</p>
                  <p class="m-0"><strong>T:</strong> {{ data.source_trans_rec_id ?? '—' }}</p>
                  <p class="m-0"><strong>Txn:</strong> {{ data.source_transaction_id ?? '—' }}</p>
                </div>
              </template>
            </Column>
            <Column header="Lifecycle Dates">
              <template #body="{ data }">
                <div class="space-y-0.5 text-xs">
                  <p class="m-0"><strong>Email:</strong> {{ formatDate(data.email_sent_at) }}</p>
                  <p class="m-0"><strong>Account:</strong> {{ formatDate(data.account_made_at) }}</p>
                  <p class="m-0"><strong>Notify:</strong> {{ formatDate(data.aime_confirmation_sent_at) }}</p>
                </div>
              </template>
            </Column>
          </DataTable>
        </template>
      </Card>

      <Card class="border border-slate-200 shadow-sm">
        <template #title>
          <span class="text-lg font-semibold text-slate-800">Incoming Packet Details</span>
        </template>
        <template #content>
          <Message v-if="packetDetails.length === 0" severity="info" :closable="false">
            No incoming packet details are linked to this person yet.
          </Message>

          <DataTable
            v-else
            :value="packetDetails"
            dataKey="packet_rec_id"
            stripedRows
            size="small"
            paginator
            :rows="20"
            :rowsPerPageOptions="[20, 50, 100]"
            responsiveLayout="scroll"
          >
            <Column field="packet_rec_id" header="Packet" sortable>
              <template #body="{ data }">
                <router-link
                  :to="{ name: 'packet-logs', query: { q: String(data.packet_rec_id) } }"
                  class="text-sky-700 no-underline hover:underline"
                >
                  {{ data.packet_rec_id }}
                </router-link>
              </template>
            </Column>
            <Column field="packet_type" header="Type" sortable />
            <Column header="Received" sortable>
              <template #body="{ data }">
                {{ formatDate(data.packet_received_at) }}
              </template>
            </Column>
            <Column header="Grant / Project">
              <template #body="{ data }">
                <div class="text-xs">
                  <p class="m-0"><strong>Grant:</strong> {{ data.grant_number }}</p>
                  <p class="m-0"><strong>Project:</strong> {{ data.project_id || '—' }}</p>
                  <p class="m-0"><strong>Resource:</strong> {{ data.resource || '—' }}</p>
                  <p class="m-0"><strong>Allocated:</strong> {{ data.allocated_resource || '—' }}</p>
                  <p class="m-0"><strong>SU Alloc:</strong> {{ data.service_units_allocated || '—' }}</p>
                  <p class="m-0"><strong>SU Remain:</strong> {{ data.service_units_remaining || '—' }}</p>
                </div>
              </template>
            </Column>
            <Column header="Org / Dept">
              <template #body="{ data }">
                <div class="text-xs">
                  <p class="m-0">{{ data.user_organization || '—' }}</p>
                  <p class="m-0">{{ data.user_department || '—' }}</p>
                </div>
              </template>
            </Column>
            <Column header="Remote Login">
              <template #body="{ data }">
                <span class="font-mono text-xs">{{ data.user_remote_site_login || '—' }}</span>
              </template>
            </Column>
            <Column header="Requested Logins">
              <template #body="{ data }">
                <span class="text-xs">{{ (data.user_requested_login_list || []).join(', ') || '—' }}</span>
              </template>
            </Column>
            <Column header="Roles">
              <template #body="{ data }">
                <span class="text-xs">{{ (data.role_list || []).join(', ') || '—' }}</span>
              </template>
            </Column>
            <Column header="DNs">
              <template #body="{ data }">
                {{ (data.user_dn_list || []).length }}
              </template>
            </Column>
          </DataTable>
        </template>
      </Card>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import PacketReferenceTable from '../components/PacketReferenceTable.vue'
import {
  fetchUser,
  fetchUserPackets,
  fetchUserMemberships,
  fetchUserPacketDetails,
  sendUserInvite,
  updateUser,
} from '../api/users'

const props = defineProps({ id: { type: String, required: true } })

const person = ref(null)
const personForm = ref(createPersonForm())
const memberships = ref([])
const packetDetails = ref([])
const userPackets = ref([])
const inviteMessage = ref(null)
const personMessage = ref(null)
const inviteTtlHours = ref(72)
const sendingInvite = ref(false)
const savingPerson = ref(false)
const editingPerson = ref(false)
const userPacketsLoading = ref(false)
const loading = ref(false)
const error = ref(null)

function createPersonForm(personData = null) {
  const tags = Array.isArray(personData?.tags) ? personData.tags : []
  return {
    email: personData?.email || '',
    name: personData?.name || '',
    tags_text: tags.join(', '),
    is_debug: hasDebugTag(tags),
    first_name: personData?.first_name || '',
    middle_name: personData?.middle_name || '',
    last_name: personData?.last_name || '',
    person_id: personData?.person_id || '',
    global_id: personData?.global_id || '',
    organization: personData?.organization || '',
    org_code: personData?.org_code || '',
    department: personData?.department || '',
    nsf_status_code: personData?.nsf_status_code || '',
    remote_site_login: personData?.remote_site_login || '',
    source_site_name: personData?.source_site_name || '',
    service_units_allocated: toNullableNumber(personData?.service_units_allocated),
    is_active: Boolean(personData?.is_active ?? true),
    dn_list_text: Array.isArray(personData?.dn_list) ? personData.dn_list.join('\n') : '',
  }
}

function normalizeTextValue(value) {
  const cleaned = String(value ?? '').trim()
  return cleaned || null
}

function toNullableNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function parseDnList(text) {
  return String(text || '')
    .split(/\r?\n|,/)
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function parseTagList(text) {
  return String(text || '')
    .split(/\r?\n|,/)
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function hasDebugTag(tags) {
  return parseTagList(Array.isArray(tags) ? tags.join(',') : '')
    .some((tag) => tag.toLowerCase() === 'debug')
}

function applyDebugTag(tags, isDebug) {
  const unique = []
  for (const tag of tags) {
    const normalized = String(tag || '').trim()
    if (!normalized) continue
    if (!unique.some((existing) => existing.toLowerCase() === normalized.toLowerCase())) {
      unique.push(normalized)
    }
  }
  const withoutDebug = unique.filter((tag) => tag.toLowerCase() !== 'debug')
  return isDebug ? ['debug', ...withoutDebug] : withoutDebug
}

function accountStateSeverity(state) {
  if (state === 'account_made') return 'success'
  if (state === 'sent_email') return 'info'
  if (state === 'not_sent_email_invite') return 'warning'
  if (state === 'just_received_packet') return 'warning'
  return 'secondary'
}

function toErrorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback
}

function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

function formatUnits(value) {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function startPersonEdit() {
  personForm.value = createPersonForm(person.value)
  personMessage.value = null
  editingPerson.value = true
}

function cancelPersonEdit() {
  editingPerson.value = false
  personForm.value = createPersonForm(person.value)
}

async function savePerson() {
  if (!normalizeTextValue(personForm.value.name)) {
    personMessage.value = { severity: 'error', text: 'Person name is required.' }
    return
  }

  savingPerson.value = true
  personMessage.value = null
  try {
    const payload = {
      email: normalizeTextValue(personForm.value.email),
      name: normalizeTextValue(personForm.value.name),
      tags: applyDebugTag(parseTagList(personForm.value.tags_text), personForm.value.is_debug),
      first_name: normalizeTextValue(personForm.value.first_name),
      middle_name: normalizeTextValue(personForm.value.middle_name),
      last_name: normalizeTextValue(personForm.value.last_name),
      person_id: normalizeTextValue(personForm.value.person_id),
      global_id: normalizeTextValue(personForm.value.global_id),
      organization: normalizeTextValue(personForm.value.organization),
      org_code: normalizeTextValue(personForm.value.org_code),
      department: normalizeTextValue(personForm.value.department),
      nsf_status_code: normalizeTextValue(personForm.value.nsf_status_code),
      dn_list: parseDnList(personForm.value.dn_list_text),
      remote_site_login: normalizeTextValue(personForm.value.remote_site_login),
      source_site_name: normalizeTextValue(personForm.value.source_site_name),
      service_units_allocated: toNullableNumber(personForm.value.service_units_allocated),
      is_active: Boolean(personForm.value.is_active),
    }

    person.value = await updateUser(props.id, payload)
    personForm.value = createPersonForm(person.value)
    userPacketsLoading.value = true
    try {
      userPackets.value = await fetchUserPackets(props.id)
    } catch {
      userPackets.value = []
    }
    editingPerson.value = false
    personMessage.value = { severity: 'success', text: 'Person details updated successfully.' }
  } catch (err) {
    personMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to update person details.'),
    }
  } finally {
    userPacketsLoading.value = false
    savingPerson.value = false
  }
}

async function sendPersonInvite() {
  sendingInvite.value = true
  inviteMessage.value = null
  try {
    const result = await sendUserInvite(props.id, {
      expires_in_hours: Number(inviteTtlHours.value || 72),
      invited_by: 'admin:person-page',
      send_email: true,
      metadata: {
        trigger: 'person-page',
      },
    })

    inviteMessage.value = {
      severity: 'success',
      text: `Invite sent for ${person.value?.name || 'this person'}.`,
      url: result.invite_url,
    }
    memberships.value = await fetchUserMemberships(props.id)
  } catch (err) {
    inviteMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to send invite for this person.'),
      url: null,
    }
  } finally {
    sendingInvite.value = false
  }
}

async function loadPerson() {
  loading.value = true
  userPacketsLoading.value = true
  error.value = null
  try {
    const [personData, membershipData, packetData, relatedPacketData] = await Promise.all([
      fetchUser(props.id),
      fetchUserMemberships(props.id),
      fetchUserPacketDetails(props.id),
      fetchUserPackets(props.id),
    ])
    person.value = personData
    if (!editingPerson.value) {
      personForm.value = createPersonForm(personData)
    }
    memberships.value = membershipData
    packetDetails.value = packetData
    userPackets.value = relatedPacketData
  } catch (err) {
    error.value = toErrorMessage(err, 'Failed to load person.')
  } finally {
    userPacketsLoading.value = false
    loading.value = false
  }
}

onMounted(async () => {
  await loadPerson()
})
</script>
