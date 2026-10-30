# QuickSell POS → LEVIII (Eleven)

One-way HTTPS push: your POS sends sales JSON to us. We store every payload and map sales into the Eleven owner app. We never write back to your system.

**Base URL (placeholder):** `https://api.example.com`  
**Endpoint:** `POST /webhooks/quicksell/data`  
**Content-Type:** `application/json`  
**Authentication:** header `x-api-key: <secret>` (LEVIII generates the key; treat it like a password)

## What to send

Send either:

- A JSON object with a `records` array (or `data`, `sales`, `transactions`, …), or  
- A JSON array of sale objects, or  
- A single sale object.

We do not require a fixed schema beyond the two rules below. Use the field names you already export; we recognise common aliases (`receipt_no`, `transaction_id`, `total_cents`, `occurred_at`, etc.).

### Required on every sale record

1. **Unique record ID** — stable across retries (e.g. `source_id`, `receipt_no`, `transaction_id`). Same ID + same version → duplicate ignored (safe to retry).
2. **Timestamp with timezone offset** — ISO-8601, e.g. `2026-09-19T14:30:00+03:00` or `…Z`. Naive local times are rejected so each sale lands on the correct Nairobi business day.

Include a **total** as `total_cents` (integer) or `total` (major units).

### Example

```json
{
  "entity": "sale",
  "records": [
    {
      "source_id": "RCP-10042",
      "occurred_at": "2026-09-19T18:05:22+03:00",
      "total_cents": 64300
    }
  ]
}
```

## Responses

| Code | Meaning |
|------|---------|
| **200** | Batch stored (`inserted`, `duplicates_ignored`, `orders_inserted` in JSON body) |
| **400** | Invalid JSON, empty batch, or a record missing ID/timestamp/total |
| **401** | Missing or wrong `x-api-key` |
| **413** | More than 500 records in one request |
| **500** | Server error — retry the whole batch |
| **503** | Eleven restaurant not configured on this server |

Rate limit: **60 requests per minute** per IP (same as our other POS webhook).

## Security

- HTTPS only in production.  
- Do not put customer PII in URLs.  
- We do not log raw sale bodies in application logs.  
- Rotate the key if it is ever exposed; ask Eleven’s LEVIII contact for a new one.

## LEVIII operator notes

Generate a key (shown once):

```bash
python3 backend/scripts/generate_quicksell_api_key.py
```

Set `QUICKSELL_API_KEY` in the API environment. Optional: `ELEVEN_RESTAURANT_NAME` (default `Eleven`).
