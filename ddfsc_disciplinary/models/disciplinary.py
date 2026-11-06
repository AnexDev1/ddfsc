from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

class DisciplinaryType(models.Model):
    _name="ddfsc.disciplinary.type"; _description="Disciplinary Category"
    name=fields.Char(required=True); severity=fields.Selection([("low","Low"),("medium","Medium"),("high","High"),("critical","Critical")],default="medium"); active=fields.Boolean(default=True)

class DisciplinaryCase(models.Model):
    _name="ddfsc.disciplinary.case"; _description="Confidential Disciplinary Case"; _inherit=["mail.thread","mail.activity.mixin"]; _order="incident_date desc,id desc"
    name=fields.Char(default="New",readonly=True,copy=False)
    employee_id=fields.Many2one("hr.employee",required=True,ondelete="restrict",tracking=True)
    type_id=fields.Many2one("ddfsc.disciplinary.type",required=True,ondelete="restrict")
    incident_date=fields.Date(required=True,default=fields.Date.context_today)
    reported_by=fields.Char(required=True); description=fields.Text(required=True)
    investigator_id=fields.Many2one("res.users"); findings=fields.Text(); employee_response=fields.Text(); hearing_date=fields.Datetime(); hearing_outcome=fields.Text()
    action_type=fields.Selection([("warning","Written Warning"),("suspension","Suspension"),("corrective","Corrective Action"),("none","No Action")],default="none")
    action_note=fields.Text(); state=fields.Selection([("draft","Draft"),("investigation","Investigation"),("response","Employee Response"),("hearing","Hearing"),("approval","Pending HR Approval"),("closed","Closed"),("rejected","Rejected")],default="draft",tracking=True)
    company_id=fields.Many2one(related="employee_id.company_id",store=True)
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name","New")=="New": vals["name"]=self.env["ir.sequence"].next_by_code("ddfsc.disciplinary.case") or "New"
        return super().create(vals_list)
    def _hr_manager(self):
        if not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")): raise AccessError(_("Only an HR Manager may perform this confidential action."))
    def action_start_investigation(self): self._hr_manager(); self.write({"state":"investigation"})
    def action_request_response(self): self._hr_manager(); self.write({"state":"response"})
    def action_schedule_hearing(self): self._hr_manager(); self.write({"state":"hearing"})
    def action_submit_decision(self): self._hr_manager(); self.write({"state":"approval"})
    def action_close(self): self._hr_manager(); self.write({"state":"closed"})
    def action_reject(self): self._hr_manager(); self.write({"state":"rejected"})
    def write(self, vals):
        if any(rec.state=="closed" for rec in self) and not self.env.is_superuser(): raise UserError(_("Closed disciplinary cases are retained as immutable confidential history."))
        return super().write(vals)
