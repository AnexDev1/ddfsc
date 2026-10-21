from datetime import datetime, time, timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class DdfscQualityReport(models.Model):
    _name = 'ddfsc.quality.report'
    _description = 'Weekly Quality Report'
    _order = 'date_start desc, id desc'

    name = fields.Char(required=True)
    date_start = fields.Date(required=True)
    date_end = fields.Date(required=True)
    note = fields.Text(string='Note to General Manager')
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted')],
        default='draft',
        required=True,
    )
    check_ids = fields.Many2many('ddfsc.quality.check', string='Checks')

    def action_collect(self):
        for report in self:
            if report.date_end < report.date_start:
                raise UserError(_('The end date is before the start date.'))
            start = datetime.combine(report.date_start, time.min)
            end = datetime.combine(report.date_end, time.min) + timedelta(days=1)
            checks = self.env['ddfsc.quality.check'].search([
                ('create_date', '>=', start),
                ('create_date', '<', end),
            ])
            report.check_ids = checks
        return True

    def action_submit(self):
        self.action_collect()
        self.write({'state': 'submitted'})
        return True
