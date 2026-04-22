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
      <Message
        v-if="projectMessage"
        :severity="projectMessage.severity"
        :closable="true"
        @close="projectMessage = null"
      >
        {{ projectMessage.text }}
        <template v-if="projectMessage.url">
          <a
            :href="projectMessage.url"
            target="_blank"
            class="ml-1 text-sky-700 underline"
            rel="noreferrer"
          >
            Invite link
          </a>
        </template>
      </Message>

      <Card v-if="editingProject" class="border border-slate-200 shadow-sm">
        <template #title>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 class="m-0 text-2xl font-bold text-slate-800">Edit Project Details</h1>
              <p class="m-0 mt-1 text-sm text-slate-500">
                Changes are saved directly to the database for this project record.
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <Button
                label="Cancel"
                severity="secondary"
                outlined
                :disabled="savingProject"
                @click="cancelProjectEdit"
              />
              <Button
                icon="pi pi-save"
                label="Save Project"
                :loading="savingProject"
                @click="saveProject"
              />
            </div>
          </div>
        </template>
        <template #content>
          <div class="space-y-6">
            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Core Details</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Project Name</label>
                  <InputText v-model="projectForm.name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">AIME Allocation ID</label>
                  <InputText v-model="projectForm.aime_allocation_id" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Grant Number</label>
                  <InputText v-model="projectForm.grant_number" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Allocation Record ID</label>
                  <InputText v-model="projectForm.allocation_record_id" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Site Project ID</label>
                  <InputText v-model="projectForm.site_project_id" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Allocation Type</label>
                  <InputText v-model="projectForm.allocation_type" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Request Type</label>
                  <InputText v-model="projectForm.request_type" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Resource Type</label>
                  <InputText v-model="projectForm.resource_type" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Allocated Resource</label>
                  <InputText v-model="projectForm.allocated_resource" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Project Title</label>
                  <InputText v-model="projectForm.project_title" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PFOS Number</label>
                  <InputText v-model="projectForm.pfos_number" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Board Type</label>
                  <InputText v-model="projectForm.board_type" class="w-full" />
                </div>
                <div class="flex items-center gap-2 pt-6">
                  <Checkbox v-model="projectForm.is_debug" binary inputId="project-debug" />
                  <label for="project-debug" class="text-sm font-medium text-slate-700">Mark project as debug</label>
                </div>
                <div class="md:col-span-2 xl:col-span-4">
                  <label class="mb-1 block text-sm font-medium text-slate-600">Custom Tags</label>
                  <Textarea
                    v-model="projectForm.tags_text"
                    rows="3"
                    class="w-full"
                    autoResize
                    placeholder="Comma-separated or one tag per line"
                  />
                </div>
              </div>
            </section>

            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Allocation and Activity</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Service Units Allocated</label>
                  <InputNumber
                    v-model="projectForm.service_units_allocated"
                    :maxFractionDigits="4"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Service Units Remaining</label>
                  <InputNumber
                    v-model="projectForm.service_units_remaining"
                    :maxFractionDigits="4"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">CPU Allocated</label>
                  <InputNumber
                    v-model="projectForm.cpu_allocated"
                    :useGrouping="false"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">GPU Allocated</label>
                  <InputNumber
                    v-model="projectForm.gpu_allocated"
                    :useGrouping="false"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Start Date</label>
                  <InputText v-model="projectForm.start_date" type="date" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">End Date</label>
                  <InputText v-model="projectForm.end_date" type="date" class="w-full" />
                </div>
                <div class="flex items-center gap-2 pt-6">
                  <Checkbox v-model="projectForm.is_active" binary inputId="project-active" />
                  <label for="project-active" class="text-sm font-medium text-slate-700">Project is active</label>
                </div>
              </div>
            </section>

            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Provisioning and Source Tracking</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Lifecycle State</label>
                  <InputText v-model="projectForm.lifecycle_state" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Provisioning State</label>
                  <InputText v-model="projectForm.provisioning_state" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Kubernetes Namespace</label>
                  <InputText v-model="projectForm.kubernetes_namespace" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Authentik Group</label>
                  <InputText v-model="projectForm.authentik_group_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Source Site</label>
                  <InputText v-model="projectForm.source_site_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Source Packet Rec ID</label>
                  <InputNumber
                    v-model="projectForm.source_packet_rec_id"
                    :useGrouping="false"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Source Trans Rec ID</label>
                  <InputNumber
                    v-model="projectForm.source_trans_rec_id"
                    :useGrouping="false"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Source Transaction ID</label>
                  <InputNumber
                    v-model="projectForm.source_transaction_id"
                    :useGrouping="false"
                    class="w-full"
                    inputClass="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Provisioning Requested At</label>
                  <InputText
                    v-model="projectForm.provisioning_requested_at"
                    type="datetime-local"
                    class="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Provisioning Started At</label>
                  <InputText
                    v-model="projectForm.provisioning_started_at"
                    type="datetime-local"
                    class="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Provisioning Completed At</label>
                  <InputText
                    v-model="projectForm.provisioning_completed_at"
                    type="datetime-local"
                    class="w-full"
                  />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">Provisioning Alerted At</label>
                  <InputText
                    v-model="projectForm.provisioning_alerted_at"
                    type="datetime-local"
                    class="w-full"
                  />
                </div>
                <div class="md:col-span-2 xl:col-span-4">
                  <label class="mb-1 block text-sm font-medium text-slate-600">Provisioning Last Error</label>
                  <Textarea v-model="projectForm.provisioning_last_error" rows="3" class="w-full" autoResize />
                </div>
              </div>
            </section>

            <section class="space-y-3">
              <h2 class="m-0 text-base font-semibold text-slate-800">Principal Investigator</h2>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Person ID</label>
                  <InputText v-model="projectForm.pi_person_id" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI First Name</label>
                  <InputText v-model="projectForm.pi_first_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Middle Name</label>
                  <InputText v-model="projectForm.pi_middle_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Last Name</label>
                  <InputText v-model="projectForm.pi_last_name" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Email</label>
                  <InputText v-model="projectForm.pi_email" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Organization</label>
                  <InputText v-model="projectForm.pi_organization" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Org Code</label>
                  <InputText v-model="projectForm.pi_org_code" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Department</label>
                  <InputText v-model="projectForm.pi_department" class="w-full" />
                </div>
                <div>
                  <label class="mb-1 block text-sm font-medium text-slate-600">PI Business Phone</label>
                  <InputText v-model="projectForm.pi_business_phone_number" class="w-full" />
                </div>
              </div>
            </section>
          </div>
        </template>
      </Card>
      <div v-else class="space-y-3">
        <div class="flex justify-end">
          <Button icon="pi pi-pencil" label="Edit Project" @click="startProjectEdit" />
        </div>
        <ProjectDetail :project="project" />
      </div>

      <section ref="addMemberSection" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="m-0 text-lg font-semibold text-slate-800">Project Provisioning Lifecycle</h2>
            <p class="m-0 mt-1 text-sm text-slate-600">
              Current state:
              <span class="font-semibold">{{ provisioningStateLabel }}</span>
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button
              icon="pi pi-cloud-upload"
              :label="provisionButtonLabel"
              :disabled="!canProvision"
              :loading="provisioningActionLoading"
              @click="onProvisionInfrastructure"
            />
            <Button
              icon="pi pi-bolt"
              label="Debug Provision (Mock)"
              severity="help"
              outlined
              :disabled="!canProvision"
              :loading="debugProvisionLoading"
              @click="onDebugProvision"
            />
          </div>
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
        <div class="mt-4 border-t border-slate-100 pt-4">
          <LifecycleFlow :steps="projectLifecycleSteps" />
        </div>
      </section>

      <section class="space-y-3">
        <div>
          <h2 class="m-0 flex items-center gap-2 text-xl font-semibold text-slate-700">
            <i class="pi pi-send text-base text-amber-600"></i>
            Project Packets
          </h2>
          <p class="m-0 mt-1 text-sm text-slate-500">
            Packets that created or updated this project. Packet and transaction IDs link back to the packet tools.
          </p>
        </div>
        <PacketReferenceTable
          :packets="projectPackets"
          :loading="projectPacketsLoading"
          empty-message="No project-related packets have been linked yet."
        />
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="m-0 text-lg font-semibold text-slate-800">Add Person to Project</h2>
            <p class="m-0 mt-1 text-sm text-slate-600">
              Attach an existing person or manually create a new one before adding the membership.
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button
              :severity="addMemberMode === 'existing' ? 'contrast' : 'secondary'"
              :outlined="addMemberMode !== 'existing'"
              label="Existing Person"
              @click="addMemberMode = 'existing'"
            />
            <Button
              :severity="addMemberMode === 'new' ? 'contrast' : 'secondary'"
              :outlined="addMemberMode !== 'new'"
              label="New Person"
              @click="addMemberMode = 'new'"
            />
          </div>
        </div>

        <Message
          v-if="addMemberMessage"
          :severity="addMemberMessage.severity"
          :closable="true"
          class="mt-3"
          @close="addMemberMessage = null"
        >
          {{ addMemberMessage.text }}
        </Message>

        <div class="mt-4 space-y-6">
          <section class="space-y-3">
            <h3 class="m-0 text-sm font-semibold uppercase tracking-wide text-slate-500">Person Record</h3>
            <div v-if="addMemberMode === 'existing'" class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Choose Existing Person</label>
                <select
                  v-model="addMemberForm.existing_user_id"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700"
                >
                  <option value="">Select a person</option>
                  <option
                    v-for="personOption in availablePeople"
                    :key="personOption.id"
                    :value="personOption.id"
                  >
                    {{ formatPersonOption(personOption) }}
                  </option>
                </select>
              </div>
            </div>
            <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Name</label>
                <InputText v-model="addMemberForm.new_user.name" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Email</label>
                <InputText v-model="addMemberForm.new_user.email" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">First Name</label>
                <InputText v-model="addMemberForm.new_user.first_name" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Middle Name</label>
                <InputText v-model="addMemberForm.new_user.middle_name" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Last Name</label>
                <InputText v-model="addMemberForm.new_user.last_name" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Person ID</label>
                <InputText v-model="addMemberForm.new_user.person_id" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Global ID</label>
                <InputText v-model="addMemberForm.new_user.global_id" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Organization</label>
                <InputText v-model="addMemberForm.new_user.organization" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Org Code</label>
                <InputText v-model="addMemberForm.new_user.org_code" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Department</label>
                <InputText v-model="addMemberForm.new_user.department" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">NSF Status Code</label>
                <InputText v-model="addMemberForm.new_user.nsf_status_code" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Remote Site Login</label>
                <InputText v-model="addMemberForm.new_user.remote_site_login" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Source Site</label>
                <InputText v-model="addMemberForm.new_user.source_site_name" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Person Service Units</label>
                <InputNumber
                  v-model="addMemberForm.new_user.service_units_allocated"
                  :maxFractionDigits="4"
                  class="w-full"
                  inputClass="w-full"
                />
              </div>
              <div class="flex items-center gap-2 pt-6">
                <Checkbox v-model="addMemberForm.new_user.is_active" binary inputId="new-member-active" />
                <label for="new-member-active" class="text-sm font-medium text-slate-700">Person is active</label>
              </div>
              <div class="flex items-center gap-2 pt-6">
                <Checkbox v-model="addMemberForm.new_user.is_debug" binary inputId="new-member-debug" />
                <label for="new-member-debug" class="text-sm font-medium text-slate-700">Mark person as debug</label>
              </div>
              <div class="md:col-span-2 xl:col-span-4">
                <label class="mb-1 block text-sm font-medium text-slate-600">Custom Tags</label>
                <Textarea
                  v-model="addMemberForm.new_user.tags_text"
                  rows="2"
                  class="w-full"
                  autoResize
                  placeholder="Comma-separated or one tag per line"
                />
              </div>
              <div class="md:col-span-2 xl:col-span-4">
                <label class="mb-1 block text-sm font-medium text-slate-600">Distinguished Names</label>
                <Textarea
                  v-model="addMemberForm.new_user.dn_list_text"
                  rows="3"
                  class="w-full"
                  autoResize
                  placeholder="One DN per line"
                />
              </div>
            </div>
          </section>

          <section class="space-y-3">
            <h3 class="m-0 text-sm font-semibold uppercase tracking-wide text-slate-500">Project Membership</h3>
            <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Role</label>
                <InputText v-model="addMemberForm.role" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Resource</label>
                <InputText v-model="addMemberForm.resource" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Allocated Resource</label>
                <InputText v-model="addMemberForm.allocated_resource" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Account State</label>
                <InputText v-model="addMemberForm.account_state" class="w-full" />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Membership Service Units</label>
                <InputNumber
                  v-model="addMemberForm.membership_service_units_allocated"
                  :maxFractionDigits="4"
                  class="w-full"
                  inputClass="w-full"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Membership SU Remaining</label>
                <InputNumber
                  v-model="addMemberForm.membership_service_units_remaining"
                  :maxFractionDigits="4"
                  class="w-full"
                  inputClass="w-full"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Membership Remote Login</label>
                <InputText v-model="addMemberForm.account_remote_site_login" class="w-full" />
              </div>
              <div class="flex items-center gap-2 pt-6">
                <Checkbox v-model="addMemberForm.account_is_active" binary inputId="membership-active" />
                <label for="membership-active" class="text-sm font-medium text-slate-700">Membership is active</label>
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Source Packet Rec ID</label>
                <InputNumber
                  v-model="addMemberForm.source_packet_rec_id"
                  :useGrouping="false"
                  class="w-full"
                  inputClass="w-full"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Source Trans Rec ID</label>
                <InputNumber
                  v-model="addMemberForm.source_trans_rec_id"
                  :useGrouping="false"
                  class="w-full"
                  inputClass="w-full"
                />
              </div>
              <div>
                <label class="mb-1 block text-sm font-medium text-slate-600">Source Transaction ID</label>
                <InputNumber
                  v-model="addMemberForm.source_transaction_id"
                  :useGrouping="false"
                  class="w-full"
                  inputClass="w-full"
                />
              </div>
            </div>
          </section>

          <div class="flex flex-wrap justify-end gap-2">
            <Button
              label="Reset"
              severity="secondary"
              outlined
              :disabled="addingMember"
              @click="resetAddMemberForm"
            />
            <Button
              icon="pi pi-user-plus"
              label="Add Person to Project"
              :loading="addingMember"
              @click="submitAddMember"
            />
          </div>
        </div>
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
          <UserList
            :users="users"
            :loading="usersLoading"
            :show-debug-actions="true"
            @debug-complete-account="onDebugCompleteAccount"
          />
        </section>
        <section class="space-y-3">
          <h2 class="m-0 flex items-center gap-2 text-xl font-semibold text-slate-700">
            <i class="pi pi-chart-line text-base text-emerald-600"></i>
            CPU/GPU Usage (Optional)
          </h2>
          <UsageDisplay :usage="usage" :loading="usageLoading" />
        </section>
      </div>

      <!-- Danger Zone -->
      <section class="mt-6 rounded-2xl border-2 border-red-300 bg-red-50 p-5">
        <h2 class="m-0 mb-1 flex items-center gap-2 text-lg font-semibold text-red-700">
          <i class="pi pi-exclamation-triangle text-base"></i>
          Danger Zone
        </h2>
        <p class="m-0 mb-4 text-sm text-red-600">
          Destructive actions. Project members will not be deleted.
        </p>
        <div class="flex items-center justify-between rounded-xl border border-red-200 bg-white p-4">
          <div>
            <p class="m-0 font-medium text-slate-800">Deactivate this project</p>
            <p class="m-0 mt-0.5 text-sm text-slate-500">
              Marks the project as inactive. Users in this project are not affected.
            </p>
          </div>
          <Button
            label="Deactivate Project"
            severity="danger"
            outlined
            icon="pi pi-trash"
            :loading="deletingProject"
            @click="showDeleteProjectDialog = true"
          />
        </div>
      </section>

      <!-- Delete confirmation dialog -->
      <Dialog
        v-model:visible="showDeleteProjectDialog"
        modal
        header="Deactivate Project"
        :style="{ width: '26rem' }"
      >
        <div class="space-y-4">
          <p class="m-0 text-slate-700">
            Are you sure you want to deactivate
            <strong>{{ project.name }}</strong>?
          </p>
          <p class="m-0 text-sm text-slate-500">
            The project will be marked inactive. Members and their accounts will not be deleted.
            This action can be reversed by editing the project and setting it back to active.
          </p>
        </div>
        <template #footer>
          <Button
            label="Cancel"
            severity="secondary"
            outlined
            @click="showDeleteProjectDialog = false"
          />
          <Button
            label="Yes, Deactivate"
            severity="danger"
            icon="pi pi-trash"
            :loading="deletingProject"
            @click="confirmDeleteProject"
          />
        </template>
      </Dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Textarea from 'primevue/textarea'
