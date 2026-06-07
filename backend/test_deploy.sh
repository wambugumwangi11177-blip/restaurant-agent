#!/bin/bash
# Usage: ./test_deploy.sh <backend_url>
# Example: ./test_deploy.sh https://my-backend.up.railway.app

set -euo pipefail

BACKEND_URL="${1:-http://localhost:8000}"
EMAIL="lavy@leviii.ai"
PASSWORD="lavy123"

echo "Testing backend at: $BACKEND_URL"

# 1. Health check (if endpoint exists)
echo -e "\n=== Health check ==="
curl -sf "$BACKEND_URL/" || echo "Root endpoint not found or error"

# 2. Login
echo -e "\n=== Login ==="
LOGIN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}") || {
    echo "Login request failed"
    exit 1
}
TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r .access_token)
if [[ "$TOKEN" == "null" || -z "$TOKEN" ]]; then
    echo "Login failed: $LOGIN_RESPONSE"
    exit 1
fi
echo "Login successful. Token received."

# 3. Get user info
echo -e "\n=== User info ==="
curl -s -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/v1/auth/me" | jq .

# 4. Propose a goal
echo -e "\n=== Propose goal ==="
GOAL_RESPONSE=$(curl -s -X POST "$BACKEND_URL/agentic/goals" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"goal_type":"optimize.profitability","description":"Increase net profit margin by 10% next quarter","success_criteria":{"profit_margin_increase":10},"priority":2}') || {
    echo "Goal proposal request failed"
    exit 1
}
GOAL_ID=$(echo "$GOAL_RESPONSE" | jq -r .goal_id)
if [[ "$GOAL_ID" == "null" || -z "$GOAL_ID" ]]; then
    echo "Goal proposal failed: $GOAL_RESPONSE"
    exit 1
fi
echo "Goal proposed with ID: $GOAL_ID"

# 5. Get goal details
echo -e "\n=== Get goal details ==="
curl -s -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/agentic/goals/$GOAL_ID" | jq .

echo -e "\n=== All tests后汉书 passed! ==="