assert env.cr.dbname == 'ddfsc'
product = env.ref('ddfsc_manufacturing.product_wheat').product_variant_id
location = env.ref('ddfsc_manufacturing.loc_mill')
qty = env.ref('uom.product_uom_kgm')._compute_quantity(1000, product.uom_id)
assert product.tracking == 'none', 'Tracked wheat requires a test lot'
quant = env['stock.quant'].search([('product_id','=',product.id),('location_id','=',location.id),('lot_id','=',False),('package_id','=',False),('owner_id','=',False)], limit=1)
if not quant:
    quant = env['stock.quant'].with_context(inventory_mode=True).create({'product_id':product.id,'location_id':location.id})
quant.with_context(inventory_mode=True).write({'inventory_quantity':quant.quantity + qty})
quant.with_context(inventory_name='TEST STOCK: manually add 1000 kg wheat to Flour Mill Floor').action_apply_inventory()
env.cr.commit()
print('Database:',env.cr.dbname,'Product:',product.display_name,'Location:',location.complete_name,'Added:',qty,product.uom_id.name,'Available:',quant.quantity-quant.reserved_quantity)
