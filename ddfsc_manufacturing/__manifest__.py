{
    'name': 'DDFSC Manufacturing',
    'version': '19.0.1.5.0',
    'category': 'Manufacturing',
    'summary': 'Shift production, quality hold, and Dire Dawa Food Complex master data',
    'description': """
Dire Dawa Food Complex manufacturing on Odoo 19 Community.
Covers three shifts, conditioning, downtime, lot quality hold and release,
and the plant locations, products, and starter recipes.
    """,
    'author': 'DDFSC',
    'license': 'LGPL-3',
    'depends': ['mrp', 'stock', 'maintenance', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'data/shift_data.xml',
        'data/plant_data.xml',
        'data/recipes_data.xml',
        'data/transfer_data.xml',
        'data/maintenance_data.xml',
        'views/ddfsc_shift_views.xml',
        'views/mrp_production_views.xml',
        'views/stock_lot_views.xml',
        'views/quality_check_views.xml',
        'views/quality_report_views.xml',
        'views/ddfsc_transfer_views.xml',
    ],
    'installable': True,
    'application': False,
}
