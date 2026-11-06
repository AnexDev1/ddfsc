# DDFSC Role and Approval Design

## Purpose

This is the production role design for Dire Dawa Food Complex.  It follows the
principle of least privilege: entering a record, approving it, receiving or
moving stock, and configuring the system are separate duties wherever the
factory process allows it.

`Administrator` remains the emergency system-administration account only. It
must not be shared as a day-to-day factory login.

## Current-state audit (November 2026)

| Area | What already exists | Gap to close |
| --- | --- | --- |
| Manufacturing | MRP User/Manager plus DDFSC Operation Manager and General Manager | Department users can create store requests; approval checks need to be consistently enforced server-side. |
| Quality | DDFSC Quality User and Quality Manager | QC review is manager-only. Release of a passed lot must be delegated to Store, not a general QC data-entry user. |
| Procurement | Requester, Verifier, Budget Manager, Store Manager, PR Manager and CEO roles | Existing role names are usable; the assigned people and financial thresholds must be confirmed before go-live. |
| Inventory | Standard Stock User/Manager | Custom inventory modules currently grant ordinary Stock Users broad create/write/delete access. This must be narrowed before production. |
| Attendance / Time Off | Standard Attendance User/Manager and HR User/Manager | Biometric-device administration is correctly manager-only; employee self-service and manager visibility need a final HR policy decision. |
| Payroll | Standard Payroll User/Manager, HR User/Manager | Finance approval is protected in code for allowances and loans. Some earlier action buttons still need matching UI and server-side restrictions. |

## Roles to assign

| Business role | Odoo group(s) | Can do | Cannot do |
| --- | --- | --- | --- |
| Department requester / production operator | Manufacturing User, Stock User where material is handled | Draft store requests, view own department work orders, record operational data | Approve own request, release QC stock, configure products/BOMs |
| Department / operation manager | **DDFSC Operation Manager** | Approve/refuse manufacturing and store requests, oversee shift/plant work | Final QC disposition, financial approval, payroll configuration |
| Store clerk | Stock User | Prepare and validate assigned receipts/internal transfers, view stock | Create products, change warehouse configuration, approve own adjustments |
| Store manager | Stock Manager + procurement Store Manager where used | Receive stock, validate releases, oversee store operations | Approve procurement budget/payment or QC results |
| QC technician | **DDFSC Quality User** | Enter measured results, submit inspections, raise NCR evidence | Approve QC, edit approved results, release inventory |
| QC manager | **DDFSC Quality Manager** | Approve/reject inspections, approve plans, close NCR/CAPA | Validate physical stock movements unless also assigned Store Manager |
| Procurement requester | Store Requisition: Requester | Create local purchase/requisition requests | Verify, budget approve, or finalize supplier/payment steps |
| Procurement verifier | Store Requisition: Verifier | Verify requests and supporting documents | Budget approve or final purchasing approval |
| Budget / finance approver | Store Requisition: Budget Manager + Accounting role | Budget review and finance approval within approved limits | Receive goods or modify a request after final approval |
| Procurement manager | Local Purchase PR Manager | Manage RFQ/PO workflow and approved purchasing | Payroll/HR approval unless separately assigned |
| HR officer | HR User + Attendance User | Employee records, attendance exceptions, draft corrections/leave administration | Approve sensitive HR/payroll decisions alone |
| HR manager | HR Manager + Attendance Manager | Approve attendance corrections, leave, HR step of allowance/loan/promotion | Finance approval or final GM approval |
| Payroll officer | Payroll User | Prepare payslips and review payroll inputs | Approve/close batch, change statutory configuration, approve own adjustments |
| Payroll / finance manager | Payroll Manager | Approve payroll batch, finance-approve allowances/loans, disburse and settle loans, maintain statutory rules | QC approval or physical inventory receipt unless separately assigned |
| General manager | **DDFSC General Manager** | Final approval for promotions and exceptional factory decisions | Routine data entry/receipt validation by default |
| System administrator | Settings Administrator (very limited people) | Users, companies, technical configuration, recovery | Routine operational approval using shared credentials |

## Approval matrix

| Process | Prepare | Review / approve | Execute / close |
| --- | --- | --- | --- |
| Purchase/requisition | Requester | Verifier -> Budget Manager -> Procurement Manager / CEO as configured | Store Manager receives goods |
| Incoming wheat QC | Store Clerk receives to Wheat Receiving; QC Technician records tests | QC Manager approves/rejects results | Store Manager validates Wheat Receiving -> General Store transfer |
| Manufacturing / store request | Department requester | Operation Manager | Store Clerk validates transfer; department confirms receipt where applicable |
| Finished flour/FG QC | Production/QC Technician | QC Manager | Store Manager validates permitted transfer |
| NCR / CAPA | QC Technician / owner | QC Manager verifies closure | Store/production completes approved disposition |
| Attendance correction / overtime | HR/attendance officer or supervisor | Attendance Manager | Payroll consumes only approved records |
| Leave | Employee/HR Officer | Employee manager then HR Manager according to leave type | Payroll consumes approved leave only |
| Allowance | Manager / HR Officer | Supervisor -> HR Manager -> Payroll Manager | Approved component appears in payroll |
| Loan | Employee/HR Officer | Supervisor -> HR Manager -> Payroll Manager | Payroll Manager records disbursement/settlement; payroll recovers installments |
| Promotion / salary revision | Supervisor/HR Officer | Supervisor -> HR Manager -> General Manager | System applies it on its effective date; payroll uses history |
| Payslip batch | Payroll Officer | Payroll Manager | Payroll Manager closes/reopens with an auditable reason |

## Mandatory production controls

1. Never give a single employee both `Requester` and the approval group for the
   same purchase/requisition process unless the GM documents a small-site
   exception.
2. Do not grant `Settings` / Administrator rights to department heads,
   storekeepers, laboratory staff, or payroll officers.
3. A Quality Manager may approve QC, but a Store Manager validates stock moves.
   This separates quality acceptance from physical custody.
4. Payroll Manager and HR Manager should be different people where staffing
   allows. General Manager remains final approver for promotions.
5. Use one named Odoo account per person. Shared accounts remove the audit
   trail and must not be used.
6. Review memberships quarterly and immediately on transfer, termination, or
   extended leave.

## Implementation order

1. **Release safety:** prevent a completed Wheat Receiving -> General Store
   release from being recreated; restrict the release action to Store Manager.
2. **Quality and Manufacturing:** align button visibility and server checks to
   Quality Technician, Quality Manager, Operation Manager, and Store Manager.
3. **Procurement and Inventory:** retain the existing requisition roles, then
   remove broad write/delete access from generic Stock Users after confirming
   the receiving and adjustment workflow with the store team.
4. **Attendance / Time Off:** retain standard HR/Attendance roles, add record
   rules only after employee self-service policy is confirmed.
5. **Payroll:** enforce manager-only finance, batch closure, statutory setup,
   and sensitive compensation/loan actions in both UI and Python methods.
6. **Go-live:** create named users, assign only the matrix roles, run an
   approval test with one user per role, and sign off the results.

## Decisions the client must confirm before go-live

- Monetary thresholds and whether CEO/GM approval is mandatory above each
  procurement amount.
- Whether Store Manager or Quality Manager is allowed to validate a QC release
  transfer when the other is absent.
- Leave approval route by leave type and department.
- Whether employees receive self-service access or HR enters all requests.
- Whether one person may hold both HR Manager and Payroll Manager in the first
  rollout; this is possible, but should be documented as an exception.
