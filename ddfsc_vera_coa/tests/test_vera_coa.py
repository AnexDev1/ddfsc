from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVeraCoA(TransactionCase):
    def test_vera_accounts_and_dimensions(self):
        accounts = self.env["account.account"].search([
            ("code", "in", ["1010", "1100", "2000", "4010", "5100", "6010", "8010"])
        ])
        self.assertEqual(len(accounts), 7)
        self.assertEqual(accounts.filtered(lambda a: a.code == "1100").account_type, "asset_receivable")
        self.assertTrue(accounts.filtered(lambda a: a.code == "1100").reconcile)
        self.assertEqual(accounts.filtered(lambda a: a.code == "2000").account_type, "liability_payable")
        self.assertTrue(accounts.filtered(lambda a: a.code == "2000").reconcile)
        plans = self.env["account.analytic.plan"].search([
            ("name", "in", ["Product Line", "Department / Cost Center", "Branch / Location"])
        ])
        self.assertEqual(len(plans), 3)
        analytics = self.env["account.analytic.account"].search([("plan_id", "in", plans.ids)])
        # Users may add values (e.g. new product lines), so check the designed ones exist.
        self.assertTrue({"PL-01", "PL-09", "DPT-01", "DPT-07", "BR-01", "BR-04"} <= set(analytics.mapped("code")))
        legacy_draft_lines = self.env["account.move.line"].search_count([
            ("move_id.state", "=", "draft"),
            ("account_id.code", "in", ["121000", "400000"]),
        ])
        self.assertEqual(legacy_draft_lines, 0)

    def test_payment_and_transfer_accounts(self):
        company = self.env.company
        Account = self.env["account.account"]
        accounts = {
            code: Account.search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
            for code in ("1091", "1092", "1093")
        }
        for code, account in accounts.items():
            self.assertTrue(account, "Account %s missing" % code)
            self.assertTrue(account.active)
            self.assertTrue(account.reconcile, "Account %s must allow reconciliation" % code)
        self.assertEqual(company.transfer_account_id, accounts["1093"])

        bank_journals = self.env["account.journal"].search([
            ("company_id", "=", company.id), ("type", "=", "bank"),
        ])
        for journal in bank_journals:
            for line in journal.inbound_payment_method_line_ids:
                self.assertTrue(line.payment_account_id, "%s: inbound %s has no outstanding account" % (journal.code, line.name))
            for line in journal.outbound_payment_method_line_ids:
                self.assertTrue(line.payment_account_id, "%s: outbound %s has no outstanding account" % (journal.code, line.name))

    def test_one_bank_journal_per_bank_account(self):
        company = self.env.company
        for code in ("1070", "1071", "1072", "1073"):
            account = self.env["account.account"].search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)
            self.assertTrue(account)
            journal = self.env["account.journal"].search([
                ("company_id", "=", company.id), ("default_account_id", "=", account.id), ("type", "=", "bank"),
            ])
            self.assertTrue(journal, "No bank journal for account %s" % code)

    def test_sync_is_idempotent(self):
        from ..hooks import sync_payment_accounts

        Journal = self.env["account.journal"]
        before = Journal.search_count([("type", "=", "bank")])
        sync_payment_accounts(self.env)
        sync_payment_accounts(self.env)
        self.assertEqual(Journal.search_count([("type", "=", "bank")]), before)
        self.assertEqual(self.env["account.account"].search_count([
            ("code", "=", "1092"), ("company_ids", "in", self.env.company.id),
        ]), 1)
