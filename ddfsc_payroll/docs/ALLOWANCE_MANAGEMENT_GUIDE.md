# DDFSC Allowance Management

## Purpose

Allowance requests use the existing payroll-component engine. This means the
same effective-date, payslip, one-time-consumption, and closed-payroll controls
apply to allowances; there is no second payroll calculation path.

## Configuration

1. In **Payroll > Configuration > Component Types**, ensure Finance has an
   approved earning component for the required treatment. Use **Taxable
   Allowance** for normal cash allowances. Do not use a non-taxable or
   pensionable component without Finance approval.
2. In **Payroll > Configuration > Allowance Policies**, create the policy.
   Set its effective dates, fixed or percentage-of-basic calculation, eligible
   employees, departments, or job positions.
3. Do not enter a cash amount that has not been approved by HR and Finance.

## Request and approval

1. HR creates **Payroll > Employee Allowances** and selects the employee and
   policy.
2. On submission, Odoo re-calculates and snapshots the policy amount.
3. The employee's supervisor approves.
4. An HR Manager approves.
5. A Payroll/Finance Manager approves. Only this final step creates an
   approved Employee Payroll Component.
6. The normal payslip process consumes that component when its dates cover the
   payslip period.

## Controls

- An employee must satisfy the policy eligibility rule on the effective date.
- Two approved records for the same employee and policy cannot overlap.
- An approved allowance cannot be edited. Create a new dated request instead.
- Cancelling an allowance also cancels its generated component, unless a
  completed payslip has already consumed it.
- Cash allowances are treated as taxable by default. Pensionability is an
  explicit Finance configuration, not a default.
