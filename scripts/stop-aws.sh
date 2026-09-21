#!/usr/bin/env bash

set -euo pipefail

REGION="us-east-1"
CLUSTER="ai-translation-prototype-cluster"
SERVICE="ai-translation-prototype-service"
DB="ai-translation-prototype-db"

echo "Stopping ECS service..."

aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 0 \
  --region "$REGION" \
  > /dev/null

echo "Waiting for ECS tasks to stop..."

aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --region "$REGION"

echo "Stopping RDS..."

aws rds stop-db-instance \
  --db-instance-identifier "$DB" \
  --region "$REGION" \
  > /dev/null

echo
echo "Development environment shut down."
echo "(RDS will automatically restart after 7 days...)"