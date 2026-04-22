"""Tests for portal-backed namespace provisioning behavior."""

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

        result = service.ensure_project_namespace(project=project)

        assert result["ok"] is True
        assert result["status"] == "verified_after_error"
        assert result["namespace"] == namespace
        assert result["authentik_group_name"] == namespace
        assert result["create_error"]["error"] == "The read operation timed out"
        assert result["existence_check"]["ok"] is True
        assert result["existence_check"]["exists"] is True
