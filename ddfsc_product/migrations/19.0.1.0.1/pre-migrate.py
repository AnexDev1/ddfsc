# -*- coding: utf-8 -*-
"""Remap legacy customer_type keys ('retail'/'wholesale') to the current
ones ('retailer'/'wholesaler'). Stale values break record copies (e.g.
duplicating a user) with "Wrong value for res.partner.customer_type"."""


def migrate(cr, version):
    cr.execute("""
        UPDATE res_partner
           SET customer_type = CASE customer_type
                                   WHEN 'wholesale' THEN 'wholesaler'
                                   WHEN 'retail' THEN 'retailer'
                               END
         WHERE customer_type IN ('wholesale', 'retail')
    """)
