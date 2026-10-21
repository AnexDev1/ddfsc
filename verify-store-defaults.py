assert env.cr.dbname == 'ddfsc'
Request=env['ddfsc.store.request']
for department in ['flour','pasta','bread','biscuit']:
    for kind in ['component','finished_goods']:
        vals=Request.with_context(default_ddfsc_department=department,default_request_type=kind).default_get(['ddfsc_department','request_type','location_id','location_dest_id'])
        source=env['stock.location'].browse(vals['location_id']).name
        destination=env['stock.location'].browse(vals['location_dest_id']).name
        print(department,kind,source,'->',destination)
        assert vals['location_id'] != vals['location_dest_id']
for q in env['stock.quant'].search([('product_id','=',env.ref('ddfsc_manufacturing.product_wheat').product_variant_id.id),('location_id.usage','=','internal'),('quantity','>',0)]):
    print('Wheat:',q.location_id.complete_name,q.quantity,q.product_id.uom_id.name)
wh=env['stock.warehouse'].search([('company_id','=',env.company.id)],limit=1)
assert wh.in_type_id.default_location_dest_id==env.ref('ddfsc_manufacturing.loc_store')
assert wh.out_type_id.default_location_src_id==env.ref('ddfsc_manufacturing.loc_finished')
print('Receipt and delivery defaults verified')
