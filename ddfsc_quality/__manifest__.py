{
    "name": "DDFSC Quality Management",
    "version": "19.0.2.0.0",
    "category": "Quality Control",
    "summary": "Standalone quality control workspace for DDFSC",
    "description": """
Standalone quality management application for Dire Dawa Food Complex.

The module combines the OCA quality inspection engine with DDFSC's lot-based
quarantine and release controls for incoming wheat, flour, and finished goods.
It deliberately keeps the factory's blocking rules: controlled stock cannot
leave a quarantine or temporary-finished location until its lot passes QC or a
manager records an authorised exception.
    """,
    "author": "DDFSC, Odoo Community Association (OCA)",
    "website": "https://github.com/AnexDev1/ddfsc",
    "license": "AGPL-3",
    "depends": ["quality_control_oca", "ddfsc_manufacturing"],
    "data": [
        "data/quality_data.xml",
        "security/ddfsc_quality_security.xml",
        "security/ir.model.access.csv",
        "views/qc_inspection_document_views.xml",
        "views/quality_workspace_views.xml",
        "views/quality_governance_views.xml",
        "views/nonconformance_views.xml",
        "reports/quality_certificate.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ddfsc_quality/static/src/js/quality_dashboard.js",
            "ddfsc_quality/static/src/xml/quality_dashboard.xml",
            "ddfsc_quality/static/src/scss/quality_dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
    "post_init_hook": "post_init_hook",
}
