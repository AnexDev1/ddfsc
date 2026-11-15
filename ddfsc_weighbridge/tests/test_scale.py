from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWeighbridgeScale(TransactionCase):
    """Readings pushed by the bridge program and captured on tickets by an operator."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.device = Users.create({
            "name": "Weighbridge Device", "login": "scale_device_test",
            "group_ids": [Command.set([cls.env.ref("base.group_user").id,
                                       cls.env.ref("ddfsc_weighbridge.group_ddfsc_weighbridge_device").id])],
        })
        cls.operator = Users.create({
            "name": "Weighbridge Operator", "login": "scale_operator_test",
            "group_ids": [Command.set([cls.env.ref("base.group_user").id,
                                       cls.env.ref("ddfsc_weighbridge.group_ddfsc_weighbridge_user").id])],
        })
        cls.scale = cls.env["ddfsc.weighbridge.scale"].create({"name": "Test Scale", "code": "TST"})
        cls.product = cls.env["product.product"].create({
            "name": "Scale Test Wheat", "default_code": "SCALE-WHEAT", "type": "consu"})
        cls.picking = cls.env["stock.picking"].create({
            "picking_type_id": cls.env.ref("stock.picking_type_in").id,
            "location_id": cls.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": cls.env.ref("stock.stock_location_stock").id,
        })

    def _push(self, weight, stable=True, dsd=None):
        self.env["ddfsc.weighbridge.scale"].with_user(self.device).push_reading(
            "TST", weight, stable=stable, raw="ST,GS,%+08d kg" % weight, dsd=dsd)

    def _ticket(self):
        return self.env["ddfsc.weighbridge.ticket"].with_user(self.operator).create({
            "operation_type": "incoming", "vehicle_plate": "3-98673", "product_id": self.product.id,
            "picking_id": self.picking.id, "scale_id": self.scale.id,
        })

    def test_capture_both_weights_from_the_scale(self):
        ticket = self._ticket()
        self._push(38760, dsd="012954")
        ticket.action_capture_first_weight()
        self.assertEqual(ticket.gross_weight, 38760)
        self.assertEqual((ticket.first_weight_source, ticket.first_dsd), ("scale", "012954"))
        self._push(15240, dsd="012955")
        ticket.action_capture_second_weight()
        self.assertEqual(ticket.net_weight, 23520)
        self.assertEqual(ticket.second_weight_source, "scale")
        # Weights from the indicator (with DSD numbers) need no photo of the slip.
        ticket.action_complete()
        self.assertEqual(ticket.state, "completed")

    def test_typed_weights_still_need_the_slip(self):
        ticket = self._ticket()
        ticket.gross_weight = 20000
        ticket.action_record_first_weight()
        self.assertEqual(ticket.first_weight_source, "manual")
        ticket.tare_weight = 8000
        ticket.action_record_second_weight()
        with self.assertRaises(UserError):
            ticket.action_complete()

    def test_refuses_moving_old_or_empty_readings(self):
        ticket = self._ticket()
        self._push(38760, stable=False)
        with self.assertRaises(UserError):
            ticket.action_capture_first_weight()
        self._push(5)
        with self.assertRaises(UserError):
            ticket.action_capture_first_weight()
        self._push(38760)
        self.scale.last_read_at = fields.Datetime.now() - timedelta(minutes=5)
        self.assertFalse(self.scale.is_online)
        with self.assertRaises(UserError):
            ticket.action_capture_first_weight()

    def test_only_the_device_account_sends_readings(self):
        with self.assertRaises(AccessError):
            self.env["ddfsc.weighbridge.scale"].with_user(self.operator).push_reading("TST", 1000)
        with self.assertRaises(UserError):
            self.env["ddfsc.weighbridge.scale"].with_user(self.device).push_reading("NOPE", 1000)
