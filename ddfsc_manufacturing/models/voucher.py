"""Data for the printed plant vouchers.

The factory runs on numbered, multi-copy paper forms. Each printout keeps the
form's title, form number, columns, signature boxes and copy distribution, so
a printed voucher can replace the paper pad. The template is generic; this
module decides what each document prints.
"""

import pytz

from odoo import _, fields, models

from .ddfsc_department import DEPARTMENTS
from .ddfsc_shift import factory_tz

COMPANY_NAME = 'Dire Dawa Food Complex Share Company'

# Titles, form numbers and copy distribution as printed on the factory pads.
FORMS = {
    'store_issue': {
        'title': 'Store Issued Voucher',
        'form_no': '',
        'distribution': 'Original – Accounts (White) · 1st Copy – Requesting Unit (Pink) · '
                        '2nd Copy – Store Recording Section (Blue) · 3rd Copy – Store Keeper (Yellow) · '
                        '4th Copy – Pad (Green)',
        'signatures': ['Prepared by', 'Issued by', 'Checked by', 'Approved by', 'Received the above goods'],
        'price': True,
    },
    'flour_transfer': {
        'title': 'Daily Wheat Flour Transfer Voucher',
        'form_no': '',
        'distribution': 'Original – Accounts · 1st Copy – Requisition · 2nd Copy – Store Recording Section · '
                        '3rd Copy – Store Keeper',
        'signatures': ['Delivered by (Flour Store)', 'Received by (Production Head)'],
    },
    'fg_receiving': {
        'title': 'Finished Goods Receiving Note',
        'form_no': 'FDOF/FD/844',
        'distribution': 'Original – Accounts · 1st Copy – Production (Pink) · 2nd Copy – Store Recording '
                        'Section (Green) · 3rd Copy – Store Keeper (Blue) · 4th Copy – Pad (Light Yellow)',
        'signatures': ['Delivered by', 'Received by', 'Checked by', 'Approved by'],
    },
    'returned_goods': {
        'title': 'Finished Products & Other Returned Goods Receiving Note',
        'form_no': '',
        'distribution': 'Original – Accounts · Yellow – User · Green – Inventory Control Section · '
                        'Pink – Store · Blue – Pad',
        'signatures': ['Returned by', 'Checked by', 'Received by'],
        'reason': True,
    },
    'wheat_receiving': {
        'title': 'Wheat Receiving Note',
        'form_no': 'PAOF/PA/505',
        'distribution': '1st Copy – Account · 2nd Copy – Store Records · 3rd Copy – Purchase · '
                        '4th Copy – Store Recording · 5th Copy – Pad',
        'signatures': ['Received by', 'Checked by', 'Approved by'],
        'price': True,
        'bags': True,
    },
    'goods_receiving': {
        'title': 'Goods Receiving Note',
        'form_no': '',
        'distribution': '1st Copy – Accounts · 2nd Copy – Stock Records · 3rd Copy – Purchase · 4th Copy – Pad',
        'signatures': ['Prepared by', 'Checked & Received by', 'Approved by'],
        'price': True,
    },
    'delivery_order': {
        'title': 'Delivery Order',
        'form_no': 'PAOF/PA/534',
        'distribution': 'White – Original Customer · Pink 1st Copy – Account Stock Recording · '
                        'Blue 2nd Copy – Store Recording Section · Green 3rd Copy – Gate Pass · '
                        'Yellow 4th Copy – Property Admin · Pink 5th Copy – Pad Commercial Dep.',
        'signatures': ['Delivered by', 'Checked by', 'Approved by', 'Received the above goods in good condition'],
        'price': True,
    },
    'transfer': {
        'title': 'Stock Transfer Voucher',
        'form_no': '',
        'distribution': 'Original – Accounts · 1st Copy – Store Recording Section · 2nd Copy – Pad',
        'signatures': ['Delivered by', 'Checked by', 'Received by'],
    },
    'store_requisition': {
        'title': 'Store Requisition',
        'form_no': 'FAOF/PA522',
        'distribution': 'Original – Store · 1st Copy – Requesting Department · 2nd Copy – Pad',
        'signatures': ['Requested by', 'Approved by', 'Received by'],
    },
}


def _name(user):
    return user.name if user else ''


def _date(record, value):
    """Day/month/year in the factory's timezone, as written on the pads."""
    if not value:
        return ''
    return pytz.utc.localize(value).astimezone(factory_tz(record.env)).strftime('%d/%m/%Y')


