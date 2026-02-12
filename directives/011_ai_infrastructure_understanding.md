# AI RESTAURANT OPERATING SYSTEM
# Executive Infrastructure Directive

## Implementation Status: ACTIVE

### Architecture Summary
The AI Intelligence Engine is built as a modular service layer in `backend/ai/`.
Each AI service queries the database, runs analytical algorithms, and returns structured insights via the `/ai/` API endpoints.

### Implemented Systems

#### 1. Intelligent POS (Transaction Intelligence)
- **Status**: Active
- **Implementation**: Order + OrderItem models capture every transaction with item-level detail
- **AI Service**: Revenue Forecaster analyzes sales patterns and forecasts demand
- **Endpoint**: `GET /ai/revenue-forecast`

#### 2. AI Kitchen Display System (KDS Intelligence)
- **Status**: Active
- **Implementation**: PrepTime model logs actual cook times per station
- **AI Service**: KDS Intelligence detects bottlenecks and measures throughput
- **Endpoint**: `GET /ai/kds-intelligence`

#### 3. AI Inventory Intelligence System
- **Status**: Active
- **Implementation**: StockMovement model tracks all inventory in/out flows
- **AI Service**: Inventory Predictor forecasts depletion and recommends reorders
- **Endpoint**: `GET /ai/inventory-predictions`

#### 4. AI Reservation & Table Flow Intelligence
- **Status**: Active
- **Implementation**: Reservation + Table models with no-show tracking
- **AI Service**: Reservation Optimizer scores no-show probability and calculates revenue per seat
- **Endpoint**: `GET /ai/reservation-insights`

#### 5. AI Operations Manager
- **Status**: Active
- **Implementation**: Central aggregator pulling from all AI services
- **AI Service**: Ops Manager calculates restaurant health score (0-100) and generates cross-system alerts
- **Endpoint**: `GET /ai/dashboard`

#### 6. AI Revenue Optimizer (Menu Engineering)
- **Status**: Active
- **Implementation**: Menu Engineering Matrix (Star/Plowhorse/Puzzle/Dog)
- **AI Service**: Classifies items by popularity vs profitability, detects upsell pairs
- **Endpoint**: `GET /ai/menu-engineering`

### Data Models (backend/models.py)
- **Tenant** — Multi-tenant isolation
- **User** — Role-based access (superadmin/admin/staff)
- **Restaurant** — Core entity
- **Table** — Physical tables with status tracking
- **MenuItem** — Enhanced with cost_price, prep_station, avg_prep_minutes
- **Order** — Enhanced with order_type, table_number, completed_at
- **OrderItem** — Links orders to items with quantity/price snapshot
- **PrepTime** — Actual kitchen prep time per item per station
- **InventoryItem** — Stock levels with expiry tracking
- **StockMovement** — Inventory in/out/adjust tracking
- **Reservation** — Bookings with no-show and deposit tracking

### API Endpoints (backend/routers/analytics.py)
All endpoints require JWT authentication.

| Endpoint | Returns |
|---|---|
| `GET /ai/dashboard` | Health score, quick stats, top alerts, module summaries |
| `GET /ai/menu-engineering` | Item matrix, upsell pairs, pricing recommendations |
| `GET /ai/revenue-forecast` | Daily/hourly/weekly patterns, 7-day forecast, trends |
| `GET /ai/kds-intelligence` | Station performance, bottlenecks, throughput metrics |
| `GET /ai/inventory-predictions` | Depletion timelines, reorder points, spoilage risk |
| `GET /ai/reservation-insights` | No-show analysis, table utilization, revenue per seat |

### Demo Data
Run `execution/seed_demo_data.py` to generate 30 days of realistic data:
- 714+ orders with item-level detail
- 18 menu items with cost prices
- 14 inventory items with stock movements
- 197+ reservations with no-show patterns
- Login: admin@leviii.ai / admin123

### Technology Stack
- **Backend**: Python + FastAPI
- **Database**: SQLAlchemy + SQLite (dev) / PostgreSQL (prod)
- **AI Engine**: Pure Python analytics (no external ML dependencies)
- **Frontend**: Next.js + TailwindCSS
- **Auth**: JWT + Argon2

### Future Enhancements
- [ ] ML-based demand forecasting (sklearn/prophet)
- [ ] Real-time WebSocket updates for KDS
- [ ] Dynamic pricing engine
- [ ] Automated purchase order generation
- [ ] WhatsApp/Voice reservation integration