from odoo import _, api, fields, models
from odoo.exceptions import UserError


class DdfscApprovalMixin(models.AbstractModel):
    _name = 'ddfsc.approval.mixin'
    _description = 'Plant document approval'

    ddfsc_approval_state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('submitted', 'Waiting Approval'),
            ('approved', 'Approved'),
            ('refused', 'Refused'),
        ],
        string='Approval',
        default='draft',
        copy=False,
        tracking=True,
    )
    ddfsc_approval_role = fields.Selection(
        [
            ('gm', 'General Manager'),
            ('operation', 'Operation Manager'),
        ],
        string='Approver',
        compute='_compute_ddfsc_needs_approval',
    )
    ddfsc_needs_approval = fields.Boolean(compute='_compute_ddfsc_needs_approval')
    ddfsc_submitted_uid = fields.Many2one('res.users', string='Submitted By', copy=False, readonly=True)
    ddfsc_approved_uid = fields.Many2one('res.users', string='Approved By', copy=False, readonly=True)
    ddfsc_approval_date = fields.Datetime(string='Approved On', copy=False, readonly=True)
    ddfsc_refusal_note = fields.Char(string='Refusal Note', copy=False)

    def _ddfsc_approval_role(self):
        """Return gm, operation, or an empty string when this document is not approved."""
        self.ensure_one()
        return ''

    @api.depends('ddfsc_approval_state')
    def _compute_ddfsc_needs_approval(self):
        for record in self:
            role = record._ddfsc_approval_role()
            record.ddfsc_approval_role = role or False
            record.ddfsc_needs_approval = bool(role)

    def _ddfsc_check_approver(self):
        self.ensure_one()
        role = self._ddfsc_approval_role()
        if role == 'gm' and not self.env.user.has_group('ddfsc_manufacturing.group_ddfsc_gm'):
            raise UserError(_('The general manager approves this document.'))
        if role == 'operation' and not self.env.user.has_group('ddfsc_manufacturing.group_ddfsc_operation_manager'):
            raise UserError(_('The operation manager approves this document.'))

    def _ddfsc_ensure_approved(self):
        pending = self.filtered(
            lambda record: record._ddfsc_approval_role() and record.ddfsc_approval_state != 'approved'
        )
        if pending:
            names = ', '.join(pending.mapped('display_name'))
            raise UserError(_('Approve these documents before continuing: %s', names))

    def action_ddfsc_submit(self):
        for record in self:
            if not record._ddfsc_approval_role():
                raise UserError(_('This document does not use plant approval.'))
            if record.ddfsc_approval_state not in ('draft', 'refused'):
                raise UserError(_('Only a draft or a refused document can be submitted.'))
            record.write({
                'ddfsc_approval_state': 'submitted',
                'ddfsc_submitted_uid': self.env.user.id,
                'ddfsc_approved_uid': False,
                'ddfsc_approval_date': False,
                'ddfsc_refusal_note': False,
            })
        return True

    def action_ddfsc_approve(self):
        for record in self:
            if record.ddfsc_approval_state != 'submitted':
                raise UserError(_('Submit the document before approval.'))
            record._ddfsc_check_approver()
            record.write({
                'ddfsc_approval_state': 'approved',
                'ddfsc_approved_uid': self.env.user.id,
                'ddfsc_approval_date': fields.Datetime.now(),
            })
        return True

    def action_ddfsc_refuse(self):
        for record in self:
            if record.ddfsc_approval_state != 'submitted':
                raise UserError(_('Submit the document before refusing it.'))
            record._ddfsc_check_approver()
            if not record.ddfsc_refusal_note:
                raise UserError(_('Write the reason for the refusal.'))
            record.write({
                'ddfsc_approval_state': 'refused',
                'ddfsc_approved_uid': self.env.user.id,
                'ddfsc_approval_date': False,
            })
        return True

    def action_ddfsc_reset(self):
        for record in self:
            if record.ddfsc_approval_state != 'refused':
                raise UserError(_('Only a refused document can go back to draft.'))
            record.write({
                'ddfsc_approval_state': 'draft',
                'ddfsc_approved_uid': False,
                'ddfsc_refusal_note': False,
            })
        return True
