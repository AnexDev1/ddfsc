# DDFSC Payroll Components

This module extends the OCA `payroll` engine. It does not replace payroll.

## Purpose

HR can assign approved, effective-dated earnings and deductions to an employee without adding a database field for every allowance. Components may recur every payslip or be consumed once.

## Configuration

1. Create or choose an OCA salary rule.
2. Add a rule input code, such as `TRANSPORT`.
3. Make the rule calculate from `inputs.TRANSPORT.amount`.
4. In **Payroll > Configuration > Component Types**, create a matching component type and select that salary rule.
5. In **Payroll > Employee Components**, add the amount and effective period, then approve it.
6. Create or refresh the employee payslip. The approved component appears under **Other Inputs** and is used by the linked salary rule.

Taxable and pensionable fields classify the component for configuration and reporting. The salary rules implement the actual Ethiopian tax, pension, accounting, and net-pay calculations.

## Controls

- Draft and cancelled components never enter payslips.
- Components outside the payslip period never enter the payslip.
- Multiple approved components with the same code are aggregated.
- A one-time component cannot be reused after a completed payslip.
- Components used by a completed payslip cannot be reset or cancelled.