import { fetchUsers, sendUserInvite } from '../api/users'
import {
  applyDebugTag,
  fromDateTimeLocalInput,
  hasDebugTag,
  normalizeTextValue,
  parseDnList,
  parseTagList,
  toDateTimeLocalInput,
  toErrorMessage,
  toNullableNumber,
} from '../utils/formUtils'
import {
  addProjectMember,
  debugProvisionProject,
  debugCompleteUserAccount,
  deleteProject,
  fetchProject,
  fetchProjectPackets,
  fetchProjectUsage,
  fetchProjectUsers,
  provisionProjectInfrastructure,
  updateProject,
} from '../api/projects'
import PacketReferenceTable from '../components/PacketReferenceTable.vue'
import ProjectDetail from '../components/ProjectDetail.vue'
import LifecycleFlow from '../components/LifecycleFlow.vue'
import UsageDisplay from '../components/UsageDisplay.vue'
import UserList from '../components/UserList.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

const addMemberSection = ref(null)
const project = ref(null)
const projectForm = ref(createProjectForm())
const users = ref([])
const usage = ref(null)
const projectPackets = ref([])
const allPeople = ref([])
const loading = ref(false)
const usersLoading = ref(false)
const usageLoading = ref(false)
const projectPacketsLoading = ref(false)
const sendingPiInvite = ref(false)
const provisioningActionLoading = ref(false)
const debugProvisionLoading = ref(false)
const savingProject = ref(false)
const addingMember = ref(false)
const editingProject = ref(false)
const deletingProject = ref(false)
const showDeleteProjectDialog = ref(false)
const provisioningSuccess = ref('')
const provisioningError = ref('')
const projectMessage = ref(null)
const addMemberMessage = ref(null)
const error = ref(null)
const addMemberMode = ref('existing')
const addMemberForm = ref(createProjectMemberForm())

