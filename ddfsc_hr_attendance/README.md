# DDFSC HR & Biometric Attendance

Odoo 19 attendance foundation for DDFSC. It uses Odoo's standard employee,
work schedule, and attendance models and adds an auditable ZKTeco integration.

## Data flow

1. ZKTeco or CSV supplies raw punches.
2. Every punch receives a stable duplicate-protection key.
3. The Biometric User ID maps the punch to an Odoo employee.
4. Unmapped or inconsistent punches stay in **Raw Punches & Exceptions**.
5. Valid IN/OUT events create or complete standard Odoo attendance records.
6. The original punches remain linked to attendance and cannot be edited or deleted.

## Initial setup

1. Open **HR & Attendance > Configuration > Attendance Devices**.
2. Create the factory device with its IP, port (usually 4370), timezone, protocol,
   and communication password.
3. Open each employee and enter the ID shown for that employee on the ZKTeco
   device in **Biometric User ID**.
4. Use **Test Connection**, then **Download Punches**.
5. Review **Raw Punches & Exceptions**, resolve unmapped IDs, and process the
   selected events.
6. Enable **Automatic Download** only after the manual test succeeds.

Leave **Use Device Check-in / Check-out Codes** disabled unless the physical
device is explicitly configured with separate IN and OUT punch modes. When it is
disabled, Odoo safely alternates an employee's first punch to IN and the next to
OUT.

## CSV test format

CSV timestamps are interpreted in the selected device's timezone.

```csv
device_user_id,timestamp,punch_type
EMP-001,2026-10-28 08:00:00,in
EMP-001,2026-10-28 17:00:00,out
```

`punch_type` is optional and accepts `in`, `out`, or `unknown`.

## Current Jira coverage

- HR-002 to HR-004: Odoo 19 dependency assessment, addon boundary, installation,
  and automated tests.
- BIO-002: device configuration.
- BIO-003: isolated ZKTeco adapter using `pyzk`.
- BIO-004: immutable raw event storage.
- BIO-005: employee/device ID mapping and unmatched queue.
- BIO-006: configurable scheduled synchronization.
- BIO-007: stable SHA-256 event keys and repeat-download protection.
- BIO-008: synchronization history, error state, and safe retry.
- AT-001 and AT-002: explicit or alternating IN/OUT pairing and inconsistent
  punch exceptions.
- AT-004: original-event links, tracked correction reason, and protected biometric
  times, with manager approval before a correction is applied.
- HR-006 and HR-009: unique employee numbers, payroll eligibility, and controlled
  employee termination using Odoo's standard contract and departure data.
- HR-011 to HR-014 and HR-016: standard work calendars, effective-dated employee
  schedule assignments, grace periods, historical schedule selection, and
  timezone-aware expected hours.
- AT-003: late arrival, early departure, missing check-out, and missing-schedule
  exceptions calculated against the effective schedule.

Daily absence generation, leave integration, overtime policy, attendance-period
locking, payroll calculation, accounting posting, and CBE export still require
the client's approved rules and representative expected results.
