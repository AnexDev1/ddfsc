from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from odoo.addons.ddfsc_quality.models.factory_standards import DEMO_PLAN_NAMES


@tagged("post_install", "-at_install")
class TestFactoryStandards(TransactionCase):
    """Factory QC standards, used by a QC user and a QC manager (not admin)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qc_user = new_test_user(
            cls.env, login="fs_qc_user",
            groups="base.group_user,ddfsc_quality.group_ddfsc_quality_user",
        )
        cls.qc_manager = new_test_user(
            cls.env, login="fs_qc_manager",
            groups="base.group_user,ddfsc_quality.group_ddfsc_quality_manager",
        )
        cls.Plan = cls.env["ddfsc.quality.plan"]
        cls.wheat = cls.env.ref("ddfsc_manufacturing.product_wheat").product_variant_id
        cls.biscuit_flour = cls.env.ref("ddfsc_manufacturing.product_flour_g2").product_variant_id

    def _standard(self, xmlid):
        return self.env.ref("ddfsc_quality.%s" % xmlid)

    def _approve(self, *xmlids):
        """Approve factory plans as the QC manager, retiring any plan they replace."""
        plans = self.Plan.browse()
        for xmlid in xmlids:
            plans |= self._standard(xmlid)
        current = self.Plan.search([
            ("approval_state", "=", "approved"),
            ("product_ids", "in", plans.product_ids.ids),
            ("id", "not in", plans.ids),
        ])
        current.with_user(self.qc_manager).action_retire()
        plans.with_user(self.qc_manager).action_approve()
        return plans

    def _line(self, inspection, check_type):
        return inspection.line_ids.filtered(lambda line: line.plan_line_id.check_type == check_type)

    def test_factory_plans_are_seeded_for_review(self):
        plan = self._standard("qc_std_wheat_imported_hard")
        self.assertEqual(plan.wheat_type, "imported_hard")
        self.assertFalse(plan.demo_specification)
        limits = {line.check_type: (line.standard_min, line.standard_max) for line in plan.line_ids}
        self.assertEqual(limits["hlw"][0], 80)
        self.assertEqual(limits["moisture"][1], 12)
        self.assertEqual(limits["impurity"][1], 6)
        self.assertEqual(limits["protein"][0], 12)
        spaghetti = self._standard("qc_std_flour_spaghetti")
        granulation = spaghetti.line_ids.filtered(lambda line: line.check_type == "granulation")
        self.assertEqual((granulation.standard_min, granulation.standard_max), (56, 63))
        self.assertEqual(granulation.limit_type, "range")
        self.assertFalse(spaghetti.line_ids.filtered(lambda line: line.check_type == "ash").mandatory)
        self.assertFalse(self.Plan.search([
            ("name", "in", DEMO_PLAN_NAMES), ("approval_state", "=", "draft"),
            ("demo_specification", "=", True),
        ]), "Untouched demo plans are archived once the factory plans exist")
        # Running the sync again creates nothing new.
        self.assertFalse(self.Plan._sync_factory_standards())

    def test_wheat_type_selects_plan_and_swaps_untouched_inspection(self):
        imported, local_red = self._approve("qc_std_wheat_imported_hard", "qc_std_wheat_local_red_mixed")
        Lot = self.env["stock.lot"].with_user(self.qc_user)
        lot = Lot.create({"name": "FS-WHEAT-1", "product_id": self.wheat.id})
        self.assertTrue(lot.ddfsc_is_wheat)
        self.assertFalse(lot.quality_plan_id, "Wheat needs its type before a receiving standard applies")

        lot.write({"ddfsc_wheat_type": "imported_hard", "ddfsc_wheat_code": "IRS"})
        first = lot.active_qc_inspection_id
        self.assertEqual(first.plan_id, imported)
        self.assertTrue(self._line(first, "protein"))

        lot.ddfsc_wheat_type = "local_red_mixed"
        second = lot.active_qc_inspection_id
        self.assertEqual(first.state, "superseded")
        self.assertEqual(second.plan_id, local_red)
        self.assertFalse(self._line(second, "protein"))

        # 76 kg/hl and 9 % impurity fail imported hard wheat but pass local red mixed.
        self._line(second, "hlw").with_user(self.qc_user).write({"measured_value": 76, "is_measured": True})
        self._line(second, "moisture").with_user(self.qc_user).write({"measured_value": 11.5, "is_measured": True})
        self._line(second, "impurity").with_user(self.qc_user).write({"measured_value": 9, "is_measured": True})
        self.assertEqual(second.result_state, "pass")

        with self.assertRaises(UserError):
            lot.ddfsc_wheat_type = "imported_hard"

    def test_flour_ash_is_recorded_but_optional(self):
        plan = self._approve("qc_std_flour_biscuit")
        lot = self.env["stock.lot"].with_user(self.qc_user).create({
            "name": "FS-FLOUR-G2-1", "product_id": self.biscuit_flour.id,
        })
        inspection = lot.active_qc_inspection_id
        self.assertEqual(inspection.plan_id, plan)
        for check_type, value in (("moisture", 13.0), ("gluten", 27.0), ("granulation", 60.0)):
            self._line(inspection, check_type).with_user(self.qc_user).write(
                {"measured_value": value, "is_measured": True})
        self.assertEqual(inspection.result_state, "pass")
        inspection.with_user(self.qc_user).action_submit()
        self.assertEqual(inspection.state, "submitted")

    def test_low_gluten_biscuit_flour_fails(self):
        self._approve("qc_std_flour_biscuit")
        lot = self.env["stock.lot"].with_user(self.qc_user).create({
            "name": "FS-FLOUR-G2-2", "product_id": self.biscuit_flour.id,
        })
        inspection = lot.active_qc_inspection_id
        for check_type, value in (("moisture", 13.0), ("gluten", 24.0), ("granulation", 60.0)):
            self._line(inspection, check_type).with_user(self.qc_user).write(
                {"measured_value": value, "is_measured": True})
        self.assertEqual(inspection.result_state, "fail")
