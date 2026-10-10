"""Department locations used by the menus, store requests, and manufacturing orders."""

# Finished goods from every department move into this location.
FINISHED_GOODS_STORE = 'loc_finished'

DEPARTMENTS = {
    'pasta': {
        'label': 'Pasta',
        'line': 'PASTA',
        # Components: flour silo → pasta floor.
        'request_source': 'loc_flour_pasta',
        'request_location': 'loc_pasta',
        'component_location': 'loc_pasta',
        # Production output, then FG transfer → Finished Goods Store.
        'finished_location': 'loc_pasta_finished',
        'fg_source': 'loc_pasta_finished',
        'fg_dest': FINISHED_GOODS_STORE,
    },
    'bread': {
        'label': 'Bread',
        'line': 'BREAD',
        'request_source': 'loc_store',
        'request_location': 'loc_bread',
        'component_location': 'loc_bread',
        'finished_location': 'loc_bread_finished',
        'fg_source': 'loc_bread_finished',
        'fg_dest': FINISHED_GOODS_STORE,
    },
    'biscuit': {
        'label': 'Biscuit',
        'line': 'BISC-CN',
        'request_source': 'loc_store',
        'request_location': 'loc_biscuit',
        'component_location': 'loc_biscuit',
        'finished_location': 'loc_biscuit_finished',
        'fg_source': 'loc_biscuit_finished',
        'fg_dest': FINISHED_GOODS_STORE,
    },
    'flour': {
        'label': 'Flour',
        'line': 'MILL',
        'request_source': 'loc_store',
        'request_location': 'loc_mill',
        'component_location': 'loc_mill',
        'finished_location': 'loc_flour',
        'fg_source': 'loc_flour',
        'fg_dest': FINISHED_GOODS_STORE,
        # Mill by-products wait here, then return to General Store.
        'byproduct_location': 'loc_byproduct',
        'byproduct_source': 'loc_byproduct',
        'byproduct_dest': 'loc_store',
    },
}


def selection(model=None):
    """Selection callable for fields.Selection; Odoo passes the model."""
    return [(key, value['label']) for key, value in DEPARTMENTS.items()]


def location(env, department, kind):
    spec = DEPARTMENTS.get(department)
    if not spec:
        return env['stock.location']
    xmlid = spec.get(kind)
    if not xmlid:
        return env['stock.location']
    return env.ref('ddfsc_manufacturing.%s' % xmlid, raise_if_not_found=False) or env['stock.location']
