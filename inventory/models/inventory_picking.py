from odoo import api, fields, models, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    valuation_reference = fields.Char(
        string='Valuation Reference',
        compute='_compute_valuation_reference',
        store=True,
        compute_sudo=True,
        readonly=True,
    )

    @api.depends('move_ids', 'name', 'state')
    def _compute_valuation_reference(self):
        for picking in self:
            references = []
            
            if picking.name and picking.name != '/':
                moves = self.env['account.move'].search([('ref', '=', picking.name)])
                lines = self.env['account.move.line'].search([('name', '=like', f"{picking.name}%")])
                
                all_moves = moves | lines.mapped('move_id')
                for m in all_moves:
                    if m.name and m.name != '/':
                        if m.name not in references:
                            references.append(m.name)
            
            if picking.move_ids and 'stock.valuation.layer' in self.env:
                layers = self.env['stock.valuation.layer'].search([('stock_move_id', 'in', picking.move_ids.ids)])
                for layer in layers:
                    if hasattr(layer, 'account_move_id') and layer.account_move_id and layer.account_move_id.name != '/':
                        name = layer.account_move_id.name
                        if name and name not in references:
                            references.append(name)

            picking.valuation_reference = ', '.join(references)

    def action_open_valuation_moves(self):
        self.ensure_one()
        if not self.valuation_reference:
            return
            
        move_names = [r.strip() for r in self.valuation_reference.split(',')]
        moves = self.env['account.move'].search([('name', 'in', move_names)])
        
        action = {
            'name': _('Valuation Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', moves.ids)],
        }
        
        if len(moves) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = moves.id
            
        return action

    def button_validate(self):
        for picking in self:
            if picking.picking_type_code == 'incoming':
                for move in picking.move_ids:
                    if move.product_id.tracking != 'none':
                        for line in move.move_line_ids:
                            if not line.lot_id and not line.lot_name:
                                raise UserError(_(
                                    "Lot/Batch number is mandatory for product: %s"
                                ) % move.product_id.display_name)

                            lot = line.lot_id
                            if lot and not lot.expiration_date:
                                raise UserError(_(
                                    "Expiration Date is mandatory for Lot: %s of product: %s"
                                ) % (lot.name, move.product_id.display_name))
        
        res = super(StockPicking, self).button_validate()
        
        for picking in self:
            if picking.state == 'done':
                products = picking.move_ids.mapped('product_id.product_tmpl_id')
                if products:
                    products._compute_amc_values()
                    products.action_update_reordering_rules()
        
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                picking_type = self.env['stock.picking.type'].browse(vals.get('picking_type_id'))
                warehouse = picking_type.warehouse_id
                
                type_code = picking_type.code.upper() if picking_type.code else 'PICK'
                division = (warehouse.wh_type or 'GEN').upper() if hasattr(warehouse, 'wh_type') else 'GEN'
                year = fields.Date.today().year
                
                seq_code = 'stock.picking.sequence'
                serial = self.env['ir.sequence'].next_by_code(seq_code) or '00001'
                
                vals['name'] = f"{type_code}/{division}/{year}/{serial}"
                
        return super(StockPicking, self).create(vals_list)
