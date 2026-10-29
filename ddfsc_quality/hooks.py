from odoo import fields


def post_init_hook(env):
    """Adopt pre-existing QC data without putting released stock back on hold."""
    lots = env["stock.lot"].search([("quality_check_ids", "!=", False)])
    lots.filtered(lambda lot: lot.ddfsc_quality_state in ("pass", "released")).write({"ddfsc_review_state": "approved"})
    lots.filtered(lambda lot: lot.ddfsc_quality_state == "rejected").write({"ddfsc_review_state": "rejected"})
