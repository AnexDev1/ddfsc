# -*- coding: utf-8 -*-
import datetime
import pytz
from odoo import _, fields, models
from odoo.fields import Domain
from odoo.tools.misc import format_date

class StockQuantityHistoryRange(models.TransientModel):
    _name = 'stock.quantity.history.range'
    _description = 'Stock Quantity History Date Range'

    date_from = fields.Date(
        'From Date', 
        required=True, 
        default=lambda self: fields.Date.context_today(self) - datetime.timedelta(days=30)
    )
    date_to = fields.Date(
        'To Date', 
        required=True, 
        default=fields.Date.context_today
    )

    def open_at_date_range(self):
        tree_view_id = self.env.ref('stock.view_stock_product_tree').id
        form_view_id = self.env.ref('stock.product_form_view_procurement_button').id
        domain = Domain('is_storable', '=', True)
        
        product_id = self.env.context.get('product_id', False)
        product_tmpl_id = self.env.context.get('product_tmpl_id', False)
        if product_id:
            domain &= Domain('id', '=', product_id)
        elif product_tmpl_id:
            domain = Domain('product_tmpl_id', '=', product_tmpl_id)

        # Get user timezone or default to UTC
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(user_tz)
        
        # Create naive local datetimes
        local_from = datetime.datetime.combine(self.date_from, datetime.time.min)
        local_to = datetime.datetime.combine(self.date_to, datetime.time.max)
        
        # Localize to user's timezone and convert to UTC naive datetimes
        from_datetime = local_tz.localize(local_from).astimezone(pytz.UTC).replace(tzinfo=None)
        to_datetime = local_tz.localize(local_to).astimezone(pytz.UTC).replace(tzinfo=None)

        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'list'), (form_view_id, 'form')],
            'view_mode': 'list,form',
            'name': _('Products'),
            'res_model': 'product.product',
            'domain': domain,
            'context': dict(self.env.context, from_date=from_datetime, to_date=to_datetime),
            'display_name': f"Inventory: {format_date(self.env, self.date_from)} - {format_date(self.env, self.date_to)}"
        }
        return action
