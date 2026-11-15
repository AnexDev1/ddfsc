"""Repeated samples for one test, and where the sample was taken.

The forms weigh several samples per test: bread every 30 minutes (OF/QC/002),
every pasta packing head (OF/QC/010), several biscuits (OF/QC/001). The
laboratory types the readings as a list; the result follows the plan's rule:
the average within limits, or every single sample within limits.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

SAMPLE_RULES = [
    ('average', 'Average within limits'),
    ('each', 'Every sample within limits'),
]


def parse_samples(text):
    values = []
    for part in (text or '').replace(';', ',').replace('\n', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except ValueError:
            raise UserError(_('"%s" is not a number. Separate sample readings with commas.') % part)
    return values


class DdfscQualityPlanLine(models.Model):
    _inherit = 'ddfsc.quality.plan.line'

    sample_count = fields.Integer(
        string='Samples', default=1,
        help='Number of readings the laboratory takes for this test (e.g. one per packing head).')
    sample_rule = fields.Selection(SAMPLE_RULES, string='Sample Rule', default='average', required=True)

    @api.constrains('sample_count')
    def _check_sample_count(self):
        for line in self:
            if line.sample_count < 1:
                raise ValidationError(_('A test needs at least one sample.'))

    def _inspection_line_values(self):
        values = super()._inspection_line_values()
        values.update(sample_count=self.sample_count, sample_rule=self.sample_rule)
        return values


class DdfscQcInspectionLine(models.Model):
    _inherit = 'ddfsc.qc.inspection.line'

    sample_count = fields.Integer(string='Samples Required', default=1, readonly=True)
    sample_rule = fields.Selection(SAMPLE_RULES, default='average', readonly=True)
    sample_values = fields.Char(
        string='Sample Readings',
        help='Readings separated by commas, in the order they were taken, e.g. 502, 498, 501, 499.')
    sample_taken = fields.Integer(string='Taken', compute='_compute_sample_stats', store=True)
    sample_min = fields.Float(string='Min', compute='_compute_sample_stats', store=True)
    sample_max = fields.Float(string='Max', compute='_compute_sample_stats', store=True)

    @api.depends('sample_values')
    def _compute_sample_stats(self):
        for line in self:
            values = parse_samples(line.sample_values)
            line.sample_taken = len(values)
            line.sample_min = min(values) if values else 0.0
            line.sample_max = max(values) if values else 0.0

    @api.onchange('sample_values')
    def _onchange_sample_values(self):
        for line in self:
            values = parse_samples(line.sample_values)
            if values:
                line.measured_value = sum(values) / len(values)
            line.is_measured = len(values) >= (line.sample_count or 1)

    def write(self, values):
        if 'sample_values' in values:
            readings = parse_samples(values['sample_values'])
            for line in self:
                line_values = dict(values)
                if readings:
                    line_values['measured_value'] = sum(readings) / len(readings)
                line_values['is_measured'] = bool(readings) and len(readings) >= (line.sample_count or 1)
                super(DdfscQcInspectionLine, line).write(line_values)
            return True
        return super().write(values)

    @api.depends('sample_values', 'sample_rule', 'sample_count')
    def _compute_result(self):
        super()._compute_result()
        for line in self.filtered(lambda item: item.result_type != 'qualitative' and item.sample_values):
            values = parse_samples(line.sample_values)
            if len(values) < (line.sample_count or 1):
                line.result = 'pending'
            elif line.sample_rule == 'each' and line.is_measured:
                ok = all((not line.apply_min or value >= line.standard_min)
                         and (not line.apply_max or value <= line.standard_max) for value in values)
                line.result = 'pass' if ok else 'fail'


class DdfscQcInspection(models.Model):
    _inherit = 'ddfsc.qc.inspection'

    die_number = fields.Char(string='Die No.', tracking=True,
                             help='Pasta die used for this lot (moisture limits depend on the die).')
    packing_machine = fields.Char(string='Packing Machine / Head', tracking=True,
                                  help='e.g. LCP-1 A, LCP-2 B, SCP.')
    silo_number = fields.Char(string='Silo / Bin No.', tracking=True)
