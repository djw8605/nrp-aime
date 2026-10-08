"""Tests for GPU project scope and created_by attribution."""

from app.models.gpu_usage_record import GpuUsageRecord
from app.services.gpu_accounting.attribution import Attribution, GpuUsageAttributor
from app.services.gpu_accounting.scope import is_exportable_gpu_project, is_gpu_project

GPU = "pnrp.sdsc.access-ci.org"
ALICE = "http://cilogon.org/serverE/users/1001"
BOB = "https://cilogon.org/serverA/users/2002"


def _gpu_project(db, make_project, **overrides):
    defaults = {
        "allocated_resource": GPU,
        "site_project_id": "p.gpu1",
        "kubernetes_namespace": "ns-gpu",
    }
    defaults.update(overrides)
    return make_project(db, **defaults)


class TestScope:
    def test_gpu_project_matches_allocated_resource(self, db, make_project):
        assert is_gpu_project(_gpu_project(db, make_project))
        assert not is_gpu_project(make_project(db, allocated_resource="nrp-classroom.access-ci.org"))
        assert not is_gpu_project(make_project(db, allocated_resource=None))

    def test_exportable_requires_ids_and_excludes_debug(self, db, make_project):
        assert is_exportable_gpu_project(_gpu_project(db, make_project))
        assert not is_exportable_gpu_project(_gpu_project(db, make_project, site_project_id=None))
        assert not is_exportable_gpu_project(_gpu_project(db, make_project, kubernetes_namespace=""))
        assert not is_exportable_gpu_project(_gpu_project(db, make_project, tags=["Debug"]))


class TestAttribution:
    def test_is_person(self):
        assert GpuUsageAttributor.is_person(ALICE)
        assert GpuUsageAttributor.is_person(BOB)
        assert not GpuUsageAttributor.is_person("system:serviceaccount:ns:sa")
        assert not GpuUsageAttributor.is_person("")

    def test_member_person_uses_project_login(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, project, alice, remote_site_login="alice_nrp")

        result = GpuUsageAttributor(db).attribute(project, ALICE)

        assert result == Attribution("alice_nrp", GpuUsageRecord.ATTRIBUTION_MEMBER)

    def test_member_with_cilogon_url_login_gets_amie_tail(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, project, alice, remote_site_login="http://cilogon.org/serverE/users/546379")

        result = GpuUsageAttributor(db).attribute(project, ALICE)

        assert result == Attribution(
            "logon.org/serverE/users/546379", GpuUsageRecord.ATTRIBUTION_MEMBER
        )

    def test_person_not_in_project_is_dropped(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        other = _gpu_project(db, make_project, kubernetes_namespace="ns-other", site_project_id="p.other")
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, other, alice, remote_site_login="alice_nrp")

        assert GpuUsageAttributor(db).attribute(project, ALICE) is None

    def test_member_without_login_is_dropped(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        alice = make_user(db, remote_site_login=ALICE)
        make_project_user(db, project, alice, remote_site_login=None)

        assert GpuUsageAttributor(db).attribute(project, ALICE) is None

    def test_unknown_person_is_dropped(self, db, make_project):
        project = _gpu_project(db, make_project)
        assert GpuUsageAttributor(db).attribute(project, BOB) is None

    def test_service_account_charged_to_pi(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        pi = make_user(db)
        make_project_user(db, project, pi, role="PI", remote_site_login="pi_nrp")
        db.refresh(project)

        result = GpuUsageAttributor(db).attribute(project, "system:serviceaccount:ns-gpu:runner")

        assert result == Attribution("pi_nrp", GpuUsageRecord.ATTRIBUTION_PI)

    def test_pi_with_cilogon_url_login_gets_amie_tail(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        pi = make_user(db)
        make_project_user(
            db, project, pi, role="PI",
            remote_site_login="http://cilogon.org/serverE/users/546379",
        )
        db.refresh(project)

        result = GpuUsageAttributor(db).attribute(project, "system:serviceaccount:ns-gpu:runner")

        assert result == Attribution(
            "logon.org/serverE/users/546379", GpuUsageRecord.ATTRIBUTION_PI
        )

    def test_service_account_with_pi_missing_login_is_pending(self, db, make_project, make_user, make_project_user):
        project = _gpu_project(db, make_project)
        pi = make_user(db)
        make_project_user(db, project, pi, role="pi", remote_site_login=None)
        db.refresh(project)

        result = GpuUsageAttributor(db).attribute(project, "")

        assert result == Attribution("", GpuUsageRecord.ATTRIBUTION_PI)
