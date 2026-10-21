from odoo.fields import Command
assert env.cr.dbname == 'ddfsc'
def loc(x): return env.ref('ddfsc_manufacturing.'+x)
store,mill,flour,fg,byproduct=[loc(x) for x in ['loc_store','loc_mill','loc_flour','loc_finished','loc_byproduct']]
wh=env['stock.warehouse'].search([('company_id','=',env.company.id)],limit=1)
wh.in_type_id.default_location_dest_id=store
wh.out_type_id.default_location_src_id=fg
for code,source,dest in [('store_requisition',store,mill),('fg_receiving',flour,fg),('byproduct_return',byproduct,store)]:
    env['stock.picking.type'].search([('ddfsc_document_type','=',code),('company_id','=',env.company.id)]).write({'default_location_src_id':source.id,'default_location_dest_id':dest.id})
# Correct only open receipts still directed at the generic parent stock.
open_receipts=env['stock.picking'].search([('picking_type_code','=','incoming'),('state','not in',['done','cancel']),('location_dest_id','=',wh.lot_stock_id.id),('company_id','=',env.company.id)])
for p in open_receipts:
    p.location_dest_id=store
    p.move_ids.filtered(lambda m:m.state not in ('done','cancel')).write({'location_dest_id':store.id})
    p.move_line_ids.write({'location_dest_id':store.id})
wheat=env.ref('ddfsc_manufacturing.product_wheat').product_variant_id
quants=env['stock.quant'].search([('product_id','=',wheat.id),('location_id','=',wh.lot_stock_id.id),('quantity','>',0)])
assert not any(quants.mapped('reserved_quantity')), 'Parent stock wheat is reserved; resolve reservation before moving'
qty=sum(quants.mapped('quantity'))
before=sum(env['stock.quant'].search([('product_id','=',wheat.id),('location_id.usage','=','internal')]).mapped('quantity'))
if qty:
    picking=env['stock.picking'].create({'picking_type_id':wh.int_type_id.id,'location_id':wh.lot_stock_id.id,'location_dest_id':store.id,'origin':'LOCATION CLEANUP: purchased wheat to General Store','move_ids':[Command.create({'product_id':wheat.id,'product_uom_qty':q.quantity,'product_uom':wheat.uom_id.id,'location_id':q.location_id.id,'location_dest_id':store.id}) for q in quants]})
    picking.action_confirm();picking.do_unreserve()
    for m in picking.move_ids:
        m.move_line_ids = [Command.create({'product_id':wheat.id,'product_uom_id':wheat.uom_id.id,'location_id':wh.lot_stock_id.id,'location_dest_id':store.id,'quantity':m.product_uom_qty})]
        m.picked=True
    picking.button_validate()
    assert picking.state=='done'
    print('Relocation:',picking.name,qty,wheat.uom_id.name)
after=sum(env['stock.quant'].search([('product_id','=',wheat.id),('location_id.usage','=','internal')]).mapped('quantity'))
assert abs(before-after)<0.0001
print('Wheat total preserved:',after,wheat.uom_id.name)
print('Open receipts corrected:',len(open_receipts))
env.cr.commit()