class StockMove(models.Model):
    _inherit = 'stock.move'

    ddfsc_bags = fields.Integer(string='No. of Bags', help='Bags counted at receiving or loading.')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Paper-document details the receiving and dispatch forms ask for.
    ddfsc_supplier_invoice = fields.Char(string='Supplier Invoice No.')
    ddfsc_supplier_delivery = fields.Char(string='Supplier Delivery Order No.')
    ddfsc_vehicle_plate = fields.Char(string='Truck Plate / Wagon No.')
    ddfsc_driver_name = fields.Char(string="Driver's Name")
    ddfsc_receiver_name = fields.Char(string='Received by (Name)', help='Customer representative who collects the goods.')
    ddfsc_receiver_identification = fields.Char(string='Receiver Identification', help='ID card or licence number.')
    ddfsc_customer_reference = fields.Char(string='Customer / Cash Sales Ref.', help='e.g. CS-02302/26 or CRSVH-00481-26.')
    ddfsc_paper_voucher = fields.Char(string='Paper Voucher No.',
                                      help='Serial of the pre-printed pad, while paper and system run side by side.')

    def _ddfsc_voucher_kind(self):
        self.ensure_one()
        doc = self.ddfsc_document_type
        if self.picking_type_code == 'incoming':
            wheat = self.env.ref('ddfsc_manufacturing.product_wheat', raise_if_not_found=False)
            if wheat and self.move_ids.product_id.product_tmpl_id == wheat:
                return 'wheat_receiving'
            return 'goods_receiving'
        if self.picking_type_code == 'outgoing':
            return 'delivery_order'
        if doc == 'fg_receiving':
            return 'fg_receiving'
        if doc in ('byproduct_return', 'material_return'):
            return 'returned_goods'
        if doc == 'store_requisition':
            flour_store = self.env.ref('ddfsc_manufacturing.loc_flour', raise_if_not_found=False)
            if flour_store and self.location_id == flour_store:
                return 'flour_transfer'
            return 'store_issue'
        return 'transfer'

    def _ddfsc_weighbridge_ticket(self):
        self.ensure_one()
        if 'ddfsc.weighbridge.ticket' not in self.env:
            return False
        return self.env['ddfsc.weighbridge.ticket'].sudo().search([('picking_id', '=', self.id)], limit=1)

    def _ddfsc_voucher(self):
        """Everything the generic voucher template prints for this transfer."""
        self.ensure_one()
        kind = self._ddfsc_voucher_kind()
        form = dict(FORMS[kind])
        request = self.ddfsc_store_request_id
        rows = [(_('Date'), _date(self, self.date_done or self.scheduled_date))]
        if self.ddfsc_paper_voucher:
            rows.append((_('Paper Voucher No.'), self.ddfsc_paper_voucher))
        if kind in ('wheat_receiving', 'goods_receiving'):
            ticket = self._ddfsc_weighbridge_ticket()
            rows += [
                (_('Supplier'), self.partner_id.display_name or ''),
                (_('Supplier Invoice No.'), self.ddfsc_supplier_invoice or ''),
                (_('Purchase Order No.'), self.purchase_id.name if 'purchase_id' in self._fields and self.purchase_id else ''),
                (_('Supplier Delivery Order No.'), self.ddfsc_supplier_delivery or ''),
                (_('Truck Plate / Wagon No.'), self.ddfsc_vehicle_plate or (ticket.vehicle_plate if ticket else '')),
                (_("Driver's Name"), self.ddfsc_driver_name or (ticket.driver_name if ticket else '')),
            ]
            if ticket:
                rows.append((_('Weighbridge Ticket / Net kg'), '%s / %s' % (ticket.name, ticket.net_weight)))
        elif kind == 'delivery_order':
            rows += [
                (_('Customer (M/S)'), self.partner_id.display_name or ''),
                (_("Customer's Ref. No."), self.ddfsc_customer_reference or self.origin or ''),
                (_('Truck Plate No.'), self.ddfsc_vehicle_plate or ''),
                (_('Receiver Name'), self.ddfsc_receiver_name or ''),
                (_('Identification'), self.ddfsc_receiver_identification or ''),
            ]
        else:
            rows += [
                (_('From'), self.location_id.display_name),
                (_('To'), self.location_dest_id.display_name),
            ]
            if request:
                department = DEPARTMENTS.get(request.ddfsc_department, {}).get('label')
                rows += [
                    (_('Department'), department or ''),
                    (_('Requisition No.'), request.name),
                ]
                if 'production_id' in request._fields and request.production_id:
                    rows.append((_('Production Order'), request.production_id.name))
            elif self.origin:
                rows.append((_('Source Document'), self.origin))
        lines = []
        for move in self.move_ids.filtered(lambda item: item.state != 'cancel'):
            quantity = move.quantity if self.state == 'done' else move.product_uom_qty
            price = move.product_id.uom_id._compute_price(move.product_id.standard_price, move.product_uom)
            sale_line = move.sale_line_id if 'sale_line_id' in move._fields else False
            if kind == 'delivery_order' and sale_line:
                price = sale_line.price_unit
            lots = ', '.join(move.move_line_ids.lot_id.mapped('name'))
            lines.append({
                'code': move.product_id.default_code or '',
                'description': move.product_id.name + (' — %s' % lots if lots else ''),
                'uom': move.product_uom.name,
                'quantity': quantity,
                'price': price if form.get('price') else 0.0,
                'total': price * quantity if form.get('price') else 0.0,
                'bags': move.ddfsc_bags or '',
            })
        form.update({
            'company': COMPANY_NAME,
            'voucher_no': self.name,
            'rows': rows,
            'lines': lines,
            'reason': (request.return_reason if request and 'return_reason' in request._fields else '') or '',
            'grand_total': sum(line['total'] for line in lines),
            'names': {'Prepared by': _name(request.user_id) if request else _name(self.create_uid),
                      'Requested by': _name(request.user_id) if request else ''},
        })
        return form


