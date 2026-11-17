from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bread is released without QC: switch it off and retire its open draft inspections."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    templates = env["product.template"]
    for xmlid in ("product_bread_market", "product_bread_university"):
        template = env.ref("ddfsc_manufacturing.%s" % xmlid, raise_if_not_found=False)
        if template:
            templates |= template
    if not templates:
        return
    templates.write({"ddfsc_qc_required": False})
    lots = env["stock.lot"].search([("product_id", "in", templates.product_variant_ids.ids)])
    lots._compute_quality_plan()
    if not lots:
        return
    # The QC module loads after this one, so its tables are handled in SQL.
    cr.execute("SELECT to_regclass('ddfsc_qc_inspection')")
    if cr.fetchone()[0]:
        cr.execute(
            "UPDATE ddfsc_qc_inspection SET state = 'superseded' WHERE state = 'draft' AND lot_id IN %s",
            (tuple(lots.ids),))
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'stock_lot' AND column_name = 'active_qc_inspection_id'
        """)
        if cr.fetchone():
            cr.execute("UPDATE stock_lot SET active_qc_inspection_id = NULL WHERE id IN %s", (tuple(lots.ids),))
