{
    'name': 'DDFSC Manufacturing',
    'version': '19.0.1.9.0',
    'category': 'Manufacturing',
    'summary': 'Shift production, with plant forms on purchase and inventory',
    'description': """
Dire Dawa Food Complex manufacturing on Odoo 19 Community.
Purchasing receives wheat and store materials. Inventory moves wheat into
silos, issues it to the mill, transfers flour, and receives finished goods.
The manufacturing order keeps the shift, conditioning, extraction, and a link
to those documents. The general manager approves wheat. The operation manager
approves store purchases, plant transfers, and the shift report.
    """,
    'author': 'DDFSC',
    'license': 'LGPL-3',
    'depends': ['mrp', 'stock', 'maintenance', 'purchase', 'purchase_stock'],
    'data': [
        'security/ddfsc_groups.xml',
        'security/ir.model.access.csv',
        'security/ddfsc_rules.xml',
        'data/shift_data.xml',
        'data/plant_data.xml',
        'data/recipes_data.xml',
        'data/transfer_data.xml',
        'data/maintenance_data.xml',
        'data/store_request_data.xml',
        'views/ddfsc_shift_views.xml',
        'views/mrp_production_views.xml',
        'views/stock_lot_views.xml',
        'views/quality_check_views.xml',
        'views/quality_report_views.xml',
        'views/plant_flow_views.xml',
        'views/department_views.xml',
    ],
    'installable': True,
    'application': False,
}
