from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    ddfsc_workcenter_id = fields.Many2one('mrp.workcenter', string='Production Line')
    ddfsc_downtime_code = fields.Selection(
        [
            ('mixer', 'Mixer'),
            ('die', 'Die'),
            ('oven', 'Oven'),
            ('packing', 'Packing machine'),
        ],
        string='Downtime Code',
    )

    @api.model
    def _sync_plant_maintenance(self):
        """Register the biscuit-line machines and their weekly and monthly checks."""
        team = self.env['maintenance.team'].search([('name', '=', 'Plant Maintenance')], limit=1)
        if not team:
            team = self.env['maintenance.team'].create({'name': 'Plant Maintenance'})
        category = self.env['maintenance.equipment.category'].search([('name', '=', 'Biscuit Line')], limit=1)
        if not category:
            category = self.env['maintenance.equipment.category'].create({'name': 'Biscuit Line'})
        floor = self.env.ref('ddfsc_manufacturing.loc_biscuit')
        machines = [
            ('Mixer', 'MIXER', 'mixer'),
            ('Dough Lifter', 'LIFTER', False),
            ('Dough Cart', 'CART', False),
            ('Dough Thickness Roller', 'ROLLER', False),
            ('Die', 'DIE', 'die'),
            ('Scrap Return', 'SCRAP', False),
            ('Oven', 'OVEN', 'oven'),
            ('Conveyor', 'CONVEYOR', False),
            ('Packing Machine', 'PACK', 'packing'),
        ]
        self._load_line_machines(team, category, floor, ('BISC-CN', 'BISC-OR'), machines)
        self._load_line_machines(
            team,
            self._equipment_category('Flour Mill'),
            self.env.ref('ddfsc_manufacturing.loc_mill'),
            ('MILL',),
            [
                ('Roller Mill', 'ROLLER', False),
                ('Sifter', 'SIFTER', False),
                ('Magnetic Separator', 'MAGNET', False),
                ('Conditioning Bin', 'CONDITION', False),
            ],
        )
        self._load_line_machines(
            team,
            self._equipment_category('Bread Line'),
            self.env.ref('ddfsc_manufacturing.loc_bread'),
            ('BREAD',),
            [
                ('Mixer', 'MIXER', 'mixer'),
                ('Oven', 'OVEN', 'oven'),
                ('Conveyor', 'CONVEYOR', False),
            ],
        )
        self._load_line_machines(
            team,
            self._equipment_category('Pasta Line'),
            self.env.ref('ddfsc_manufacturing.loc_pasta'),
            ('PASTA',),
            [
                ('Extruder', 'EXTRUDER', 'die'),
                ('Dryer', 'DRYER', False),
                ('Packing Scale', 'PACK', 'packing'),
            ],
        )
        self._load_line_machines(
            team,
            self._equipment_category('Macaroni Line'),
            self.env.ref('ddfsc_manufacturing.loc_macaroni'),
            ('MAC',),
            [
                ('Extruder', 'EXTRUDER', 'die'),
                ('Dryer', 'DRYER', False),
                ('Packing Scale', 'PACK', 'packing'),
            ],
        )

    def _equipment_category(self, name):
        category = self.env['maintenance.equipment.category'].search([('name', '=', name)], limit=1)
        if not category:
            category = self.env['maintenance.equipment.category'].create({'name': name})
        return category

    def _load_line_machines(self, team, category, floor, line_codes, machines):
        for line_code in line_codes:
            line = self.env['mrp.workcenter'].search([('code', '=', line_code)], limit=1)
            for name, suffix, downtime_code in machines:
                serial = '%s-%s' % (line_code, suffix)
                equipment = self.search([('serial_no', '=', serial)], limit=1)
                vals = {
                    'name': '%s %s' % (line.name, name),
                    'serial_no': serial,
                    'category_id': category.id,
                    'maintenance_team_id': team.id,
                    'ddfsc_workcenter_id': line.id,
                    'ddfsc_downtime_code': downtime_code or False,
                    'location_id': floor.id,
                }
                if equipment:
                    equipment.write(vals)
                else:
                    equipment = self.create(vals)
                for unit, label in (('week', 'Weekly'), ('month', 'Monthly')):
                    existing = self.env['maintenance.request'].search([
                        ('equipment_id', '=', equipment.id),
                        ('maintenance_type', '=', 'preventive'),
                        ('repeat_unit', '=', unit),
                        ('archive', '=', False),
                    ], limit=1)
                    if existing:
                        continue
                    self.env['maintenance.request'].create({
                        'name': '%s check: %s' % (label, equipment.name),
                        'equipment_id': equipment.id,
                        'maintenance_team_id': team.id,
                        'maintenance_type': 'preventive',
                        'recurring_maintenance': True,
                        'repeat_interval': 1,
                        'repeat_unit': unit,
                        'repeat_type': 'forever',
                        'schedule_date': fields.Datetime.now(),
                    })
