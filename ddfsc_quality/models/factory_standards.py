"""Acceptance plans copied from the factory's signed QC forms (Issue No. 01, Feb 2026).

Each plan is created once, in Draft, so the factory Quality Manager reviews and
approves it like any other plan. After that the plan belongs to the QC team:
upgrades never change, re-create or re-approve it.
"""

from odoo import Command, _, api, models

# (min, max) — None means no limit on that side.
# Line: (check type, (min, max), unit / method, mandatory)
FACTORY_STANDARDS = [
    # OF/QC/015 Wheat physical characteristics at receiving
    ('qc_std_wheat_imported_hard', 'Wheat at Receiving – Imported Hard Wheat (OF/QC/015)',
     'incoming_wheat', ['product_wheat'], 'imported_hard', [
         ('hlw', (80, None), 'kg/hl', True),
         ('moisture', (None, 12), '%', True),
         ('impurity', (None, 6), '%', True),
         ('protein', (12, None), '% at 11 % moisture', True),
         ('hardness', (80, None), '% hard kernels (hard to soft ratio)', True),
     ]),
    ('qc_std_wheat_local_white_hard', 'Wheat at Receiving – Local White Hard Wheat (OF/QC/015)',
     'incoming_wheat', ['product_wheat'], 'local_white_hard', [
         ('hlw', (78, None), 'kg/hl', True),
         ('moisture', (None, 12), '%', True),
         ('impurity', (None, 8), '%', True),
     ]),
    ('qc_std_wheat_local_red_mixed', 'Wheat at Receiving – Local Red Mixed Wheat (OF/QC/015)',
     'incoming_wheat', ['product_wheat'], 'local_red_mixed', [
         ('hlw', (75, None), 'kg/hl', True),
         ('moisture', (None, 12), '%', True),
         ('impurity', (None, 10), '%', True),
     ]),
    # OF/QC/003 Flour transfer report — ash is a laboratory test that is not
    # on the transfer results table, so it is recorded but not required.
    ('qc_std_flour_spaghetti', 'Flour Release – Spaghetti / Long Cut Pasta (OF/QC/003)',
     'flour_release', ['product_flour_lcp'], False, [
         ('moisture', (None, 15.5), '%', True),
         ('gluten', (36, None), '% wet gluten', True),
         ('granulation', (56, 63), '% through 106 µm sieve', True),
         ('ash', (None, 0.55), '%', False),
     ]),
    ('qc_std_flour_macaroni', 'Flour Release – Macaroni / Short Cut Pasta (OF/QC/003)',
     'flour_release', ['product_flour_scp'], False, [
         ('moisture', (None, 15.5), '%', True),
         ('gluten', (30, None), '% wet gluten', True),
         ('granulation', (56, 65), '% through 106 µm sieve', True),
         ('ash', (None, 0.6), '%', False),
     ]),
    ('qc_std_flour_biscuit', 'Flour Release – Biscuit Flour, Grade 2 (OF/QC/003)',
     'flour_release', ['product_flour_g2'], False, [
         ('moisture', (None, 15.5), '%', True),
         ('gluten', (25, None), '% wet gluten', True),
         ('granulation', (58, 75), '% through 106 µm sieve', True),
         ('ash', (None, 0.7), '%', False),
     ]),
    ('qc_std_flour_bread', 'Flour Release – Bread Flour, Grade 1 (OF/QC/003)',
     'flour_release', ['product_flour_g1'], False, [
         ('moisture', (None, 15.5), '%', True),
         ('gluten', (26, None), '% wet gluten', True),
         ('granulation', (58, 73), '% through 106 µm sieve', True),
         ('ash', (None, 0.65), '%', False),
     ]),
    # OF/QC/001 Biscuit production follow-up
    ('qc_std_biscuit_new_zebib', 'Biscuit Release – New Zebib (OF/QC/001)',
     'finished_goods', ['product_zebib'], False, [
         ('dry_weight', (10.0, 10.5), 'g per piece', True),
         ('moisture', (None, 8), '% dry biscuit', True),
     ]),
    ('qc_std_biscuit_defense', 'Biscuit Release – Defense Biscuit (OF/QC/001)',
     'finished_goods', ['product_defense'], False, [
         ('dry_weight', (27, 28), 'g per piece', True),
         ('moisture', (None, 10), '% dry biscuit', True),
     ]),
    # OF/QC/002 Bread baking analysis — weighed 30 minutes after the oven
    ('qc_std_bread_market', 'Bread Release – Market Bread 100 g (OF/QC/002)',
     'finished_goods', ['product_bread_market'], False, [
         ('weight', (95, 105), 'g baked weight, 30 min after oven', True),
     ]),
    ('qc_std_bread_university', 'Bread Release – University Bread 120 g (OF/QC/002)',
     'finished_goods', ['product_bread_university'], False, [
         ('weight', (114, 126), 'g baked weight, 30 min after oven', True),
     ]),
    # OF/QC/010 packing weight and OF/QC/009 packing moisture. Packing
    # moisture depends on the die; these are the limits for the main dies.
    ('qc_std_pasta_long', 'Pasta Release – Long Cut Pasta 500 g (OF/QC/009, OF/QC/010)',
     'finished_goods', ['product_pasta_long'], False, [
         ('weight', (495, 505), 'g per pack', True),
         ('moisture', (None, 12), '% at packing (die 96057)', True),
     ]),
    ('qc_std_pasta_short', 'Pasta Release – Short Cut Pasta 500 g (OF/QC/009, OF/QC/010)',
     'finished_goods', ['product_pasta_short'], False, [
         ('weight', (495, 505), 'g per pack', True),
         ('moisture', (None, 13), '% at packing (most dies; check the die limit)', True),
     ]),
]

