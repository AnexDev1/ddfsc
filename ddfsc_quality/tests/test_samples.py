from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestSamples(TransactionCase):
    """Several readings per test, entered by a QC user (not admin)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qc_user = new_test_user(
            cls.env, login="smp_qc_user", groups="base.group_user,ddfsc_quality.group_ddfsc_quality_user")
        cls.qc_manager = new_test_user(
            cls.env, login="smp_qc_manager", groups="base.group_user,ddfsc_quality.group_ddfsc_quality_manager")

    def _inspection(self, rule, name):
        product = self.env["product.product"].create({
            "name": "Sample Pack %s" % name, "default_code": "SMP-%s" % name,
            "is_storable": True, "tracking": "lot",
        })
        plan = self.env["ddfsc.quality.plan"].create({
            "name": "Packing weight %s" % name, "checkpoint": "finished_goods",
            "product_ids": [(6, 0, product.ids)], "demo_specification": False,
            "line_ids": [(0, 0, {"check_type": "weight", "result_type": "numeric", "mandatory": True,
                                 "apply_min": True, "standard_min": 495, "apply_max": True,
                                 "standard_max": 505, "note": "g", "sample_count": 4, "sample_rule": rule})],
        })
        plan.with_user(self.qc_manager).action_approve()
        lot = self.env["stock.lot"].with_user(self.qc_user).create({"name": "SMP-%s" % name, "product_id": product.id})
        inspection = lot.active_qc_inspection_id.with_user(self.qc_user)
        return inspection, inspection.line_ids

    def test_too_few_samples_stay_pending(self):
        inspection, line = self._inspection("each", "FEW")
        line.write({"sample_values": "502, 498"})
        self.assertEqual(line.sample_taken, 2)
        self.assertEqual(line.result, "pending")
        with self.assertRaises(UserError):
            inspection.action_submit()

    def test_every_sample_rule_fails_on_one_bad_pack(self):
        inspection, line = self._inspection("each", "EACH")
        line.write({"sample_values": "502, 498, 501, 499"})
        self.assertEqual(line.measured_value, 500)
        self.assertEqual(line.result, "pass")
        line.write({"sample_values": "502, 498, 510, 499"})
        self.assertEqual((line.sample_min, line.sample_max), (498, 510))
        self.assertEqual(line.result, "fail", "One pack at 510 g fails although the average is in range")

    def test_average_rule_accepts_spread_within_average(self):
        inspection, line = self._inspection("average", "AVG")
        line.write({"sample_values": "502; 498\n510, 494"})
        self.assertEqual(line.sample_taken, 4)
        self.assertEqual(line.measured_value, 501)
        self.assertEqual(line.result, "pass")
        inspection.write({"die_number": "115288", "packing_machine": "LCP-1 A", "silo_number": "3"})
        inspection.action_submit()
        self.assertEqual(inspection.state, "submitted")
        with self.assertRaises(UserError):
            line.write({"sample_values": "500, 500, 500, 500"})

    def test_readings_must_be_numbers(self):
        _inspection, line = self._inspection("average", "NUM")
        with self.assertRaises(UserError):
            line.write({"sample_values": "502, five hundred"})
