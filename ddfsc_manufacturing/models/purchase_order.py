from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'ddfsc.approval.mixin']

    ddfsc_production_id = fields.Many2one(
        'mrp.production',
        string='Manufacturing Order',
        index=True,
        copy=False,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        document_type = self.env.context.get('ddfsc_document_type')
        if document_type:
            picking_type = self.env['stock.picking.type'].search([
                ('ddfsc_document_type', '=', document_type),
            ], limit=1)
            if picking_type:
                values['picking_type_id'] = picking_type.id
        return values

    def _ddfsc_approval_role(self):
        self.ensure_one()
        document_type = self.picking_type_id.ddfsc_document_type
        if document_type == 'wheat_purchase':
            return 'gm'
        if document_type == 'store_purchase':
            return 'operation'
        return ''

    @api.depends('picking_type_id', 'picking_type_id.ddfsc_document_type')
    def _compute_ddfsc_needs_approval(self):
        super()._compute_ddfsc_needs_approval()

    def button_confirm(self):
        self._ddfsc_ensure_approved()
        return super().button_confirm()

    def write(self, vals):
        res = super().write(vals)
        if 'ddfsc_production_id' in vals:
            self.picking_ids.write({'ddfsc_production_id': vals['ddfsc_production_id']})
        return res

    def _prepare_picking(self):
        values = super()._prepare_picking()
        if self.ddfsc_production_id:
            values['ddfsc_production_id'] = self.ddfsc_production_id.id
        return values
