#!/usr/bin/env bash

set -euo pipefail

REGION="us-east-1"
CLUSTER="ai-translation-prototype-cluster"
SERVICE="ai-translation-prototype-service"
DB="ai-translation-prototype-db"

echo "Starting RDS..."

aws rds start-db-instance \
  --db-instance-identifier "$DB" \
  --region "$REGION" \
  > /dev/null

echo "Waiting for RDS..."

aws rds wait db-instance-available \
  --db-instance-identifier "$DB" \
  --region "$REGION"

echo "Starting ECS service..."

aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --desired-count 1 \
  --region "$REGION" \
  > /dev/null

echo "Waiting for ECS service..."

aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --region "$REGION"

echo
echo "Development environment is running."