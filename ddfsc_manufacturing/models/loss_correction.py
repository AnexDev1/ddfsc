"""Correct sweepings / disposed dough after the order is closed.

Sweepings and disposed dough are loss figures (kg) with no stock move, so a
late weighing can be corrected safely after "Produce All" — by the Operation
Manager only, with a reason, and only while the output has not been released
by QC nor sent to finished goods. Saleable breakage is stock and is not
correctable here.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    ddfsc_can_correct_losses = fields.Boolean(compute='_compute_ddfsc_can_correct_losses')

    def _ddfsc_loss_correction_blocker(self):
        """Why the losses can no longer be corrected, or False."""
        self.ensure_one()
        if self.state != 'done':
            return _('The order is still open: change the figures on the Shift Report tab.')
        if self.ddfsc_fg_request_state and self.ddfsc_fg_request_state != 'cancel':
            return _('The output has already been sent to finished goods (%s).') % self.ddfsc_fg_request_id.name
        decided = self.ddfsc_quality_lot_ids.filtered(
            lambda lot: lot.ddfsc_quality_state in ('pass', 'released', 'rejected'))
        if decided:
            return _('QC has already decided on lot(s) %s.') % ', '.join(decided.mapped('name'))
        return False

    @api.depends('state', 'ddfsc_fg_request_state')
    def _compute_ddfsc_can_correct_losses(self):
        for production in self:
            production.ddfsc_can_correct_losses = production.state == 'done' \
                and not production._ddfsc_loss_correction_blocker()

    def action_ddfsc_correct_losses(self):
        self.ensure_one()
        if not self.env.user.has_group('ddfsc_manufacturing.group_ddfsc_operation_manager'):
            raise UserError(_('Only the Operation Manager corrects losses on a closed order.'))
        blocker = self._ddfsc_loss_correction_blocker()
        if blocker:
            raise UserError(blocker)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Correct Losses'),
            'res_model': 'ddfsc.loss.correction.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_production_id': self.id},
        }


class DdfscLossCorrectionWizard(models.TransientModel):
    _name = 'ddfsc.loss.correction.wizard'
    _description = 'Correct Losses on a Closed Production Order'

    production_id = fields.Many2one('mrp.production', required=True, readonly=True)
    sweeping_qty = fields.Float(string='Sweepings / Waste (kg)')
    disposed_qty = fields.Float(string='Disposed Dough / Product (kg)')
    show_disposed = fields.Boolean(compute='_compute_show_disposed')
    reason = fields.Text(required=True, help='Why the figure changed, e.g. sweepings weighed after cleaning.')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        production = self.env['mrp.production'].browse(values.get('production_id'))
        if production:
            values.update(sweeping_qty=production.sweeping_qty, disposed_qty=production.disposed_qty)
        return values

    @api.depends('production_id')
    def _compute_show_disposed(self):
        for wizard in self:
            wizard.show_disposed = wizard.production_id.ddfsc_line_id.code != 'MILL'

    def action_apply(self):
        self.ensure_one()
        production = self.production_id
        if not self.env.user.has_group('ddfsc_manufacturing.group_ddfsc_operation_manager'):
            raise UserError(_('Only the Operation Manager corrects losses on a closed order.'))
        blocker = production._ddfsc_loss_correction_blocker()
        if blocker:
            raise UserError(blocker)
        if self.sweeping_qty < 0 or self.disposed_qty < 0:
            raise UserError(_('Losses cannot be negative.'))
        if not (self.reason or '').strip():
            raise UserError(_('Write the reason for the correction.'))
        changes = []
        values = {}
        for field_name, label in (('sweeping_qty', _('Sweepings')), ('disposed_qty', _('Disposed dough'))):
            old, new = production[field_name], self[field_name]
            if float_compare(old, new, precision_digits=3):
                values[field_name] = new
                changes.append('%s: %s → %s kg' % (label, old, new))
        if not changes:
            raise UserError(_('Nothing changed.'))
        production.write(values)
        production.message_post(body=_(
            'Losses corrected after closing by %(user)s. %(changes)s. Reason: %(reason)s',
            user=self.env.user.name, changes='; '.join(changes), reason=self.reason))
        return {'type': 'ir.actions.act_window_close'}
