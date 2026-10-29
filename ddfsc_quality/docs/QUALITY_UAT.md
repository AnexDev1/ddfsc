# DDFSC Quality Control UAT and Sign-off

Run this checklist in the local `ddfsc` database with representatives from Quality,
Warehouse, Procurement, Production, and Management. Record the document and lot
numbers used, the expected result, the actual result, and the person accepting it.

## Configuration sign-off

- Confirm the approved test, unit, minimum, maximum, and qualitative answers for
  incoming wheat, each flour grade, pasta, bread, and biscuits.
- Clear **Demo Specification** only after Quality signs the limits. Approve the plan
  and record its effective date.
- Confirm who can enter results, review inspections, reject a lot, and release an
  exception. Result entry and final approval should use different users when the
  factory requires separation of duties.
- Confirm whether every receipt and production batch is tested. Document any
  sampling frequency before enabling sample tracking.

## Incoming wheat

1. Confirm a wheat purchase and receive it into **Wheat Receiving** with a lot.
2. Verify tests appear automatically on the lot.
3. Try to move the pending lot to General Store. The transfer must be blocked and
   open the QC lot.
4. Enter an in-range result for every mandatory test and submit it.
5. Verify results are locked while awaiting review.
6. Approve with a Quality Manager. Release the wheat to General Store and confirm
   the quantity is available there.
7. Repeat with one failed mandatory result. Verify the lot is held, transfer is
   blocked, and an NCR is created with the receipt and supplier.

## Flour production

1. Issue approved wheat to the flour department and finish a manufacturing order.
2. Verify the flour lot arrives in **Flour Temp Finished** with its tests prepared.
3. Confirm a pending/failed lot cannot move to Flour Store.
4. Approve a passing inspection and transfer the lot to **Flour Store**.
5. Confirm only the relevant flour products appear in each department request.

## Pasta, bread, and biscuit production

For each department, request the approved ingredient, complete one manufacturing
order, and verify the finished lot enters that department's temporary finished
location. Pending or failed lots must not reach Finished Goods. An approved lot
must transfer successfully and remain traceable to its manufacturing order.

## Non-conformance and reinspection

1. Open the automatically created NCR and record severity, owner, due date, root
   cause, corrective action, preventive action, and disposition.
2. Verify the owner receives an activity and overdue NCRs appear in the filter.
3. Request reinspection. Confirm the original results remain in Inspection History
   and the current result fields reset.
4. Complete and approve the reinspection.
5. Close the NCR only after disposition, verification, and closure note are filled.
6. Print both the QC Inspection and Non-Conformance reports.

## Exception release

- Verify an ordinary QC user cannot release a lot by exception.
- Verify a Quality Manager must record a reason before release.
- Confirm the report and lot audit trail show the manager, time, and reason.

## Acceptance

Do not deploy factory limits from this demo database as production standards.
Deployment is accepted only after all routes above pass and the factory Quality
Manager signs the specification sheet and this UAT record.
