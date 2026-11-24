"""Tests for portal-backed namespace provisioning behavior."""

import pytest

from app.config import settings
from app.services.kubernetes.service import KubernetesProvisioningService


class TestEnsureProjectNamespace:
    """Verify namespace provisioning handles portal timing edge cases."""

    def test_uses_create_namespace_timeout(self, db, make_project, monkeypatch):
        project = make_project(db, grant_number="AGR260006")
        service = KubernetesProvisioningService()
        captured: dict[str, object] = {}

        monkeypatch.setattr(settings, "portal_rpc_create_namespace_timeout_seconds", 75.0)

        def fake_call_portal_rpc(*, method, params, timeout_seconds=None):
            captured["method"] = method
            captured["params"] = params
            captured["timeout_seconds"] = timeout_seconds
            return {"ok": True, "result": {"created": True}}

        monkeypatch.setattr(service, "_call_portal_rpc", fake_call_portal_rpc)

        result = service.ensure_project_namespace(project=project)

        assert result["ok"] is True
        assert captured["method"] == "admin.CreateNamespace"
        assert captured["timeout_seconds"] == 75.0

    def test_recovers_when_namespace_exists_after_create_error(
        self,
        db,
        make_project,
        monkeypatch,
    ):
        project = make_project(db, grant_number="AGR260006")
        service = KubernetesProvisioningService()
        namespace = service.namespace_for_project(project=project)

        def fake_call_portal_rpc(*, method, params, timeout_seconds=None):
            _ = params
            _ = timeout_seconds
            if method == "admin.CreateNamespace":
                return {
                    "ok": False,
                    "status": "rpc_error",
                    "method": method,
                    "error": "The read operation timed out",
                }
            raise AssertionError(f"Unexpected RPC method {method}")

        monkeypatch.setattr(service, "_call_portal_rpc", fake_call_portal_rpc)
        monkeypatch.setattr(
            service,
            "list_all_namespaces",
            lambda *, timeout_seconds=None: {
                "ok": True,
                "status": "rpc",
                "namespaces": [namespace],
                "rpc_result": {"namespaces": [namespace], "timeout_seconds": timeout_seconds},
            },
        )

        monkeypatch.setattr(
            service,
            "get_namespace_users",
            lambda *, namespace: {
                "ok": True,
                "status": "rpc",
                "namespace": namespace,
                "member_ids": ["portal-provisioner"],
            },
        )

        result = service.ensure_project_namespace(project=project)

        assert result["ok"] is True
        assert result["status"] == "verified_after_error"
        assert result["namespace"] == namespace
        assert result["authentik_group_name"] == namespace
        assert result["create_error"]["error"] == "The read operation timed out"
        assert result["existence_check"]["ok"] is True
        assert result["existence_check"]["exists"] is True

    @pytest.mark.parametrize(
        "group_check",
        [
            # Portal GetNSUsers returns an empty list when the Authentik group
            # is missing; a real group always contains its creator.
            {"ok": True, "status": "rpc", "member_ids": []},
            {"ok": False, "status": "rpc_error", "error": "boom"},
        ],
        ids=["group-has-no-members", "group-check-failed"],
    )
    def test_fails_when_namespace_exists_but_authentik_group_missing(
        self,
        db,
        make_project,
        monkeypatch,
        group_check,
    ):
        """Portal creates the k8s namespace before the Authentik group.

        If the group step fails, the namespace alone must not count as
        provisioned: users could never be added (AddNSUser fails with
        "authentik group ... does not exist yet").
        """
        project = make_project(db, grant_number="NAIRR260536")
        service = KubernetesProvisioningService()
        namespace = service.namespace_for_project(project=project)

        monkeypatch.setattr(
            service,
            "_call_portal_rpc",
            lambda *, method, params, timeout_seconds=None: {
                "ok": False,
                "status": "rpc_error",
                "method": method,
                "error": "error creating authentik group: 500",
            },
        )
        monkeypatch.setattr(
            service,
            "list_all_namespaces",
            lambda *, timeout_seconds=None: {
                "ok": True,
                "status": "rpc",
                "namespaces": [namespace],
            },
        )
        monkeypatch.setattr(
            service,
            "get_namespace_users",
            lambda *, namespace: {"namespace": namespace, **group_check},
        )

        result = service.ensure_project_namespace(project=project)

        assert result["ok"] is False
        assert result["status"] == "authentik_group_missing"
        assert result["namespace"] == namespace
        assert result["create_error"]["error"] == "error creating authentik group: 500"
