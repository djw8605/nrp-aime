"""Portal-backed namespace provisioning service."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import re
from typing import Any
import uuid

import httpx

from app.config import settings
from app.models.project_user import ProjectUser
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)

_SAFE_CHARS = re.compile(r"[^a-z0-9-]+")


class KubernetesProvisioningService:
    """Namespace and membership provisioning via NRP portal JSON-RPC."""

    @staticmethod
    def _normalize_namespace_fragment(value: str) -> str:
        normalized = _SAFE_CHARS.sub("-", (value or "").strip().lower())
        normalized = normalized.strip("-")
        return normalized[:63] if normalized else "project"

    def namespace_for_project(self, *, project: Project) -> str:
        """Build deterministic namespace name for a project."""
        if project.kubernetes_namespace:
            return project.kubernetes_namespace

        seed = (
            project.site_project_id
            or project.grant_number
            or project.aime_allocation_id
            or str(project.id)
        )
        return f"nrp-{self._normalize_namespace_fragment(seed)}"

    @staticmethod
    def membership_identifier(
        *,
        user: User,
        project_user: ProjectUser | None = None,
    ) -> str | None:
        """Resolve Authentik username for namespace membership operations."""
        if project_user is not None and project_user.remote_site_login:
            value = str(project_user.remote_site_login).strip()
            if value:
                return value
        if user.remote_site_login:
            value = str(user.remote_site_login).strip()
            if value:
                return value
        return None

    @staticmethod
    def _portal_token_configured() -> bool:
        return bool((settings.portal_rpc_token or "").strip())

    @staticmethod
    def _rpc_headers() -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Portal-RPC-Token": settings.portal_rpc_token,
        }

    def _call_portal_rpc(
        self,
        *,
        method: str,
        params: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self._portal_token_configured():
            return {
                "ok": False,
                "status": "config_error",
                "method": method,
                "error": "PORTAL_RPC_TOKEN is not configured",
            }

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id,
        }
        request_timeout = (
            settings.portal_rpc_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )

        try:
            response = httpx.post(
                settings.portal_rpc_url,
                json=payload,
                headers=self._rpc_headers(),
                timeout=request_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Portal RPC request failed method=%s", method)
            return {
                "ok": False,
                "status": "rpc_error",
                "method": method,
                "error": str(exc),
            }

        if response.status_code >= 400:
            return {
                "ok": False,
                "status": "http_error",
                "method": method,
                "http_status": response.status_code,
                "error": response.text,
            }

        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            return {
                "ok": False,
                "status": "rpc_error",
                "method": method,
                "error": "Invalid JSON response from portal RPC",
                "response_text": response.text,
            }

        if body.get("error") is not None:
            return {
                "ok": False,
                "status": "rpc_error",
                "method": method,
                "error": body.get("error"),
            }

        return {
            "ok": True,
            "status": "rpc",
            "method": method,
            "result": body.get("result"),
        }

    @staticmethod
    def _extract_rows(result: Any, keys: tuple[str, ...]) -> list[Any]:
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in keys:
                value = result.get(key)
                if isinstance(value, list):
                    return value
            nested_result = result.get("result")
            if isinstance(nested_result, dict):
                for key in keys:
                    value = nested_result.get(key)
                    if isinstance(value, list):
                        return value
        return []

    @staticmethod
    def _namespace_from_row(row: Any) -> str | None:
        if isinstance(row, str):
            value = row.strip()
            return value or None
        if isinstance(row, dict):
            for key in ("Namespace", "namespace", "Name", "name"):
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _user_from_row(row: Any) -> str | None:
        if isinstance(row, str):
            value = row.strip()
            return value or None
        if isinstance(row, dict):
            for key in (
                "UserID",
                "user_id",
                "User",
                "user",
                "Username",
                "username",
                "ID",
                "id",
            ):
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def namespace_info_for_project(*, project: Project) -> dict[str, Any]:
        """Build flattened NSInfo metadata from project registration fields."""
        pi_name = " ".join(
            part.strip()
            for part in (
                project.pi_first_name or "",
                project.pi_middle_name or "",
                project.pi_last_name or "",
            )
            if part and part.strip()
        ).strip()
        pi_value = pi_name or (project.pi_email or project.pi_person_id or "")

        institution_parts = [
            part.strip()
            for part in (
                project.pi_organization,
                project.pi_department,
                project.pi_org_code,
            )
            if part and str(part).strip()
        ]
        institution_value = " / ".join(institution_parts)

        grant_value = (
            project.grant_number
            or project.pfos_number
            or project.aime_allocation_id
            or project.allocation_record_id
            or ""
        )

        description_parts: list[str] = []
        if project.project_title and project.project_title.strip():
            description_parts.append(project.project_title.strip())
        if project.name and project.name.strip() and project.name.strip() not in description_parts:
            description_parts.append(project.name.strip())
        if project.request_type:
            description_parts.append(f"request_type={project.request_type}")
        if project.allocation_type:
            description_parts.append(f"allocation_type={project.allocation_type}")
        if project.site_project_id:
            description_parts.append(f"site_project_id={project.site_project_id}")
        if project.aime_allocation_id:
            description_parts.append(f"aime_allocation_id={project.aime_allocation_id}")
        if project.start_date:
            description_parts.append(f"start={project.start_date.isoformat()}")
        if project.end_date:
            description_parts.append(f"end={project.end_date.isoformat()}")
        description_value = " | ".join(description_parts)

        software_parts: list[str] = []
        if project.resource_type:
            software_parts.append(str(project.resource_type).strip())
        if project.board_type:
            software_parts.append(f"board_type={project.board_type}")
        if project.cpu_allocated or project.gpu_allocated:
            software_parts.append(
                f"cpu_allocated={project.cpu_allocated},gpu_allocated={project.gpu_allocated}"
            )
        software_value = "; ".join(software_parts)

        descrmtime = int(
            project.source_transaction_id
            or project.source_trans_rec_id
            or project.source_packet_rec_id
            or int((project.created_at or datetime.now(UTC)).timestamp())
        )

        # Fields not currently represented in project registration are left empty.
        return {
            "pi": pi_value,
            "grant": str(grant_value),
            "description": description_value,
            "gitrepo": "",
            "institution": institution_value,
            "software": software_value,
            "publications": "",
            "pubmtime": 0,
            "descrmtime": max(0, descrmtime),
        }

    def ensure_project_namespace(self, *, project: Project) -> dict[str, Any]:
        """Create namespace via portal RPC and return status."""
        namespace = self.namespace_for_project(project=project)
        create_timeout_seconds = settings.portal_rpc_create_namespace_timeout_seconds
        params = {
            "Namespace": settings.portal_rpc_namespace,
            "NewNamespace": namespace,
            "GroupFeatures": ["is_k8s_namespace"],
        }
        rpc = self._call_portal_rpc(
            method="admin.CreateNamespace",
            params=params,
            timeout_seconds=create_timeout_seconds,
        )
        if not rpc.get("ok", False):
            existence_check = self.namespace_exists(
                namespace=namespace,
                timeout_seconds=create_timeout_seconds,
            )
            if existence_check.get("ok") and existence_check.get("exists"):
                logger.warning(
                    "Portal namespace create returned error but namespace exists "
                    "project_id=%s namespace=%s rpc=%s existence_check=%s",
                    project.id,
                    namespace,
                    rpc,
                    existence_check,
                )
                return {
                    "ok": True,
                    "status": "verified_after_error",
                    "namespace": namespace,
                    "authentik_group_name": namespace,
                    "create_error": rpc,
                    "existence_check": existence_check,
                }

            logger.warning(
                "Portal namespace provisioning failed project_id=%s namespace=%s "
                "rpc=%s existence_check=%s",
                project.id,
                namespace,
                rpc,
                existence_check,
            )
            return {
                **rpc,
                "namespace": namespace,
                "existence_check": existence_check,
            }

        logger.info(
            "Portal namespace provisioned project_id=%s namespace=%s",
            project.id,
            namespace,
        )
        return {
            "ok": True,
            "status": "rpc",
            "namespace": namespace,
            "authentik_group_name": namespace,
            "rpc_result": rpc.get("result"),
        }

    def set_project_namespace_info(self, *, project: Project) -> dict[str, Any]:
        """Set namespace metadata for project via portal RPC."""
        namespace = self.namespace_for_project(project=project)
        info = self.namespace_info_for_project(project=project)
        return self.set_namespace_info(namespace=namespace, info=info)

    def set_namespace_info(
        self,
        *,
        namespace: str,
        info: dict[str, Any],
    ) -> dict[str, Any]:
        """Update namespace metadata via portal RPC (flattened params)."""
        cleaned_info = {str(key): value for key, value in (info or {}).items() if value is not None}
        if not cleaned_info:
            return {
                "ok": True,
                "status": "skipped",
                "namespace": namespace,
                "info": {},
            }
        params = {"Namespace": namespace, **cleaned_info}
        rpc = self._call_portal_rpc(method="admin.SetNamespaceInfo", params=params)
        if rpc.get("ok", False):
            return {
                "ok": True,
                "status": "rpc",
                "namespace": namespace,
                "info": cleaned_info,
                "rpc_result": rpc.get("result"),
            }

        return {
            "ok": False,
            "status": "rpc_error",
            "namespace": namespace,
            "info": cleaned_info,
            "error": rpc,
        }

    def list_all_namespaces(
        self,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """List namespaces via portal RPC for reconciliation."""
        rpc = self._call_portal_rpc(
            method="admin.ListAllNamespaces",
            params={},
            timeout_seconds=timeout_seconds,
        )
        if not rpc.get("ok", False):
            return rpc

        rows = self._extract_rows(
            rpc.get("result"),
            ("Namespaces", "namespaces", "Items", "items"),
        )
        namespaces = sorted(
            {
                namespace
                for row in rows
                for namespace in [self._namespace_from_row(row)]
                if namespace
            }
        )
        return {
            "ok": True,
            "status": "rpc",
            "namespaces": namespaces,
            "rpc_result": rpc.get("result"),
        }

    def namespace_exists(
        self,
        *,
        namespace: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Check whether a namespace is visible in the portal."""
        list_result = self.list_all_namespaces(timeout_seconds=timeout_seconds)
        if not list_result.get("ok", False):
            return {
                "ok": False,
                "status": list_result.get("status", "rpc_error"),
                "namespace": namespace,
                "error": list_result,
            }

        exists = namespace in set(list_result.get("namespaces", []))
        return {
            "ok": True,
            "status": "rpc",
            "namespace": namespace,
            "exists": exists,
            "rpc_result": list_result.get("rpc_result"),
        }

    def get_namespace_users(self, *, namespace: str) -> dict[str, Any]:
        """List namespace user identifiers via portal RPC."""
        rpc = self._call_portal_rpc(
            method="admin.GetNSUsers",
            params={"Namespace": namespace},
        )
        if not rpc.get("ok", False):
            return {
                **rpc,
                "namespace": namespace,
            }

        user_rows = self._extract_rows(
            rpc.get("result"),
            ("Users", "users"),
        )
        admin_rows = self._extract_rows(
            rpc.get("result"),
            ("Admins", "admins"),
        )
        user_ids = sorted(
            {
                user_id
                for row in user_rows
                for user_id in [self._user_from_row(row)]
                if user_id
            }
        )
        admin_ids = sorted(
            {
                user_id
                for row in admin_rows
                for user_id in [self._user_from_row(row)]
                if user_id
            }
        )
        member_ids = sorted(set(user_ids) | set(admin_ids))
        return {
            "ok": True,
            "status": "rpc",
            "namespace": namespace,
            "user_ids": user_ids,
            "admin_ids": admin_ids,
            "member_ids": member_ids,
            "rpc_result": rpc.get("result"),
        }

    def add_namespace_user(self, *, namespace: str, user_id: str) -> dict[str, Any]:
        """Add user to namespace via portal RPC."""
        rpc = self._call_portal_rpc(
            method="admin.AddNSUser",
            params={
                "Namespace": namespace,
                "UserID": str(user_id),
            },
        )
        if not rpc.get("ok", False):
            return {
                **rpc,
                "namespace": namespace,
                "user": str(user_id),
            }
        return {
            "ok": True,
            "status": "rpc",
            "namespace": namespace,
            "user": str(user_id),
            "rpc_result": rpc.get("result"),
        }

    def remove_namespace_user(self, *, namespace: str, user_id: str) -> dict[str, Any]:
        """Remove user from namespace via portal RPC."""
        rpc = self._call_portal_rpc(
            method="admin.DeleteNSUser",
            params={
                "Namespace": namespace,
                "UserID": str(user_id),
            },
        )
        if not rpc.get("ok", False):
            return {
                **rpc,
                "namespace": namespace,
                "user": str(user_id),
            }
        return {
            "ok": True,
            "status": "rpc",
            "namespace": namespace,
            "user": str(user_id),
            "rpc_result": rpc.get("result"),
        }

    def ensure_user_project_access(
        self,
        *,
        project: Project,
        user: User,
        project_user: ProjectUser | None = None,
    ) -> dict[str, Any]:
        """Ensure user's namespace/group membership via portal RPC."""
        namespace = self.namespace_for_project(project=project)
        identity = self.membership_identifier(user=user, project_user=project_user)
        if not identity:
            return {
                "ok": False,
                "status": "missing_username",
                "namespace": namespace,
                "error": (
                    "Missing Authentik username (remote_site_login); "
                    "cannot call admin.AddNSUser"
                ),
                "project_id": str(project.id),
                "user_id": str(user.id),
                "project_user_id": str(project_user.id) if project_user else None,
            }
        add_result = self.add_namespace_user(namespace=namespace, user_id=str(identity))
        if not add_result.get("ok", False):
            logger.warning(
                "Portal namespace membership failed namespace=%s project_id=%s user=%s rpc=%s",
                namespace,
                project.id,
                identity,
                add_result,
            )
            return add_result

        logger.info(
            "Portal namespace membership ensured namespace=%s project_id=%s user=%s",
            namespace,
            project.id,
            identity,
        )
        return add_result

    def remove_user_project_access(
        self,
        *,
        project: Project,
        user: User,
        project_user: ProjectUser | None = None,
    ) -> dict[str, Any]:
        """Remove user's namespace/group membership via portal RPC."""
        namespace = self.namespace_for_project(project=project)
        identity = self.membership_identifier(user=user, project_user=project_user)
        if not identity:
            return {
                "ok": False,
                "status": "missing_username",
                "namespace": namespace,
                "error": (
                    "Missing Authentik username (remote_site_login); "
                    "cannot call admin.DeleteNSUser"
                ),
                "project_id": str(project.id),
                "user_id": str(user.id),
                "project_user_id": str(project_user.id) if project_user else None,
            }
        remove_result = self.remove_namespace_user(
            namespace=namespace,
            user_id=str(identity),
        )
        if not remove_result.get("ok", False):
            logger.warning(
                "Portal namespace membership removal failed namespace=%s project_id=%s user=%s rpc=%s",
                namespace,
                project.id,
                identity,
                remove_result,
            )
            return remove_result

        logger.info(
            "Portal namespace membership removed namespace=%s project_id=%s user=%s",
            namespace,
            project.id,
            identity,
        )
        return remove_result
