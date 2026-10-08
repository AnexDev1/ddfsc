"""Department locations used by the menus, store requisitions, and manufacturing orders."""

DEPARTMENTS = {
    'pasta': {
        'label': 'Pasta',
        'line': 'PASTA',
        'request_location': 'loc_pasta',
        'component_location': 'loc_flour_pasta',
        'finished_location': 'loc_pasta',
    },
    'bread': {
        'label': 'Bread',
        'line': 'BREAD',
        'request_location': 'loc_bread',
        'component_location': 'loc_bread',
        'finished_location': 'loc_bread',
    },
    'biscuit': {
        'label': 'Biscuit',
        'line': 'BISC-CN',
        'request_location': 'loc_biscuit',
        'component_location': 'loc_biscuit',
        'finished_location': 'loc_biscuit',
    },
    'flour': {
        'label': 'Flour',
        'line': 'MILL',
        'request_location': 'loc_mill',
        'component_location': 'loc_mill',
        'finished_location': 'loc_flour',
    },
}


def selection():
    return [(key, value['label']) for key, value in DEPARTMENTS.items()]


def location(env, department, kind):
    spec = DEPARTMENTS.get(department)
    if not spec:
        return env['stock.location']
    return env.ref('ddfsc_manufacturing.%s' % spec[kind])
