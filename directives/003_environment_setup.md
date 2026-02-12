# Directive: Environment Setup

**Goal**: Configure environment variables for the Restaurant Agent.

**Inputs**:
-   Target Directory: `Restaurant Agent` root.

**Tools**:
-   `execution/setup_env.py`

**Steps**:
1.  Check if `execution/setup_env.py` exists.
2.  Run `python execution/setup_env.py`.
3.  Verify that `frontend/.env.local` and `backend/.env` are created with template values.

**Edge Cases**:
-   If `.env` files already exist, the script should NOT overwrite them (warn and skip).
-   If directories `frontend/` or `backend/` are missing, the script should fail.
