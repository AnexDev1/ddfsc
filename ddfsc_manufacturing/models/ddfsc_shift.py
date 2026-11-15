from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command

# Dire Dawa runs on East Africa Time.  Used when the company has no timezone.
FACTORY_TZ = 'Africa/Addis_Ababa'


def factory_tz(env, company=None):
    """One timezone for every shift calculation, whatever the user's own setting."""
    company = company or env.company
    return pytz.timezone(company.partner_id.tz or FACTORY_TZ)


class DdfscShift(models.Model):
    _name = 'ddfsc.shift'
    _description = 'Production Shift'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    hour_from = fields.Float(string='Start Hour', help='Factory time, 24-hour clock (06:00 = 6.0).')
    hour_to = fields.Float(string='End Hour', help='A shift that ends after midnight (22:00-06:00) belongs to the day it starts.')
    duration = fields.Float(string='Hours', compute='_compute_duration')
    crosses_midnight = fields.Boolean(compute='_compute_duration')
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('unique(code)', 'Each shift needs its own code.')

    @api.depends('hour_from', 'hour_to')
    def _compute_duration(self):
        for shift in self:
            shift.crosses_midnight = shift.hour_to <= shift.hour_from
            shift.duration = (shift.hour_to - shift.hour_from) % 24 or 24.0

    @api.depends('name', 'hour_from', 'hour_to')
    def _compute_display_name(self):
        for shift in self:
            shift.display_name = '%s (%s-%s)' % (
                shift.name, self._format_hour(shift.hour_from), self._format_hour(shift.hour_to))

    @staticmethod
    def _format_hour(value):
        value = value % 24
        return '%02d:%02d' % (int(value), round((value - int(value)) * 60) % 60)

    @api.constrains('hour_from', 'hour_to', 'active')
    def _check_hours(self):
        for shift in self:
            if not (0 <= shift.hour_from < 24 and 0 <= shift.hour_to <= 24):
                raise ValidationError(_('Shift hours must be between 00:00 and 24:00.'))
            if shift.hour_from == shift.hour_to % 24 and shift.duration != 24:
                raise ValidationError(_('A shift cannot start and end at the same time.'))
        # Shifts may not overlap: a moment of the day belongs to exactly one shift.
        active = self.search([('active', '=', True)])
        minutes = {}
        for shift in active:
            start = int(round(shift.hour_from * 60))
            for offset in range(int(round(shift.duration * 60))):
                minute = (start + offset) % 1440
                if minute in minutes:
                    raise ValidationError(_(
                        '%(a)s and %(b)s overlap. Each moment of the day must belong to one shift.',
                        a=minutes[minute].display_name, b=shift.display_name))
                minutes[minute] = shift

    def _contains_hour(self, hour):
        self.ensure_one()
        if self.crosses_midnight:
            return hour >= self.hour_from or hour < self.hour_to
        return self.hour_from <= hour < self.hour_to

    @api.model
    def _shift_at(self, moment=None, company=None):
        """Return (shift, production_day) for a UTC moment, in factory time."""
        moment = moment or fields.Datetime.now()
        local = pytz.utc.localize(moment).astimezone(factory_tz(self.env, company))
        hour = local.hour + local.minute / 60.0
        for shift in self.search([]):
            if shift._contains_hour(hour):
                day = local.date()
                if shift.crosses_midnight and hour < shift.hour_to:
                    day -= timedelta(days=1)
                return shift, day
        return self.browse(), local.date()

    def _start_on(self, production_day, company=None):
        """UTC start of this shift on a production day."""
        self.ensure_one()
        tz = factory_tz(self.env, company)
        hours = int(self.hour_from)
        minutes = int(round((self.hour_from - hours) * 60))
        local = tz.localize(datetime.combine(production_day, time(hours % 24, minutes % 60)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    def _window_on(self, production_day, company=None):
        self.ensure_one()
        start = self._start_on(production_day, company)
        return start, start + timedelta(hours=self.duration)

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
            'res_id': product.id,
            'model': 'product.template',
            'noupdate': True,
        })
        return product

    @api.model
    def _ddfsc_disable_lot_tracking(self):
        """Starter data used to force lot tracking; turn it off on plant products."""
        products = self.env['ir.model.data'].search([
            ('module', '=', 'ddfsc_manufacturing'),
            ('model', '=', 'product.template'),
        ]).mapped('res_id')
        templates = self.env['product.template'].browse(products).exists().filtered(
            lambda product: product.tracking != 'none'
        )
        if templates:
            templates.write({'tracking': 'none'})

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
        """Create a starter recipe once.  Never overwrite it afterwards.

        Recipes belong to the factory once installed: production managers tune
        quantities in the Bill of Materials screen and a module upgrade must not
        silently put the starter figures back.  Archived recipes stay archived.
        """
        product = self.env.ref(product_xmlid)
        bom = self.env['mrp.bom'].with_context(active_test=False).search([('code', '=', code)], limit=1)
        if bom:
            return bom
        return self.env['mrp.bom'].create({
            'product_tmpl_id': product.id,
            'product_qty': qty,
            'product_uom_id': self.env.ref(uom_xmlid).id,
            'code': code,
            'type': 'normal',
            'bom_line_ids': [Command.create(line) for line in lines],
            'byproduct_ids': [Command.create(line) for line in (byproducts or [])],
        })

    def _sync_bom_lines(self, bom, field_name, lines):
        existing = {line.product_id.id: line for line in bom[field_name]}
        seen = set()
        commands = []
        for line_vals in lines:
            product_id = line_vals['product_id']
            seen.add(product_id)
            current = existing.get(product_id)
            if current:
                current.write(line_vals)
            else:
                commands.append(Command.create(line_vals))
        extras = bom[field_name].filtered(lambda line: line.product_id.id not in seen)
        commands.extend(Command.delete(line.id) for line in extras)
        if commands:
            bom.write({field_name: commands})

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
        self._ensure_product('product_maize_flour', 'Maize Flour', quintal)
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
        self._ensure_product('product_bran', 'Wheat Bran', quintal)
        self._ensure_product('product_water', 'Process Water', kg)
        self._ensure_product('product_bread_market', 'Bread Market 100g', unit)
        self._ensure_product('product_bread_university', 'Bread University 120g', unit)
        self._ensure_product('product_pasta_long', 'Long Cut Pasta 500g', unit)
        self._ensure_product('product_pasta_short', 'Short Cut Pasta 500g', unit)

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
        flour_store.ddfsc_flour_hold = False
        flour_finished = self._ensure_record('loc_flour_finished', 'stock.location', {
            'name': 'Flour Temp Finished',
            'location_id': parent.id,
            'usage': 'internal',
        })
        flour_finished.ddfsc_flour_hold = True
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
        self._ensure_record('loc_pasta_finished', 'stock.location', {
            'name': 'Pasta Temp Finished',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_macaroni_finished', 'stock.location', {
            'name': 'Macaroni Temp Finished',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_bread_finished', 'stock.location', {
            'name': 'Bread Temp Finished',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_biscuit_finished', 'stock.location', {
            'name': 'Biscuit Temp Finished',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_byproduct', 'stock.location', {
            'name': 'By-product Temp',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_recycle', 'stock.location', {
            'name': 'Recycled Material',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_pasta_byproduct', 'stock.location', {
            'name': 'Pasta By-products Temp',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_bread_byproduct', 'stock.location', {
            'name': 'Bread By-products Temp',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_record('loc_biscuit_byproduct', 'stock.location', {
            'name': 'Biscuit By-products Temp',
            'location_id': parent.id,
            'usage': 'internal',
        })
        self._ensure_product('product_flour_scp', 'Short Cut Pasta Flour', quintal)
        self._ensure_product('product_flour_lcp', 'Long Cut Pasta Flour', quintal)
        self._ensure_product('product_rf', 'By-product RF', quintal)
        self._ensure_product('product_rc', 'By-product RC', quintal)
        self._ensure_product('product_pasta_breakage', 'Pasta Breakage (Saleable)', kg)
        self._ensure_product('product_bread_breakage', 'Bread Breakage (Saleable)', kg)
        self._ensure_product('product_biscuit_breakage', 'Biscuit Breakage (Saleable)', kg)
        self.env.ref('ddfsc_manufacturing.product_flour_scp').ddfsc_is_flour = True
        self.env.ref('ddfsc_manufacturing.product_flour_lcp').ddfsc_is_flour = True
        byproducts = {
            'product_rf': 'flour',
            'product_rc': 'flour',
            'product_pasta_breakage': 'pasta',
            'product_bread_breakage': 'bread',
            'product_biscuit_breakage': 'biscuit',
        }
        for xmlid, department in byproducts.items():
            self.env.ref('ddfsc_manufacturing.%s' % xmlid).write({
                'ddfsc_is_byproduct': True,
                'ddfsc_byproduct_department': department,
                'sale_ok': True,
                'purchase_ok': False,
            })
        # Breakage is weighed, not counted.  Switch the unit to kg only while
        # the product has never moved, so existing stock is never re-valued.
        kg_uom = self.env.ref('uom.product_uom_kgm')
        for xmlid in ('product_pasta_breakage', 'product_bread_breakage', 'product_biscuit_breakage'):
            template = self.env.ref('ddfsc_manufacturing.%s' % xmlid)
            if template.uom_id != kg_uom and not self.env['stock.move'].search_count(
                    [('product_id', 'in', template.product_variant_ids.ids)], limit=1):
                template.write({'uom_id': kg_uom.id})
        self._ensure_product('product_defense', 'Defense Biscuit 160x4', unit)
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
        # Biscuit mixes 1.5 qtl of flour per batch (biscuit daily report).
        for code in ('BISC-CN', 'BISC-OR'):
            line = self.env['mrp.workcenter'].search([('code', '=', code)], limit=1)
            if line and not line.ddfsc_batch_qtl:
                line.ddfsc_batch_qtl = 1.5
        self._sync_operations()
        self._sync_quality_control()
        self._sync_mill_packing()
        self._sync_store_structure()

    @api.model
    def _sync_quality_control(self):
        """Require lots on QC-controlled products. Acceptance plans come from ddfsc_quality (factory standards)."""
        groups = {
            'incoming_wheat': ['product_wheat'],
            'flour_release': ['product_flour_g1', 'product_flour_g2', 'product_flour_scp', 'product_flour_lcp'],
            'finished_goods': ['product_pasta_long', 'product_pasta_short', 'product_bread_market',
                               'product_bread_university', 'product_zebib', 'product_defense'],
        }
        products = {}
        for checkpoint, xmlids in groups.items():
            variants = self.env['product.product']
            for xmlid in xmlids:
                template = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
                if template:
                    variants |= template.product_variant_id
                    if template.tracking != 'lot':
                        template.write({'tracking': 'lot'})
            products[checkpoint] = variants
        tracked = self.env['product.product'].concat(*products.values())
        self._migrate_untracked_quality_stock(tracked)
        quality_products = self.env['ddfsc.quality.plan'].search([]).mapped('product_ids')
        lots_without_tests = self.env['stock.lot'].search([
            ('product_id', 'in', quality_products.ids), ('quality_check_ids', '=', False),
            ('name', 'not like', 'LEGACY-OPENING-'),
        ])
        lots_without_tests.filtered('quality_plan_id').action_prepare_quality_checks()

    @api.model
    def _migrate_untracked_quality_stock(self, products=None):
        """Keep stock that predates mandatory tracking usable and auditable."""
        products = (products or self.env['product.product']) | self.env['ddfsc.quality.plan'].search([]).mapped('product_ids')
        quants = self.env['stock.quant'].search([
            ('product_id', 'in', products.ids), ('location_id.usage', '=', 'internal'),
            ('quantity', '!=', 0), ('lot_id', '=', False),
        ])
        for product in quants.mapped('product_id'):
            product_quants = quants.filtered(lambda quant: quant.product_id == product)
            company = product_quants.company_id[:1] or self.env.company
            lot_name = 'LEGACY-OPENING-%s' % product.id
            lot = self.env['stock.lot'].search([
                ('name', '=', lot_name), ('product_id', '=', product.id),
                ('company_id', '=', company.id),
            ], limit=1)
            if not lot:
                lot = self.env['stock.lot'].create({
                    'name': lot_name, 'product_id': product.id, 'company_id': company.id,
                    'ddfsc_quality_state': 'released',
                    'quality_release_note': 'Existing balance migrated when mandatory QC tracking was enabled.',
                    'quality_decision_by_id': self.env.user.id,
                    'quality_decision_date': fields.Datetime.now(),
                })
            product_quants.write({'lot_id': lot.id})

    @api.model
    def _sync_operations(self):
        """Enable multi-location, keep request picking types on the Inventory dashboard."""
        internal_users = self.env.ref('base.group_user')
        multi_locations = self.env.ref('stock.group_stock_multi_locations')
        if multi_locations not in internal_users.implied_ids:
            internal_users.write({'implied_ids': [Command.link(multi_locations.id)]})
        self._sync_warehouse_defaults()
        self._ensure_request_picking_types()
        self._retire_plant_operation_types()
        self._retire_manufacturing_transfer_menus()

    def _sync_warehouse_defaults(self):
        """Route receipts by product instead of sending everything to one place.

        Wheat lands in Wheat Receiving for the incoming QC (then QC Release to
        General Store); every other purchased material lands in General Store.
        Receipts target the warehouse stock and putaway rules pick the store,
        so one Receipts operation serves both.
        """
        dock = self.env.ref('ddfsc_manufacturing.loc_wheat_dock')
        store = self.env.ref('ddfsc_manufacturing.loc_store')
        finished_goods = self.env.ref('ddfsc_manufacturing.loc_finished')
        wheat = self.env.ref('ddfsc_manufacturing.product_wheat').product_variant_id
        Putaway = self.env['stock.putaway.rule'].with_context(active_test=False)
        warehouses = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ])
        for warehouse in warehouses:
            stock = warehouse.lot_stock_id
            if warehouse.in_type_id and warehouse.in_type_id.default_location_dest_id in (dock, store):
                warehouse.in_type_id.default_location_dest_id = stock
            if warehouse.out_type_id:
                warehouse.out_type_id.default_location_src_id = finished_goods
            if dock.location_id == stock and not Putaway.search_count([
                    ('location_in_id', '=', stock.id), ('product_id', '=', wheat.id)]):
                Putaway.create({'location_in_id': stock.id, 'location_out_id': dock.id,
                                'product_id': wheat.id, 'category_id': False,
                                'company_id': warehouse.company_id.id, 'sequence': 1})
            # A rule with no product and no category matches every product;
            # Odoo always prefers the product-specific wheat rule above it.
            if store.location_id == stock and not Putaway.search_count([
                    ('location_in_id', '=', stock.id), ('product_id', '=', False),
                    ('category_id', '=', False)]):
                Putaway.create({'location_in_id': stock.id, 'location_out_id': store.id,
                                'product_id': False, 'category_id': False,
                                'company_id': warehouse.company_id.id, 'sequence': 50})

    def _ensure_request_picking_types(self):
        """Store / FG request pickings need their own operation types to show on Overview."""
        warehouse = self.env['stock.warehouse'].search([
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not warehouse:
            return
        defaults = {
            'store_requisition': ('loc_store', 'loc_mill'),
            'fg_receiving': ('loc_flour', 'loc_finished'),
            'byproduct_return': ('loc_byproduct', 'loc_store'),
            'qc_release': ('loc_wheat_dock', 'loc_store'),
            'material_return': ('loc_biscuit', 'loc_store'),
        }
        for xmlid, name, prefix, doc_type, sequence in (
            ('picking_type_store_requisition', 'Store Transfer Request', 'MTR', 'store_requisition', 35),
            ('picking_type_fg_receiving', 'FG Transfer Request', 'FGR', 'fg_receiving', 36),
            ('picking_type_byproduct_return', 'By-product Return', 'BPR', 'byproduct_return', 37),
            ('picking_type_qc_release', 'QC Release to General Store', 'QCR', 'qc_release', 38),
            ('picking_type_material_return', 'Material Return to Store', 'MRN', 'material_return', 39),
        ):
            picking_type = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
            vals = {
                'name': name,
                'code': 'internal',
                'sequence_code': prefix,
                'warehouse_id': warehouse.id,
                'default_location_src_id': self.env.ref('ddfsc_manufacturing.' + defaults[doc_type][0]).id,
                'default_location_dest_id': self.env.ref('ddfsc_manufacturing.' + defaults[doc_type][1]).id,
                'ddfsc_document_type': doc_type,
                'active': True,
                'sequence': sequence,
                'reservation_method': 'at_confirm',
                'show_operations': True,
            }
            if picking_type:
                picking_type.write(vals)
                continue
            picking_type = self.env['stock.picking.type'].create(vals)
            self.env['ir.model.data'].create({
                'module': 'ddfsc_manufacturing',
                'name': xmlid,
                'model': 'stock.picking.type',
                'res_id': picking_type.id,
                'noupdate': True,
            })

    def _retire_plant_operation_types(self):
        """Archive obsolete plant picking types; keep Store / FG request types active."""
        xmlids = [
            'picking_type_wheat_receiving',
            'picking_type_store_receipt',
            'picking_type_wheat_to_silo',
            'picking_type_silo_issue',
            'picking_type_flour_transfer',
            'picking_type_wheat_purchase',
            'picking_type_store_purchase',
        ]
        for xmlid in xmlids:
            picking_type = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
            if not picking_type:
                continue
            picking_type.write({
                'active': False,
                'ddfsc_document_type': False,
            })

    def _retire_manufacturing_transfer_menus(self):
        """Drop obsolete custom-transfer menus and purchase-based plant forms."""
        xmlids = [
            'menu_ddfsc_store_requisition',
            'menu_ddfsc_silo_issue',
            'menu_ddfsc_flour_transfer',
            'menu_ddfsc_byproduct_return',
            'menu_ddfsc_fg_receiving',
            'menu_ddfsc_transfers',
            'menu_ddfsc_wheat_purchase',
            'menu_ddfsc_store_purchase',
            'menu_ddfsc_picking_requisition',
            'menu_ddfsc_wheat_receiving',
            'menu_ddfsc_store_receipt',
            'menu_ddfsc_wheat_to_silo',
            'menu_ddfsc_picking_silo_issue',
            'menu_ddfsc_picking_flour',
            'menu_ddfsc_picking_byproduct',
            'menu_ddfsc_picking_fg',
            'action_ddfsc_store_requisition',
            'action_ddfsc_wheat_receiving',
            'action_ddfsc_silo_issue',
            'action_ddfsc_flour_transfer',
            'action_ddfsc_byproduct_return',
            'action_ddfsc_fg_receiving',
            'action_ddfsc_wheat_purchase',
            'action_ddfsc_store_purchase',
            'action_ddfsc_picking_store_requisition',
            'action_ddfsc_picking_wheat_receiving',
            'action_ddfsc_picking_store_receipt',
            'action_ddfsc_picking_wheat_to_silo',
            'action_ddfsc_picking_silo_issue',
            'action_ddfsc_picking_flour_transfer',
            'action_ddfsc_picking_byproduct_return',
            'action_ddfsc_picking_fg_receiving',
            'purchase_order_form_ddfsc',
            'view_picking_form_ddfsc_store_request',
        ]
        for xmlid in xmlids:
            record = self.env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False)
            if record:
                record.unlink()

    def _line_request(self, code, name, flour_qtl):
        line = self.env['mrp.workcenter'].search([('code', '=', code)], limit=1)
        if not line:
            line = self.env['mrp.workcenter'].create({
                'name': name, 'code': code, 'ddfsc_flour_request_qtl': flour_qtl,
            })
        return line
