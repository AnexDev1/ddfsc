from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Turn each saved downtime entry into a stoppage line."""
    cr.execute("SELECT to_regclass('ddfsc_downtime_migration')")
    if not cr.fetchone()[0]:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    reasons = dict(env['ddfsc.production.downtime']._fields['reason'].selection)
    cr.execute("SELECT production_id, hours, reason FROM ddfsc_downtime_migration")
    values = [{
        'production_id': production_id,
        'hours': min(hours, 24.0),
        'reason': reason if reason in reasons else 'other',
    } for production_id, hours, reason in cr.fetchall()]
    if values:
        env['ddfsc.production.downtime'].create(values)
    cr.execute("DROP TABLE ddfsc_downtime_migration")
