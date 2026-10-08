{
    'name': 'DDFSC Manufacturing',
    'version': '19.0.2.4.0',
    'category': 'Manufacturing',
    'summary': 'Production, shift reports, quality, and store transfer requests',
    'description': """
Dire Dawa Food Complex manufacturing on Odoo 19 Community.
Manufacturing owns production orders, shift reports, quality hold/release, and
recipes. Departments raise Store Transfer Requests (destination, request date,
product details). Submit to Manager, approve to create an inventory internal
transfer, then mark received when the picking is validated.
    """,
    'author': 'DDFSC',
    'license': 'LGPL-3',
    'depends': ['mrp', 'stock', 'maintenance'],
    'data': [
        'security/ddfsc_groups.xml',
        'security/ir.model.access.csv',
        'security/ddfsc_rules.xml',
        'data/shift_data.xml',
        'data/plant_data.xml',
        'data/recipes_data.xml',
        'data/maintenance_data.xml',
        'data/store_request_data.xml',
        'views/ddfsc_shift_views.xml',
        'views/mrp_production_views.xml',
        'views/stock_lot_views.xml',
        'views/quality_check_views.xml',
        'views/quality_report_views.xml',
        'views/plant_flow_views.xml',
        'views/department_views.xml',
        'views/product_views.xml',
    ],
    'installable': True,
    'application': False,
}
