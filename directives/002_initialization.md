# Directive: Project Initialization

**Goal**: Initialize the Next.js frontend and Python FastAPI backend for the Restaurant Agent.

**Inputs**:
-   Target Directory: `Restaurant Agent` root.

**Tools**:
-   `execution/setup_project.py`

**Steps**:
1.  Check if `execution/setup_project.py` exists.
2.  Run `python execution/setup_project.py`.
3.  Verify that `frontend/` and `backend/` directories are created.

**Edge Cases**:
-   If `frontend/` already exists, the script should skip creation or asking for overwrite (ensure it handles this gracefully).
-   If `npm` or `python` is missing, the script should fail with a clear error.
