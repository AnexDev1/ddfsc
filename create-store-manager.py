from odoo.fields import Command
assert env.cr.dbname == 'ddfsc'
group = env.ref('sale_approval_workflow.group_store_manager')
user = env['res.users'].with_context(no_reset_password=True).create({'name':'Store Manager','login':'store.manager','password':'StoreTest123!','company_id':env.company.id,'company_ids':[Command.set(env.company.ids)],'group_ids':[Command.set([env.ref('base.group_user').id,group.id])],'allowed_warehouse_ids':[Command.set(env['stock.warehouse'].search([('company_id','=',env.company.id)]).ids)]})
assert user.has_group('sale_approval_workflow.group_store_manager')
assert user.has_group('stock.group_stock_manager')
print('Created Store Manager:',user.login,'Warehouses:',user.allowed_warehouse_ids.mapped('name'))
print('Accessible receipts:',env['stock.picking'].with_user(user).search_count([('picking_type_code','=','incoming')]))
env.cr.commit()
