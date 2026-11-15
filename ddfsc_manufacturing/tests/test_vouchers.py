from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestVouchers(TransactionCase):
    """Printed plant vouchers render for department users with the factory titles."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        def user(login, groups, department=False):
            return Users.create({
                'name': login, 'login': login, 'ddfsc_department': department,
                'group_ids': [Command.set([cls.env.ref(g).id for g in ['base.group_user'] + groups])],
            })

        cls.biscuit_user = user('vo_biscuit', ['mrp.group_mrp_user'], 'biscuit')
        cls.manager = user('vo_opm', ['mrp.group_mrp_user', 'ddfsc_manufacturing.group_ddfsc_operation_manager'])
        cls.sugar = cls.env.ref('ddfsc_manufacturing.product_sugar').product_variant_id
        cls.flour = cls.env.ref('ddfsc_manufacturing.product_flour_g2').product_variant_id

    def _html(self, user, report, records):
        html, _kind = self.env['ir.actions.report'].with_user(user)._render_qweb_html(report, records.ids)
        return html.decode()

    def _request(self, request_type, product, qty=5.0, **values):
        return self.env['ddfsc.store.request'].with_user(self.biscuit_user).with_context(
            default_request_type=request_type,
        ).create(dict(values, line_ids=[Command.create({'product_id': product.id, 'product_uom_qty': qty})]))

    def test_store_requisition_prints(self):
        request = self._request('component', self.sugar, 12.0)
        html = self._html(self.biscuit_user, 'ddfsc_manufacturing.action_report_store_request_voucher', request)
        self.assertIn('Store Requisition', html)
        self.assertIn('FAOF/PA522', html)
        self.assertIn(request.name, html)
        self.assertIn('Biscuit', html)

    def test_issue_and_return_vouchers_use_the_factory_forms(self):
        store = self.env.ref('ddfsc_manufacturing.loc_store')
        self.env['stock.quant']._update_available_quantity(self.sugar, store, 100.0)
        issue = self._request('component', self.sugar, 12.0)
        issue.action_submit_to_manager()
        issue.with_user(self.manager).action_approve_manager()
        self.assertEqual(issue.picking_id._ddfsc_voucher_kind(), 'store_issue')
        html = self._html(self.manager, 'ddfsc_manufacturing.action_report_picking_voucher', issue.picking_id)
        self.assertIn('Store Issued Voucher', html)
        self.assertIn('Unit Price', html)
        self.assertIn(issue.name, html)

        floor = self.env.ref('ddfsc_manufacturing.loc_biscuit')
        self.env['stock.quant']._update_available_quantity(self.sugar, floor, 10.0)
        back = self._request('material_return', self.sugar, 4.0, return_reason='Line stopped')
        back.action_submit_to_manager()
        back.with_user(self.manager).action_approve_manager()
        html = self._html(self.manager, 'ddfsc_manufacturing.action_report_picking_voucher', back.picking_id)
        self.assertIn('Returned Goods Receiving Note', html)
        self.assertIn('Line stopped', html)

    def test_flour_issue_prints_the_daily_flour_transfer_voucher(self):
        flour_store = self.env.ref('ddfsc_manufacturing.loc_flour')
        lot = self.env['stock.lot'].create({'name': 'VO-FLOUR-1', 'product_id': self.flour.id,
                                            'ddfsc_quality_state': 'released'})
        self.env['stock.quant']._update_available_quantity(self.flour, flour_store, 10.0, lot_id=lot)
        request = self._request('component', self.flour, 3.0)
        request.action_submit_to_manager()
        request.with_user(self.manager).action_approve_manager()
        self.assertEqual(request.picking_id._ddfsc_voucher_kind(), 'flour_transfer')
        html = self._html(self.manager, 'ddfsc_manufacturing.action_report_picking_voucher', request.picking_id)
        self.assertIn('Daily Wheat Flour Transfer Voucher', html)

    def test_lot_hold_and_release_forms(self):
        lot = self.env['stock.lot'].create({'name': 'VO-HOLD-1', 'product_id': self.flour.id})
        lot.write({'ddfsc_quality_state': 'hold', 'quality_release_note': 'Moisture above limit'})
        html = self._html(self.manager, 'ddfsc_manufacturing.action_report_lot_hold_release', lot)
        self.assertIn('OF/QC/019', html)
        self.assertIn('Moisture above limit', html)
        lot.ddfsc_quality_state = 'released'
        html = self._html(self.manager, 'ddfsc_manufacturing.action_report_lot_hold_release', lot)
        self.assertIn('OF/QC/018A', html)
