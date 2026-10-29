# DDFSC Quality Management

This is the standalone Quality Control application for Dire Dawa Food Complex.
It depends on the OCA `quality_control_oca` inspection engine and retains the
DDFSC lot disposition and stock release controls implemented by
`ddfsc_manufacturing`.

## Factory checkpoints

- Incoming wheat: Vendor to Wheat Receiving, QC, then release to General Store.
- Flour: Mill output to Flour Temp Finished, QC, then release to Flour Store.
- Finished products: Production output to the department's Temp Finished
  location, QC, then release to Finished Goods Store.

Pending, held, and rejected lots cannot leave controlled locations. A passed
lot can be released normally. A quality manager can release an exception only
after recording the reason.

The acceptance limits currently marked as demo values must be reviewed and
approved by the factory quality team before production use.
