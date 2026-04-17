# Payments Service Runbook

## Overview

This runbook covers common operational tasks for the `payments-api` service.

## Ownership

- owner: platform-sre
- backup_owner: payments-oncall

## Service Details

- service: payments-api
- cluster: prod-us-east-1
- helm_chart: payments-api
- dashboard: https://grafana.example.com/d/payments-api-overview

## Environment Variables

- DATABASE_URL
- REDIS_URL
- STRIPE_SECRET_KEY

## IAM Roles

- arn:aws:iam::123456789012:role/payments-api-runtime

## Common Commands

```bash
kubectl -n payments get pods
kubectl -n payments rollout restart deployment/payments-api
helm list -n payments
```

## Incident Checklist

1. Confirm latest deployment status.
2. Check error rate and latency dashboard.
3. Verify queue backlog and worker health.
4. Notify `#payments-incidents` if impact is customer-facing.

