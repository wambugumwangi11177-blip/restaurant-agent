# Directive: Authentication Setup

**Goal**: Implement secure authentication for the Restaurant Agent.

**Inputs**:
-   Frontend: Next.js App Router
-   Backend: FastAPI

**Tools**:
-   `execution/setup_auth_frontend.py`
-   `execution/setup_auth_backend.py`

**Architecture**:
1.  **Frontend (NextAuth/Auth.js)**:
    -   Use `CredentialsProvider` for email/password login.
    -   Store JWT token in session.
    -   Middleware to protect `/dashboard` routes.
2.  **Backend (FastAPI Security)**:
    -   Use `OAuth2PasswordBearer` for token retrieval.
    -   JWT generation and verification using `python-jose` and `passlib`.
    -   `get_current_user` dependency for protected endpoints.

**Steps**:
1.  **Backend**:
    -   Install `python-jose[cryptography]`, `passlib[bcrypt]`, `python-multipart`.
    -   Create `auth.py` for token logic.
    -   Create `/token` endpoint for login.
    -   Create `User` model (SQLAlchemy).
2.  **Frontend**:
    -   Install `next-auth`.
    -   Create `app/api/auth/[...nextauth]/route.ts`.
    -   Configure `CredentialsProvider` to call backend `/token`.
    -   Add `SessionProvider` to root layout.

**Edge Cases**:
-   Token expiry: Frontend should handle 401 errors by redirecting to login.
-   Role-based access: Ensure `SuperAdmin` vs `Tenant` logic is enforced in backend.