class StoreRequest(models.Model):
    _inherit = 'ddfsc.store.request'

    def _ddfsc_voucher(self):
        self.ensure_one()
        form = dict(FORMS['store_requisition'])
        department = DEPARTMENTS.get(self.ddfsc_department, {}).get('label')
        request_type = dict(self._fields['request_type'].selection).get(self.request_type)
        rows = [
            (_('Date'), _date(self, self.date_request)),
            (_('Requesting Department'), department or ''),
            (_('Request Type'), request_type or ''),
            (_('From'), self.location_id.display_name),
            (_('To'), self.location_dest_id.display_name),
        ]
        if 'production_id' in self._fields and self.production_id:
            rows.append((_('Purpose'), _('Production order %s') % self.production_id.name))
        if self.return_reason:
            rows.append((_('Reason'), self.return_reason))
        form.update({
            'company': COMPANY_NAME,
            'voucher_no': self.name,
            'rows': rows,
            'lines': [{
                'code': line.product_id.default_code or '',
                'description': line.product_id.name + (' — %s' % line.lot_id.name if line.lot_id else ''),
                'uom': line.product_uom_id.name,
                'quantity': line.product_uom_qty,
                'price': 0.0, 'total': 0.0,
            } for line in self.line_ids],
            'reason': '',
            'grand_total': 0.0,
            'names': {'Requested by': _name(self.user_id)},
        })
        return form


class StockLot(models.Model):
    _inherit = 'stock.lot'

    def _ddfsc_hold_release(self):
        """OF/QC/019 Product Holding form, or OF/QC/018A Product Release form."""
        self.ensure_one()
        held = self.ddfsc_quality_state in ('hold', 'rejected', 'pending')
        moisture = ''
        inspection = self.active_qc_inspection_id if 'active_qc_inspection_id' in self._fields else False
        if inspection:
            line = inspection.line_ids.filtered(
                lambda item: item.plan_line_id.check_type == 'moisture' and item.is_measured)[:1]
            moisture = '%g %%' % line.measured_value if line else ''
        else:
            check = self.quality_check_ids.filtered(
                lambda item: item.check_type == 'moisture' and item.is_measured)[:1]
            moisture = '%g %%' % check.measured_value if check else ''
        status = dict(self._fields['ddfsc_quality_state'].selection).get(self.ddfsc_quality_state)
        decided = self.quality_decision_date or self.write_date
        return {
            'company': COMPANY_NAME,
            'held': held,
            'title': 'Product Holding Form' if held else 'Product Release Form',
            'form_no': 'OF/QC/019' if held else 'OF/QC/018A',
            'rows': [
                (_('Date'), _date(self, decided)),
                (_('Product Name'), self.product_id.display_name),
                (_('Batch No.'), self.name),
                (_('Product Location'), self.ddfsc_quality_location or ''),
                (_('Quality Status'), status or ''),
                (_('Moisture Content'), moisture),
                (_('Quantity'), '%g %s' % (self.product_qty, self.product_uom_id.name)),
                (_('Reason') if held else _('Remark'), self.quality_release_note or ''),
            ],
            'by_label': 'Hold by' if held else 'Released by',
            'by_name': _name(self.quality_decision_by_id),
        }
