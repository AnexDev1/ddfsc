{
    "name": "DDFSC Payroll Components",
    "version": "19.0.1.0.0",
    "summary": "Effective-dated recurring and one-off payroll components",
    "category": "Payroll",
    "license": "LGPL-3",
    "author": "DDFSC",
    "depends": ["payroll", "payroll_account", "ddfsc_hr_attendance"],
    "data": [
        "security/ir.model.access.csv",
        "security/ddfsc_payroll_security.xml",
        "views/payroll_component_type_views.xml",
        "views/employee_payroll_component_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_payslip_views.xml",
        "views/menus.xml",
    ],
    "application": False,
    "installable": True,
}

