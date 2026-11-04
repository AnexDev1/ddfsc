# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import format_amount


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    hs_code = fields.Char(
        string='HS Code',
        index=True,
        help="Harmonized System Code used for international trade, customs classification, and foreign procurement.",
    )
    hs_description = fields.Char(
        string='HS Description',
        help="Customs or tariff commodity description.",
    )
    wholesale_price = fields.Float(
        string='Wholesale Price',
        digits='Product Price',
        default=0.0,
        help="Wholesale selling price for this product.",
    )

    def _get_single_tax_amount_and_type(self, price):
        currency = self.currency_id
        taxes = self.taxes_id._filter_taxes_by_company(self.env.company)
        if not taxes:
            return None, ""
        res = taxes.compute_all(price, product=self, partner=self.env['res.partner'])
        included = res['total_included']
        excluded = res['total_excluded']
        if currency.compare_amounts(included, price) > 0:
            return format_amount(self.env, included, currency), "Incl. Taxes"
        elif currency.compare_amounts(excluded, price) < 0:
            return format_amount(self.env, excluded, currency), "Excl. Taxes"
        return None, ""

    @api.depends('taxes_id', 'list_price', 'wholesale_price')
    @api.depends_context('company')
    def _compute_tax_string(self):
        for record in self:
            if not record.taxes_id:
                record.tax_string = " "
                continue
            if record.wholesale_price > 0:
                r_amt, r_type = record._get_single_tax_amount_and_type(record.list_price)
                w_amt, w_type = record._get_single_tax_amount_and_type(record.wholesale_price)
                if r_amt and w_amt:
                    tax_type = r_type or w_type
                    record.tax_string = f"(= Retail: {r_amt} | Wholesale: {w_amt} {tax_type})"
                elif r_amt:
                    record.tax_string = f"(= Retail: {r_amt} {r_type})"
                else:
                    record.tax_string = record._construct_tax_string(record.list_price)
            else:
                record.tax_string = record._construct_tax_string(record.list_price)

    @api.constrains('default_code')
    def _check_default_code_unique(self):
        for record in self:
            code = (record.default_code or '').strip()
            if code:
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('default_code', '=ilike', code),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _("The Product Code '%(code)s' is already used by product '%(product)s'. Product Code must be unique!")
                        % {'code': code, 'product': duplicate.display_name}
                    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            is_landed_cost = bool(
                vals.get('landed_cost_ok')
                or self.env.context.get('default_landed_cost_ok')
                or self.env.context.get('landed_cost_product_entry')
            )
            if vals.get('type') == 'service' and not is_landed_cost:
                if not vals.get('default_code'):
                    vals['default_code'] = 'DISC' if 'discount' in (vals.get('name') or '').lower() else 'SRV'
            if self.env.context.get('create_product_product') is False:
                continue

            if not is_landed_cost:
                if not vals.get('default_code') and not self.env.context.get('install_mode'):
                    raise ValidationError(_("Product Code is required for product registration!"))
        return super().create(vals_list)

    def write(self, vals):
        for tmpl in self:
            is_landed_cost = vals.get('landed_cost_ok', tmpl.landed_cost_ok)
            if not is_landed_cost:
                if 'default_code' in vals and not vals.get('default_code'):
                    raise ValidationError(_("Product Code cannot be empty!"))
        return super().write(vals)
