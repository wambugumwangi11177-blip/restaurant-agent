# Directive: Verify Frontend Initialization

**Goal**: Confirm that the Next.js frontend is correctly initialized and ready for development.

**Inputs**:
-   `frontend/` directory.

**Steps**:
1.  Check if `frontend/package.json` exists.
2.  Check if `frontend/node_modules` exists and is not empty.
3.  Check if `frontend/src/app/page.tsx` exists (or `pages/index.tsx` depending on router choice).
4.  Run `npm run build` to verify build passes (optional but good).

**Edge Cases**:
-   `node_modules` missing: Run `npm install`.
-   `package.json` missing: Re-run `create-next-app`.
