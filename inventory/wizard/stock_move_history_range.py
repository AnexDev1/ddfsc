# -*- coding: utf-8 -*-
import datetime
import pytz
from odoo import _, fields, models
from odoo.tools.misc import format_date

class StockMoveHistoryRange(models.TransientModel):
    _name = 'stock.move.history.range'
    _description = 'Stock Move History Date Range'

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

    def open_move_history_range(self):
        tree_view_id = self.env.ref('stock.view_move_line_tree').id
        
        # Get user timezone or default to UTC
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(user_tz)
        
        # Create naive local datetimes
        local_from = datetime.datetime.combine(self.date_from, datetime.time.min)
        local_to = datetime.datetime.combine(self.date_to, datetime.time.max)
        
        # Localize to user's timezone and convert to UTC naive datetimes
        from_datetime = local_tz.localize(local_from).astimezone(pytz.UTC).replace(tzinfo=None)
        to_datetime = local_tz.localize(local_to).astimezone(pytz.UTC).replace(tzinfo=None)

        domain = [
            ('date', '>=', from_datetime),
            ('date', '<=', to_datetime)
        ]
        
        product_id = self.env.context.get('default_product_id') or self.env.context.get('product_id')
        if product_id:
            domain.append(('product_id', '=', product_id))
            
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Moves History'),
            'res_model': 'stock.move.line',
            'view_mode': 'list,kanban,pivot,form',
            'views': [(tree_view_id, 'list'), (False, 'kanban'), (False, 'pivot'), (False, 'form')],
            'domain': domain,
            'context': dict(self.env.context, create=0),
            'display_name': f"Moves: {format_date(self.env, self.date_from)} - {format_date(self.env, self.date_to)}"
        }
        return action
