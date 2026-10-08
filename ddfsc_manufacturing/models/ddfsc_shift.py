from odoo import api, fields, models
from odoo.fields import Command


class DdfscShift(models.Model):
    _name = 'ddfsc.shift'
    _description = 'Production Shift'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    hour_from = fields.Float(string='Start Hour')
    hour_to = fields.Float(string='End Hour')
    active = fields.Boolean(default=True)

    @api.model
    def _load_starter_bom(self):
        self._sync_recipes()

    def _variant(self, xmlid):
        record = self.env.ref(xmlid)
        if record._name == 'product.template':
            return record.product_variant_id
        return record

    def _ensure_product(self, xmlid, name, uom_xmlid, tracking='none'):
        record = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
        if record:
            return record
        product = self.env['product.template'].create({
            'name': name,
            'is_storable': True,
            'tracking': tracking,
            'uom_id': self.env.ref(uom_xmlid).id,
        })
        self.env['ir.model.data'].create({
            'module': 'ddfsc_manufacturing',
            'name': xmlid,
            'model': 'product.template',
            'res_id': product.id,
            'noupdate': True,
        })
        return product

    def _ensure_record(self, xmlid, model, vals):
        record = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
        if record:
            return record
        record = self.env[model].create(vals)
        self.env['ir.model.data'].create({
            'module': 'ddfsc_manufacturing',
            'name': xmlid,
            'model': model,
            'res_id': record.id,
            'noupdate': True,
        })
        return record

    def _silo(self, xmlid, name, use):
        parent = self.env.ref('stock.stock_location_stock')
        location = self._ensure_record(xmlid, 'stock.location', {
            'name': name,
            'location_id': parent.id,
            'usage': 'internal',
        })
        location.ddfsc_silo_use = use
        return location

    def _sync_bom(self, code, product_xmlid, qty, uom_xmlid, lines, byproducts=None):
        product = self.env.ref(product_xmlid)
        vals = {
            'product_tmpl_id': product.id,
            'product_qty': qty,
            'product_uom_id': self.env.ref(uom_xmlid).id,
            'code': code,
            'type': 'normal',
            'bom_line_ids': [Command.clear()] + [Command.create(line) for line in lines],
            'byproduct_ids': [Command.clear()] + [Command.create(line) for line in (byproducts or [])],
        }
        bom = self.env['mrp.bom'].search([('code', '=', code)], limit=1)
        if bom:
            bom.write(vals)
        else:
            bom = self.env['mrp.bom'].create(vals)
        return bom

    def _line(self, product, qty, uom_xmlid):
        return {
            'product_id': product.id,
            'product_qty': qty,
            'product_uom_id': self.env.ref(uom_xmlid).id,
        }

    @api.model
    def _sync_recipes(self):
        """Starter recipes from the plant forms. Ratios are per 1 quintal of flour or wheat."""
        quintal = 'ddfsc_manufacturing.uom_quintal'
        kg = 'uom.product_uom_kgm'
        unit = 'uom.product_uom_unit'
        self._ensure_product('product_maize_flour', 'Maize Flour', quintal, tracking='lot')
        self._ensure_product('product_abc', 'Ammonium Bicarbonate', kg)
        self._ensure_product('product_sbc', 'Sodium Bicarbonate', kg)
        self._ensure_product('product_sms', 'Sodium Metabisulfite', kg)
        self._ensure_product('product_salt', 'Common Salt', kg)
        citric_tmpl = self._ensure_product('product_citric', 'Citric Acid', 'uom.product_uom_gram')
        if citric_tmpl.uom_id != self.env.ref('uom.product_uom_gram'):
            citric_tmpl.uom_id = self.env.ref('uom.product_uom_gram')
        self._ensure_product('product_zebib_film', 'Zebib Film', kg)
        self._ensure_product('product_carton_78', 'Carton 78x4', unit)
        self._ensure_product('product_scotch', 'Scotch Tape', unit)
        self._ensure_product('product_bran', 'Wheat Bran', quintal, tracking='lot')
        self._ensure_product('product_water', 'Process Water', kg)
        self._ensure_product('product_bread_market', 'Bread Market 100g', unit, tracking='lot')
        self._ensure_product('product_bread_university', 'Bread University 120g', unit, tracking='lot')
        self._ensure_product('product_pasta_long', 'Long Cut Pasta 500g', unit, tracking='lot')
        self._ensure_product('product_pasta_short', 'Short Cut Pasta 500g', unit, tracking='lot')

        flour_g1 = self._variant('ddfsc_manufacturing.product_flour_g1')
        flour_g2 = self._variant('ddfsc_manufacturing.product_flour_g2')
        wheat = self._variant('ddfsc_manufacturing.product_wheat')
        maize = self._variant('ddfsc_manufacturing.product_maize_flour')
        sugar = self._variant('ddfsc_manufacturing.product_sugar')
        shortening = self._variant('ddfsc_manufacturing.product_shortening')
        abc = self._variant('ddfsc_manufacturing.product_abc')
        sbc = self._variant('ddfsc_manufacturing.product_sbc')
        sms = self._variant('ddfsc_manufacturing.product_sms')
        salt = self._variant('ddfsc_manufacturing.product_salt')
        citric = self._variant('ddfsc_manufacturing.product_citric')
        film = self._variant('ddfsc_manufacturing.product_zebib_film')
        carton = self._variant('ddfsc_manufacturing.product_carton_78')
        tape = self._variant('ddfsc_manufacturing.product_scotch')
        bran = self._variant('ddfsc_manufacturing.product_bran')
        water = self._variant('ddfsc_manufacturing.product_water')
        for xmlid in ('product_flour_g1', 'product_flour_g2', 'product_maize_flour'):
            self.env.ref('ddfsc_manufacturing.%s' % xmlid).ddfsc_is_flour = True
        parent = self.env.ref('stock.stock_location_stock')
        self._ensure_record('loc_mill', 'stock.location', {
            'name': 'Mill Floor',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_store', 'stock.location', {
            'name': 'General Store',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._silo('loc_silo_pasta', 'Pasta Wheat Silo', 'pasta')
        self._silo('loc_silo_macaroni', 'Macaroni Wheat Silo', 'macaroni')
        self._silo('loc_silo_bread', 'Bread Wheat Silo', 'bread')
        self._silo('loc_silo_biscuit', 'Biscuit Wheat Silo', 'biscuit')
        self._ensure_record('loc_wheat_dock', 'stock.location', {
            'name': 'Wheat Receiving',
            'location_id': parent.id,
            'usage': 'internal',
        })
        flour_store = self.env.ref('ddfsc_manufacturing.loc_flour')
        flour_store.ddfsc_flour_hold = True
        for xmlid, name in (
            ('loc_flour_pasta', 'Pasta Flour Silo'),
            ('loc_flour_macaroni', 'Macaroni Flour Silo'),
        ):
            silo = self._ensure_record(xmlid, 'stock.location', {
                'name': name,
                'location_id': parent.id,
                'usage': 'internal',
            })
            silo.ddfsc_flour_hold = True
        self._ensure_record('loc_macaroni', 'stock.location', {
            'name': 'Macaroni Floor',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_recycle', 'stock.location', {
            'name': 'Recycled Material',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_product('product_flour_scp', 'Short Cut Pasta Flour', quintal, tracking='lot')
        self._ensure_product('product_flour_lcp', 'Long Cut Pasta Flour', quintal, tracking='lot')
        self._ensure_product('product_rf', 'By-product RF', quintal, tracking='lot')
        self._ensure_product('product_rc', 'By-product RC', quintal, tracking='lot')
        self.env.ref('ddfsc_manufacturing.product_flour_scp').ddfsc_is_flour = True
        self.env.ref('ddfsc_manufacturing.product_flour_lcp').ddfsc_is_flour = True
        self.env.ref('ddfsc_manufacturing.product_rf').ddfsc_is_byproduct = True
        self.env.ref('ddfsc_manufacturing.product_rc').ddfsc_is_byproduct = True
        self._ensure_product('product_defense', 'Defense Biscuit 160x4', unit, tracking='lot')
        self._ensure_product('product_carton_160', 'Carton 160x4', unit)
        self._ensure_product('product_defense_film', 'Defense Film', kg)
        defense_film = self._variant('ddfsc_manufacturing.product_defense_film')
        carton_160 = self._variant('ddfsc_manufacturing.product_carton_160')
        flour_scp = self._variant('ddfsc_manufacturing.product_flour_scp')
        flour_lcp = self._variant('ddfsc_manufacturing.product_flour_lcp')
        byproduct_rf = self._variant('ddfsc_manufacturing.product_rf')

        # Planning example from the meeting: 125 qtl wheat gives 100 qtl flour (80%), about 20% by-product.
        # A real batch changes these quantities from the hectoliter weight.
        old_mill = self.env['mrp.bom'].search([('code', '=', 'MILL-WHEAT')])
        if old_mill:
            old_mill.active = False
        self._sync_bom(
            'MILL-SCP',
            'ddfsc_manufacturing.product_flour_scp',
            1.0,
            quintal,
            [self._line(wheat, 1.25, quintal)],
            [self._line(byproduct_rf, 0.25, quintal)],
        )
        self._sync_bom(
            'MILL-LCP',
            'ddfsc_manufacturing.product_flour_lcp',
            1.0,
            quintal,
            [self._line(wheat, 1.25, quintal)],
            [self._line(byproduct_rf, 0.25, quintal)],
        )
        self._sync_bom(
            'MILL-G1',
            'ddfsc_manufacturing.product_flour_g1',
            1.0,
            quintal,
            [self._line(wheat, 1.25, quintal)],
            [self._line(byproduct_rf, 0.25, quintal)],
        )
        self._sync_bom(
            'MILL-G2',
            'ddfsc_manufacturing.product_flour_g2',
            1.0,
            quintal,
            [self._line(wheat, 1.25, quintal)],
            [self._line(byproduct_rf, 0.25, quintal)],
        )
        # Consumption sheet per 100 kg flour: 90 kg wheat flour, 10 kg maize flour.
        self._sync_bom(
            'ZEBIB-1QTL',
            'ddfsc_manufacturing.product_zebib',
            30,
            unit,
            [
                self._line(flour_g2, 0.9, quintal),
                self._line(maize, 0.1, quintal),
                self._line(sugar, 21.6, kg),
                self._line(shortening, 5, kg),
                self._line(abc, 3.33, kg),
                self._line(sbc, 1, kg),
                self._line(sms, 0.08, kg),
                self._line(salt, 0.6, kg),
                self._line(citric, 3.3, 'uom.product_uom_gram'),
                self._line(carton, 30, unit),
                self._line(film, 4.2, kg),
                self._line(tape, 0.43, unit),
            ],
        )
        # 1 quintal grade 1 flour, 55 kg water, about 10% bake loss.
        self._sync_bom(
            'BREAD-MARKET',
            'ddfsc_manufacturing.product_bread_market',
            1400,
            unit,
            [
                self._line(flour_g1, 1, quintal),
                self._line(water, 55, kg),
            ],
        )
        self._sync_bom(
            'BREAD-UNIVERSITY',
            'ddfsc_manufacturing.product_bread_university',
            1160,
            unit,
            [
                self._line(flour_g1, 1, quintal),
                self._line(water, 55, kg),
            ],
        )
        # Dried pasta weight follows the flour. One pack is the 500 g quality-control unit.
        self._sync_bom(
            'PASTA-LONG',
            'ddfsc_manufacturing.product_pasta_long',
            200,
            unit,
            [self._line(flour_lcp, 1, quintal)],
        )
        self._sync_bom(
            'PASTA-SHORT',
            'ddfsc_manufacturing.product_pasta_short',
            200,
            unit,
            [self._line(flour_scp, 1, quintal)],
        )
        # Paper pack count is 5 cartons of 160x4 per quintal. Ingredients follow the Zebib sheet.
        self._sync_bom(
            'DEFENSE-1QTL',
            'ddfsc_manufacturing.product_defense',
            5,
            unit,
            [
                self._line(flour_g2, 0.9, quintal),
                self._line(maize, 0.1, quintal),
                self._line(sugar, 21.6, kg),
                self._line(shortening, 5, kg),
                self._line(abc, 3.33, kg),
                self._line(sbc, 1, kg),
                self._line(sms, 0.08, kg),
                self._line(salt, 0.6, kg),
                self._line(citric, 3.3, 'uom.product_uom_gram'),
                self._line(carton_160, 5, unit),
                self._line(defense_film, 4.2, kg),
                self._line(tape, 0.43, unit),
            ],
        )
        self._line_request('PASTA', 'Pasta Line', 300)
        self._line_request('MAC', 'Macaroni Line', 360)
        self._line_request('BREAD', 'Bread Line', 30)
        self._line_request('BISC-CN', 'Biscuit Line China', 100)
        self._line_request('BISC-OR', 'Biscuit Line Orland', 60)
        self._line_request('MILL', 'Flour Mill', 0)
        self._sync_operations()

    def _sync_operations(self):
        """Purchase receipts and inventory transfers for the plant forms."""
        internal_users = self.env.ref('base.group_user')
        multi_locations = self.env.ref('stock.group_stock_multi_locations')
        if multi_locations not in internal_users.implied_ids:
            internal_users.write({'implied_ids': [Command.link(multi_locations.id)]})
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        suppliers = self.env.ref('stock.stock_location_suppliers')
        operations = [
            ('picking_type_wheat_purchase', 'wheat_purchase', 'Wheat Receiving', 'incoming', 'WHEAT', suppliers, 'loc_wheat_dock'),
            ('picking_type_store_purchase', 'store_purchase', 'Store Receipt', 'incoming', 'STORE', suppliers, 'loc_store'),
            ('picking_type_wheat_to_silo', 'wheat_to_silo', 'Wheat to Silo', 'internal', 'SILO', 'loc_wheat_dock', 'loc_silo_pasta'),
            ('picking_type_silo_issue', 'silo_issue', 'Silo Issue', 'internal', 'ISSUE', 'loc_silo_pasta', 'loc_mill'),
            ('picking_type_flour_transfer', 'flour_transfer', 'Flour Transfer', 'internal', 'FLOUR', 'loc_flour', 'loc_flour_pasta'),
            ('picking_type_store_requisition', 'store_requisition', 'Store Requisition', 'internal', 'REQ', 'loc_store', 'loc_biscuit'),
            ('picking_type_byproduct_return', 'byproduct_return', 'By-product to Store', 'internal', 'BYP', 'loc_mill', 'loc_store'),
            ('picking_type_fg_receiving', 'fg_receiving', 'Finished Goods Receiving', 'internal', 'FG', 'loc_biscuit', 'loc_finished'),
        ]
        for xmlid, document_type, name, code, prefix, source, destination in operations:
            source_location = self.env.ref('ddfsc_manufacturing.%s' % source) if isinstance(source, str) else source
            dest_location = self.env.ref('ddfsc_manufacturing.%s' % destination)
            picking_type = self._ensure_record(xmlid, 'stock.picking.type', {
                'name': name,
                'code': code,
                'sequence_code': prefix,
                'sequence': 50,
                'warehouse_id': warehouse.id,
                'company_id': self.env.company.id,
            })
            picking_type.write({
                'name': name,
                'ddfsc_document_type': document_type,
                'default_location_src_id': source_location.id,
                'default_location_dest_id': dest_location.id,
            })
        self.env['mrp.production']._ddfsc_rehome_default_transfers()
        self._retire_manufacturing_transfer_menus()

    def _retire_manufacturing_transfer_menus(self):
        xmlids = [
            'menu_ddfsc_store_requisition',
            'menu_ddfsc_wheat_receiving',
            'menu_ddfsc_silo_issue',
            'menu_ddfsc_flour_transfer',
            'menu_ddfsc_byproduct_return',
            'menu_ddfsc_fg_receiving',
            'menu_ddfsc_transfers',
            'action_ddfsc_store_requisition',
            'action_ddfsc_wheat_receiving',
            'action_ddfsc_silo_issue',
            'action_ddfsc_flour_transfer',
            'action_ddfsc_byproduct_return',
            'action_ddfsc_fg_receiving',
        ]
        for xmlid in xmlids:
            record = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
            if record:
                record.unlink()

    def _line_request(self, code, name, flour_qtl):
        line = self.env['mrp.workcenter'].search([('code', '=', code)], limit=1)
        if not line:
            line = self.env['mrp.workcenter'].create({'name': name, 'code': code})
        line.ddfsc_flour_request_qtl = flour_qtl
        return line
