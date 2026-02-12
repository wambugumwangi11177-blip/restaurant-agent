# Directive: Reservations & Table Management

**Goal**: Visual table layout and booking system with SMS reminders.

**Inputs**:
-   Frontend, Backend

**Architecture**:
1.  **Backend**:
    -   `Reservation` model: `id`, `restaurant_id`, `customer_name`, `phone`, `time`, `party_size`, `table_id`, `status` (Confirmed, Seated, Cancelled).
    -   `Table` model: `id`, `restaurant_id`, `x`, `y`, `shape`, `capacity`.
    -   `POST /reservations`: Create booking.
    -   `GET /tables`: Fetch layout and current status.
2.  **Frontend**:
    -   Route: `/reservations`.
    -   Canvas/Drag-and-drop editor for floor plan (admin).
    -   Calendar view for bookings.
3.  **Integrations**:
    -   Twilio/WhatsApp API for confirmation SMS.

**Steps**:
1.  **Backend**:
    -   Define `Reservation` and `Table` models.
    -   Create CRUD endpoints.
2.  **Frontend**:
    -   Use `react-draggable` for table map.
    -   Implement Booking Modal.

**Edge Cases**:
-   Double Booking: Database constraint on `table_id` + time range.
-   No-shows: Auto-release table after 15 mins.
