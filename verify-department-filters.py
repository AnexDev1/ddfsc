from odoo.exceptions import ValidationError
from odoo.fields import Command
assert env.cr.dbname=='ddfsc'
def product(x):return env.ref('ddfsc_manufacturing.'+x).product_variant_id
for dept in ['flour','pasta','bread','biscuit']:
    r=env['ddfsc.store.request'].new({'ddfsc_department':dept,'request_type':'component'})
    print(dept,'ingredients:',', '.join(r.allowed_product_ids.mapped('name')))
    if dept=='bread':
        print('DEBUG bread IDs',r.allowed_product_ids.ids,product('product_flour_g1').ids); assert product('product_flour_g1').id in r.allowed_product_ids.ids
        assert product('product_flour_g2').id not in r.allowed_product_ids.ids
    if dept=='pasta':
        assert product('product_flour_g1').id not in r.allowed_product_ids.ids
        assert product('product_flour_g2').id not in r.allowed_product_ids.ids
try:
    with env.cr.savepoint():
        env['ddfsc.store.request'].create({'ddfsc_department':'bread','request_type':'component','line_ids':[Command.create({'product_id':product('product_flour_g2').id,'product_uom_qty':1})]})
        raise AssertionError('Wrong flour was accepted')
except ValidationError:
    print('PASS: wrong bread flour rejected on save')
line=env['mrp.workcenter'].search([('code','=','BREAD')],limit=1)
mo=env['mrp.production'].new({'ddfsc_line_id':line.id,'product_id':product('product_pasta_long').id})
try:
    mo._check_department_output()
    raise AssertionError('Wrong output accepted')
except ValidationError:
    print('PASS: pasta output rejected on bread production line')
for code,expected in [('PASTA','product_pasta_long'),('MAC','product_pasta_short')]:
    line=env['mrp.workcenter'].search([('code','=',code)],limit=1)
    mo=env['mrp.production'].new({'ddfsc_line_id':line.id})
    assert mo.allowed_output_ids.ids==product(expected).ids
    print('PASS:',code,'output restriction')
env.cr.rollback()


