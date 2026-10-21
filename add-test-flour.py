from odoo import fields
assert env.cr.dbname == 'ddfsc'
location = env.ref('ddfsc_manufacturing.loc_flour')
kg = env.ref('uom.product_uom_kgm')
for xmlid in ['product_flour_g1','product_flour_g2','product_flour_lcp','product_flour_scp']:
    template = env.ref('ddfsc_manufacturing.' + xmlid)
    product = template.product_variant_id
    qty = kg._compute_quantity(1000, product.uom_id)
    quant = env['stock.quant'].search([('product_id','=',product.id),('location_id','=',location.id),('lot_id','=',False),('package_id','=',False),('owner_id','=',False)], limit=1)
    if not quant:
        quant = env['stock.quant'].with_context(inventory_mode=True).create({'product_id':product.id,'location_id':location.id})
    quant.with_context(inventory_mode=True).write({'inventory_quantity':quant.quantity + qty})
    quant.with_context(inventory_name='TEST STOCK: manually add 1000 kg flour for flow testing').action_apply_inventory()
    print(product.display_name, 'added', qty, product.uom_id.name, 'total', quant.quantity)
env.cr.commit()
