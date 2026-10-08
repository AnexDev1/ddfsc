from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from .ddfsc_department import location, selection


class DdfscStoreRequest(models.Model):
    _name = 'ddfsc.store.request'
    _description = 'Store Transfer Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('store_manager', 'Store Manager'),
            ('requested', 'Requested'),
            ('received', 'Received'),
            ('cancel', 'Cancelled'),
        ],
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    date_request = fields.Datetime(
        string='Request Date',
        default=fields.Datetime.now,
        required=True,
        tracking=True,
    )
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
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        required=True,
        check_company=True,
        domain="[('usage', '=', 'internal')]",
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Default Source',
        required=True,
        default=lambda self: self.env.ref('ddfsc_manufacturing.loc_store', raise_if_not_found=False),
        check_company=True,
        domain="[('usage', '=', 'internal')]",
        help='Default source location for new product lines.',
    )
    line_ids = fields.One2many('ddfsc.store.request.line', 'request_id', string='Product Details')
    picking_id = fields.Many2one('stock.picking', string='Transfer', copy=False, readonly=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        department = self.env.user.ddfsc_department or values.get('ddfsc_department')
        if department:
            values['ddfsc_department'] = department
            dest = location(self.env, department, 'request_location')
            if dest:
                values['location_dest_id'] = dest.id
            source = location(self.env, department, 'request_source')
            if source:
                values['location_id'] = source.id
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
            source = location(self.env, request.ddfsc_department, 'request_source')
            if source:
                request.location_id = source
                for line in request.line_ids:
                    line.location_id = source

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('ddfsc.store.request') or 'New'
        return super().create(vals_list)

    def action_submit_to_manager(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            if not request.line_ids:
                raise UserError(_('Add at least one product line.'))
            if not request.location_dest_id:
                raise UserError(_('Set the destination location.'))
            for line in request.line_ids:
                if not line.location_id:
                    raise UserError(_('Set a source location on every product line.'))
                if line.product_uom_qty <= 0:
                    raise UserError(_('Request quantity must be greater than zero for %s.', line.product_id.display_name))
            request.write({'state': 'store_manager'})
        return True

    def action_approve_manager(self):
        for request in self:
            if request.state != 'store_manager':
                raise UserError(_('Only requests waiting for the store manager can be approved.'))
            if not self.env.user.has_group('ddfsc_manufacturing.group_ddfsc_operation_manager'):
                raise UserError(_('Only the operation manager can approve this request.'))
            request._ddfsc_create_internal_transfer()
            request.write({'state': 'requested'})
        return True

    def action_cancel(self):
        for request in self:
            if request.state in ('received', 'cancel'):
                raise UserError(_('This request cannot be cancelled.'))
            if request.picking_id and request.picking_id.state not in ('done', 'cancel'):
                request.picking_id.action_cancel()
            request.write({'state': 'cancel'})
        return True

    def action_reset_draft(self):
        for request in self:
            if request.state != 'cancel':
                raise UserError(_('Only cancelled requests can go back to draft.'))
            request.write({'state': 'draft', 'picking_id': False})
        return True

    def _ddfsc_mark_received(self):
        self.filtered(lambda request: request.state == 'requested').write({'state': 'received'})

    def _ddfsc_create_internal_transfer(self):
        for request in self.filtered(lambda item: not item.picking_id):
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', request.company_id.id),
            ], limit=1)
            if not warehouse.int_type_id:
                raise UserError(_('The warehouse has no internal transfer operation type.'))
            # One picking; moves may come from different source locations.
            first_source = request.line_ids[:1].location_id or request.location_id
            picking = self.env['stock.picking'].create({
                'picking_type_id': warehouse.int_type_id.id,
                'location_id': first_source.id,
                'location_dest_id': request.location_dest_id.id,
                'origin': request.name,
                'scheduled_date': request.date_request,
                'ddfsc_store_request_id': request.id,
                'company_id': request.company_id.id,
                'move_ids': [Command.create({
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': line.location_id.id,
                    'location_dest_id': request.location_dest_id.id,
                    'company_id': request.company_id.id,
                    'origin': request.name,
                }) for line in request.line_ids],
            })
            picking.write({
                'location_id': first_source.id,
                'location_dest_id': request.location_dest_id.id,
            })
            for line in request.line_ids:
                move = picking.move_ids.filtered(
                    lambda item: item.product_id == line.product_id
                    and item.location_id == line.location_id
                    and item.state != 'cancel'
                )[:1]
                if not move:
                    move = picking.move_ids.filtered(
                        lambda item: item.product_id == line.product_id and item.state != 'cancel'
                    )[:1]
                if move:
                    move.write({
                        'location_id': line.location_id.id,
                        'location_dest_id': request.location_dest_id.id,
                    })
            picking.action_confirm()
            picking.action_assign()
            for line in request.line_ids.filtered('lot_id'):
                move = picking.move_ids.filtered(
                    lambda item: item.product_id == line.product_id
                    and item.location_id == line.location_id
                    and item.state != 'cancel'
                )[:1]
                if move and move.move_line_ids:
                    move.move_line_ids.write({'lot_id': line.lot_id.id})
                elif move:
                    move.lot_ids = line.lot_id
            request.picking_id = picking.id

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No inventory transfer has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Transfer'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
        }


