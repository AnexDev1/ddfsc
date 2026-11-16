from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestQcLogs(TransactionCase):
    """Shift log sheets, filled by the assistant QC and checked by the QC head."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qc_user = new_test_user(
            cls.env, login="log_qc_user", groups="base.group_user,ddfsc_quality.group_ddfsc_quality_user")
        cls.qc_head = new_test_user(
            cls.env, login="log_qc_head", groups="base.group_user,ddfsc_quality.group_ddfsc_quality_manager")
        cls.Log = cls.env["ddfsc.qc.log"].with_user(cls.qc_user)
        cls.shift = cls.env.ref("ddfsc_manufacturing.shift_1")

    def _log(self, xmlid, **values):
        return self.Log.create(dict(values, template_id=self.env.ref("ddfsc_quality.%s" % xmlid).id))

    def _row(self, log, subject):
        return log.line_ids.filtered(lambda line: line.subject == subject)

    def test_templates_from_the_forms(self):
        forms = self.env["ddfsc.qc.log.template"].search([]).mapped("form_no")
        for form in ("OF/QC/004", "OF/QC/005", "OF/QC/006", "OF/QC/011", "OF/QC/013", "OF/QC/014", "OF/QC/016"):
            self.assertIn(form, forms)

    def test_dryer_log_flags_out_of_standard_and_needs_a_remark(self):
        log = self._log("qc_log_dryer_115288", shift_id=self.shift.id)
        self.assertTrue(log.name.startswith("QCL/"))
        self.assertEqual(len(log.line_ids), 6)
        for line in log.line_ids:
            line.write({"value": (line.standard_min + line.standard_max) / 2})
        self.assertEqual(log.result_state, "pass")
        self._row(log, "Cooler").write({"value": 14.5})
        self.assertEqual(log.result_state, "fail")
        self.assertEqual(log.out_of_standard_count, 1)
        with self.assertRaises(UserError):
            log.action_submit()
        log.remark = "Cooler fan speed raised; product held for re-test."
        log.action_submit()
        with self.assertRaises(UserError):
            self._row(log, "Cooler").write({"value": 13.0})
        with self.assertRaises(AccessError):
            log.action_check()
        log.with_user(self.qc_head).action_check()
        self.assertEqual(log.state, "checked")
        self.assertEqual(log.checked_by_id, self.qc_head)

    def test_magnet_log_is_qualitative(self):
        log = self._log("qc_log_magnet", shift_id=self.shift.id)
        for line in log.line_ids:
            line.write({"text_value": "absent"})
        self.assertEqual(log.result_state, "pass")
        self._row(log, "Rework powder").write({"text_value": "Present"})
        self.assertEqual(log.result_state, "fail")

    def test_record_only_rows_pass_when_entered(self):
        log = self._log("qc_log_wheat_transfer")
        log.line_ids.write({"value": 11.2})
        self.assertEqual(log.result_state, "pass")

    def test_one_log_per_template_date_and_shift(self):
        self._log("qc_log_calibration", shift_id=self.shift.id)
        with self.assertRaises(ValidationError):
            self._log("qc_log_calibration", shift_id=self.shift.id)
        self._log("qc_log_water")
        with self.assertRaises(ValidationError):
            self._log("qc_log_water")

    def test_shift_log_needs_a_shift(self):
        with self.assertRaises(ValidationError):
            self._log("qc_log_magnet")
