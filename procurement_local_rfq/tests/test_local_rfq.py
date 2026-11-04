from odoo.tests.common import TransactionCase, tagged
import logging
_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install')
class TestLocalRFQ(TransactionCase):

    def setUp(self):
        super(TestLocalRFQ, self).setUp()
        self.PR = self.env['local.purchase.requisition']
        self.RFQ = self.env['local.rfq']
        self.Product = self.env['product.product']
        self.Partner = self.env['res.partner']
        
        self.product_1 = self.Product.create({'name': 'RFQ Product 1', 'default_code': 'P001'})
        self.product_2 = self.Product.create({'name': 'RFQ Product 2', 'default_code': 'P002'})
        self.vendor = self.Partner.create({'name': 'Test Vendor', 'supplier_rank': 1, 'vendor_type': 'local'})

    def test_01_create_rfq_from_pr(self):
        """Test creating an RFQ from a PR."""
        pr1 = self.PR.create({
            'line_ids': [(0, 0, {'product_id': self.product_1.id, 'quantity': 10})]
        })
        
        # Create RFQ and link the PR
        rfq = self.RFQ.create({
            'requisition_id': pr1.id
        })
        
        # Add vendor and trigger onchange
        rfq.vendor_ids = [(4, self.vendor.id)]
        rfq._onchange_vendor_ids()
        
        # Verify that lines from the PR are added to the comparison
        comparison_lines = rfq.quote_ids
        products_in_rfq = comparison_lines.mapped('product_id')
        self.assertIn(self.product_1, products_in_rfq)
        self.assertEqual(len(comparison_lines), 1)

    def test_02_submit_approve_create_po(self):
        """Test 5-step approval workflow: Pick Winner -> Submit -> 5 Approvals -> Create PO."""
        pr = self.PR.create({
            'line_ids': [(0, 0, {'product_id': self.product_1.id, 'quantity': 5, 'unit_price': 100.0})]
        })
        rfq = self.RFQ.create({
            'requisition_id': pr.id,
            'vendor_ids': [(4, self.vendor.id)],
        })
        rfq._onchange_vendor_ids()
        self.assertTrue(rfq.quote_ids)
        # Set price and pick winner
        rfq.quote_ids[0].write({'price_unit': 95.0})
        rfq.action_select_winners()
        self.assertEqual(rfq.state, 'winner_picked', "RFQ should be in 'winner_picked' state after picking winners")
        self.assertTrue(rfq.quote_ids[0].selected, "Quote should be selected")
        
        # 1. Submit
        rfq.action_submit()
        self.assertEqual(rfq.state, 'submitted', "RFQ should be in 'submitted' state after submit")

        # 2. Step 1: Commercial Dep't Approval
        rfq.action_commercial_approve()
        self.assertEqual(rfq.state, 'finance_approval', "RFQ should be in 'finance_approval' after Commercial Dep't approval")
        self.assertTrue(rfq.commercial_approver_id)

        # 3. Step 2: Finance Approval
        rfq.action_finance_approve()
        self.assertEqual(rfq.state, 'production_approval', "RFQ should be in 'production_approval' after Finance approval")
        self.assertTrue(rfq.finance_approver_id)

        # 4. Step 3: Production Head Approval
        rfq.action_production_approve()
        self.assertEqual(rfq.state, 'sales_purchase_approval', "RFQ should be in 'sales_purchase_approval' after Production Head approval")
        self.assertTrue(rfq.production_approver_id)

        # 5. Step 4: Sales & Purchase Approval
        rfq.action_sales_purchase_approve()
        self.assertEqual(rfq.state, 'gm_approval', "RFQ should be in 'gm_approval' after Sales & Purchase approval")
        self.assertTrue(rfq.sales_purchase_approver_id)

        # 6. Step 5: General Manager Approval
        rfq.action_gm_approve()
        self.assertEqual(rfq.state, 'approved', "RFQ should be in 'approved' state after GM approval")
        self.assertTrue(rfq.gm_approver_id)

        # 7. Create PO
        rfq.action_create_po()
        self.assertEqual(rfq.state, 'po_created', "RFQ should be in 'po_created' state after PO creation")
        self.assertEqual(rfq.po_count, 1, "One PO should have been created")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        _logger.info("All local rfq tests passed successfully!")