class DdfscStoreRequestLine(models.Model):
    _name = 'ddfsc.store.request.line'
    _description = 'Store Transfer Request Line'

    request_id = fields.Many2one(
        'ddfsc.store.request',
        string='Transfer Request',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one('product.product', required=True)
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit',
        required=True,
        compute='_compute_product_uom_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Source Warehouse',
        required=True,
        check_company=True,
        domain="[('usage', '=', 'internal')]",
    )
    qty_available = fields.Float(
        string='Available',
        compute='_compute_qty_available',
        digits='Product Unit of Measure',
    )
    product_uom_qty = fields.Float(string='Request', required=True, default=1.0)
    lot_id = fields.Many2one(
        'stock.lot',
        string='Destination Lot',
        domain="[('product_id', '=', product_id)]",
        check_company=True,
    )
    company_id = fields.Many2one(related='request_id.company_id', store=True)

    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id

    @api.depends('product_id', 'location_id', 'product_uom_id')
    def _compute_qty_available(self):
        for line in self:
            if not line.product_id or not line.location_id:
                line.qty_available = 0.0
                continue
            qty = line.product_id.with_context(location=line.location_id.id).qty_available
            if line.product_uom_id and line.product_uom_id != line.product_id.uom_id:
                qty = line.product_id.uom_id._compute_quantity(qty, line.product_uom_id)
            line.qty_available = qty

    def _ddfsc_source_for_product(self, product, request):
        """Flour comes from the flour silo; other components from General Store."""
        store = self.env.ref('ddfsc_manufacturing.loc_store', raise_if_not_found=False)
        if not product:
            return request.location_id or store
        if product.ddfsc_is_flour:
            source = location(self.env, request.ddfsc_department, 'request_source')
            return source or request.location_id or store
        return store or request.location_id

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        request = self.env['ddfsc.store.request'].browse(self.env.context.get('default_request_id'))
        if not request and self.env.context.get('active_model') == 'ddfsc.store.request':
            request = self.env['ddfsc.store.request'].browse(self.env.context.get('active_id'))
        if request.location_id and not values.get('location_id'):
            values['location_id'] = request.location_id.id
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            request = self.env['ddfsc.store.request'].browse(vals.get('request_id'))
            product = self.env['product.product'].browse(vals.get('product_id'))
            if not vals.get('location_id') and request:
                source = self._ddfsc_source_for_product(product, request)
                if source:
                    vals['location_id'] = source.id
        return super().create(vals_list)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
                line.lot_id = False
                source = line._ddfsc_source_for_product(line.product_id, line.request_id)
                if source:
                    line.location_id = source
            elif not line.location_id and line.request_id.location_id:
                line.location_id = line.request_id.location_id
