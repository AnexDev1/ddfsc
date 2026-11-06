from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestDdfscWeighbridgeTicket(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({"name": "Weighbridge Test Wheat", "type": "consu"})
        cls.picking = cls.env["stock.picking"].create({
            "picking_type_id": cls.env.ref("stock.picking_type_in").id,
            "location_id": cls.env.ref("stock.stock_location_suppliers").id,
            "location_dest_id": cls.env.ref("stock.stock_location_stock").id,
        })
        cls.outgoing_picking = cls.env["stock.picking"].create({
            "picking_type_id": cls.env.ref("stock.picking_type_out").id,
            "location_id": cls.env.ref("stock.stock_location_stock").id,
            "location_dest_id": cls.env.ref("stock.stock_location_customers").id,
        })

    def _ticket(self):
        return self.env["ddfsc.weighbridge.ticket"].create({
            "operation_type": "incoming",
            "vehicle_plate": "3-12345 AA",
            "product_id": self.product.id,
            "picking_id": self.picking.id,
            "gross_weight": 20000,
        })

    def test_ticket_calculates_net_and_requires_paper_slip(self):
        ticket = self._ticket()
        ticket.action_record_first_weight()
        self.assertEqual(ticket.state, "first_recorded")
        ticket.tare_weight = 8000
        ticket.action_record_second_weight()
        self.assertEqual(ticket.net_weight, 12000)
        with self.assertRaises(UserError):
            ticket.action_complete()
        self.env["ir.attachment"].create({
            "name": "printed-slip.jpg",
            "type": "binary",
            "datas": b"dGVzdA==",
            "res_model": ticket._name,
            "res_id": ticket.id,
        })
        ticket.action_complete()
        self.assertEqual(ticket.state, "completed")
        self.assertEqual(ticket.completed_by_id, self.env.user)

    def test_tare_must_be_less_than_gross(self):
        ticket = self._ticket()
        ticket.action_record_first_weight()
        with self.assertRaises(ValidationError):
            ticket.write({"tare_weight": 20000})

    def test_outgoing_ticket_can_capture_tare_first(self):
        ticket = self.env["ddfsc.weighbridge.ticket"].create({
            "operation_type": "outgoing",
            "first_weight_kind": "tare",
            "vehicle_plate": "3-67890 AA",
            "product_id": self.product.id,
            "picking_id": self.outgoing_picking.id,
            "tare_weight": 7000,
        })
        ticket.action_record_first_weight()
        ticket.gross_weight = 19500
        ticket.action_record_second_weight()
        self.assertEqual(ticket.net_weight, 12500)
