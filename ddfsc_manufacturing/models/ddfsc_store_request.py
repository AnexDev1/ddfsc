from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .ddfsc_department import location, selection


class DdfscStoreRequest(models.Model):
    _name = 'ddfsc.store.request'
    _description = 'Store Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ddfsc.approval.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    ddfsc_department = fields.Selection(
        selection=selection,
        string='Requesting Department',
        required=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
    ddfsc_user_department = fields.Selection(
        related='user_id.ddfsc_department',
        string='User Department',
    )
    ddfsc_user_department = fields.Selection(
        related='user_id.ddfsc_department',
        string='User Department',
    )
    location_id = fields.Many2one(
        'stock.location',
        string='From',
        required=True,
        default=lambda self: self.env.ref('ddfsc_manufacturing.loc_store', raise_if_not_found=False),
    )
    location_dest_id = fields.Many2one('stock.location', string='To', required=True)
    line_ids = fields.One2many('ddfsc.store.request.line', 'request_id', string='Products')
    picking_id = fields.Many2one('stock.picking', string='Internal Transfer', copy=False, readonly=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )

    def _ddfsc_approval_role(self):
        self.ensure_one()
        return 'operation'

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        department = self.env.user.ddfsc_department or values.get('ddfsc_department')
        if department:
            values['ddfsc_department'] = department
            dest = location(self.env, department, 'request_location')
            if dest:
                values['location_dest_id'] = dest.id
        if not values.get('location_id'):
            store = self.env.ref('ddfsc_manufacturing.loc_store', raise_if_not_found=False)
            if store:
                values['location_id'] = store.id
        return values

    @api.onchange('ddfsc_department')
    def _onchange_ddfsc_department(self):
        for request in self:
            dest = location(self.env, request.ddfsc_department, 'request_location')
            if dest:
                request.location_dest_id = dest

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('ddfsc.store.request') or 'New'
        return super().create(vals_list)

    def action_ddfsc_submit(self):
        for request in self:
            if not request.line_ids:
                raise UserError(_('Add the products this department is requesting.'))
        return super().action_ddfsc_submit()

    def action_ddfsc_approve(self):
        result = super().action_ddfsc_approve()
        self._ddfsc_create_internal_transfer()
        return result

    def _ddfsc_create_internal_transfer(self):
        for request in self.filtered(lambda item: item.ddfsc_approval_state == 'approved' and not item.picking_id):
            if not request.line_ids:
                raise UserError(_('Add the products this department is requesting.'))
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', request.company_id.id),
            ], limit=1)
            if not warehouse.int_type_id:
                raise UserError(_('The warehouse has no internal transfer operation.'))
            picking = self.env['stock.picking'].create({
                'picking_type_id': warehouse.int_type_id.id,
                'location_id': request.location_id.id,
                'location_dest_id': request.location_dest_id.id,
                'origin': request.name,
                'ddfsc_store_request_id': request.id,
                'company_id': request.company_id.id,
                'move_ids': [Command.create({
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': request.location_id.id,
                    'location_dest_id': request.location_dest_id.id,
                    'company_id': request.company_id.id,
                    'origin': request.name,
                }) for line in request.line_ids],
            })
            picking.write({
                'location_id': request.location_id.id,
                'location_dest_id': request.location_dest_id.id,
            })
            picking.move_ids.filtered(lambda move: move.state != 'cancel').write({
                'location_id': request.location_id.id,
                'location_dest_id': request.location_dest_id.id,
            })
            picking.action_confirm()
            request.picking_id = picking.id

    def action_view_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Internal Transfer'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
        }


class DdfscStoreRequestLine(models.Model):
    _name = 'ddfsc.store.request.line'
    _description = 'Store Requisition Line'

    request_id = fields.Many2one('ddfsc.store.request', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    product_uom_qty = fields.Float(string='Quantity', required=True, default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string='Unit', required=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
