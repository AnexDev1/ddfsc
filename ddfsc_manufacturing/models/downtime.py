"""Downtime per stoppage, and production batches.

The biscuit daily report lists every stoppage of a shift with its hours and
reason (power cut, fuel, no space in the FG store, stock count…). One order
can stop several times, so stoppages are lines; the order keeps the total
and its main reason for reports and lists.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

DOWNTIME_REASONS = [
    ('power', 'Power cut'),
    ('fuel', 'Fuel shortage'),
    ('film', 'Short of film / packing material'),
    ('raw_material', 'Raw material shortage'),
    ('fg_full', 'No space in finished goods store'),
    ('stock_count', 'Stock count / inventory'),
    ('transport', 'Transport'),
    ('mixer', 'Mixer'),
    ('die', 'Die'),
    ('oven', 'Oven'),
    ('packing', 'Packing machine'),
    ('other', 'Other'),
]
# Stoppages caused by a machine open a maintenance request.
EQUIPMENT_REASONS = ('mixer', 'die', 'oven', 'packing')


class DdfscProductionDowntime(models.Model):
    _name = 'ddfsc.production.downtime'
    _description = 'Production Stoppage'
    _order = 'hours desc, id'

    production_id = fields.Many2one('mrp.production', required=True, ondelete='cascade', index=True)
    hours = fields.Float(string='Hours', required=True)
    reason = fields.Selection(DOWNTIME_REASONS, required=True)
    note = fields.Char(string='Details')
    department = fields.Selection(related='production_id.ddfsc_department', store=True)
    line_id = fields.Many2one(related='production_id.ddfsc_line_id', store=True, string='Production Line')
    shift_id = fields.Many2one(related='production_id.ddfsc_shift_id', store=True, string='Shift')
    production_date = fields.Date(related='production_id.ddfsc_production_date', store=True, string='Production Day')

    @api.constrains('hours')
    def _check_hours(self):
        for line in self:
            if line.hours <= 0 or line.hours > 24:
                raise UserError(_('A stoppage lasts more than 0 and at most 24 hours.'))


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    ddfsc_batch_qtl = fields.Float(
        string='Flour per Batch (qtl)',
        help='Flour in one mixer batch on this line, for the batch count on the shift report '
             '(biscuit: 1.5 qtl). Leave 0 where the line does not work in batches.',
    )


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    ddfsc_downtime_line_ids = fields.One2many(
        'ddfsc.production.downtime', 'production_id', string='Stoppages', copy=False)
    downtime_hours = fields.Float(
        string='Downtime (hours)', compute='_compute_ddfsc_downtime', store=True, copy=False)
    downtime_reason = fields.Selection(
        DOWNTIME_REASONS, string='Main Downtime Reason', compute='_compute_ddfsc_downtime',
        store=True, copy=False)
    ddfsc_has_equipment_downtime = fields.Boolean(compute='_compute_ddfsc_downtime')
    ddfsc_batches = fields.Float(
        string='Batches', compute='_compute_ddfsc_batches', digits=(16, 1),
        help='Flour used divided by the flour in one batch on this line.')

    @api.depends('ddfsc_downtime_line_ids.hours', 'ddfsc_downtime_line_ids.reason')
    def _compute_ddfsc_downtime(self):
        for production in self:
            lines = production.ddfsc_downtime_line_ids.sorted(lambda line: -line.hours)
            production.downtime_hours = sum(lines.mapped('hours'))
            production.downtime_reason = lines[:1].reason or False
            production.ddfsc_has_equipment_downtime = any(
                line.reason in EQUIPMENT_REASONS for line in lines)

    @api.depends('ddfsc_flour_used_qtl', 'ddfsc_line_id.ddfsc_batch_qtl')
    def _compute_ddfsc_batches(self):
        for production in self:
            size = production.ddfsc_line_id.ddfsc_batch_qtl
            production.ddfsc_batches = production.ddfsc_flour_used_qtl / size if size else 0.0

    def action_log_downtime(self):
        """Open a corrective request for the longest machine stoppage."""
        self.ensure_one()
        if self.ddfsc_maintenance_request_id:
            return self._maintenance_request_action(self.ddfsc_maintenance_request_id)
        stoppage = self.ddfsc_downtime_line_ids.filtered(
            lambda line: line.reason in EQUIPMENT_REASONS).sorted(lambda line: -line.hours)[:1]
        if not stoppage:
            raise UserError(_(
                'A maintenance request is opened for mixer, die, oven, or packing stoppages. '
                'Power, fuel and supply stoppages stay on the shift report.'))
        if not self.ddfsc_line_id:
            raise UserError(_('Choose the production line before logging this downtime.'))
        reason = dict(DOWNTIME_REASONS).get(stoppage.reason)
        # Department operators report breakdowns but are not maintenance users:
        # the plant equipment and the request are handled by the system, with
        # the operator recorded as the person who raised it.
        equipment = self.env['maintenance.equipment'].sudo().search([
            ('ddfsc_workcenter_id', '=', self.ddfsc_line_id.id),
            ('ddfsc_downtime_code', '=', stoppage.reason),
        ], limit=1)
        if not equipment:
            raise UserError(_('No %(reason)s is registered on %(line)s.',
                              reason=reason, line=self.ddfsc_line_id.display_name))
        request = self.env['maintenance.request'].sudo().create({
            'name': '%s downtime on %s' % (reason, self.name),
            'equipment_id': equipment.id,
            'maintenance_team_id': equipment.maintenance_team_id.id,
            'maintenance_type': 'corrective',
            'owner_user_id': self.env.user.id,
            'description': '<p>%s hours. Shift %s. %s</p>' % (
                stoppage.hours, self.ddfsc_shift_id.name or '', stoppage.note or ''),
        })
        self.sudo().ddfsc_maintenance_request_id = request
        if request.with_user(self.env.user).has_access('read'):
            return self._maintenance_request_action(request)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Maintenance request %s sent to the maintenance team.') % request.name,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