const provisioningStateLabel = computed(() => {
  const state = String(project.value?.lifecycle_state || 'received')
    .trim()
    .toLowerCase()
  const labels = {
    received: 'Received',
    waiting_pi_account: 'Waiting on PI Account Creation',
    pending_provisioning: 'Pending Provisioning (awaiting admin action)',
    provisioning: 'Provisioning in progress',
    provisioning_failed: 'Provisioning Failed',
    provisioned: 'Provisioned',
    aime_notified: 'AIME Notified',
    active: 'Active',
    inactive: 'Inactive',
  }
  return labels[state] || state || 'Unknown'
})

const canProvision = computed(() => {
  const current = project.value
  if (!current) return false
  const state = String(current.lifecycle_state || '').trim().toLowerCase()
  if (state === 'provisioning') return false
  if (state === 'pending_provisioning' || state === 'provisioning_failed') return true
  if (!current.kubernetes_namespace || !current.authentik_group_name) return true
  return false
})

const provisionButtonLabel = computed(() => {
  const state = String(project.value?.lifecycle_state || '').trim().toLowerCase()
  if (state === 'provisioning_failed') return 'Retry Provisioning'
  return 'Create Namespace + Authentik Group'
})

const availablePeople = computed(() =>
  [...allPeople.value].sort((left, right) =>
    formatPersonOption(left).localeCompare(formatPersonOption(right)),
  ),
)

