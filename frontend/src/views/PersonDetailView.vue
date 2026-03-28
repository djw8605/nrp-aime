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
              <Tag
                v-if="person.is_pi"
                :value="person.pi_project_count > 1 ? `PI on ${person.pi_project_count} projects` : 'PI on 1 project'"
                severity="warn"
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
                <Tag
                  v-if="data.is_project_pi"
                  value="PI"
                  severity="warn"
                  rounded
                />
                <span v-else>{{ data.role || '—' }}</span>
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
            <Column header="Debug">
              <template #body="{ data }">
                <Button
                  v-if="canDebugComplete(data.account_state)"
                  icon="pi pi-bolt"
                  label="Mock OAuth"
                  severity="help"
                  outlined
                  size="small"
                  @click="onDebugCompleteAccount(data.project_id, data.project_user_id)"
                />
                <span v-else class="text-xs text-slate-400">--</span>
              </template>
            </Column>
          </DataTable>
        </template>
      </Card>

      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="mb-4">
          <h2 class="m-0 flex items-center gap-2 text-lg font-semibold text-slate-800">
            <i class="pi pi-sitemap text-base text-violet-600"></i>
            Account Creation Lifecycle
          </h2>
          <p class="m-0 mt-1 text-sm text-slate-500">
            Per-project lifecycle showing where each membership is in the account creation process.
          </p>
        </div>

        <Message v-if="memberships.length === 0" severity="info" :closable="false">
          No project memberships — no lifecycle to display.
        </Message>

        <Accordion v-else multiple :value="userLifecycleStepsByMembership.map((_, i) => String(i))">
          <AccordionPanel
            v-for="(item, idx) in userLifecycleStepsByMembership"
            :key="item.membership.project_user_id"
            :value="String(idx)"
          >
            <AccordionHeader>
              <div class="flex flex-wrap items-center gap-3">
                <span class="font-semibold text-slate-800">{{ item.membership.project_name }}</span>
                <Tag
                  :value="item.membership.account_state"
                  :severity="accountStateSeverity(item.membership.account_state)"
                  rounded
                />
                <span
                  v-if="item.membership.project_site_project_id"
                  class="font-mono text-xs text-slate-500"
                >
                  {{ item.membership.project_site_project_id }}
                </span>
              </div>
            </AccordionHeader>
            <AccordionContent>
              <LifecycleFlow :steps="item.steps" />
              <div v-if="canDebugComplete(item.membership.account_state)" class="mt-3 border-t border-slate-100 pt-3">
                <Button
                  icon="pi pi-bolt"
                  label="Mock OAuth (Debug)"
                  severity="help"
                  outlined
                  size="small"
                  @click="onDebugCompleteAccount(item.membership.project_id, item.membership.project_user_id)"
                />
              </div>
            </AccordionContent>
          </AccordionPanel>
        </Accordion>
      </section>

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

      <!-- User Action Log -->
      <Card class="border border-slate-200 shadow-sm">
        <template #title>
          <div class="flex items-center gap-2">
            <i class="pi pi-history text-base text-violet-600"></i>
            <span class="text-lg font-semibold text-slate-800">User Action Log</span>
          </div>
        </template>
        <template #content>
          <Message v-if="actionLogLoading" severity="info" :closable="false">Loading action log…</Message>
          <Message v-else-if="actionLog.length === 0" severity="info" :closable="false">
            No action log entries yet for this person.
          </Message>
          <DataTable
            v-else
            :value="actionLog"
            dataKey="id"
            stripedRows
            size="small"
            paginator
            :rows="20"
            :rowsPerPageOptions="[20, 50]"
            responsiveLayout="scroll"
          >
            <Column header="When" sortable field="created_at">
              <template #body="{ data }">
                <span class="text-xs">{{ formatDate(data.created_at) }}</span>
              </template>
            </Column>
            <Column field="event_type" header="Event" sortable>
              <template #body="{ data }">
                <Tag
                  :value="formatEventType(data.event_type)"
                  :severity="actionEventSeverity(data.event_type, data.event_status)"
                  rounded
                />
              </template>
            </Column>
            <Column field="event_status" header="Status" sortable>
              <template #body="{ data }">
                <span class="text-xs font-medium" :class="data.event_status === 'error' ? 'text-red-600' : 'text-slate-600'">
                  {{ data.event_status }}
                </span>
              </template>
            </Column>
            <Column field="message" header="Message">
              <template #body="{ data }">
                <span class="text-xs text-slate-700">{{ data.message || '—' }}</span>
              </template>
            </Column>
            <Column header="Details">
              <template #body="{ data }">
                <div v-if="data.event_type === 'oauth_flow_completed'" class="space-y-0.5 text-xs">
                  <p v-if="data.event_payload?.auth_email" class="m-0">
                    <strong>Email:</strong> {{ data.event_payload.auth_email }}
                  </p>
                  <p v-if="data.event_payload?.auth_username" class="m-0">
                    <strong>Username:</strong> {{ data.event_payload.auth_username }}
                  </p>
                  <p v-if="data.event_payload?.identity_name" class="m-0">
                    <strong>Name:</strong> {{ data.event_payload.identity_name }}
                  </p>
                  <p v-if="data.event_payload?.identity_subject" class="m-0">
                    <strong>Subject:</strong>
                    <span class="font-mono">{{ data.event_payload.identity_subject }}</span>
                  </p>
                  <p v-if="data.event_payload?.applied_group_names?.length" class="m-0">
                    <strong>Groups:</strong> {{ data.event_payload.applied_group_names.join(', ') }}
                  </p>
                </div>
                <div v-else-if="data.event_type === 'email_sent'" class="space-y-0.5 text-xs">
                  <p v-if="data.event_payload?.to_email" class="m-0">
                    <strong>To:</strong> {{ data.event_payload.to_email }}
                  </p>
                  <p v-if="data.event_payload?.invited_by" class="m-0">
                    <strong>By:</strong> {{ data.event_payload.invited_by }}
                  </p>
                  <p v-if="data.event_payload?.project_names?.length" class="m-0">
                    <strong>Projects:</strong> {{ data.event_payload.project_names.join(', ') }}
                  </p>
                </div>
                <span v-else class="text-xs text-slate-400">—</span>
              </template>
            </Column>
          </DataTable>
        </template>
      </Card>

      <!-- Danger Zone -->
      <section class="rounded-2xl border-2 border-red-300 bg-red-50 p-5">
        <h2 class="m-0 mb-1 flex items-center gap-2 text-lg font-semibold text-red-700">
          <i class="pi pi-exclamation-triangle text-base"></i>
          Danger Zone
        </h2>
        <p class="m-0 mb-4 text-sm text-red-600">
          Destructive actions. This person's project memberships will not be deleted.
        </p>
        <div class="flex items-center justify-between rounded-xl border border-red-200 bg-white p-4">
          <div>
            <p class="m-0 font-medium text-slate-800">Deactivate this person</p>
            <p class="m-0 mt-0.5 text-sm text-slate-500">
              Marks the person as inactive. Projects they belong to are not affected.
            </p>
          </div>
          <Button
            label="Deactivate Person"
            severity="danger"
            outlined
            icon="pi pi-user-minus"
            :loading="deletingPerson"
            @click="showDeletePersonDialog = true"
          />
        </div>
      </section>

      <!-- Delete confirmation dialog -->
      <Dialog
        v-model:visible="showDeletePersonDialog"
        modal
        header="Deactivate Person"
        :style="{ width: '26rem' }"
      >
        <div class="space-y-4">
          <p class="m-0 text-slate-700">
            Are you sure you want to deactivate
            <strong>{{ person.name }}</strong>?
          </p>
          <p class="m-0 text-sm text-slate-500">
            The person will be marked inactive. Their project memberships and projects will not be
            deleted. This action can be reversed by editing the person and setting them back to active.
          </p>
        </div>
        <template #footer>
          <Button
            label="Cancel"
            severity="secondary"
            outlined
            @click="showDeletePersonDialog = false"
          />
          <Button
            label="Yes, Deactivate"
            severity="danger"
            icon="pi pi-user-minus"
            :loading="deletingPerson"
            @click="confirmDeletePerson"
          />
        </template>
      </Dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Accordion from 'primevue/accordion'
