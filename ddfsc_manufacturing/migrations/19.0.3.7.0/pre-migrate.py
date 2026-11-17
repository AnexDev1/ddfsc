def migrate(cr, version):
    """Keep each order's single downtime entry before it becomes a computed total."""
    cr.execute("""
        CREATE TABLE IF NOT EXISTS ddfsc_downtime_migration AS
        SELECT id AS production_id, downtime_hours AS hours, downtime_reason AS reason
          FROM mrp_production
         WHERE COALESCE(downtime_hours, 0) > 0
    """)
