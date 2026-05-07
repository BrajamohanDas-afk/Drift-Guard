import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field

from app.config import settings

_DNS1123_LABEL_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class KubernetesDeploymentEvidence(BaseModel):
    cluster_api_url: str
    namespace: str
    deployment: str
    exists: bool
    deployment_uid: Optional[str] = None
    replicas: Optional[int] = None
    updated_replicas: Optional[int] = None
    ready_replicas: Optional[int] = None
    available_replicas: Optional[int] = None
    unavailable_replicas: Optional[int] = None
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KubernetesCollector:
    def __init__(
        self,
        api_url: Optional[str] = None,
        bearer_token: Optional[str] = None,
        timeout_seconds: float = 5.0,
        verify_ssl: Optional[bool] = None,
    ):
        self.api_url = settings.kubernetes_api_url if api_url is None else api_url
        self.bearer_token = (
            settings.kubernetes_bearer_token
            if bearer_token is None
            else bearer_token
        )
        self.timeout_seconds = timeout_seconds
        self.verify_ssl = (
            settings.kubernetes_verify_ssl if verify_ssl is None else verify_ssl
        )

    async def collect_deployment(
        self,
        deployment: str,
        namespace: str = "default",
    ) -> KubernetesDeploymentEvidence:
        checked_at = datetime.now(timezone.utc)
        safe_api_url = (self.api_url or "").strip()
        safe_namespace = namespace.strip()
        safe_deployment = deployment.strip()

        if not safe_deployment:
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=namespace,
                deployment=deployment,
                exists=False,
                error="deployment must not be empty",
                checked_at=checked_at,
            )

        if not safe_namespace:
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=namespace,
                deployment=deployment,
                exists=False,
                error="namespace must not be empty",
                checked_at=checked_at,
            )

        if not _is_dns1123_label(safe_namespace):
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=namespace,
                deployment=deployment,
                exists=False,
                error="namespace must be a valid Kubernetes DNS-1123 label",
                checked_at=checked_at,
            )

        if not _is_dns1123_subdomain(safe_deployment):
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=namespace,
                deployment=deployment,
                exists=False,
                error="deployment must be a valid Kubernetes DNS-1123 name",
                checked_at=checked_at,
            )

        if not safe_api_url:
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=namespace,
                deployment=deployment,
                exists=False,
                error="Kubernetes API URL is not configured",
                checked_at=checked_at,
            )

        if not self.bearer_token:
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=namespace,
                deployment=deployment,
                exists=False,
                error="Kubernetes bearer token is not configured",
                checked_at=checked_at,
            )

        base_url = safe_api_url.rstrip("/")
        encoded_namespace = quote(safe_namespace, safe="")
        encoded_deployment = quote(safe_deployment, safe="")
        endpoint = (
            f"{base_url}/apis/apps/v1/namespaces/"
            f"{encoded_namespace}/deployments/{encoded_deployment}"
        )
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
                follow_redirects=False,
            ) as client:
                response = await client.get(endpoint, headers=headers)

            if response.status_code == 401:
                return KubernetesDeploymentEvidence(
                    cluster_api_url=safe_api_url,
                    namespace=namespace,
                    deployment=deployment,
                    exists=False,
                    error="Unauthorized: invalid Kubernetes bearer token",
                    checked_at=checked_at,
                )

            if response.status_code == 404:
                return KubernetesDeploymentEvidence(
                    cluster_api_url=safe_api_url,
                    namespace=namespace,
                    deployment=deployment,
                    exists=False,
                    error=None,
                    checked_at=checked_at,
                )

            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError as exc:
                return KubernetesDeploymentEvidence(
                    cluster_api_url=safe_api_url,
                    namespace=namespace,
                    deployment=deployment,
                    exists=False,
                    error=f"Invalid Kubernetes JSON response: {exc}",
                    checked_at=checked_at,
                )

            metadata = payload.get("metadata") or {}
            status = payload.get("status") or {}

            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=metadata.get("namespace", namespace),
                deployment=metadata.get("name", deployment),
                exists=True,
                deployment_uid=metadata.get("uid"),
                replicas=status.get("replicas"),
                updated_replicas=status.get("updatedReplicas"),
                ready_replicas=status.get("readyReplicas"),
                available_replicas=status.get("availableReplicas"),
                unavailable_replicas=status.get("unavailableReplicas"),
                error=None,
                checked_at=checked_at,
            )
        except httpx.HTTPError as exc:
            return KubernetesDeploymentEvidence(
                cluster_api_url=safe_api_url,
                namespace=safe_namespace,
                deployment=safe_deployment,
                exists=False,
                error=str(exc),
                checked_at=checked_at,
            )


def _is_dns1123_label(value: str) -> bool:
    return len(value) <= 63 and _DNS1123_LABEL_RE.fullmatch(value) is not None


def _is_dns1123_subdomain(value: str) -> bool:
    return (
        len(value) <= 253
        and all(_is_dns1123_label(label) for label in value.split("."))
    )
