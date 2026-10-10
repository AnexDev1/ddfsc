from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_order_source = fields.Boolean(
        related='company_id.enable_order_source',
        readonly=False,
        string="Enable Order Source"
    )

    credit_invoice_notification_user_id = fields.Many2one(
        related='company_id.credit_invoice_notification_user_id',
        readonly=False,
        string="Credit Invoice Notification User"
    )


    use_so_manual_sequence_limit = fields.Boolean(
        related='company_id.use_so_manual_sequence_limit',
        readonly=False,
        string="Use Sales Order Manual Sequence Limit"
    )

    so_manual_sequence_limit = fields.Integer(
        related='company_id.so_manual_sequence_limit',
        readonly=False,
        string="Sales Order Last Manual Limit"
    )

    group_allow_manual_discount = fields.Boolean(

        string="Enable Manual Discounts",
        implied_group='sale_approval_workflow.group_allow_manual_discount'
    )
