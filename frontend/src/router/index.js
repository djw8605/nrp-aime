import { createRouter, createWebHistory } from 'vue-router'
import ProjectsView from '../views/ProjectsView.vue'
import ProjectDetailView from '../views/ProjectDetailView.vue'
import PacketLogsView from '../views/PacketLogsView.vue'
import ManualPacketInputView from '../views/ManualPacketInputView.vue'
import TransactionDetailView from '../views/TransactionDetailView.vue'
import AdminView from '../views/AdminView.vue'
import InviteAcceptView from '../views/InviteAcceptView.vue'
import InviteSuccessView from '../views/InviteSuccessView.vue'
import InviteErrorView from '../views/InviteErrorView.vue'
import PeopleView from '../views/PeopleView.vue'
import PersonDetailView from '../views/PersonDetailView.vue'

const routes = [
  {
    path: '/',
    name: 'projects',
    component: ProjectsView,
  },
  {
    path: '/projects/:id',
    name: 'project-detail',
    component: ProjectDetailView,
    props: true,
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminView,
  },
  {
    path: '/people',
    name: 'people',
    component: PeopleView,
  },
  {
    path: '/people/:id',
    name: 'person-detail',
    component: PersonDetailView,
    props: true,
  },
  {
    path: '/invite/accept',
    name: 'invite-accept',
    component: InviteAcceptView,
  },
  {
    path: '/invite/success',
    name: 'invite-success',
    component: InviteSuccessView,
  },
  {
    path: '/invite/error',
    name: 'invite-error',
    component: InviteErrorView,
  },
  {
    path: '/packets/logs',
    name: 'packet-logs',
    component: PacketLogsView,
  },
  {
    path: '/packets/manual',
    name: 'manual-packet-input',
    component: ManualPacketInputView,
  },
  {
    path: '/transactions/:transactionId',
    name: 'transaction-detail',
    component: TransactionDetailView,
    props: true,
  },
  {
    path: '/packets/unprocessed',
    redirect: { name: 'packet-logs' },
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
