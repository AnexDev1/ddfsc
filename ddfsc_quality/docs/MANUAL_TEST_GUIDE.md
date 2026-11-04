# Manual QC Test Guide

Use the local `ddfsc` database. Keep the values labelled as demonstration values;
they are for workflow testing and are not factory-approved specifications.

## 1. Test incoming wheat pass

1. Open **Procurement**, create a wheat purchase order, confirm it, and open its receipt.
2. Enter the received quantity and assign a new lot/batch number from **Details**.
3. Complete the store approval and validate the receipt. The wheat must appear in
   **WH/Stock/Wheat Receiving**.
4. Open **Quality Control → DDFSC Operations → QC Lots** and open the new wheat lot.
5. Confirm the four tests are already present. Do not use **Load/Refresh QC Tests**
   during the normal flow.
6. For the current demo plan, enter values inside every displayed Required Range.
   A simple pass set is moisture `12`, impurity `1`, hectoliter weight `77`, and wet
   gluten `25`. Tick **Test Complete** for each result.
7. Click **Submit for QC Approval**, then **Approve / Reject Results** as a Quality
   Manager.
8. Click **Release Wheat to General Store**, approve/validate the transfer, and
   confirm the lot now shows **WH/Stock/General Store**.

## 2. Test incoming wheat failure

1. Repeat the receipt with a different lot.
2. Enter at least one value outside its displayed range, for example moisture `15`.
3. Complete the remaining tests, submit, and review.
4. Confirm the inspection becomes **Rejected**, the lot becomes **On Hold**, and an
   NCR appears under **Quality Control → DDFSC Operations → Non-Conformances**.
5. Try moving the lot from Wheat Receiving. Odoo must block the transfer and give
   an **Open QC Lot** route.

## 3. Test NCR and reinspection

1. Open the NCR and fill severity, owner, due date, disposition, and root cause.
2. Click **Start Investigation**, enter root cause, and click **Require Action**.
3. Enter corrective and preventive actions, then click **Send for Verification**.
4. Choose **Additional Test / Reinspection** and click **Start Reinspection**.
5. Confirm the previous results remain in **Inspection History** and the active test
   fields are empty.
6. Enter new results, submit, and approve again. Return to the NCR, enter verification
   and closure note, then close it.

## 4. Test flour release

1. Request approved wheat for the flour department and complete a flour manufacturing
   order with a finished lot.
2. Confirm the lot is in **Flour Temp Finished** and its QC tests were created.
3. Attempt transfer to Flour Store before QC. Odoo must block it.
4. Enter values within the displayed range, submit, approve, and validate the release.
5. Confirm the flour appears in **Flour Store** and becomes available to the relevant
   pasta, bread, or biscuit department only.

## 5. Test finished products

Repeat the same sequence for one pasta, bread, and biscuit manufacturing order:

1. Finish production with a lot in the department's temporary finished location.
2. Verify QC tests are present automatically.
3. Verify transfer to Finished Goods is blocked before QC.
4. Submit passing results and obtain Quality Manager approval.
5. Validate the transfer and confirm the finished lot is in Finished Goods.

## 6. Test permissions and reports

1. As an ordinary QC user, verify result entry is allowed but plan approval, final
   inspection approval, NCR closure, and exception release are unavailable or blocked.
2. As Quality Manager, enter an exception reason and verify exception release works.
3. From a lot, print **QC Inspection and Release Report**.
4. From an NCR, print **Non-Conformance Report**.
5. Open the pivot and graph icons on QC Lots and Non-Conformances and verify grouping
   by checkpoint, product, supplier, severity, and status.
