from odoo import api, models

from ..hooks import sync_payment_accounts


class AccountAccount(models.Model):
    _inherit = "account.account"

    @api.model
    def _ddfsc_sync_payment_accounts(self):
        """Run on install/upgrade: make sure the outstanding receipt, outstanding
        payment and liquidity transfer accounts exist and are used."""
        sync_payment_accounts(self.env)
        return True