function buildProvisioningStepActions() {
  return [
    {
      key: 'provision-project',
      label: provisionButtonLabel.value,
      icon: 'pi pi-cloud-upload',
      loading: provisioningActionLoading.value,
      disabled: !canProvision.value,
      onClick: onProvisionInfrastructure,
    },
  ]
}

function buildPiInviteStepActions(piMembership, label = 'Send PI Invite') {
  if (!piMembership || piMembership.account_made_at || piMembership.email_sent_at) {
    return []
  }

  return [
    {
      key: `pi-invite-${piMembership.project_user_id}`,
      label,
      icon: 'pi pi-send',
      loading: sendingPiInvite.value,
      disabled: sendingPiInvite.value || !piMembership.email,
      onClick: () => sendPiInvite(piMembership),
    },
  ]
}

const projectLifecycleSteps = computed(() => {
  const p = project.value
  if (!p) return []
  const ls = String(p.lifecycle_state || 'received').trim().toLowerCase()

  // Canonical order: received → provisioning → provisioned → waiting_pi_account → aime_notified → active
  // waiting_pi_account only appears for project_create flow; non-PI projects skip it.
  const ps = String(p.provisioning_state || 'received').trim().toLowerCase()
  const provisioningDone = ['provisioned', 'waiting_pi_account', 'aime_notified', 'active'].includes(ls)
  const pastWaiting = ['aime_notified', 'active'].includes(ls)
  const isCurrent = (targetState) => ls === targetState

  // Find the PI membership from the loaded project members list.
  const piMembership = users.value.find((u) => u.is_project_pi) ?? null

  // Step 1: Received packet creation — always complete
  const step1 = {
    label: 'Received packet creation',
    status: 'completed',
    timestamp: p.created_at,
    description: 'AIME packet received and project record created.',
  }

  // Step 2: Provisioning (namespace + Authentik group)
  let step2
  if (isCurrent('pending_provisioning') || isCurrent('received')) {
    step2 = {
      label: 'Create namespace in NRP',
      status: 'waiting',
      actionRequired: 'Create the Kubernetes namespace and Authentik group to continue provisioning.',
      actions: buildProvisioningStepActions(),
    }
  } else if (isCurrent('provisioning')) {
    step2 = {
      label: 'Create namespace in NRP',
      status: 'active',
      timestamp: p.provisioning_started_at,
      description: 'Kubernetes namespace and Authentik group are being created.',
    }
  } else if (isCurrent('provisioning_failed')) {
    step2 = {
      label: 'Create namespace in NRP',
      status: 'error',
      timestamp: p.provisioning_started_at,
      description: p.provisioning_last_error || 'Provisioning failed.',
      actionRequired: 'Resolve the provisioning issue, then retry this step.',
      actions: buildProvisioningStepActions(),
    }
  } else if (provisioningDone) {
    step2 = {
      label: 'Create namespace in NRP',
      status: 'completed',
      timestamp: p.provisioning_completed_at || p.provisioning_started_at,
      description: p.kubernetes_namespace ? `Namespace: ${p.kubernetes_namespace}` : null,
    }
  } else {
    step2 = { label: 'Create namespace in NRP', status: 'pending' }
  }

  // Step 3: PI creates account
  // The PI's account creation does NOT require a separate notify_account_create response to
  // AIME — it is covered by the notify_project_create packet sent in step 4.
  let step3
  if (!piMembership) {
    // PI membership not yet linked to a user record (e.g. still being ingested)
    step3 = {
      label: 'PI creates account',
      status: ps === 'received' ? 'pending' : 'waiting',
      description: 'PI has not yet been linked as a project member.',
      actionRequired:
        ps !== 'received'
          ? 'Add the PI as a project member so account setup can begin.'
          : null,
      actions: ps !== 'received'
        ? [
            {
              key: 'add-pi-membership',
              label: 'Add PI to Project',
              icon: 'pi pi-user-plus',
              severity: 'secondary',
              outlined: true,
              onClick: scrollToAddMemberSection,
            },
          ]
        : [],
    }
  } else if (piMembership.account_made_at) {
    step3 = {
      label: 'PI creates account',
      status: 'completed',
      timestamp: piMembership.account_made_at,
      description: `${piMembership.name} has completed account setup.`,
      link: {
        to: { name: 'person-detail', params: { id: piMembership.id } },
        label: `View PI user page — ${piMembership.name}`,
      },
    }
  } else if (piMembership.email_sent_at) {
    step3 = {
      label: 'PI creates account',
      status: 'active',
      timestamp: piMembership.email_sent_at,
      description: 'Invite sent — waiting for the PI to complete account setup.',
      link: {
        to: { name: 'person-detail', params: { id: piMembership.id } },
        label: `View PI user page — ${piMembership.name}`,
      },
    }
  } else {
    // PI is linked but no invite has been sent yet
    const piLabel = piMembership.name || piMembership.email || 'the PI'
    step3 = {
      label: 'PI creates account',
      status: 'waiting',
      actionRequired: piMembership.email
        ? `Send the invite email to ${piLabel} so they can create a local account.`
        : `Add an email address for ${piLabel}, then send the invite email.`,
      actions: buildPiInviteStepActions(piMembership),
      link: {
        to: { name: 'person-detail', params: { id: piMembership.id } },
        label: `View PI user page — ${piLabel}`,
      },
    }
  }

  const piAccountReady = Boolean(piMembership?.account_made_at)

  // Step 4: Notify project create back to AIME server
  // Requires both: namespace provisioned AND PI account created.
  let step4
  const notifyDone = ['aime_notified', 'active', 'inactive'].includes(ls)
  if (isCurrent('waiting_pi_account')) {
    step4 = {
      label: 'Notify project create to AIME server',
      status: 'waiting',
      actionRequired: 'Waiting for PI to complete account setup before sending project create notification.',
    }
  } else if (!provisioningDone) {
    step4 = {
      label: 'Notify project create to AIME server',
      status: 'pending',
      description: 'Waiting for namespace provisioning to complete.',
    }
  } else if (notifyDone) {
    step4 = {
      label: 'Notify project create to AIME server',
      status: 'completed',
      timestamp: p.provisioning_alerted_at,
      description: 'Project create notification sent to AIME.',
    }
  } else {
    // provisioned state — ready to notify, waiting on worker
    step4 = {
      label: 'Notify project create to AIME server',
      status: 'active',
      description: 'Namespace ready. Worker will send notify_project_create to AIME shortly.',
    }
  }

  // Step 5: Project active
  const step5 = {
    label: 'Project active',
    status: ['active', 'inactive'].includes(ls) ? 'completed'
      : notifyDone ? 'active'
      : 'pending',
    description: ls === 'inactive' ? 'Project is currently inactive.' : null,
  }

  // Step 6: Inactive / deactivated (only relevant when inactive)
  const step6 = {
    label: 'Project lifecycle complete',
    status: ['active', 'inactive'].includes(ls) ? 'completed' : 'pending',
  }

  return [step1, step2, step3, step4, step5, step6]
})

