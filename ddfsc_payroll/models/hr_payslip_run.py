from odoo import _, fields, models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    """Add operational progress to Odoo's existing payroll batch.

    A separate period model would duplicate ``hr.payslip.run``.  This extension
    keeps one source of truth while making a manager's batch progress visible.
    """

    _inherit = "hr.payslip.run"

    ddfsc_payslip_count = fields.Integer(compute="_compute_ddfsc_batch_progress")
    ddfsc_draft_count = fields.Integer(string="Draft", compute="_compute_ddfsc_batch_progress")
    ddfsc_waiting_count = fields.Integer(string="Waiting", compute="_compute_ddfsc_batch_progress")
    ddfsc_done_count = fields.Integer(string="Done", compute="_compute_ddfsc_batch_progress")
    ddfsc_rejected_count = fields.Integer(string="Rejected", compute="_compute_ddfsc_batch_progress")
    ddfsc_batch_progress = fields.Char(string="Batch Progress", compute="_compute_ddfsc_batch_progress")
    ddfsc_validation_state = fields.Selection(
        [("draft", "Not validated"), ("passed", "Validated"), ("failed", "Validation failed")],
        string="Validation", default="draft", readonly=True, copy=False, tracking=True,
    )
    ddfsc_validation_note = fields.Text(string="Validation Notes", readonly=True, copy=False)
    ddfsc_validated_by = fields.Many2one("res.users", string="Validated By", readonly=True, copy=False)
    ddfsc_validated_on = fields.Datetime(string="Validated On", readonly=True, copy=False)
    ddfsc_approved_by = fields.Many2one("res.users", string="Approved By", readonly=True, copy=False)
    ddfsc_approved_on = fields.Datetime(string="Approved On", readonly=True, copy=False)
    ddfsc_reopen_reason = fields.Text(string="Reopening Reason", copy=False, tracking=True)
    ddfsc_reopened_by = fields.Many2one("res.users", string="Reopened By", readonly=True, copy=False)
    ddfsc_reopened_on = fields.Datetime(string="Reopened On", readonly=True, copy=False)

    def _compute_ddfsc_batch_progress(self):
        for batch in self:
            counts = {state: 0 for state in ("draft", "verify", "done", "cancel")}
            for payslip in batch.slip_ids:
                counts[payslip.state] = counts.get(payslip.state, 0) + 1
            batch.ddfsc_payslip_count = len(batch.slip_ids)
            batch.ddfsc_draft_count = counts["draft"]
            batch.ddfsc_waiting_count = counts["verify"]
            batch.ddfsc_done_count = counts["done"]
            batch.ddfsc_rejected_count = counts["cancel"]
            batch.ddfsc_batch_progress = _(
                "%(total)s payslips: %(draft)s draft, %(waiting)s waiting, %(done)s done, %(rejected)s rejected",
                total=batch.ddfsc_payslip_count,
                draft=batch.ddfsc_draft_count,
                waiting=batch.ddfsc_waiting_count,
                done=batch.ddfsc_done_count,
                rejected=batch.ddfsc_rejected_count,
            )

    def action_compute_draft_payslips(self):
        for batch in self:
            if batch.state != "draft":
                raise UserError(_("Reopen the batch before recalculating its draft payslips."))
            drafts = batch.slip_ids.filtered(lambda payslip: payslip.state == "draft")
            if drafts:
                drafts.compute_sheet()
            batch.write({
                "ddfsc_validation_state": "draft", "ddfsc_validation_note": False,
                "ddfsc_validated_by": False, "ddfsc_validated_on": False,
                "ddfsc_approved_by": False, "ddfsc_approved_on": False,
            })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payroll batch calculated"),
                "message": _("All draft payslips in this batch have been recalculated."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_validate_batch(self):
        """Perform deterministic pre-finalisation checks without changing payslips."""
        for batch in self:
            issues = []
            if not batch.slip_ids:
                issues.append(_("No payslips have been generated for this batch."))
            drafts = batch.slip_ids.filtered(lambda payslip: payslip.state == "draft")
            if drafts:
                issues.append(_("%(count)s payslip(s) are still draft; calculate them first.", count=len(drafts)))
            rejected = batch.slip_ids.filtered(lambda payslip: payslip.state == "cancel")
            if rejected:
                issues.append(_("%(count)s payslip(s) are rejected and require review.", count=len(rejected)))
            no_lines = batch.slip_ids.filtered(lambda payslip: not payslip.line_ids)
            if no_lines:
                issues.append(_("%(count)s calculated payslip(s) have no computation lines.", count=len(no_lines)))
            negative_net = batch.slip_ids.filtered(
                lambda payslip: payslip.ddfsc_net_pay < 0
            )
            if negative_net:
                issues.append(_("%(count)s payslip(s) have a negative net pay and need HR/Finance review.", count=len(negative_net)))
            if issues:
                batch.write({
                    "ddfsc_validation_state": "failed", "ddfsc_validation_note": "\n".join(issues),
                    "ddfsc_validated_by": self.env.user.id, "ddfsc_validated_on": fields.Datetime.now(),
                    "ddfsc_approved_by": False, "ddfsc_approved_on": False,
                })
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Payroll batch validation failed"),
                        "message": "\n".join(issues),
                        "type": "danger",
                        "sticky": True,
                    },
                }
            batch.write({
                "ddfsc_validation_state": "passed", "ddfsc_validation_note": _("All generated payslips have computation lines and passed automated pre-finalisation checks."),
                "ddfsc_validated_by": self.env.user.id, "ddfsc_validated_on": fields.Datetime.now(),
            })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payroll batch validated"),
                "message": _("The batch passed automated pre-finalisation checks and is ready for approval."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_approve_batch(self):
        if not self.env.user.has_group("payroll.group_payroll_manager"):
            raise UserError(_("Only a Payroll Manager can approve a payroll batch."))
        for batch in self:
            if batch.ddfsc_validation_state != "passed":
                raise UserError(_("Validate the payroll batch successfully before approving it."))
            batch.write({"ddfsc_approved_by": self.env.user.id, "ddfsc_approved_on": fields.Datetime.now()})
        return True

    def close_payslip_run(self):
        for batch in self:
            if not batch.ddfsc_approved_by:
                raise UserError(_("A Payroll Manager must approve the validated batch before it can be closed."))
            incomplete = batch.slip_ids.filtered(lambda payslip: payslip.state != "done")
            if incomplete:
                raise UserError(_("All payslips must be confirmed before closing the batch."))
        return super().close_payslip_run()

    def draft_payslip_run(self):
        for batch in self.filtered(lambda record: record.state == "close"):
            if not self.env.user.has_group("payroll.group_payroll_manager"):
                raise UserError(_("Only a Payroll Manager can reopen a closed payroll batch."))
            if not (batch.ddfsc_reopen_reason or "").strip():
                raise UserError(_("Enter a reopening reason before reopening a closed payroll batch."))
        result = super().draft_payslip_run()
        self.write({
            "ddfsc_validation_state": "draft", "ddfsc_validation_note": False,
            "ddfsc_validated_by": False, "ddfsc_validated_on": False,
            "ddfsc_approved_by": False, "ddfsc_approved_on": False,
            "ddfsc_reopened_by": self.env.user.id, "ddfsc_reopened_on": fields.Datetime.now(),
        })
        return result
