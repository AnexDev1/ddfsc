# DDFSC Weighbridge — Phase 1 operator guide

Phase 1 records the values already printed by the MASTER-K indicator. It does
not connect to the indicator, validate inventory, or release a QC lot.

## Incoming wheat

1. Create a **Weighbridge Ticket** and choose **Incoming Receipt**.
2. Select the supplier, product, purchase order or receipt, and enter the
   vehicle plate.
3. Keep **First Weighing = Gross Weight First**. On the indicator, take the
   loaded-truck weighing. Copy its value into **Gross Weight (kg)** and select
   **Record First Weight**.
4. After unloading, take the empty-truck weighing. Copy its value into
   **Tare Weight (kg)** and select **Record Second Weight & Calculate Net**.
5. Confirm that net weight is sensible: `gross − tare = net`.
6. Upload a photo or scan of the indicator’s printed ticket using the chatter
   attachment button.
7. Select **Complete Ticket**.
8. The warehouse team continues the normal receipt and QC process. A completed
   weighbridge ticket is evidence; it does not move stock or make QC pass.

## Corrections

- Before completion, use **Cancel Ticket** with a reason for an incorrect or
  duplicate ticket. Create a new ticket; do not overwrite recorded weights.
- Completed and cancelled tickets are locked to preserve the audit trail.

## Hardware safety

Do not unplug the scale, printer, or power. Hardware reading will be added in
Phase 2 after the indicator’s COM1 settings and output protocol are confirmed.

## Empty truck first (usually outgoing goods)

Choose **First Weighing = Tare Weight First** before entering a value. Record
the empty vehicle as tare, load it, then record the loaded vehicle as gross.
The system calculates the same net result: `gross − tare`.
