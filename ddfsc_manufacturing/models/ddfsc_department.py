"""Department locations used by the menus, store requests, and manufacturing orders."""

DEPARTMENTS = {
    'pasta': {
        'label': 'Pasta',
        'line': 'PASTA',
        # Flour is requested from the pasta flour silo onto the pasta floor.
        'request_source': 'loc_flour_pasta',
        'request_location': 'loc_pasta',
        'component_location': 'loc_pasta',
        # Finished pasta waits here before Finished Goods Store.
        'finished_location': 'loc_pasta_finished',
    },
    'bread': {
        'label': 'Bread',
        'line': 'BREAD',
        'request_source': 'loc_store',
        'request_location': 'loc_bread',
        'component_location': 'loc_bread',
        'finished_location': 'loc_bread',
    },
    'biscuit': {
        'label': 'Biscuit',
        'line': 'BISC-CN',
        'request_source': 'loc_store',
        'request_location': 'loc_biscuit',
        'component_location': 'loc_biscuit',
        'finished_location': 'loc_biscuit',
    },
    'flour': {
        'label': 'Flour',
        'line': 'MILL',
        'request_source': 'loc_store',
        'request_location': 'loc_mill',
        'component_location': 'loc_mill',
        'finished_location': 'loc_flour',
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