import AccordionContent from 'primevue/accordioncontent'
import AccordionHeader from 'primevue/accordionheader'
import AccordionPanel from 'primevue/accordionpanel'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import LifecycleFlow from '../components/LifecycleFlow.vue'
import PacketReferenceTable from '../components/PacketReferenceTable.vue'
import {
  applyDebugTag,
  hasDebugTag,
  normalizeTextValue,
  parseDnList,
  parseTagList,
  toErrorMessage,
  toNullableNumber,
} from '../utils/formUtils'
import { debugCompleteUserAccount } from '../api/projects'
import {
  deleteUser,
  fetchUser,
  fetchUserActionLog,
  fetchUserPackets,
  fetchUserMemberships,
  fetchUserPacketDetails,
  sendUserInvite,
  updateUser,
} from '../api/users'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

const person = ref(null)
const personForm = ref(createPersonForm())
const memberships = ref([])
const packetDetails = ref([])
const userPackets = ref([])
const actionLog = ref([])
const inviteMessage = ref(null)
const personMessage = ref(null)
const inviteTtlHours = ref(72)
const sendingInvite = ref(false)
const savingPerson = ref(false)
const editingPerson = ref(false)
const deletingPerson = ref(false)
const showDeletePersonDialog = ref(false)
const actionLogLoading = ref(false)
const userPacketsLoading = ref(false)
const loading = ref(false)
const error = ref(null)

