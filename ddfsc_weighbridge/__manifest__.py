{
    "name": "DDFSC Weighbridge",
    "version": "19.0.1.0.0",
    "category": "Inventory/Operations",
    "summary": "Controlled weighbridge tickets for DDFSC receipts and dispatches",
    "description": """
DDFSC Weighbridge - Phase 1
===========================

Creates an auditable manual weighbridge workflow while the physical indicator
remains standalone.  Operators capture gross and tare weights, attach the
printed scale slip, and link the completed ticket to the appropriate stock
receipt or delivery.  The module deliberately does not validate stock moves,
post quantities, or release QC-controlled inventory.
    """,
    "author": "Dire Dawa Food Complex",
    "website": "https://github.com/AnexDev1/ddfsc",
    "license": "AGPL-3",
    "depends": ["mail", "purchase_stock", "ddfsc_manufacturing"],
    "data": [
        "security/ddfsc_weighbridge_security.xml",
        "security/ir.model.access.csv",
        "data/weighbridge_sequence.xml",
        "views/weighbridge_ticket_views.xml",
        "views/weighbridge_menus.xml",
    ],
    "installable": True,
    "application": True,
}
