from odoo.exceptions import ValidationError
assert env.cr.dbname=='ddfsc'
for dept,xmlid,code in [('pasta','product_pasta_long','PASTA'),('bread','product_bread_market','BREAD'),('biscuit','product_zebib','BISC-CN'),('flour','product_flour_g1','MILL')]:
    product=env.ref('ddfsc_manufacturing.'+xmlid).product_variant_id
    bom=env['mrp.bom'].search([('product_tmpl_id','=',product.product_tmpl_id.id),('active','=',True)],limit=1)
    line=env['mrp.workcenter'].search([('code','=',code)],limit=1)
    mo=env['mrp.production'].with_context(ddfsc_department=dept).create({'product_id':product.id,'product_qty':bom.product_qty,'product_uom_id':bom.product_uom_id.id,'bom_id':bom.id,'ddfsc_line_id':line.id})
    action=mo.action_request_ingredients()
    req=env['ddfsc.store.request'].with_context(**action['context']).create({})
    assert req.production_id==mo
    assert set(req.line_ids.product_id.ids)==set(bom.bom_line_ids.product_id.ids)
    req.action_submit_to_manager();req.action_approve_manager()
    assert req.picking_id
    again=mo.action_request_ingredients()
    assert again['res_id']==req.id
    try:mo.action_request_finished_goods();raise AssertionError('FG allowed before done')
    except ValidationError:pass
    print('PASS',dept,'recipe-filled request, correct product set, approval/transfer, reuse existing request, FG blocked before completion')
env.cr.rollback()