const userLifecycleStepsByMembership = computed(() =>
  memberships.value.map((membership) => ({
    membership,
    steps:
      membership.account_confirmation_via === 'notify_project_create'
        ? buildProjectCreatePiLifecycleSteps(membership)
        : buildAccountCreateLifecycleSteps(membership),
  })),
)

function buildAccountCreateLifecycleSteps(membership) {
  const step1 = {
    label: 'Received request account create',
    status: 'completed',
    timestamp: membership.account_state_updated_at,
    description: 'Account creation request received from AIME packet.',
  }

  const step2 =
    membership.email_sent_at || membership.account_made_at
      ? {
          label: 'Send account invite to user',
          status: 'completed',
          timestamp: membership.email_sent_at,
        }
      : {
          label: 'Send account invite to user',
          status: 'waiting',
          actionRequired: 'Admin must click "Send User Invite" to dispatch the invite email.',
        }

  let step3
  if (membership.account_made_at) {
    step3 = {
      label: 'User creates account',
      status: 'completed',
      timestamp: membership.account_made_at,
    }
  } else if (membership.email_sent_at || membership.account_made_at) {
    step3 = {
      label: 'User creates account',
      status: 'active',
      description: 'Waiting for the user to accept the invite and register.',
    }
  } else {
    step3 = { label: 'User creates account', status: 'pending' }
  }

  let step4
  if (membership.aime_confirmation_sent_at) {
    step4 = {
      label: 'Notify account create to AIME',
      status: 'completed',
      timestamp: membership.aime_confirmation_sent_at,
    }
  } else if (membership.account_made_at) {
    step4 = {
      label: 'Notify account create to AIME',
      status: 'active',
      description: 'Sending account creation confirmation to AIME server.',
    }
  } else {
    step4 = { label: 'Notify account create to AIME', status: 'pending' }
  }

  const step5 = {
    label: 'Received data account create',
    status: membership.aime_confirmation_sent_at ? 'active' : 'pending',
    description: membership.aime_confirmation_sent_at
      ? 'Waiting for AIME to acknowledge account creation.'
      : null,
  }

  const step6 = { label: 'Inform transaction complete', status: 'pending' }

  return [step1, step2, step3, step4, step5, step6]
}

