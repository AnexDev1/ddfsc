from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.ddfsc_product.models.res_company import merge_analytic_distribution


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    state = fields.Selection(
        selection_add=[
            ('to_approve', 'Waiting Quotation Approval'),
            ('to_approve_discount', 'Waiting Discount Approval'),
            ('sale',),
        ],
        ondelete={
            'to_approve': 'set default',
            'to_approve_discount': 'set default',
        },
    )
    quotation_approver_id = fields.Many2one(
        'res.users',
        string='Quotation Approved By',
        copy=False,
        readonly=True,
        tracking=True,
        help="Manager or GM who approved the quotation.",
    )
    quotation_approval_date = fields.Datetime(
        string='Quotation Approval Date',
        copy=False,
        readonly=True,
        tracking=True,
    )
    discount_approver_id = fields.Many2one(
        'res.users',
        string='Discount Approved By',
        copy=False,
        readonly=True,
        tracking=True,
        help="Manager or GM who approved the discount.",
    )
    discount_approval_date = fields.Datetime(
        string='Discount Approval Date',
        copy=False,
        readonly=True,
        tracking=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        copy=False,
        readonly=True,
        tracking=True,
        help="Manager who approved this sales order.",
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        copy=False,
        readonly=True,
        tracking=True,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        copy=False,
        readonly=True,
        tracking=True,
        help="Reason provided by the manager when rejecting this order.",
    )
    branch_plan_id = fields.Many2one(
        'account.analytic.plan',
        string='Branch Plan',
        compute='_compute_branch_plan_id',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Branch',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('plan_id', '=?', branch_plan_id)]",
        check_company=True,
        copy=False,
        help="Branch cost center / analytic account for this order.",
    )

    @api.depends('company_id')
    def _compute_branch_plan_id(self):
        for order in self:
            company = order.company_id or self.env.company
            order.branch_plan_id = company.get_branch_analytic_plan()
    payment_proof = fields.Binary(
        string='Payment Proof / Receipt',
        attachment=True,
        copy=False,
        help="Upload payment screenshot, bank transfer slip, Telebirr/CBE Birr confirmation, or receipt.",
    )
    payment_proof_filename = fields.Char(string='Payment Proof Filename', copy=False)
    payment_note = fields.Char(
        string='Payment Note / Reference',
        copy=False,
        help="Add notes about the payment, e.g. Transaction ID, bank deposit reference, Telebirr/CBE Birr confirmation code, etc.",
    )
    sale_type = fields.Selection([
        ('cash', 'Cash Sale'),
        ('credit', 'Credit Sale'),
    ], string='Sale Type', default='cash', required=True, tracking=True,
       help="Specifies whether this order is a Cash Sale (requiring payment proof/reference) or a Credit Sale (subject to customer credit checks).")
    partner_credit_status = fields.Selection(
        related='partner_id.credit_status',
        string='Customer Credit Status',
        readonly=True,
    )
    apply_order_discount = fields.Boolean(
        string='Order Discount',
        default=False,
        tracking=True,
        help="Check to apply a global discount across all products.",
    )
    order_discount_percent = fields.Float(
        string='Discount (%)',
        default=0.0,
        digits=(16, 2),
        tracking=True,
        help="Global discount percentage applied to all products combined.",
    )
    order_discount_amount = fields.Monetary(
        string='Discount Amount',
        compute='_compute_order_discount_amount',
        currency_field='currency_id',
    )
    gross_amount_untaxed = fields.Monetary(
        string='Gross Subtotal',
        compute='_compute_order_discount_amount',
        currency_field='currency_id',
    )
    max_discount = fields.Float(
        string='Max Discount (%)',
        compute='_compute_discount_approval',
        store=True,
        tracking=True,
        help="Highest discount percentage given on this order (global or line-level).",
    )
    has_excessive_discount = fields.Boolean(
        string='Discount > 5%',
        compute='_compute_discount_approval',
        store=True,
        help="True if the global discount or any product line discount exceeds 5%.",
    )
    is_sales_approver = fields.Boolean(
        compute='_compute_is_sales_approver',
        string='Can Approve Sales',
    )
    is_sales_manager = fields.Boolean(
        compute='_compute_is_sales_approver',
        string='Is Sales Manager',
    )

    def _compute_is_sales_approver(self):
        user = self.env.user
        can_approve = (
            user.has_group('ddfsc_sale.group_sales_approver')
            or user.has_group('base.group_system')
        )
        for order in self:
            order.is_sales_approver = can_approve
            order.is_sales_manager = can_approve

    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.discount', 'order_line.price_subtotal', 'order_line.product_id')
    def _compute_discount_approval(self):
        for order in self:
            line_discounts = [
                line.discount for line in order.order_line
                if line.product_id and not line.display_type and not line.is_downpayment
            ]
            max_line_disc = max(line_discounts) if line_discounts else 0.0

            global_disc = order.order_discount_percent if order.apply_order_discount else 0.0
            eff_max = max(global_disc, max_line_disc)
            order.max_discount = eff_max
            order.has_excessive_discount = eff_max > 5.0

    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.price_subtotal')
    def _compute_order_discount_amount(self):
        for order in self:
            regular_lines = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)
            gross = sum(regular_lines.mapped('price_subtotal'))
            order.gross_amount_untaxed = gross
            if order.apply_order_discount and order.order_discount_percent > 0:
                order.order_discount_amount = -round(gross * (order.order_discount_percent / 100.0), 2)
            else:
                order.order_discount_amount = 0.0

    apply_withholding_tax = fields.Boolean(
        string='Withholding Tax',
        default=False,
        tracking=True,
        help="Turn on when withholding tax is required on this quotation/order.",
    )
    withholding_tax_threshold = fields.Float(
        related='company_id.sale_withholding_tax_threshold',
        string='Withholding Tax Threshold',
        readonly=True,
    )
    withholding_tax_amount = fields.Monetary(
        string='Withholding Tax Amount',
        compute='_compute_withholding_tax_amount',
        currency_field='currency_id',
    )

    @api.depends('order_line.tax_ids', 'order_line.price_subtotal', 'apply_withholding_tax')
    def _compute_withholding_tax_amount(self):
        for order in self:
            wh_tax = order._get_or_create_withholding_tax()
            total_wh = 0.0
            if wh_tax:
                for line in order.order_line:
                    if wh_tax in line.tax_ids:
                        total_wh += round(line.price_subtotal * (wh_tax.amount / 100.0), 2)
            order.withholding_tax_amount = total_wh

    def _get_or_create_withholding_tax(self):
        self.ensure_one()
        wh_tax = self.company_id.sale_withholding_tax_id
        if not wh_tax:
            wh_tax = self.env['account.tax'].search([
                ('name', '=', '2% WH'),
                ('type_tax_use', '=', 'sale'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
        return wh_tax

    def _should_apply_automatic_withholding_tax(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        threshold = company.sale_withholding_tax_threshold or 0.0
        return bool(
            company.enable_sale_withholding_tax
            and self._get_or_create_withholding_tax()
            and self.amount_untaxed >= threshold
        )

    def _sync_automatic_withholding_tax(self):
        for order in self:
            should_apply = order._should_apply_automatic_withholding_tax()
            if order.apply_withholding_tax != should_apply:
                order.apply_withholding_tax = should_apply
            order._update_withholding_taxes_on_lines()

    def _update_withholding_taxes_on_lines(self):
        for order in self:
            wh_tax = order._get_or_create_withholding_tax()
            if not wh_tax:
                continue
            wh_tax_id = wh_tax.id
            for line in order.order_line:
                if line.display_type or line.is_downpayment:
                    continue
                has_wh = any((t._origin.id or t.id) == wh_tax_id for t in line.tax_ids)
                if order.apply_withholding_tax:
                    if not has_wh:
                        line.tax_ids = line.tax_ids | wh_tax
                else:
                    if has_wh:
                        line.tax_ids = line.tax_ids.filtered(lambda t: (t._origin.id or t.id) != wh_tax_id)

    @api.onchange('apply_withholding_tax')
    def _onchange_apply_withholding_tax(self):
        self._update_withholding_taxes_on_lines()

    @api.onchange('order_line')
    def _onchange_order_line_withholding_tax(self):
        self._sync_automatic_withholding_tax()

    @api.onchange('apply_order_discount')
    def _onchange_apply_order_discount(self):
        if not self.apply_order_discount:
            self.order_discount_percent = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        if not (
            self.env.user.has_group('ddfsc_sale.group_sales_initiator')
            or self.env.user.has_group('base.group_system')
            or self.env.context.get('install_mode')
        ):
            raise UserError(_("Only users with the Sales: Initiator role can create quotations."))
        orders = super().create(vals_list)
        if not self.env.context.get('skip_automatic_withholding_sync'):
            orders._sync_automatic_withholding_tax()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'apply_order_discount' in vals or 'order_discount_percent' in vals:
            for order in self:
                order._apply_global_discount()
        if not self.env.context.get('skip_automatic_withholding_sync') and (
            'order_line' in vals or 'company_id' in vals
        ):
            self.with_context(skip_automatic_withholding_sync=True)._sync_automatic_withholding_tax()
        return res

    def _get_or_create_discount_product(self):
        company = self.company_id or self.env.company
        discount_product = company.sale_discount_product_id
        if not discount_product:
            discount_product = self.env['product.product'].search([('default_code', '=', 'DISC')], limit=1)
            if not discount_product:
                discount_product = self.env['product.product'].create({
                    'name': 'Discount',
                    'type': 'service',
                    'default_code': 'DISC',
                    'invoice_policy': 'order',
                    'list_price': 0.0,
                    'company_id': company.id,
                })
            company.sale_discount_product_id = discount_product
        return discount_product

    def action_apply_global_discount(self):
        for order in self:
            order._apply_global_discount()

    def action_remove_global_discount(self):
        for order in self:
            order.apply_order_discount = False
            order.order_discount_percent = 0.0
            order._apply_global_discount()

    def _apply_global_discount(self):
        # In Option B, clean up any discount products from order lines table
        for order in self:
            disc_lines = order.order_line.filtered(
                lambda l: (l.product_id and l.product_id.default_code == 'DISC') or getattr(l, 'is_discount_line', False) or l.price_unit < 0
            )
            if disc_lines:
                disc_lines.unlink()

    @api.depends_context('lang')
    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.price_subtotal', 'currency_id', 'company_id', 'payment_term_id')
    def _compute_tax_totals(self):
        AccountTax = self.env['account.tax']
        for order in self:
            base_lines = order._get_net_price_tax_base_lines()
            base_lines += order._add_base_lines_for_early_payment_discount()

            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            order.tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_id.currency_id,
                company=order.company_id,
            )

    @api.depends('apply_order_discount', 'order_discount_percent', 'order_line.price_subtotal')
    def _compute_amounts(self):
        AccountTax = self.env['account.tax']
        for order in self:
            base_lines = order._get_net_price_tax_base_lines()
            base_lines += order._add_base_lines_for_early_payment_discount()

            AccountTax._add_tax_details_in_base_lines(base_lines, order.company_id)
            AccountTax._round_base_lines_tax_details(base_lines, order.company_id)
            tax_totals = AccountTax._get_tax_totals_summary(
                base_lines=base_lines,
                currency=order.currency_id or order.company_id.currency_id,
                company=order.company_id,
            )
            order.amount_untaxed = tax_totals['base_amount_currency']
            order.amount_tax = tax_totals['tax_amount_currency']
            order.amount_total = tax_totals['total_amount_currency']

    def _get_net_price_tax_base_lines(self):
        """Build sales tax bases exactly like the generated net-price invoice."""
        self.ensure_one()
        order_discount = self.order_discount_percent if self.apply_order_discount else 0.0
        base_lines = []
        for line in self._get_priced_lines():
            line_discount = line.discount or 0.0
            combined_discount = 100.0 * (
                1.0 - (1.0 - line_discount / 100.0) * (1.0 - order_discount / 100.0)
            )
            net_price = self.currency_id.round(
                line.price_unit * (1.0 - combined_discount / 100.0)
            )
            base_lines.append(line._prepare_base_line_for_taxes_computation(
                price_unit=net_price,
                discount=0.0,
            ))
        return base_lines

    @api.onchange('payment_term_id')
    def _onchange_payment_term_id_sale_type(self):
        if self.payment_term_id:
            has_credit = False
            if hasattr(self.payment_term_id, 'line_ids'):
                for line in self.payment_term_id.line_ids:
                    if (getattr(line, 'nb_days', 0) or 0) > 0 or getattr(line, 'delay_type', '') != 'days_after':
                        has_credit = True
                        break
            self.sale_type = 'credit' if has_credit else 'cash'

    def action_submit_approval(self):
        if not (
            self.env.user.has_group('ddfsc_sale.group_sales_initiator')
            or self.env.user.has_group('base.group_system')
        ):
            raise UserError(_("Only users with the Sales: Initiator role can submit quotations for approval."))
        for order in self:
            order._check_customer_is_not_own_company()
            if not order.order_line:
                raise UserError(_("You cannot submit an empty quotation for approval. Please add products first."))
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            if order.sale_type == 'credit':
                partner = order.partner_id
                if partner and getattr(partner, 'credit_status', False) == 'blocked':
                    due_amt = getattr(partner, 'due_amount', 0.0)
                    limit = getattr(partner, 'blocking_stage', 0.0)
                    raise UserError(_(
                        "Customer '%s' has a BLOCKED credit status (Due: %.2f, Blocking limit: %.2f). "
                        "Credit sales cannot be submitted for this customer."
                    ) % (partner.name, due_amt, limit))
            order.write({
                'state': 'to_approve',
                'rejection_reason': False,
            })
            order.message_post(
                body=_("Quotation submitted for approval by %s.") % self.env.user.name,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

    def action_approve_quotation(self):
        for order in self:
            order._check_customer_is_not_own_company()
            if not order.is_sales_approver:
                raise UserError(_("Only users with the Sales: Approver role can approve quotations."))
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            if order.sale_type == 'credit':
                partner = order.partner_id
                if partner and getattr(partner, 'credit_status', False) == 'blocked':
                    raise UserError(_(
                        "Customer '%s' has a BLOCKED credit status. Credit sales cannot be approved."
                    ) % partner.name)
            now = fields.Datetime.now()
            vals = {
                'quotation_approver_id': self.env.user.id,
                'quotation_approval_date': now,
                'approver_id': self.env.user.id,
                'approval_date': now,
                'rejection_reason': False,
            }

            if order.has_excessive_discount:
                vals['state'] = 'to_approve_discount'
                order.write(vals)
                order.message_post(
                    body=Markup(
                        "<b>Quotation Approved</b> by %s.<br/>"
                        "⚠️ <b>Discount Approval Required:</b> Order has a discount of %.2f%% (&gt; 5.0%%). Awaiting Discount Approval."
                    ) % (self.env.user.name, order.max_discount),
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
            else:
                order.write(vals)
                order.message_post(
                    body=Markup("<b>Quotation Approved</b> by %s.") % self.env.user.name,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
                order.action_confirm()

    def action_approve(self):
        # Backward compatibility alias
        return self.action_approve_quotation()

    def action_approve_discount(self):
        for order in self:
            order._check_customer_is_not_own_company()
            if not order.is_sales_approver:
                raise UserError(_("Only users with the Sales: Approver role can approve discounts."))
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            now = fields.Datetime.now()
            order.write({
                'discount_approver_id': self.env.user.id,
                'discount_approval_date': now,
                'approver_id': self.env.user.id,
                'approval_date': now,
                'rejection_reason': False,
            })
            order.message_post(
                body=Markup(
                    "<b>Discount Approved (%.2f%%)</b> by %s.<br/>"
                    "Order is now confirmed."
                ) % (order.max_discount, self.env.user.name),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            order.action_confirm()

    def action_reject_wizard(self):
        self.ensure_one()
        if not self.is_sales_approver:
            raise UserError(_("Only users with the Sales: Approver role can reject sales orders."))
        return {
            'name': _('Reject Sales Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _confirmation_error_message(self):
        self.ensure_one()
        if self.state in ('to_approve', 'to_approve_discount'):
            if any(
                not line.display_type
                and not line.is_downpayment
                and not line.product_id
                for line in self.order_line
            ):
                return _("Some order lines are missing a product, you need to correct them before going further.")
            return False
        return super()._confirmation_error_message()

    def action_confirm(self):
        for order in self:
            order._check_customer_is_not_own_company()
            if order.order_discount_percent > 0:
                order._apply_global_discount()
            if order.sale_type == 'credit' and order.partner_id and getattr(order.partner_id, 'credit_status', False) == 'blocked':
                raise UserError(_("Customer '%s' has a BLOCKED credit status. Credit sales cannot be confirmed.") % order.partner_id.name)
            # If salesperson tries to confirm directly in draft or sent
            if not order.is_sales_approver and order.state in ('draft', 'sent'):
                raise UserError(_(
                    "Salespeople cannot confirm quotations directly. Please click 'Submit for Approval' to request Manager/GM approval."
                ))
            if order.state == 'to_approve' and not order.is_sales_approver:
                raise UserError(_("This order is awaiting Quotation Approval by a Manager or General Manager."))
            if order.state == 'to_approve_discount' and not order.is_sales_approver:
                raise UserError(_("This order is awaiting Discount Approval by a Manager or General Manager."))
        return super().action_confirm()

    def _check_customer_is_not_own_company(self):
        for order in self:
            if order.partner_id.commercial_partner_id == order.company_id.partner_id.commercial_partner_id:
                raise UserError(_(
                    "You cannot create a customer sale to your own company (%s). "
                    "Select the actual customer. For stock movement between company warehouses, "
                    "use an internal/location transfer instead."
                ) % order.company_id.display_name)

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        if hasattr(self, 'sale_type') and self.sale_type:
            invoice_vals['sale_type'] = self.sale_type
        if self.warehouse_id:
            invoice_vals['warehouse_id'] = self.warehouse_id.id

        return invoice_vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        if not (
            self.env.user.has_group('ddfsc_sale.group_sales_invoicer')
            or self.env.user.has_group('base.group_system')
        ):
            raise UserError(_("Only users with the Sales: Invoicer role can create sales invoices."))
        return super()._create_invoices(grouped=grouped, final=final, date=date)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company_id = res.get('company_id') or self.env.context.get('default_company_id') or self.env.company.id

        if 'warehouse_id' in fields_list:
            wh_id = res.get('warehouse_id')
            if wh_id:
                wh = self.env['stock.warehouse'].browse(wh_id)
                if wh.company_id.id != company_id:
                    res['warehouse_id'] = False

            if not res.get('warehouse_id'):
                user_wh = self.env.user.default_warehouse_id
                if user_wh and user_wh.company_id.id == company_id:
                    res['warehouse_id'] = user_wh.id
                else:
                    comp_whs = self.env.user.allowed_warehouse_ids.filtered(lambda w: w.company_id.id == company_id)
                    if comp_whs:
                        res['warehouse_id'] = comp_whs[0].id
                    else:
                        wh_found = self.env['stock.warehouse'].search([('company_id', '=', company_id)], limit=1)
                        res['warehouse_id'] = wh_found.id if wh_found else False

        if res.get('warehouse_id') and 'analytic_account_id' in fields_list and not res.get('analytic_account_id'):
            warehouse = self.env['stock.warehouse'].browse(res['warehouse_id'])
            if warehouse.analytic_account_id:
                if not warehouse.analytic_account_id.company_id or warehouse.analytic_account_id.company_id.id == company_id:
                    res['analytic_account_id'] = warehouse.analytic_account_id.id
                else:
                    res['warehouse_id'] = False
            else:
                res['warehouse_id'] = False
        return res

    @api.onchange('company_id')
    def _onchange_company_id_update_warehouse_and_branch(self):
        if self.company_id:
            if self.warehouse_id and self.warehouse_id.company_id != self.company_id:
                self.warehouse_id = False
            if self.analytic_account_id and self.analytic_account_id.company_id and self.analytic_account_id.company_id != self.company_id:
                self.analytic_account_id = False

    @api.constrains('warehouse_id', 'analytic_account_id')
    def _check_warehouse_branch(self):
        for order in self:
            if order.warehouse_id:
                if not order.analytic_account_id:
                    raise ValidationError(_("Please select a Branch before selecting a Warehouse."))
                if order.warehouse_id.analytic_account_id and order.warehouse_id.analytic_account_id != order.analytic_account_id:
                    raise ValidationError(_(
                        "The selected warehouse '%(warehouse)s' belongs to branch '%(wh_branch)s', "
                        "but the order branch is '%(order_branch)s'. Please select a warehouse belonging to the selected branch.",
                        warehouse=order.warehouse_id.display_name,
                        wh_branch=order.warehouse_id.analytic_account_id.display_name,
                        order_branch=order.analytic_account_id.display_name,
                    ))

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        if self.analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.analytic_account_id.id),
                ('company_id', '=', self.company_id.id)
            ])
            if self.warehouse_id and self.warehouse_id not in warehouses:
                self.warehouse_id = False
            if len(warehouses) == 1:
                self.warehouse_id = warehouses[0].id
            elif not warehouses:
                self.warehouse_id = False

            for line in self.order_line:
                if not line.display_type:
                    line.analytic_distribution = merge_analytic_distribution(
                        line.analytic_distribution,
                        self.analytic_account_id,
                        plan=self.branch_plan_id
                    )
        else:
            self.warehouse_id = False
            for line in self.order_line:
                if not line.display_type:
                    line.analytic_distribution = merge_analytic_distribution(
                        line.analytic_distribution,
                        plan=self.branch_plan_id,
                        remove_plan=True
                    )

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id_analytic(self):
        if self.warehouse_id and self.warehouse_id.analytic_account_id:
            self.analytic_account_id = self.warehouse_id.analytic_account_id.id

    @api.onchange('partner_id')
    def _onchange_partner_id_update_prices(self):
        for line in self.order_line:
            if line.product_id and not line.is_downpayment:
                line._reset_price_unit()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_discount_line = fields.Boolean(
        string='Is Discount Line',
        default=False,
        copy=False,
    )
    image_128 = fields.Image(
        string='Image',
        compute='_compute_product_images',
        store=False,
        readonly=True,
    )
    image_1920 = fields.Image(
        string='Full Image',
        compute='_compute_product_images',
        store=False,
        readonly=True,
    )

    @api.depends('product_id.image_1920', 'product_template_id.image_1920')
    def _compute_product_images(self):
        for line in self:
            line.image_1920 = (line.product_id and line.product_id.image_1920) or (line.product_template_id and line.product_template_id.image_1920) or False
            line.image_128 = (line.product_id and line.product_id.image_128) or (line.product_template_id and line.product_template_id.image_128) or False

    @api.onchange('product_id', 'product_template_id')
    def _onchange_product_images(self):
        self.image_1920 = (self.product_id and self.product_id.image_1920) or (self.product_template_id and self.product_template_id.image_1920) or False
        self.image_128 = (self.product_id and self.product_id.image_128) or (self.product_template_id and self.product_template_id.image_128) or False

    @api.onchange('tax_ids')
    def _onchange_tax_ids_sync_withholding(self):
        if self.order_id:
            self.order_id._onchange_order_line_withholding_tax()

    @api.onchange('product_id')
    def _onchange_product_id_set_analytic(self):
        dist = self.analytic_distribution or {}
        if self.order_id.analytic_account_id:
            dist = merge_analytic_distribution(dist, self.order_id.analytic_account_id, plan=self.order_id.branch_plan_id)
        if self.product_id and self.product_id.analytic_account_id:
            dist = merge_analytic_distribution(dist, self.product_id.analytic_account_id)
        self.analytic_distribution = dist
        if self.order_id.apply_withholding_tax:
            wh_tax = self.order_id._get_or_create_withholding_tax()
            if wh_tax and wh_tax not in self.tax_ids:
                self.tax_ids = self.tax_ids | wh_tax

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('display_type'):
                order_id = vals.get('order_id')
                product_id = vals.get('product_id')
                if order_id or product_id:
                    order = self.env['sale.order'].browse(order_id) if order_id else False
                    product = self.env['product.product'].browse(product_id) if product_id else False
                    dist = vals.get('analytic_distribution') or {}
                    if order and order.analytic_account_id:
                        dist = merge_analytic_distribution(dist, order.analytic_account_id, plan=order.branch_plan_id)
                    if product and product.analytic_account_id:
                        dist = merge_analytic_distribution(dist, product.analytic_account_id)
                    if dist:
                        vals['analytic_distribution'] = dist
        return super().create(vals_list)

    def _get_display_price_ignore_combo(self):
        self.ensure_one()
        partner = self.order_id.partner_id.commercial_partner_id or self.order_id.partner_id
        if partner and partner.customer_type == 'wholesaler' and self.product_id and self.product_id.wholesale_price > 0:
            price = self.product_id.wholesale_price
            if self.product_uom_id and self.product_id.uom_id and self.product_uom_id != self.product_id.uom_id:
                price = self.product_id.uom_id._compute_price(price, self.product_uom_id)
            return price
        return super()._get_display_price_ignore_combo()

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        order_discount = (
            self.order_id.order_discount_percent
            if self.order_id.apply_order_discount
            else 0.0
        )
        if not self.display_type and not self.is_downpayment:
            # Combine line and order discounts multiplicatively, then absorb
            # the result into the invoice unit price. The percentage remains
            # informational and is not posted as a separate discount.
            line_discount = self.discount or 0.0
            combined_discount = 100.0 * (
                1.0 - (1.0 - line_discount / 100.0) * (1.0 - order_discount / 100.0)
            )
            if combined_discount > 0:
                vals['price_unit'] = self.price_unit * (1.0 - combined_discount / 100.0)
                vals['discount'] = 0.0
                vals['applied_discount_percent'] = combined_discount
        return vals
