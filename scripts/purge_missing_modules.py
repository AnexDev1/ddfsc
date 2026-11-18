# Runs inside `odoo shell` (see purge-missing-modules.sh). Removes modules whose
# code is gone: everything they created (groups, menus, views, actions, fields,
# tables) through Odoo's own uninstall, then their line in the Apps list.
# Lines starting with "PURGE" are read by the wrapper script.
import os

from odoo.modules.module import get_modules

apply_changes = os.environ.get('PURGE_APPLY') == '1'
asked = [name for name in os.environ.get('PURGE_MODULES', '').split() if name]
on_disk = set(get_modules())
stop = None

missing_core = [name for name in ('base', 'web', 'mail', 'stock') if name not in on_disk]
if missing_core:
    stop = 'core modules %s were not found on disk: the addons path was not read correctly' % missing_core

Module = env['ir.module.module'].with_context(active_test=False)
# to_buy: Odoo's own Enterprise placeholders shown in Apps ("Upgrade"); they never have code here.
modules = Module.search([('name', 'in', asked)]) if asked else Module.search([('to_buy', '=', False)]).filtered(
    lambda module: module.name not in on_disk)
if not stop:
    with_code = modules.filtered(lambda module: module.name in on_disk)
    if with_code:
        stop = 'these modules still have code, uninstall them from Apps instead: %s' % ', '.join(with_code.mapped('name'))

for module in modules.sorted('name'):
    print('PURGE-MODULE %-40s %-12s %s' % (module.name, module.state, module.shortdesc or ''))

if not stop and modules:
    dependency = env['ir.module.module.dependency'].search([('name', 'in', modules.mapped('name'))])
    blockers = dependency.mapped('module_id').filtered(
        lambda module: module not in modules and module.state in ('installed', 'to upgrade', 'to install'))
    if blockers:
        stop = 'these installed modules depend on them: %s' % ', '.join(
            '%s (needs %s)' % (module.name, ', '.join(module.dependencies_id.filtered(
                lambda dep: dep.name in modules.mapped('name')).mapped('name'))) for module in blockers)

if stop:
    print('PURGE-STOP ' + stop)
elif not modules:
    print('PURGE-NOTHING')
elif apply_changes:
    names = modules.mapped('name')
    modules._remove_copied_views()
    modules.module_uninstall()
    env['ir.model.data'].search([('model', '=', 'ir.module.module'), ('res_id', 'in', modules.ids)]).unlink()
    modules.unlink()
    env.cr.commit()
    print('PURGE-DONE %d modules removed: %s' % (len(names), ', '.join(names)))
else:
    print('PURGE-FOUND %d' % len(modules))
