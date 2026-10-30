# QuickSell POS → LEVIII (Eleven)

One-way HTTPS push: your POS sends JSON to us in **your existing format**. We store every payload in our mirror first and return success; we only map records we recognise as sales/orders into the Eleven owner app. Other data (stock, staff, payments, etc.) stays in the mirror for later mapping. We never write back to your system.

**Base URL (placeholder):** `https://api.example.com`  
**Endpoint:** `POST /webhooks/quicksell/data`  
**Content-Type:** `application/json`  
**Authentication:** header `x-api-key: <secret>` (LEVIII generates the key; treat it like a password)

## What to send

Send your data as JSON in your existing format — for example:

- A JSON object with a `records` array (or `data`, `sales`, `transactions`, …), or  
- A JSON array of objects, or  
- A single object.

We do not require a fixed schema. Use the field names you already export; we recognise common aliases when mapping sales (`receipt_no`, `transaction_id`, `total_cents`, `occurred_at`, etc.).

**IDs:** If you include a stable record id, we use it for deduplication (safe retries). If not, we dedupe on a hash of the record content.

**Timestamps:** If a timestamp includes a timezone offset, we use it. If it is naive (no offset), we treat it as **Africa/Nairobi**. If there is no timestamp, we use the time we received the batch.

For **sales**, include a **total** as `total_cents` (integer) or `total` (major units) so we can create order rows.

### Example (one possible shape)

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
| **400** | Body is not valid JSON |
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
