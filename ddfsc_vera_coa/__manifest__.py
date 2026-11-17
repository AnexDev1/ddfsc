{
    "name": "DDFSC Vera Chart of Accounts",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "summary": "Vera master chart of accounts and reporting dimensions",
    "author": "DDFSC",
    "license": "LGPL-3",
    "depends": ["account", "analytic", "stock_account", "mrp_account", "ddfsc_product"],
    "data": ["data/migration.xml"],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