# The placeholder plans older versions created. Only these exact plans are
# archived, and only while they are still unapproved demo drafts.
DEMO_PLAN_NAMES = (
    'Incoming Wheat - DEMO limits',
    'Produced Flour - DEMO limits',
    'Finished Products - DEMO limits',
)


class DdfscQualityPlan(models.Model):
    _inherit = "ddfsc.quality.plan"

    @api.model
    def _sync_factory_standards(self):
        created = self.browse()
        for xmlid, name, checkpoint, product_xmlids, wheat_type, lines in FACTORY_STANDARDS:
            if self.env['ir.model.data'].search_count([
                    ('module', '=', 'ddfsc_quality'), ('name', '=', xmlid)]):
                continue
            products = self.env['product.product']
            for product_xmlid in product_xmlids:
                template = self.env.ref('ddfsc_manufacturing.%s' % product_xmlid, raise_if_not_found=False)
                if template:
                    products |= template.product_variant_id
            if not products:
                continue
            plan = self.create({
                'name': name,
                'checkpoint': checkpoint,
                'product_ids': [Command.set(products.ids)],
                'wheat_type': wheat_type,
                'demo_specification': False,
                'version': '1.0',
                'line_ids': [Command.create({
                    'sequence': index * 10,
                    'check_type': check_type,
                    'apply_min': minimum is not None,
                    'standard_min': minimum or 0.0,
                    'apply_max': maximum is not None,
                    'standard_max': maximum or 0.0,
                    'note': note,
                    'mandatory': mandatory,
                    'result_type': 'numeric',
                }) for index, (check_type, (minimum, maximum), note, mandatory) in enumerate(lines, 1)],
            })
            self.env['ir.model.data'].create({
                'module': 'ddfsc_quality', 'name': xmlid, 'model': self._name,
                'res_id': plan.id, 'noupdate': True,
            })
            created |= plan
        if created:
            self._retire_demo_plans(created)
        return created

    def _retire_demo_plans(self, factory_plans):
        demo_plans = self.search([
            ('name', 'in', DEMO_PLAN_NAMES),
            ('demo_specification', '=', True),
            ('approval_state', '=', 'draft'),
        ])
        for plan in demo_plans:
            plan.message_post(body=_(
                "Archived: replaced by the factory standards from the signed QC forms "
                "(see the Draft plans awaiting Quality Manager approval)."
            ))
        demo_plans.write({'active': False})
