from odoo import models, fields, api

class InvoiceAtDateWizard(models.TransientModel):
    _name = 'invoice.at.date.wizard'
    _description = 'Invoice at Date Wizard'

    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.context_today)
    end_date = fields.Date(string='End Date', required=True, default=fields.Date.context_today)

    def action_apply(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('yohannes_sales_report_customization.action_my_invoices_salesman')
        action['domain'] = [
            ('move_type', '=', 'out_invoice'), 
            ('state', '=', 'posted'), 
            ('create_uid', '!=', self.env.uid),
            ('is_manual_invoice', '=', False),
            ('invoice_date', '>=', self.start_date),
            ('invoice_date', '<=', self.end_date)
        ]
        action['context'] = dict(self.env.context, default_move_type='out_invoice')
        
        if self.start_date == self.end_date:
            dynamic_name = f"Invoices on {self.start_date.strftime('%Y-%m-%d')}"
        else:
            dynamic_name = f"Invoices from {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
            
        action['name'] = dynamic_name
        action['display_name'] = dynamic_name
        action['flags'] = {'initial_mode': 'view'}
        
        # Strip all identifiers so the client treats it as a brand-new dynamic action
        for key in ['id', 'xml_id', 'action_id', 'display_name']:
            if key in action and key != 'display_name':
                action.pop(key, None)
                
        return action

