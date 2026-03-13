"""Prometheus metrics service.

Queries the NRP Prometheus endpoint for CPU and GPU usage metrics
associated with a specific Kubernetes namespace.
"""

import logging

import httpx

from app.config import settings
from app.schemas.project import ProjectUsage

logger = logging.getLogger(__name__)


class PrometheusService:
    """Client for the NRP Prometheus instance."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.prometheus_url).rstrip("/")

    def _query(self, promql: str) -> float:
        """Execute an instant PromQL query and return the scalar result."""
        url = f"{self.base_url}/api/v1/query"
        try:
            resp = httpx.get(url, params={"query": promql}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            if results:
                return float(results[0]["value"][1])
        except Exception as exc:
            logger.warning("Prometheus query failed (%s): %s", promql, exc)
        return 0.0

    def get_usage(self, project) -> ProjectUsage:
        """Retrieve CPU and GPU usage for the given project.

        Args:
            project: A :class:`~app.models.project.Project` ORM instance.

        Returns:
            A :class:`~app.schemas.project.ProjectUsage` with current metrics.
        """
        ns = project.kubernetes_namespace or ""

        # CPU: sum of CPU cores used by all pods in the namespace
        cpu_used = self._query(
            f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}"}}[5m]))'
        )

        # GPU: sum of GPU resources allocated in the namespace
        gpu_used = self._query(
            f'sum(kube_pod_container_resource_requests{{namespace="{ns}",resource="nvidia.com/gpu"}})'
        )

        return ProjectUsage(
            cpu_allocated=project.cpu_allocated,
            cpu_used=round(cpu_used, 4),
            gpu_allocated=project.gpu_allocated,
            gpu_used=round(gpu_used, 4),
        )
