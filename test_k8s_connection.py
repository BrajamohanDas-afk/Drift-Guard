import asyncio

from app.config import settings
from app.services.evidence.kubernetes_collector import KubernetesCollector


async def test_connection() -> None:
    if not settings.kubernetes_api_url:
        print("KUBERNETES_API_URL not configured in .env")
        return

    if not settings.kubernetes_bearer_token:
        print("KUBERNETES_BEARER_TOKEN not configured in .env")
        return

    print(f"Testing connection to: {settings.kubernetes_api_url}")
    print(f"Verify SSL: {settings.kubernetes_verify_ssl}")

    collector = KubernetesCollector(
        api_url=settings.kubernetes_api_url,
        bearer_token=settings.kubernetes_bearer_token,
        verify_ssl=settings.kubernetes_verify_ssl,
    )

    # In this collector, 404 maps to exists=False and error=None.
    result = await collector.collect_deployment(
        deployment="test-deployment",
        namespace="default",
    )

    print("\nConnection test result:")
    print(f"  Deployment: {result.deployment}")
    print(f"  Exists: {result.exists}")
    print(f"  Error: {result.error}")
    print(f"  Checked at: {result.checked_at}")

    if result.error is None:
        print("\nSuccessfully connected to Kubernetes.")
        if not result.exists:
            print("Deployment does not exist, but API connectivity works.")
    else:
        print(f"\nConnection error: {result.error}")


if __name__ == "__main__":
    asyncio.run(test_connection())
