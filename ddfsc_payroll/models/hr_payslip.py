from collections import defaultdict

from odoo import api, fields, models


class HrPayslipInput(models.Model):
    _inherit = "hr.payslip.input"

    component_ids = fields.Many2many(
        "ddfsc.employee.payroll.component", "ddfsc_component_payslip_input_rel",
        "input_id", "component_id", string="Source Components", readonly=True,
    )


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    @api.model
    def get_inputs(self, contracts, date_from, date_to):
        result = super().get_inputs(contracts, date_from, date_to)
        if not contracts or not self.employee_id:
            return result
        components = self.env["ddfsc.employee.payroll.component"].search([
            ("employee_id", "=", self.employee_id.id), ("company_id", "=", self.company_id.id),
            ("state", "=", "approved"), ("date_from", "<=", date_to),
            "|", ("date_to", "=", False), ("date_to", ">=", date_from),
        ])
        one_off = components.filtered(lambda component: component.recurrence == "one_off")
        if one_off:
            used_ids = set(self.env["hr.payslip.input"].search([
                ("component_ids", "in", one_off.ids), ("payslip_id.state", "=", "done"),
                ("payslip_id.id", "!=", self.id or 0),
            ]).mapped("component_ids").ids)
            components = components.filtered(lambda component: component.id not in used_ids)

        grouped = defaultdict(lambda: {"amount": 0.0, "ids": [], "type": False})
        for component in components:
            grouped[component.code]["amount"] += component.amount
            grouped[component.code]["ids"].append(component.id)
            grouped[component.code]["type"] = component.component_type_id
        contract = contracts[:1]
        for code, values in grouped.items():
            vals = {
                "name": values["type"].name, "code": code, "amount": values["amount"],
                "contract_id": contract.id, "component_ids": [(6, 0, values["ids"])],
            }
            existing = next((line for line in result if line.get("code") == code), None)
            if existing:
                existing.update(vals)
            else:
                result.append(vals)
        return result

