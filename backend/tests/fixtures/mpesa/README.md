# M-Pesa statement fixtures

`statement_sample.csv` is **designed, not exported**. No real M-Pesa business statement was available to the build (SPEC Appendix B #1),
so it follows public descriptions of the Safaricom M-PESA for Business transaction report: a few lines about the till, then a header row,
then one row per transaction. The names, numbers and receipts are made up.

What is in it on purpose, so the parser tests have something to be wrong about: a preamble and a blank row before the header; a quoted
amount with a thousands comma; a Failed payment; money going out (a supplier payment and its charge); a lower-case receipt that repeats an
upper-case one; a row whose time is not a time; a blank row and a "Total" row.

**A real sample is needed** before the parser is trusted on a real till. Drop it here as `real_sample.csv` (remove names and numbers) and
add a test that reads it.