function createProjectForm(projectData = null) {
  const tags = Array.isArray(projectData?.tags) ? projectData.tags : []
  return {
    aime_allocation_id: projectData?.aime_allocation_id || '',
    name: projectData?.name || '',
    grant_number: projectData?.grant_number || '',
    allocation_record_id: projectData?.allocation_record_id || '',
    site_project_id: projectData?.site_project_id || '',
    allocation_type: projectData?.allocation_type || '',
    request_type: projectData?.request_type || '',
    source_packet_rec_id: toNullableNumber(projectData?.source_packet_rec_id),
    source_trans_rec_id: toNullableNumber(projectData?.source_trans_rec_id),
    source_transaction_id: toNullableNumber(projectData?.source_transaction_id),
    source_site_name: projectData?.source_site_name || '',
    tags_text: tags.join(', '),
    is_debug: hasDebugTag(tags),
    allocated_resource: projectData?.allocated_resource || '',
    service_units_allocated: toNullableNumber(projectData?.service_units_allocated),
    service_units_remaining: toNullableNumber(projectData?.service_units_remaining),
    start_date: projectData?.start_date || '',
    end_date: projectData?.end_date || '',
    project_title: projectData?.project_title || '',
    pfos_number: projectData?.pfos_number || '',
    board_type: projectData?.board_type || '',
    pi_person_id: projectData?.pi_person_id || '',
    pi_first_name: projectData?.pi_first_name || '',
    pi_middle_name: projectData?.pi_middle_name || '',
    pi_last_name: projectData?.pi_last_name || '',
    pi_email: projectData?.pi_email || '',
    pi_organization: projectData?.pi_organization || '',
    pi_org_code: projectData?.pi_org_code || '',
    pi_department: projectData?.pi_department || '',
    pi_business_phone_number: projectData?.pi_business_phone_number || '',
    resource_type: projectData?.resource_type || '',
    cpu_allocated: toNullableNumber(projectData?.cpu_allocated) ?? 0,
    gpu_allocated: toNullableNumber(projectData?.gpu_allocated) ?? 0,
    is_active: Boolean(projectData?.is_active ?? true),
    kubernetes_namespace: projectData?.kubernetes_namespace || '',
    authentik_group_name: projectData?.authentik_group_name || '',
    lifecycle_state: projectData?.lifecycle_state || 'received',
    provisioning_state: projectData?.provisioning_state || 'received',
    provisioning_requested_at: toDateTimeLocalInput(projectData?.provisioning_requested_at),
    provisioning_started_at: toDateTimeLocalInput(projectData?.provisioning_started_at),
    provisioning_completed_at: toDateTimeLocalInput(projectData?.provisioning_completed_at),
    provisioning_last_error: projectData?.provisioning_last_error || '',
    provisioning_alerted_at: toDateTimeLocalInput(projectData?.provisioning_alerted_at),
  }
}

