"""Stock card (bin card), weekly critical items and department production report.

* Stock Card: every done movement in or out of a store or floor with the
  voucher number and a running balance — the paper bin card, and, filtered on
  a production floor, the floor balance and store-issue reconciliation.
* Critical Items: the weekly report of packing materials and ingredients
  (store stock, floor stock, monthly consumption, hold limit, on order).
* Department Production Report: the daily / monthly report the production
  divisions send to Production & Technique.
"""

from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from .ddfsc_department import DEPARTMENTS, selection


class DdfscStockCard(models.Model):
    _name = 'ddfsc.stock.card'
    _description = 'Stock Card (Bin Card)'
    _auto = False
    _order = 'location_id, product_id, date, id'

    date = fields.Datetime(readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unit', readonly=True)
    location_id = fields.Many2one('stock.location', string='Store / Floor', readonly=True)
    reference = fields.Char(string='Voucher / Reference', readonly=True)
    counterpart_id = fields.Many2one('stock.location', string='From / To', readonly=True)
    lot_id = fields.Many2one('stock.lot', readonly=True)
    received = fields.Float(readonly=True, digits='Product Unit')
    issued = fields.Float(readonly=True, digits='Product Unit')
    balance = fields.Float(readonly=True, digits='Product Unit', aggregator=False,
                           help='Running balance of this product in this store or floor after the movement.')
    company_id = fields.Many2one('res.company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH movements AS (
                    SELECT ml.id * 2 AS id, ml.date, ml.product_id, ml.location_dest_id AS location_id,
                           ml.location_id AS counterpart_id, ml.lot_id, ml.company_id,
                           COALESCE(m.reference, m.origin) AS reference,
                           ml.quantity_product_uom AS received, 0.0 AS issued
                      FROM stock_move_line ml
                      JOIN stock_move m ON m.id = ml.move_id
                      JOIN stock_location dest ON dest.id = ml.location_dest_id
                     WHERE ml.state = 'done' AND dest.usage = 'internal'
                       AND ml.location_id != ml.location_dest_id
                    UNION ALL
                    SELECT ml.id * 2 + 1 AS id, ml.date, ml.product_id, ml.location_id AS location_id,
                           ml.location_dest_id AS counterpart_id, ml.lot_id, ml.company_id,
                           COALESCE(m.reference, m.origin) AS reference,
                           0.0 AS received, ml.quantity_product_uom AS issued
                      FROM stock_move_line ml
                      JOIN stock_move m ON m.id = ml.move_id
                      JOIN stock_location src ON src.id = ml.location_id
                     WHERE ml.state = 'done' AND src.usage = 'internal'
                       AND ml.location_id != ml.location_dest_id
                )
                SELECT mv.id, mv.date, mv.product_id, pt.uom_id, mv.location_id, mv.counterpart_id,
                       mv.lot_id, mv.company_id, mv.reference, mv.received, mv.issued,
                       SUM(mv.received - mv.issued) OVER (
                           PARTITION BY mv.product_id, mv.location_id ORDER BY mv.date, mv.id
                       ) AS balance
                  FROM movements mv
                  JOIN product_product pp ON pp.id = mv.product_id
                  JOIN product_template pt ON pt.id = pp.product_tmpl_id
            )
        """ % self._table)


class DdfscCriticalItemsWizard(models.TransientModel):
    _name = 'ddfsc.critical.items.wizard'
    _description = 'Weekly Report of Critical Items'

    date = fields.Date(required=True, default=fields.Date.context_today)
    product_ids = fields.Many2many(
        'product.product', string='Items',
        help='Leave empty for every ingredient and packing material the recipes use.')
    line_ids = fields.One2many('ddfsc.critical.items.line', 'wizard_id', readonly=True)

    def _default_items(self):
        boms = self.env['mrp.bom'].search([('active', '=', True)])
        return boms.bom_line_ids.product_id.filtered(lambda product: not product.ddfsc_is_flour
                                                     and product.is_storable)

    def action_compute(self):
        self.ensure_one()
        store = self.env.ref('ddfsc_manufacturing.loc_store')
        floors = self.env['stock.location']
        for spec in DEPARTMENTS.values():
            for key in ('component_location', 'request_location'):
                floor = self.env.ref('ddfsc_manufacturing.%s' % spec[key], raise_if_not_found=False)
                floors |= floor or self.env['stock.location']
        products = self.product_ids or self._default_items()
        since = fields.Datetime.to_datetime(self.date) - timedelta(days=30)
        Line = self.env['ddfsc.critical.items.line']
        self.line_ids.unlink()
        values = []
        for product in products.sorted('name'):
            consumed = sum(self.env['stock.move'].search([
                ('product_id', '=', product.id), ('state', '=', 'done'),
                ('raw_material_production_id', '!=', False), ('date', '>=', since),
            ]).mapped('product_qty'))
            orderpoint = self.env['stock.warehouse.orderpoint'].search([('product_id', '=', product.id)], limit=1)
            on_order = 0.0
            if 'purchase.order.line' in self.env:
                on_order = sum(
                    line.product_uom_id._compute_quantity(line.product_qty - line.qty_received, product.uom_id)
                    for line in self.env['purchase.order.line'].search([
                        ('product_id', '=', product.id), ('state', 'in', ('purchase', 'done')),
                    ]) if line.product_qty > line.qty_received
                )
            values.append({
                'wizard_id': self.id, 'product_id': product.id,
                'store_qty': product.with_context(location=store.id).qty_available,
                'floor_qty': sum(product.with_context(location=floor.id).qty_available for floor in floors),
                'monthly_consumption': consumed,
                'hold_limit': orderpoint.product_min_qty if orderpoint else 0.0,
                'on_order': on_order,
            })
        Line.create(values)
        return {
            'type': 'ir.actions.act_window', 'name': _('Critical Items %s') % self.date,
            'res_model': 'ddfsc.critical.items.line', 'view_mode': 'list',
            'domain': [('wizard_id', '=', self.id)],
        }


class DdfscCriticalItemsLine(models.TransientModel):
    _name = 'ddfsc.critical.items.line'
    _description = 'Critical Item'
    _order = 'below_limit desc, product_id'

    wizard_id = fields.Many2one('ddfsc.critical.items.wizard', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Item', readonly=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    store_qty = fields.Float(string='Stock on Hand (Store)', readonly=True)
    floor_qty = fields.Float(string='Stock on Production', readonly=True)
    total_qty = fields.Float(string='Total Stock', compute='_compute_cover')
    monthly_consumption = fields.Float(string='Monthly Consumption', readonly=True)
    months_cover = fields.Float(string='Months Cover', compute='_compute_cover')
    hold_limit = fields.Float(string='Hold Limit (Min)', readonly=True)
    on_order = fields.Float(string='Ordered, Not Received', readonly=True)
    below_limit = fields.Boolean(string='Below Hold Limit', compute='_compute_cover', store=True)

    @api.depends('store_qty', 'floor_qty', 'monthly_consumption', 'hold_limit')
    def _compute_cover(self):
        for line in self:
            line.total_qty = line.store_qty + line.floor_qty
            line.months_cover = line.total_qty / line.monthly_consumption if line.monthly_consumption else 0.0
            line.below_limit = bool(line.hold_limit) and line.total_qty < line.hold_limit


class DdfscProductionReportWizard(models.TransientModel):
    _name = 'ddfsc.production.report.wizard'
    _description = 'Department Production Report'

    department = fields.Selection(selection, required=True,
                                  default=lambda self: self.env.user.ddfsc_department or 'biscuit')
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True, default=fields.Date.context_today)

    def action_print(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_('The end date is before the start date.'))
        return self.env.ref('ddfsc_manufacturing.action_report_department_production').report_action(self)

    def _report_data(self):
        """Figures of the department's orders produced in the period."""
        self.ensure_one()
        codes = DEPARTMENTS[self.department]['lines']
        orders = self.env['mrp.production'].search([
            ('ddfsc_line_id.code', 'in', codes), ('state', '!=', 'cancel'),
            ('ddfsc_production_date', '>=', self.date_from), ('ddfsc_production_date', '<=', self.date_to),
        ], order='ddfsc_production_date, ddfsc_line_id, ddfsc_shift_id')
        done = orders.filtered(lambda order: order.state == 'done')
        materials = {}
        for move in done.move_raw_ids.filtered(lambda move: move.state == 'done'):
            key = move.product_id
            entry = materials.setdefault(key, {'product': key.display_name, 'uom': key.uom_id.name, 'qty': 0.0})
            entry['qty'] += move.product_qty
        outputs = {}
        for order in done:
            entry = outputs.setdefault(order.product_id, {
                'product': order.product_id.display_name, 'uom': order.product_uom_id.name, 'qty': 0.0})
            entry['qty'] += order.ddfsc_output_qty
        downtime = {}
        for stop in orders.ddfsc_downtime_line_ids:
            label = dict(stop._fields['reason'].selection).get(stop.reason)
            downtime[label] = downtime.get(label, 0.0) + stop.hours
        flour = sum(done.mapped('ddfsc_flour_used_qtl'))
        shift_hours = sum(order.ddfsc_shift_id.duration or 8.0 for order in done)
        working_hours = max(shift_hours - sum(done.mapped('downtime_hours')), 0.0)
        output_total = sum(entry['qty'] for entry in outputs.values())
        return {
            'department': DEPARTMENTS[self.department]['label'],
            'period': '%s – %s' % (self.date_from.strftime('%d/%m/%Y'), self.date_to.strftime('%d/%m/%Y')),
            'orders': orders,
            'materials': sorted(materials.values(), key=lambda item: item['product']),
            'outputs': sorted(outputs.values(), key=lambda item: item['product']),
            'downtime': sorted(downtime.items(), key=lambda item: -item[1]),
            'flour_qtl': flour,
            'breakage': sum(done.mapped('scrap_qty')),
            'sweepings': sum(done.mapped('sweeping_qty')),
            'disposed': sum(done.mapped('disposed_qty')),
            'rework': sum(done.mapped('ddfsc_rework_qty')),
            'batches': sum(done.mapped('ddfsc_batches')),
            'working_hours': working_hours,
            'output_per_hour': output_total / working_hours if working_hours else 0.0,
            'output_per_qtl': output_total / flour if flour else 0.0,
            'wheat_qtl': sum(done.mapped('wheat_consumed_qtl')),
            'flour_out_qtl': sum(done.mapped('flour_produced_qtl')),
            'byproduct_qtl': sum(done.mapped('byproduct_qtl')),
        }
