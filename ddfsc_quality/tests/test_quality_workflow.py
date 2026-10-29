from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import RedirectWarning, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDdfscQualityWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "QC Workflow Test Product",
            "is_storable": True,
            "tracking": "lot",
        })
        cls.plan = cls.env["ddfsc.quality.plan"].create({
            "name": "QC Workflow Test Plan",
            "checkpoint": "finished_goods",
            "product_ids": [(6, 0, cls.product.ids)],
            "demo_specification": False,
            "line_ids": [
                (0, 0, {"check_type": "moisture", "mandatory": True,
                        "result_type": "numeric", "apply_max": True, "standard_max": 12.0, "note": "%"}),
                (0, 0, {"check_type": "organoleptic", "mandatory": True,
                        "result_type": "qualitative", "allowed_answers": "Acceptable, Pass"}),
            ],
        })
        cls.plan.action_approve()

    def _new_lot(self, name):
        lot = self.env["stock.lot"].create({"name": name, "product_id": self.product.id})
        if not lot.quality_check_ids:
            lot.action_prepare_quality_checks()
        return lot

    def test_pass_requires_submission_and_manager_approval(self):
        lot = self._new_lot("QC-PASS-TEST")
        numeric = lot.quality_check_ids.filtered(lambda check: check.result_type == "numeric")
        qualitative = lot.quality_check_ids.filtered(lambda check: check.result_type == "qualitative")
        numeric.write({"measured_value": 10.0, "is_measured": True})
        qualitative.write({"measured_text": "Acceptable", "is_measured": True})
        self.assertEqual(lot.ddfsc_quality_state, "pending")
        lot.action_submit_quality()
        lot.action_approve_quality()
        self.assertEqual(lot.ddfsc_review_state, "approved")
        self.assertEqual(lot.ddfsc_quality_state, "pass")
        with self.assertRaises(UserError):
            numeric.write({"measured_value": 11.0})

    def test_failed_result_creates_nonconformance_and_reinspection_history(self):
        lot = self._new_lot("QC-FAIL-TEST")
        numeric = lot.quality_check_ids.filtered(lambda check: check.result_type == "numeric")
        qualitative = lot.quality_check_ids.filtered(lambda check: check.result_type == "qualitative")
        numeric.write({"measured_value": 15.0, "is_measured": True})
        qualitative.write({"measured_text": "Acceptable", "is_measured": True})
        lot.action_submit_quality()
        lot.action_approve_quality()
        self.assertEqual(lot.ddfsc_quality_state, "hold")
        self.assertTrue(lot.nonconformance_ids)
        ncr = lot.nonconformance_ids
        ncr.write({"due_date": fields.Date.today() - timedelta(days=1)})
        self.assertTrue(ncr.is_overdue)
        self.assertTrue(ncr.activity_ids.filtered(
            lambda activity: activity.summary == "Investigate non-conformance %s" % ncr.name
        ))
        ncr._cron_notify_overdue()
        self.assertTrue(ncr.activity_ids.filtered(
            lambda activity: activity.summary == "Overdue non-conformance %s" % ncr.name
        ))
        lot.correction_reason = "Laboratory requested a fresh sample"
        lot.action_request_reinspection()
        self.assertEqual(lot.ddfsc_review_state, "draft")
        self.assertEqual(lot.ddfsc_quality_state, "pending")
        self.assertEqual(len(lot.quality_revision_ids), 1)
        self.assertTrue(all(not check.is_measured for check in lot.quality_check_ids))

    def test_plan_versioning_and_demo_limits_are_governed(self):
        action = self.plan.action_new_version()
        new_plan = self.env["ddfsc.quality.plan"].browse(action["res_id"])
        self.assertEqual(new_plan.version, "1.1")
        self.assertEqual(new_plan.approval_state, "draft")
        new_plan.demo_specification = True
        with self.assertRaises(UserError):
            new_plan.action_approve()
        new_plan.demo_specification = False
        with self.assertRaises(UserError):
            new_plan.action_approve()
        self.plan.action_retire()
        new_plan.action_approve()
        self.assertEqual(new_plan.approval_state, "approved")

    def test_controlled_stock_cannot_leave_before_qc_release(self):
        lot = self._new_lot("QC-STOCK-GATE")
        source = self.env.ref("ddfsc_manufacturing.loc_flour_finished")
        destination = self.env.ref("ddfsc_manufacturing.loc_flour")
        picking_type = self.env.ref("ddfsc_manufacturing.picking_type_qc_release")
        self.env["stock.quant"]._update_available_quantity(
            self.product, source, 1.0, lot_id=lot
        )
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "move_ids": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "product_uom": self.product.uom_id.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
            })],
        })
        move = picking.move_ids
        self.env["stock.move.line"].create({
            "move_id": move.id,
            "picking_id": picking.id,
            "product_id": self.product.id,
            "product_uom_id": self.product.uom_id.id,
            "quantity": 1.0,
            "location_id": source.id,
            "location_dest_id": destination.id,
            "lot_id": lot.id,
        })
        with self.assertRaises(RedirectWarning):
            picking.button_validate()

        lot.write({"quality_release_note": "Approved deviation for test"})
        lot.action_quality_release()
        result = picking.button_validate()
        self.assertIn(result, (True, None))
        self.assertEqual(picking.state, "done")
