"""Maintenance requests as on the MTD forms.

* Annual plan (PL/MTD/002): each preventive request is I (inspection),
  L (lubrication) or S (service).
* Daily corrective report (OF/MTD/004): shift, downtime, spare parts used,
  assigned mechanics, labour cost and manpower.
* Spare parts are issued from the Spare Parts & Supplies Store to a
  maintenance-use location, so their cost lands on the request.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class MaintenanceRequest(models.Model):
    _inherit = 'maintenance.request'

    ddfsc_pm_type = fields.Selection(
        [('inspection', 'I – Inspection'), ('lubrication', 'L – Lubrication'), ('service', 'S – Service')],
        string='Plan Type')
    ddfsc_shift_id = fields.Many2one('ddfsc.shift', string='Shift')
    ddfsc_downtime_hours = fields.Float(string='Downtime (hours)', help='Production time lost on the line.')
    ddfsc_mechanic_ids = fields.Many2many('res.users', string='Assigned Mechanics')
    ddfsc_manpower = fields.Integer(string='Manpower')
    ddfsc_labour_cost = fields.Float(string='Labour Cost')
    ddfsc_work_done = fields.Text(string='Maintenance Done')
    ddfsc_spare_line_ids = fields.One2many('ddfsc.maintenance.spare', 'request_id', string='Spare Parts Used')
    ddfsc_spare_picking_id = fields.Many2one('stock.picking', string='Spare Parts Issue', readonly=True, copy=False)
    ddfsc_spare_cost = fields.Float(string='Spare Parts Cost', compute='_compute_ddfsc_cost', store=True)
    ddfsc_total_cost = fields.Float(string='Maintenance Cost', compute='_compute_ddfsc_cost', store=True)
    ddfsc_workcenter_id = fields.Many2one(related='equipment_id.ddfsc_workcenter_id', store=True,
                                          string='Production Line')

    @api.depends('ddfsc_spare_line_ids.subtotal', 'ddfsc_labour_cost')
    def _compute_ddfsc_cost(self):
        for request in self:
            request.ddfsc_spare_cost = sum(request.ddfsc_spare_line_ids.mapped('subtotal'))
            request.ddfsc_total_cost = request.ddfsc_spare_cost + request.ddfsc_labour_cost

    def action_issue_spare_parts(self):
        """Issue the listed spare parts from the Spare Parts & Supplies Store."""
        self.ensure_one()
        if self.ddfsc_spare_picking_id:
            return self._ddfsc_open_picking()
        if not self.ddfsc_spare_line_ids:
            raise UserError(_('List the spare parts used first.'))
        source = self.env.ref('ddfsc_manufacturing.loc_store_spares')
        destination = self.env.ref('ddfsc_manufacturing.loc_maintenance_use')
        picking_type = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).int_type_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': self.name,
            'move_ids': [Command.create({
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            }) for line in self.ddfsc_spare_line_ids],
        })
        picking.action_confirm()
        picking.action_assign()
        self.ddfsc_spare_picking_id = picking
        return self._ddfsc_open_picking()

    def _ddfsc_open_picking(self):
        return {
            'type': 'ir.actions.act_window', 'name': _('Spare Parts Issue'),
            'res_model': 'stock.picking', 'view_mode': 'form', 'res_id': self.ddfsc_spare_picking_id.id,
        }


class DdfscMaintenanceSpare(models.Model):
    _name = 'ddfsc.maintenance.spare'
    _description = 'Spare Part Used in Maintenance'

    request_id = fields.Many2one('maintenance.request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Spare Part', required=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    quantity = fields.Float(required=True, default=1.0)
    unit_cost = fields.Float(compute='_compute_subtotal', store=True, readonly=False)
    subtotal = fields.Float(compute='_compute_subtotal', store=True)

    @api.depends('product_id', 'quantity', 'unit_cost')
    def _compute_subtotal(self):
        for line in self:
            if line.product_id and not line.unit_cost:
                line.unit_cost = line.product_id.standard_price
            line.subtotal = line.quantity * line.unit_cost
