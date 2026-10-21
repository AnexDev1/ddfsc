assert env.cr.dbname == 'ddfsc'
po=env['purchase.order'].search([('name','=','PO-L2600001')],limit=1)
active=po.picking_ids.filtered(lambda p:p.state not in ('done','cancel'))
if not active:
    po._create_picking()
    active=po.picking_ids.filtered(lambda p:p.state not in ('done','cancel'))
for p in active:
    p.location_dest_id=env.ref('ddfsc_manufacturing.loc_store')
    p.move_ids.write({'location_dest_id':p.location_dest_id.id})
    print('Replacement receipt:',p.name,'State:',p.state,'ID:',p.id)
env.cr.commit()