function createProjectMemberForm() {
  return {
    existing_user_id: '',
    role: '',
    resource: '',
    allocated_resource: '',
    membership_service_units_allocated: null,
    membership_service_units_remaining: null,
    account_remote_site_login: '',
    account_is_active: true,
    account_state: 'received',
    source_packet_rec_id: null,
    source_trans_rec_id: null,
    source_transaction_id: null,
    new_user: {
      name: '',
      email: '',
      first_name: '',
      middle_name: '',
      last_name: '',
      person_id: '',
      global_id: '',
      organization: '',
      org_code: '',
      department: '',
      nsf_status_code: '',
      remote_site_login: '',
      source_site_name: '',
      service_units_allocated: null,
      is_active: true,
      is_debug: false,
      tags_text: '',
      dn_list_text: '',
    },
  }
}

function formatPersonOption(personOption) {
  const email = personOption?.email ? ` (${personOption.email})` : ''
  const personId = personOption?.person_id ? ` [${personOption.person_id}]` : ''
  const debug = hasDebugTag(personOption?.tags) ? ' [debug]' : ''
  return `${personOption?.name || 'Unnamed Person'}${email}${personId}${debug}`
}

function startProjectEdit() {
  projectForm.value = createProjectForm(project.value)
  editingProject.value = true
  projectMessage.value = null
}

function cancelProjectEdit() {
  editingProject.value = false
  projectForm.value = createProjectForm(project.value)
}

function resetAddMemberForm(clearMessage = true) {
  addMemberForm.value = createProjectMemberForm()
  if (clearMessage) {
    addMemberMessage.value = null
  }
}

async function loadPeopleCatalog() {
  try {
    allPeople.value = await fetchUsers(true)
  } catch {
    allPeople.value = []
  }
}

