from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class DdfscTransfer(models.Model):
    _name = 'ddfsc.transfer'
    _description = 'Earlier plant form kept for documents already posted'
    _order = 'id desc'

    name = fields.Char(default='New', required=True, copy=False)
    document_type = fields.Selection(
        [
            ('store_requisition', 'Store Requisition'),
            ('wheat_receiving', 'Wheat Receiving'),
            ('silo_issue', 'Silo Issue'),
            ('flour_transfer', 'Flour Transfer'),
            ('byproduct_return', 'By-product to Store'),
            ('fg_receiving', 'Finished Goods Receiving'),
        ],
        required=True,
        default='store_requisition',
    )
    location_id = fields.Many2one('stock.location', string='From', required=True)
    location_dest_id = fields.Many2one('stock.location', string='To', required=True)
    line_ids = fields.One2many('ddfsc.transfer.line', 'transfer_id', string='Lines')
    picking_id = fields.Many2one('stock.picking', string='Transfer', copy=False, readonly=True)
    note = fields.Char()
    board_open = fields.Float(string='Board Opening')
    board_close = fields.Float(string='Board Closing')
    impurity_qtl = fields.Float(string='Impurity (qtl)')
    wheat_qtl = fields.Float(string='Wheat (qtl)', compute='_compute_board_wheat')
    cleaned_qtl = fields.Float(string='Cleaned Wheat (qtl)', compute='_compute_board_wheat')
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Done')],
        default='draft',
        required=True,
        copy=False,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        document_type = values.get('document_type') or self.env.context.get('default_document_type')
        if document_type:
            source, destination = self._locations_for(document_type)
            values.setdefault('location_id', source.id)
            values.setdefault('location_dest_id', destination.id)
        return values

    @api.depends('board_open', 'board_close', 'impurity_qtl')
    def _compute_board_wheat(self):
        for transfer in self:
            transfer.wheat_qtl = (transfer.board_open - transfer.board_close) * 2
            transfer.cleaned_qtl = transfer.wheat_qtl - transfer.impurity_qtl

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            document_type = vals.get('document_type') or 'store_requisition'
            if not vals.get('location_id') or not vals.get('location_dest_id'):
                source, destination = self._locations_for(document_type)
                vals.setdefault('location_id', source.id)
                vals.setdefault('location_dest_id', destination.id)
        return super().create(vals_list)

    @api.onchange('document_type')
    def _onchange_document_type(self):
        if self.document_type:
            self.location_id, self.location_dest_id = self._locations_for(self.document_type)

    @api.model
    def _locations_for(self, document_type):
        pairs = {
            'store_requisition': ('loc_store', 'loc_biscuit'),
            'wheat_receiving': ('loc_wheat_dock', 'loc_silo_pasta'),
            'silo_issue': ('loc_silo_pasta', 'loc_mill'),
            'flour_transfer': ('loc_flour', 'loc_flour_pasta'),
            'byproduct_return': ('loc_flour', 'loc_store'),
            'fg_receiving': ('loc_biscuit', 'loc_finished'),
        }
        source_xmlid, dest_xmlid = pairs[document_type]
        return (
            self.env.ref('ddfsc_manufacturing.%s' % source_xmlid),
            self.env.ref('ddfsc_manufacturing.%s' % dest_xmlid),
        )

    def action_confirm(self):
        for transfer in self:
            if transfer.state == 'done':
                continue
            if not transfer.line_ids:
                raise UserError(_('Add at least one product line.'))
            if transfer.document_type == 'silo_issue':
                transfer._check_silo_board()
            if transfer.name == 'New':
                transfer.name = self.env['ir.sequence'].next_by_code('ddfsc.transfer') or _('New')
            warehouse = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id),
            ], limit=1)
            picking = self.env['stock.picking'].create({
                'picking_type_id': warehouse.int_type_id.id,
                'location_id': transfer.location_id.id,
                'location_dest_id': transfer.location_dest_id.id,
                'origin': transfer.name,
                'move_ids': [Command.create({
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom': line.product_uom_id.id,
                    'location_id': transfer.location_id.id,
                    'location_dest_id': transfer.location_dest_id.id,
                }) for line in transfer.line_ids],
            })
            picking.action_confirm()
            picking.action_assign()
            for line in transfer.line_ids:
                move = picking.move_ids.filtered(lambda item: item.product_id == line.product_id)[:1]
                if line.product_id.tracking != 'none' and not line.lot_id:
                    raise UserError(_('Lot is required for %s.', line.product_id.display_name))
                if not move.move_line_ids:
                    raise UserError(_(
                        '%s is not available in %s.',
                        line.product_id.display_name,
                        transfer.location_id.display_name,
                    ))
                move.move_line_ids.write({
                    'lot_id': line.lot_id.id,
                    'quantity': line.product_uom_qty,
                    'picked': True,
                })
            picking.button_validate()
            transfer.write({'picking_id': picking.id, 'state': 'done'})
        return True

    def _check_silo_board(self):
        self.ensure_one()
        if self.board_open <= self.board_close:
            raise UserError(_('The closing board reading has to be lower than the opening reading.'))
        issued = sum(self.line_ids.mapped('product_uom_qty'))
        if abs(issued - self.wheat_qtl) > 0.01:
            raise UserError(_(
                'The issued quantity is %(issued)s quintals. '
                'The board difference times 2 is %(wheat)s quintals.',
                issued=issued,
                wheat=self.wheat_qtl,
            ))


class DdfscTransferLine(models.Model):
    _name = 'ddfsc.transfer.line'
    _description = 'Plant Transfer Line'

    transfer_id = fields.Many2one('ddfsc.transfer', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', required=True)
    product_uom_qty = fields.Float(string='Quantity', required=True, default=1.0)
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='Unit',
        required=True,
        compute='_compute_product_uom_id',
        store=True,
        readonly=False,
        precompute=True,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Lot',
        domain="[('product_id', '=', product_id)]",
    )

    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id:
                line.product_uom_id = line.product_id.uom_id
