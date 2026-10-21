from odoo.fields import Command
assert env.cr.dbname == 'ddfsc'
admin = env.ref('base.user_admin')
role = env.ref('sale_approval_workflow.group_store_manager')
role.write({'user_ids':[Command.link(admin.id)]})
assert admin.has_group('sale_approval_workflow.group_store_manager')
assert admin.has_group('stock.group_stock_manager')
env.cr.commit()
print('Verified: admin has Store Manager and Inventory Manager roles in ddfsc')