function buildProjectCreatePiLifecycleSteps(membership) {
  const step1 = {
    label: 'Received request project create',
    status: 'completed',
    timestamp: membership.account_state_updated_at,
    description: 'Project creation request included the PI account details.',
  }

  const step2 =
    membership.email_sent_at
      ? {
          label: 'Send PI invite to user',
          status: 'completed',
          timestamp: membership.email_sent_at,
        }
      : {
          label: 'Send PI invite to user',
          status: membership.account_made_at ? 'completed' : 'pending',
          description: membership.account_made_at
            ? 'PI login was already available locally.'
            : 'Invite is only needed if the PI does not yet have a local login.',
        }

  let step3
  if (membership.account_made_at) {
    step3 = {
      label: 'PI account becomes available locally',
      status: 'completed',
      timestamp: membership.account_made_at,
    }
  } else if (membership.email_sent_at) {
    step3 = {
      label: 'PI account becomes available locally',
      status: 'active',
      description: 'Waiting for the PI to accept the invite and create a local login.',
    }
  } else {
    step3 = {
      label: 'PI account becomes available locally',
      status: 'pending',
    }
  }

  let step4
  if (membership.aime_confirmation_sent_at) {
    step4 = {
      label: 'Notify project create to AIME (covers PI account)',
      status: 'completed',
      timestamp: membership.aime_confirmation_sent_at,
    }
  } else if (membership.account_made_at) {
    step4 = {
      label: 'Notify project create to AIME (covers PI account)',
      status: 'active',
      description: 'Project notification will carry the PI account creation information.',
    }
  } else {
    step4 = {
      label: 'Notify project create to AIME (covers PI account)',
      status: 'pending',
    }
  }

  const step5 = {
    label: 'Received data project create',
    status: membership.aime_confirmation_sent_at ? 'active' : 'pending',
    description: membership.aime_confirmation_sent_at
      ? 'Waiting for AIME to acknowledge project creation.'
      : null,
  }

  const step6 = { label: 'Inform transaction complete', status: 'pending' }

  return [step1, step2, step3, step4, step5, step6]
}

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

function accountStateSeverity(state) {
  if (state === 'aime_notified' || state === 'covered_by_project_notification') return 'success'
  if (state === 'user_completed_oauth') return 'success'
  if (state === 'email_invite_sent') return 'info'
  if (state === 'received') return 'warning'
  // Legacy states
  if (state === 'account_made') return 'success'
  if (state === 'sent_email') return 'info'
  if (state === 'not_sent_email_invite') return 'warning'
  if (state === 'just_received_packet') return 'warning'
  return 'secondary'
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

function formatEventType(type) {
  const labels = {
    email_sent: 'Email Sent',
    oauth_flow_started: 'OAuth Started',
    oauth_flow_completed: 'OAuth Completed',
    oauth_flow_failed: 'OAuth Failed',
  }
  return labels[type] || type
}

function actionEventSeverity(type, status) {
  if (status === 'error') return 'danger'
  if (type === 'oauth_flow_completed') return 'success'
  if (type === 'oauth_flow_started') return 'info'
  if (type === 'email_sent') return 'info'
  return 'secondary'
}

async function loadActionLog() {
  actionLogLoading.value = true
  try {
    actionLog.value = await fetchUserActionLog(props.id)
  } catch {
    actionLog.value = []
  } finally {
    actionLogLoading.value = false
  }
}

async function confirmDeletePerson() {
  deletingPerson.value = true
  showDeletePersonDialog.value = false
  try {
    await deleteUser(props.id)
    router.push({ name: 'people' })
  } catch (err) {
    personMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to deactivate person.'),
    }
  } finally {
    deletingPerson.value = false
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

function canDebugComplete(state) {
  return state === 'received' || state === 'email_invite_sent'
}

async function onDebugCompleteAccount(projectId, projectUserId) {
  try {
    const result = await debugCompleteUserAccount(projectId, projectUserId)
    if (result?.ok) {
      personMessage.value = {
        severity: 'success',
        text: `Debug account complete for ${result.remote_site_login}. State: ${result.account_state}`,
      }
    }
  } catch (err) {
    personMessage.value = {
      severity: 'error',
      text: err?.response?.data?.detail || 'Failed to debug-complete user account.',
    }
  }
  await loadPerson()
}

onMounted(async () => {
  await Promise.all([loadPerson(), loadActionLog()])
})
</script>
