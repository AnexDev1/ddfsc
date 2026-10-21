from odoo.fields import Command
assert env.cr.dbname=='ddfsc'
wheat=env.ref('ddfsc_manufacturing.product_wheat').product_variant_id
store=env.ref('ddfsc_manufacturing.loc_store'); mill=env.ref('ddfsc_manufacturing.loc_mill')
qty=11.75
p=env['stock.picking'].create({'picking_type_id':env.ref('ddfsc_manufacturing.picking_type_store_requisition').id,'location_id':store.id,'location_dest_id':mill.id,'origin':'LOCATION CLEANUP: preserve pre-existing mill wheat','move_ids':[Command.create({'product_id':wheat.id,'product_uom_qty':qty,'product_uom':wheat.uom_id.id,'location_id':store.id,'location_dest_id':mill.id})]})
p.action_confirm();p.do_unreserve()
for m in p.move_ids:
    m.move_line_ids=[Command.create({'product_id':wheat.id,'product_uom_id':wheat.uom_id.id,'location_id':store.id,'location_dest_id':mill.id,'quantity':qty})]
    m.picked=True
p.button_validate();assert p.state=='done'
for q in env['stock.quant'].search([('product_id','=',wheat.id),('location_id.usage','=','internal'),('quantity','>',0)]):print(q.location_id.complete_name,q.quantity,wheat.uom_id.name)
assert not env['stock.quant'].search([('product_id','=',wheat.id),('location_id','=',env.ref('stock.stock_location_stock').id),('quantity','!=',0)])
env.cr.commit()
