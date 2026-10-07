from odoo import _, fields, models
from odoo.exceptions import UserError


class StockLot(models.Model):
    _inherit = 'stock.lot'

    ddfsc_quality_state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('pass', 'Passed'),
            ('hold', 'On Hold'),
            ('released', 'Released'),
        ],
        string='Quality Status',
        default='pending',
        tracking=True,
        copy=False,
    )
    quality_check_ids = fields.One2many('ddfsc.quality.check', 'lot_id', string='Quality Checks')
    quality_release_note = fields.Char(copy=False)
    ddfsc_wheat_use = fields.Selection(
        [
            ('pasta', 'Pasta'),
            ('macaroni', 'Macaroni'),
            ('bread', 'Bread'),
            ('biscuit', 'Biscuit'),
        ],
        string='Intended Use',
        tracking=True,
    )
    ddfsc_gm_approved = fields.Boolean(string='General Manager Approved', copy=False, tracking=True)
    ddfsc_hectoliter = fields.Float(string='Hectoliter Weight', tracking=True)

    def action_gm_approve(self):
        for lot in self:
            if not lot.ddfsc_wheat_use:
                raise UserError(_('Choose pasta, macaroni, bread, or biscuit before approval.'))
            if lot.ddfsc_quality_state != 'pass':
                raise UserError(_('The wheat sample has to pass before the general manager approves it.'))
            lot.ddfsc_gm_approved = True

    def _ddfsc_apply_quality_checks(self):
        for lot in self:
            if lot.ddfsc_quality_state == 'released':
                continue
            if any(check.result == 'fail' for check in lot.quality_check_ids):
                lot.ddfsc_quality_state = 'hold'
            elif lot.quality_check_ids:
                lot.ddfsc_quality_state = 'pass'

    def action_quality_hold(self):
        self.write({'ddfsc_quality_state': 'hold'})

    def action_quality_release(self):
        missing = self.filtered(lambda lot: not lot.quality_release_note)
        if missing:
            raise UserError(_('Write a release note before releasing a lot that was on hold.'))
        self.write({'ddfsc_quality_state': 'released'})
