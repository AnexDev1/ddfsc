from odoo import models, fields, api, _
from odoo.exceptions import UserError
from markupsafe import Markup

class LocalRFQ(models.Model):
    _name = 'local.rfq'
    _description = 'Local Request for Quotation / Comparison Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        tracking=True
    )
    date_rfq = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    committee_ids = fields.Many2many('hr.employee', string='Committee')
    for_pharmacy = fields.Boolean(string='For Pharmacy', default=False)
    requested_by = fields.Many2one(
        'res.users',
        string='Procurement Officer',
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True
    )
    
    # Link to Requisition
    requisition_id = fields.Many2one(
        'local.purchase.requisition',
        string='Purchase Requisition',
        required=True,
        readonly=True
    )

    # Vendor Management
    vendor_ids = fields.Many2many(
        'res.partner',
        string='Suppliers',
        domain=[('supplier_rank', '>', 0)]
    )
    
    # Comparison Logic
    winner_selection_method = fields.Selection([
        ('financial', 'Financial Only'),
        ('technical', 'Technical Only'),
        ('price', 'Lowest Price'),
        ('total', 'Total Score')
    ], string='Winner Selection Method', default='price')

    quote_ids = fields.One2many('local.rfq.quote', 'rfq_id', string='Comparison Sheet')
    
    # We remove the generic line_ids as they are now handled by quote_ids linked to PR lines
    # line_ids = fields.One2many(...) 

    po_ids = fields.One2many('purchase.order', 'local_rfq_id', string='Purchase Orders')
    po_count = fields.Integer(compute='_compute_po_count')
    
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True, tracking=True)
    
    # Renaming to committee_action_ids to match the new model, keeping 'approval_ids' as a legacy name if needed, but better to migrate. 
    # For now, let's keep the field name 'approval_ids' to avoid heavy refactoring if other modules depend on it, 
    # BUT update the relation to the new model.
    approval_ids = fields.One2many('local.rfq.committee.action', 'rfq_id', string='Committee Actions', readonly=True)
    
    committee_status_html = fields.Html(compute='_compute_committee_status_html', string='Committee Status')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('winner_picked', 'Winner Picked'),
        ('submitted', 'Commercial Dep\'t'),
        ('finance_approval', 'Finance'),
        ('production_approval', 'Production Head'),
        ('sales_purchase_approval', 'Sales & Purchase'),
        ('gm_approval', 'General Manager'),
        ('approved', 'Approved'),
        ('po_created', 'PO Created'),
        ('cancel', 'Cancelled'),
    ], default='draft', string="Status", tracking=True)

    # 5-step approval workflow fields
    commercial_approver_id = fields.Many2one('res.users', string='Commercial Approver', readonly=True, copy=False, tracking=True)
    commercial_approval_date = fields.Datetime(string='Commercial Approval Date', readonly=True, copy=False, tracking=True)

    finance_approver_id = fields.Many2one('res.users', string='Finance Approver', readonly=True, copy=False, tracking=True)
    finance_approval_date = fields.Datetime(string='Finance Approval Date', readonly=True, copy=False, tracking=True)

    production_approver_id = fields.Many2one('res.users', string='Production Head Approver', readonly=True, copy=False, tracking=True)
    production_approval_date = fields.Datetime(string='Production Head Approval Date', readonly=True, copy=False, tracking=True)

    sales_purchase_approver_id = fields.Many2one('res.users', string='Sales & Purchase Approver', readonly=True, copy=False, tracking=True)
    sales_purchase_approval_date = fields.Datetime(string='Sales & Purchase Approval Date', readonly=True, copy=False, tracking=True)

    gm_approver_id = fields.Many2one('res.users', string='General Manager Approver', readonly=True, copy=False, tracking=True)
    gm_approval_date = fields.Datetime(string='GM Approval Date', readonly=True, copy=False, tracking=True)

    rejected_by = fields.Many2one('res.users', string='Rejected By', readonly=True, copy=False, tracking=True)
    rejection_date = fields.Datetime(string='Rejection Date', readonly=True, copy=False, tracking=True)
    rejection_reason = fields.Text(string='Rejection Reason', copy=False, tracking=True)

    @api.depends('po_ids')
    def _compute_po_count(self):
        for rec in self:
            rec.po_count = len(rec.po_ids)

    @api.depends('quote_ids.selected', 'quote_ids.total_price')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.quote_ids.filtered(lambda q: q.selected).mapped('total_price'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company_id = vals.get('company_id') or self.env.company.id
                self._ensure_company_sequence(company_id)
                vals['name'] = self.env['ir.sequence'].with_company(company_id).next_by_code('local.rfq') or 'New'
        return super().create(vals_list)

    def _ensure_company_sequence(self, company_id):
        """Automatically create a separate sequence for a company if it doesn't exist."""
        Sequence = self.env['ir.sequence'].sudo()
        exists = Sequence.search([('code', '=', 'local.rfq'), ('company_id', '=', company_id)], limit=1)
        if not exists:
            template = Sequence.search([('code', '=', 'local.rfq'), ('company_id', '=', False)], limit=1)
            if template:
                template.copy({
                    'company_id': company_id,
                    'name': f"{template.name} ({self.env['res.company'].browse(company_id).name})"
                })

    def action_submit(self):
        self.ensure_one()
        selected_quotes = self.quote_ids.filtered(lambda q: q.selected)
        if not selected_quotes:
            raise UserError(_("Please select winning vendors in the Comparison Sheet before submitting."))
        self.write({'state': 'submitted'})
        self.message_post(body=_("Local RFQ submitted for Commercial Dep't approval by %s.") % self.env.user.name)
        self._notify_next_approver('submitted')

    def action_commercial_approve(self):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Commercial approval is only allowed in 'Commercial Dep't' approval state."))
        if not (self.env.user.has_group('procurement_local_rfq.group_local_rfq_commercial') or self.env.is_superuser()):
            raise UserError(_("Only Commercial Department members can approve at this step."))
        self.write({
            'state': 'finance_approval',
            'commercial_approver_id': self.env.user.id,
            'commercial_approval_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Approved by Commercial Dep't (%s). Waiting for Finance approval.") % self.env.user.name)
        self._notify_next_approver('finance_approval')

    def action_finance_approve(self):
        self.ensure_one()
        if self.state != 'finance_approval':
            raise UserError(_("Finance approval is only allowed in 'Finance' approval state."))
        if not (self.env.user.has_group('procurement_local_rfq.group_local_rfq_finance') or self.env.is_superuser()):
            raise UserError(_("Only Finance members can approve at this step."))
        self.write({
            'state': 'production_approval',
            'finance_approver_id': self.env.user.id,
            'finance_approval_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Approved by Finance (%s). Waiting for Production Head approval.") % self.env.user.name)
        self._notify_next_approver('production_approval')

    def action_production_approve(self):
        self.ensure_one()
        if self.state != 'production_approval':
            raise UserError(_("Production Head approval is only allowed in 'Production Head' approval state."))
        if not (self.env.user.has_group('procurement_local_rfq.group_local_rfq_production_head') or self.env.is_superuser()):
            raise UserError(_("Only Production Head can approve at this step."))
        self.write({
            'state': 'sales_purchase_approval',
            'production_approver_id': self.env.user.id,
            'production_approval_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Approved by Production Head (%s). Waiting for Sales & Purchase approval.") % self.env.user.name)
        self._notify_next_approver('sales_purchase_approval')

    def action_sales_purchase_approve(self):
        self.ensure_one()
        if self.state != 'sales_purchase_approval':
            raise UserError(_("Sales & Purchase approval is only allowed in 'Sales & Purchase' approval state."))
        if not (self.env.user.has_group('procurement_local_rfq.group_local_rfq_sales_purchase') or self.env.is_superuser()):
            raise UserError(_("Only Sales & Purchase members can approve at this step."))
        self.write({
            'state': 'gm_approval',
            'sales_purchase_approver_id': self.env.user.id,
            'sales_purchase_approval_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Approved by Sales & Purchase (%s). Waiting for General Manager approval.") % self.env.user.name)
        self._notify_next_approver('gm_approval')

    def action_gm_approve(self):
        self.ensure_one()
        if self.state != 'gm_approval':
            raise UserError(_("General Manager approval is only allowed in 'General Manager' approval state."))
        if not (self.env.user.has_group('procurement_local_rfq.group_local_rfq_general_manager') or self.env.is_superuser()):
            raise UserError(_("Only General Manager can approve at this step."))
        self.write({
            'state': 'approved',
            'gm_approver_id': self.env.user.id,
            'gm_approval_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Approved by General Manager (%s). Ready for PO creation.") % self.env.user.name)
        self._notify_next_approver('approved')

    def action_approve(self):
        self.ensure_one()
        if self.state == 'submitted':
            return self.action_commercial_approve()
        elif self.state == 'finance_approval':
            return self.action_finance_approve()
        elif self.state == 'production_approval':
            return self.action_production_approve()
        elif self.state == 'sales_purchase_approval':
            return self.action_sales_purchase_approve()
        elif self.state == 'gm_approval':
            return self.action_gm_approve()
        else:
            raise UserError(_("No approval step is pending for the current state (%s).") % self.state)

    def action_reject(self):
        self.ensure_one()
        self.write({
            'state': 'cancel',
            'rejected_by': self.env.user.id,
            'rejection_date': fields.Datetime.now(),
        })
        self.message_post(body=_("Rejected by %s.") % self.env.user.name)
        self._notify_next_approver('cancel')

    def action_cancel(self):
        return self.action_reject()

    def action_draft(self):
        self.ensure_one()
        self.write({
            'state': 'draft',
            'commercial_approver_id': False,
            'commercial_approval_date': False,
            'finance_approver_id': False,
            'finance_approval_date': False,
            'production_approver_id': False,
            'production_approval_date': False,
            'sales_purchase_approver_id': False,
            'sales_purchase_approval_date': False,
            'gm_approver_id': False,
            'gm_approval_date': False,
            'rejected_by': False,
            'rejection_date': False,
            'rejection_reason': False,
        })
        self.message_post(body=_("Reset to Draft by %s.") % self.env.user.name)
        self._notify_next_approver('draft')

    @api.depends('approval_ids', 'committee_ids', 'state')
    def _compute_committee_status_html(self):
        for rec in self:
            rec.committee_status_html = ""

    def _notify_next_approver(self, next_state):
        self.activity_unlink(['mail.mail_activity_data_todo'])

        requester_user = self.requested_by if self.requested_by else self.create_uid
        state_label = dict(self._fields['state'].selection).get(next_state, next_state)
        if requester_user:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=requester_user.id,
                summary=_("Local RFQ Update: %s") % self.name,
                note=_("Your local RFQ (%s) is now in state: %s.") % (self.name, state_label)
            )

        group_xmlid_map = {
            'submitted': 'procurement_local_rfq.group_local_rfq_commercial',
            'finance_approval': 'procurement_local_rfq.group_local_rfq_finance',
            'production_approval': 'procurement_local_rfq.group_local_rfq_production_head',
            'sales_purchase_approval': 'procurement_local_rfq.group_local_rfq_sales_purchase',
            'gm_approval': 'procurement_local_rfq.group_local_rfq_general_manager',
            'approved': 'procurement_local_purchase.group_local_purchase_pr_manager',
        }
        
        group_xmlid = group_xmlid_map.get(next_state)
        if not group_xmlid:
            return

        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if not group:
            return

        company_id = self.sudo().company_id.id
        users = group.sudo().user_ids.filtered(lambda u: u.company_id.id == company_id or company_id in u.company_ids.ids)
        if not users:
            return

        for user in users:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_("RFQ Action Required"),
                note=_("Local RFQ (%s) is awaiting your action (State: %s).") % (self.name, state_label)
            )

    # ---- Auto generate quotes when vendor added ----
    @api.onchange('vendor_ids', 'show_financial', 'show_technical')
    def _onchange_vendor_ids(self):
        for rec in self:
            if not rec.requisition_id:
                continue

            vendors = rec.vendor_ids
            quote_commands = []

            # 1. Keep existing quotes that are still valid
            valid_existing_quotes = rec.quote_ids.filtered(lambda q: q.partner_id in vendors)
            # We don't need to re-add them if we are just returning commands for OnChange
            # But for correct behavior in UI, commonly we reconstruct or just add new.
            # Odoo's onchange behaves diff than write. 
            # Ideally we want to ensure all combinations exist.
            
            # Simple approach for OnChange:
            # We can't easily "keep" without risking duplication if we aren't careful in OnChange context.
            # However, typically we just append new ones. 
            
            existing_pairs = {(q.pr_line_id.id, q.partner_id.id) for q in rec.quote_ids}

            # 2. Add quotes for missing combinations
            for vendor in vendors:
                for line in rec.requisition_id.line_ids:
                    if (line.id, vendor.id) not in existing_pairs:
                        quote_commands.append((0, 0, {
                            'pr_line_id': line.id,
                            'product_id': line.product_id.id,
                            'partner_id': vendor.id,
                        }))

            # 3. Remove quotes for de-selected vendors
            # specific to onchange logic
            quotes_to_remove = rec.quote_ids.filtered(lambda q: q.partner_id not in vendors)
            for q in quotes_to_remove:
                quote_commands.append((2, q.id))

            rec.quote_ids = quote_commands

    def action_select_winners(self):
        self.ensure_one()
        # 1. Clear all previous selections
        self.quote_ids.write({'selected': False})
        
        # 2. Group by product line and pick based on winner selection method
        pr_lines = self.quote_ids.mapped('pr_line_id')
        for line in pr_lines:
            quotes = self.quote_ids.filtered(lambda q: q.pr_line_id == line)
            if not quotes:
                continue
            
            winner = self.env['local.rfq.quote']
            
            if self.winner_selection_method == 'financial':
                max_val = max(quotes.mapped('financial_percent') or [0.0])
                winner = quotes.filtered(lambda q: q.financial_percent == max_val)
            elif self.winner_selection_method == 'technical':
                max_val = max(quotes.mapped('technical_percent') or [0.0])
                winner = quotes.filtered(lambda q: q.technical_percent == max_val)
            elif self.winner_selection_method == 'price':
                # Skip zero prices - find the best valid quote
                valid_quotes = quotes.filtered(lambda q: q.price_unit > 0)
                if valid_quotes:
                    min_price = min(valid_quotes.mapped('price_unit'))
                    winner = valid_quotes.filtered(lambda q: q.price_unit == min_price)
                else:
                    winner = quotes[:1]
            else:  # 'total'
                max_val = max(quotes.mapped('total_percent') or [0.0])
                winner = quotes.filtered(lambda q: q.total_percent == max_val)
            
            if winner:
                # Pick the first one in case of a value tie
                winner[:1].write({'selected': True})
        
        if not self.quote_ids.filtered(lambda q: q.selected):
            raise UserError(_("No quotes could be selected as winners. Please ensure prices or scores are entered."))

        self.write({'state': 'winner_picked'})
        self.message_post(body=_("Winners picked based on %s selection method.") % dict(self._fields['winner_selection_method'].selection).get(self.winner_selection_method))
        return True

    def action_view_comparison_matrix(self):
        self.ensure_one()
        action = self.env.ref('procurement_local_rfq.action_local_rfq_comparison_matrix').read()[0]
        action['domain'] = [('rfq_id', '=', self.id)]
        return action

    def action_create_po(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("Purchase Order can only be created once the RFQ is fully approved."))
        selected_quotes = self.quote_ids.filtered(lambda q: q.selected)
        if not selected_quotes:
            raise UserError(_("Please select winning vendors in the Comparison Sheet."))

        pos = self.env['purchase.order']
        vendors = selected_quotes.mapped('partner_id')

        for vendor in vendors:
            vendor_quotes = selected_quotes.filtered(lambda q: q.partner_id == vendor)
            po_vals = {
                'partner_id': vendor.id,
                'origin': self.name,
                'local_rfq_id': self.id,
                'state': 'draft',
                'order_line': [(0, 0, {
                    'product_id': quote.product_id.id,
                    'product_qty': quote.pr_line_id.quantity, # Assuming quantity is on PR line
                    'name': quote.product_id.display_name,
                    'price_unit': quote.price_unit,
                    'date_planned': fields.Datetime.now(),
                    'analytic_distribution': {str(quote.pr_line_id.cost_center_id.id): 100} if quote.pr_line_id.cost_center_id else False,
                }) for quote in vendor_quotes],
            }
            pos |= self.env['purchase.order'].create(po_vals)

        self.write({'state': 'po_created'})
        return self.action_view_pos()

    def action_view_pos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('local_rfq_id', '=', self.id)],
            'context': {'default_local_rfq_id': self.id},
        }

class LocalRFQQuote(models.Model):
    _name = 'local.rfq.quote'
    _description = 'Local RFQ Quote / Comparison Line'

    rfq_id = fields.Many2one('local.rfq', string='RFQ', ondelete='cascade')
    
    # Link to Original PR Line to track quantity and product
    pr_line_id = fields.Many2one(
        'local.purchase.requisition.line',
        string='PR Line',
        required=True,
        ondelete='restrict'
    )
    product_id = fields.Many2one('product.product', string='Product', related='pr_line_id.product_id')
    categ_id = fields.Many2one('product.category', string='Category', related='product_id.categ_id', readonly=True)
    image_128 = fields.Image(string='Image', related='product_id.image_128', readonly=True)
    image_1920 = fields.Image(string='Full Image', related='product_id.image_1920', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, domain="[('vendor_type', '=', 'local')]")
    cost_center_id = fields.Many2one('account.analytic.account', string='Cost Center', related='pr_line_id.cost_center_id')
    
    price_unit = fields.Float(string='Unit Price')
    delivery_date = fields.Date(string='Expected Delivery')
    selected = fields.Boolean(string='Selected', default=False)
    
    financial_percent = fields.Float(string='Financial %')
    technical_percent = fields.Float(string='Technical %')
    total_percent = fields.Float(string='Total %', compute='_compute_total_percent', store=True)

    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)

    @api.depends('price_unit', 'pr_line_id.quantity')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = rec.price_unit * (rec.pr_line_id.quantity if rec.pr_line_id else 0.0)

    @api.depends('financial_percent', 'technical_percent')
    def _compute_total_percent(self):
        for rec in self:
            rec.total_percent = (rec.financial_percent + rec.technical_percent) / 2

# Inherit Local Purchase Requisition to add link
class LocalPurchaseRequisition(models.Model):
    _inherit = 'local.purchase.requisition'

    rfq_ids = fields.One2many('local.rfq', 'requisition_id', string='RFQs')
    rfq_count = fields.Integer(compute='_compute_rfq_count')

    @api.depends('rfq_ids')
    def _compute_rfq_count(self):
        for rec in self:
            rec.rfq_count = len(rec.rfq_ids)

    def action_create_rfq(self):
        self.ensure_one()
        
        # Threshold Validation
        min_threshold = self.company_id.rfq_threshold_from
        max_threshold = self.company_id.rfq_threshold_to
        
        if not (min_threshold <= self.amount_total <= max_threshold):
            raise UserError(_("Total amount (%.2f) must be between %.2f and %.2f to create an RFQ.") % (
                self.amount_total, min_threshold, max_threshold))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'local.rfq',
            'view_mode': 'form',
            'context': {'default_requisition_id': self.id},
            'target': 'current',
        }

    def action_view_rfqs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('RFQs'),
            'res_model': 'local.rfq',
            'view_mode': 'list,form',
            'domain': [('requisition_id', '=', self.id)],
            'context': {'default_requisition_id': self.id},
        }

# Inherit Purchase Order to add link
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    local_rfq_id = fields.Many2one('local.rfq', string='Source Local RFQ')

class LocalRFQCommitteeAction(models.Model):
    _name = 'local.rfq.committee.action'
    _description = 'Local RFQ Committee Action (Check/Approve/Reject)'
    _order = 'approval_date desc'

    rfq_id = fields.Many2one('local.rfq', string='RFQ', ondelete='cascade', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True)
    approval_date = fields.Datetime(string='Date', required=True)
    action_type = fields.Selection([
        ('check', 'Checked'),
        ('approve', 'Approved'),
        ('reject', 'Rejected')
    ], string='Action', required=True)
    comment = fields.Text(string='Comment')
