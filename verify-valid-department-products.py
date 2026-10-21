from odoo.fields import Command
r=env['ddfsc.store.request'].create({'ddfsc_department':'bread','request_type':'component','line_ids':[Command.create({'product_id':env.ref('ddfsc_manufacturing.product_flour_g1').product_variant_id.id,'product_uom_qty':1})]})
r._check_department_products()
print('PASS: valid Grade 1 bread request accepted')
line=env['mrp.workcenter'].search([('code','=','BREAD')],limit=1)
mo=env['mrp.production'].new({'ddfsc_line_id':line.id,'product_id':env.ref('ddfsc_manufacturing.product_bread_market').product_variant_id.id})
mo._check_department_output()
print('PASS: valid bread output accepted')
env.cr.rollback()
