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
      <Card class="border border-slate-200 shadow-sm">
        <template #title>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 class="m-0 text-2xl font-bold text-slate-800">{{ person.name }}</h1>
              <p class="m-0 mt-1 text-sm text-slate-500">
                {{ person.email || 'No email on file' }}
              </p>
            </div>
            <Tag
              :value="person.is_active ? 'Active User' : 'Inactive User'"
              :severity="person.is_active ? 'success' : 'danger'"
              rounded
            />
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
            <Column field="packet_rec_id" header="Packet" sortable />
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
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputNumber from 'primevue/inputnumber'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import {
  fetchUser,
  fetchUserMemberships,
  fetchUserPacketDetails,
  sendUserInvite,
} from '../api/users'

const props = defineProps({ id: { type: String, required: true } })

const person = ref(null)
const memberships = ref([])
const packetDetails = ref([])
const inviteMessage = ref(null)
const inviteTtlHours = ref(72)
const sendingInvite = ref(false)
const loading = ref(false)
const error = ref(null)

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
  error.value = null
  try {
    const [personData, membershipData, packetData] = await Promise.all([
      fetchUser(props.id),
      fetchUserMemberships(props.id),
      fetchUserPacketDetails(props.id),
    ])
    person.value = personData
    memberships.value = membershipData
    packetDetails.value = packetData
  } catch (err) {
    error.value = toErrorMessage(err, 'Failed to load person.')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadPerson()
})
</script>
