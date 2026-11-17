"""The factory's stores (Property Administration "Store list").

General Store and Finished Goods Store stay the addresses every request
uses; the real stores are their sub-locations, so existing requests keep
working (Odoo reserves from sub-locations) while stock lands where the store
keepers look for it. Putaway rules send each product to its store.
"""

from odoo import api, models

# xmlid, name, parent xmlid
STORES = [
    ('loc_store_packing', 'Packing Materials Store', 'loc_store'),
    ('loc_store_ingredients', 'Ingredients Store', 'loc_store'),
    ('loc_store_spares', 'Spare Parts & Supplies Store', 'loc_store'),
    ('loc_store_byproduct', 'By-product Store', 'loc_store'),
    ('loc_fg_pasta', 'Pasta & Macaroni Store', 'loc_finished'),
    ('loc_fg_biscuit', 'Biscuit Store', 'loc_finished'),
    ('loc_fg_bread', 'Bread Store', 'loc_finished'),
]

# store xmlid -> (address the stock arrives at, products)
ROUTING = {
    'loc_store_ingredients': ('stock', ['product_sugar', 'product_shortening', 'product_abc', 'product_sbc',
                                        'product_sms', 'product_salt', 'product_citric', 'product_maize_flour']),
    'loc_store_packing': ('stock', ['product_zebib_film', 'product_defense_film', 'product_carton_78',
                                    'product_carton_160', 'product_scotch', 'product_pp_bag_10', 'product_pp_bag_25',
                                    'product_pp_bag_50', 'product_pp_bag_100', 'product_bag_thread']),
    'loc_store_byproduct': ('loc_store', ['product_rf', 'product_rc', 'product_pasta_breakage',
                                          'product_bread_breakage', 'product_biscuit_breakage']),
    'loc_fg_pasta': ('loc_finished', ['product_pasta_long', 'product_pasta_short']),
    'loc_fg_biscuit': ('loc_finished', ['product_zebib', 'product_defense']),
    'loc_fg_bread': ('loc_finished', ['product_bread_market', 'product_bread_university']),
}


class DdfscShift(models.Model):
    _inherit = 'ddfsc.shift'

    @api.model
    def _sync_store_structure(self):
        """Create the stores and their putaway rules once; never move existing stock."""
        for xmlid, name, parent in STORES:
            parent_location = self.env.ref('ddfsc_manufacturing.%s' % parent, raise_if_not_found=False)
            if parent_location:
                self._ensure_record(xmlid, 'stock.location', {
                    'name': name, 'location_id': parent_location.id, 'usage': 'internal',
                })
        stock = self.env.ref('stock.stock_location_stock')
        self._ensure_record('loc_transit_asama', 'stock.location', {
            'name': 'Asama Transit Store (Sabian)', 'location_id': stock.location_id.id or stock.id,
            'usage': 'internal',
        })
        # Spare parts used in maintenance leave stock here (cost of the request).
        self._ensure_record('loc_maintenance_use', 'stock.location', {
            'name': 'Maintenance Use', 'location_id': stock.location_id.id or stock.id,
            'usage': 'inventory',
        })
        Putaway = self.env['stock.putaway.rule'].with_context(active_test=False)
        for store_xmlid, (arrival, products) in ROUTING.items():
            store = self.env.ref('ddfsc_manufacturing.%s' % store_xmlid, raise_if_not_found=False)
            arrive_at = stock if arrival == 'stock' else self.env.ref('ddfsc_manufacturing.%s' % arrival)
            if not store:
                continue
            for product_xmlid in products:
                template = self.env.ref('ddfsc_manufacturing.%s' % product_xmlid, raise_if_not_found=False)
                if not template:
                    continue
                product = template.product_variant_id
                if Putaway.search_count([('location_in_id', '=', arrive_at.id), ('product_id', '=', product.id)]):
                    continue
                Putaway.create({
                    'location_in_id': arrive_at.id, 'location_out_id': store.id,
                    'product_id': product.id, 'company_id': self.env.company.id, 'sequence': 5,
                })
