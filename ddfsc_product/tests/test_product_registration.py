from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductRegistration(TransactionCase):
    """Product Code and Analytic Account are asked of people registering
    products, never of Odoo while it installs modules or of system products."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        plan = cls.env['account.analytic.plan'].create({'name': 'Test Product Line'})
        cls.account = cls.env['account.analytic.account'].create({'name': 'Test Flour', 'plan_id': plan.id})

    def test_people_must_give_code_and_analytic_account(self):
        Template = self.env['product.template']
        with self.assertRaises(ValidationError):
            Template.create({'name': 'No code', 'analytic_account_id': self.account.id})
        with self.assertRaises(ValidationError):
            Template.create({'name': 'No analytic', 'default_code': 'REG-TEST-1'})
        product = Template.create({'name': 'Complete', 'default_code': 'REG-TEST-2',
                                   'analytic_account_id': self.account.id})
        self.assertEqual(product.default_code, 'REG-TEST-2')

    def test_module_installation_is_never_blocked(self):
        product = self.env['product.template'].with_context(install_mode=True).create({'name': 'From module data'})
        self.assertTrue(product)
        self.env.registry.ready = False  # as while modules load (set-up functions, migrations)
        try:
            product = self.env['product.template'].create({'name': 'From a set-up function'})
        finally:
            self.env.registry.ready = True
        self.assertTrue(product)

    def test_system_products_are_exempt(self):
        product = self.env['product.product'].with_context(ddfsc_system_product=True).create({
            'name': 'System discount', 'type': 'service', 'default_code': 'REG-TEST-DISC'})
        self.assertTrue(product)