async function loadProject() {
  loading.value = true
  error.value = null
  try {
    project.value = await fetchProject(props.id)
    if (!editingProject.value) {
      projectForm.value = createProjectForm(project.value)
    }
  } catch (err) {
    error.value = toErrorMessage(err, 'Failed to load project.')
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

async function loadProjectPackets() {
  projectPacketsLoading.value = true
  try {
    projectPackets.value = await fetchProjectPackets(props.id)
  } catch {
    projectPackets.value = []
  } finally {
    projectPacketsLoading.value = false
  }
}

function scrollToAddMemberSection() {
  addMemberSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function saveProject() {
  if (!normalizeTextValue(projectForm.value.name)) {
    projectMessage.value = { severity: 'error', text: 'Project name is required.' }
    return
  }
  if (!normalizeTextValue(projectForm.value.aime_allocation_id)) {
    projectMessage.value = { severity: 'error', text: 'AIME allocation ID is required.' }
    return
  }
  if (!normalizeTextValue(projectForm.value.provisioning_state)) {
    projectMessage.value = { severity: 'error', text: 'Provisioning state is required.' }
    return
  }

  savingProject.value = true
  projectMessage.value = null
  try {
    const payload = {
      aime_allocation_id: normalizeTextValue(projectForm.value.aime_allocation_id),
      name: normalizeTextValue(projectForm.value.name),
      grant_number: normalizeTextValue(projectForm.value.grant_number),
      allocation_record_id: normalizeTextValue(projectForm.value.allocation_record_id),
      site_project_id: normalizeTextValue(projectForm.value.site_project_id),
      allocation_type: normalizeTextValue(projectForm.value.allocation_type),
      request_type: normalizeTextValue(projectForm.value.request_type),
      source_packet_rec_id: toNullableNumber(projectForm.value.source_packet_rec_id),
      source_trans_rec_id: toNullableNumber(projectForm.value.source_trans_rec_id),
      source_transaction_id: toNullableNumber(projectForm.value.source_transaction_id),
      source_site_name: normalizeTextValue(projectForm.value.source_site_name),
      tags: applyDebugTag(parseTagList(projectForm.value.tags_text), projectForm.value.is_debug),
      allocated_resource: normalizeTextValue(projectForm.value.allocated_resource),
      service_units_allocated: toNullableNumber(projectForm.value.service_units_allocated),
      service_units_remaining: toNullableNumber(projectForm.value.service_units_remaining),
      start_date: projectForm.value.start_date || null,
      end_date: projectForm.value.end_date || null,
      project_title: normalizeTextValue(projectForm.value.project_title),
      pfos_number: normalizeTextValue(projectForm.value.pfos_number),
      board_type: normalizeTextValue(projectForm.value.board_type),
      pi_person_id: normalizeTextValue(projectForm.value.pi_person_id),
      pi_first_name: normalizeTextValue(projectForm.value.pi_first_name),
      pi_middle_name: normalizeTextValue(projectForm.value.pi_middle_name),
      pi_last_name: normalizeTextValue(projectForm.value.pi_last_name),
      pi_email: normalizeTextValue(projectForm.value.pi_email),
      pi_organization: normalizeTextValue(projectForm.value.pi_organization),
      pi_org_code: normalizeTextValue(projectForm.value.pi_org_code),
      pi_department: normalizeTextValue(projectForm.value.pi_department),
      pi_business_phone_number: normalizeTextValue(projectForm.value.pi_business_phone_number),
      resource_type: normalizeTextValue(projectForm.value.resource_type),
      cpu_allocated: toNullableNumber(projectForm.value.cpu_allocated) ?? 0,
      gpu_allocated: toNullableNumber(projectForm.value.gpu_allocated) ?? 0,
      is_active: Boolean(projectForm.value.is_active),
      kubernetes_namespace: normalizeTextValue(projectForm.value.kubernetes_namespace),
      authentik_group_name: normalizeTextValue(projectForm.value.authentik_group_name),
      provisioning_state: normalizeTextValue(projectForm.value.provisioning_state),
      provisioning_requested_at: fromDateTimeLocalInput(projectForm.value.provisioning_requested_at),
      provisioning_started_at: fromDateTimeLocalInput(projectForm.value.provisioning_started_at),
      provisioning_completed_at: fromDateTimeLocalInput(projectForm.value.provisioning_completed_at),
      provisioning_last_error: normalizeTextValue(projectForm.value.provisioning_last_error),
      provisioning_alerted_at: fromDateTimeLocalInput(projectForm.value.provisioning_alerted_at),
    }

    project.value = await updateProject(props.id, payload)
    projectForm.value = createProjectForm(project.value)
    await loadProjectPackets()
    editingProject.value = false
    projectMessage.value = { severity: 'success', text: 'Project details updated successfully.' }
  } catch (err) {
    projectMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to update project details.'),
    }
  } finally {
    savingProject.value = false
  }
}

async function submitAddMember() {
  addMemberMessage.value = null

  if (addMemberMode.value === 'existing' && !addMemberForm.value.existing_user_id) {
    addMemberMessage.value = { severity: 'error', text: 'Choose an existing person first.' }
    return
  }

  if (addMemberMode.value === 'new') {
    const hasName = normalizeTextValue(addMemberForm.value.new_user.name)
    const hasFirst = normalizeTextValue(addMemberForm.value.new_user.first_name)
    const hasLast = normalizeTextValue(addMemberForm.value.new_user.last_name)
    if (!hasName && !(hasFirst && hasLast)) {
      addMemberMessage.value = {
        severity: 'error',
        text: 'New people need either a full name or both first and last name.',
      }
      return
    }
  }

  addingMember.value = true
  try {
    const payload = {
      role: normalizeTextValue(addMemberForm.value.role),
      resource: normalizeTextValue(addMemberForm.value.resource),
      allocated_resource: normalizeTextValue(addMemberForm.value.allocated_resource),
      membership_service_units_allocated: toNullableNumber(
        addMemberForm.value.membership_service_units_allocated,
      ),
      membership_service_units_remaining: toNullableNumber(
        addMemberForm.value.membership_service_units_remaining,
      ),
      account_remote_site_login: normalizeTextValue(addMemberForm.value.account_remote_site_login),
      account_is_active: Boolean(addMemberForm.value.account_is_active),
      account_state: normalizeTextValue(addMemberForm.value.account_state),
      source_packet_rec_id: toNullableNumber(addMemberForm.value.source_packet_rec_id),
      source_trans_rec_id: toNullableNumber(addMemberForm.value.source_trans_rec_id),
      source_transaction_id: toNullableNumber(addMemberForm.value.source_transaction_id),
    }

    if (addMemberMode.value === 'existing') {
      payload.existing_user_id = addMemberForm.value.existing_user_id
    } else {
      payload.new_user = {
        name: normalizeTextValue(addMemberForm.value.new_user.name),
        email: normalizeTextValue(addMemberForm.value.new_user.email),
        tags: applyDebugTag(
          parseTagList(addMemberForm.value.new_user.tags_text),
          addMemberForm.value.new_user.is_debug,
        ),
        first_name: normalizeTextValue(addMemberForm.value.new_user.first_name),
        middle_name: normalizeTextValue(addMemberForm.value.new_user.middle_name),
        last_name: normalizeTextValue(addMemberForm.value.new_user.last_name),
        person_id: normalizeTextValue(addMemberForm.value.new_user.person_id),
        global_id: normalizeTextValue(addMemberForm.value.new_user.global_id),
        organization: normalizeTextValue(addMemberForm.value.new_user.organization),
        org_code: normalizeTextValue(addMemberForm.value.new_user.org_code),
        department: normalizeTextValue(addMemberForm.value.new_user.department),
        nsf_status_code: normalizeTextValue(addMemberForm.value.new_user.nsf_status_code),
        remote_site_login: normalizeTextValue(addMemberForm.value.new_user.remote_site_login),
        source_site_name: normalizeTextValue(addMemberForm.value.new_user.source_site_name),
        service_units_allocated: toNullableNumber(
          addMemberForm.value.new_user.service_units_allocated,
        ),
        is_active: Boolean(addMemberForm.value.new_user.is_active),
        dn_list: parseDnList(addMemberForm.value.new_user.dn_list_text),
      }
    }

    await addProjectMember(props.id, payload)
    resetAddMemberForm(false)
    addMemberMessage.value = { severity: 'success', text: 'Person added to the project.' }
    await Promise.all([loadUsers(), loadPeopleCatalog()])
  } catch (err) {
    addMemberMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to add person to the project.'),
    }
  } finally {
    addingMember.value = false
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

async function sendPiInvite(piMembership) {
  if (!piMembership?.id) return
  sendingPiInvite.value = true
  projectMessage.value = null
  try {
    const result = await sendUserInvite(piMembership.id, {
      expires_in_hours: 72,
      invited_by: 'admin:project-lifecycle',
      send_email: true,
      metadata: {
        trigger: 'project-lifecycle',
        project_id: project.value?.id || null,
      },
    })
    projectMessage.value = {
      severity: 'success',
      text: `Invite sent for ${piMembership.name || piMembership.email || 'the PI'}.`,
      url: result?.invite_url || null,
    }
  } catch (err) {
    projectMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to send the PI invite.'),
    }
  } finally {
    sendingPiInvite.value = false
    await loadUsers()
  }
}

async function onDebugProvision() {
  if (!project.value) return
  debugProvisionLoading.value = true
  provisioningSuccess.value = ''
  provisioningError.value = ''
  try {
    const result = await debugProvisionProject(project.value.id)
    if (result?.ok) {
      provisioningSuccess.value =
        `Debug provisioning complete. Mock namespace: ${result.kubernetes_namespace}`
    } else {
      provisioningError.value = 'Debug provisioning failed.'
    }
  } catch (err) {
    provisioningError.value =
      err?.response?.data?.detail || 'Failed to debug-provision project.'
  } finally {
    debugProvisionLoading.value = false
    await Promise.all([loadProject(), loadUsers()])
  }
}

async function onDebugCompleteAccount(projectUserId) {
  if (!project.value) return
  try {
    const result = await debugCompleteUserAccount(project.value.id, projectUserId)
    if (result?.ok) {
      projectMessage.value = {
        severity: 'success',
        text: `Debug account complete for ${result.remote_site_login}. State: ${result.account_state}`,
      }
    }
  } catch (err) {
    projectMessage.value = {
      severity: 'error',
      text: err?.response?.data?.detail || 'Failed to debug-complete user account.',
    }
  }
  await Promise.all([loadProject(), loadUsers()])
}

async function confirmDeleteProject() {
  deletingProject.value = true
  showDeleteProjectDialog.value = false
  try {
    await deleteProject(props.id)
    router.push({ name: 'projects' })
  } catch (err) {
    projectMessage.value = {
      severity: 'error',
      text: toErrorMessage(err, 'Failed to deactivate project.'),
    }
  } finally {
    deletingProject.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    loadProject(),
    loadUsers(),
    loadUsage(),
    loadProjectPackets(),
    loadPeopleCatalog(),
  ])
})
</script>
