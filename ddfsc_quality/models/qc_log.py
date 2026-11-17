"""QC log sheets: checks recorded per shift or per day, not per lot.

Half of the factory's QC forms monitor the process rather than a lot: dryer
moisture by die, the magnetic separator, instrument calibration, water
chlorine and hardness, wheat at the mixing bins, milling granulation and
wheat in the warehouse. A template copies the rows of the paper form; each
shift (or day) the assistant QC fills one log and the QC head checks it.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

FREQUENCIES = [
    ('shift', 'Every shift'),
    ('day', 'Once a day'),
    ('event', 'When the process runs'),
    ('week', 'Weekly'),
]
RESULT_TYPES = [('numeric', 'Measured Number'), ('qualitative', 'Qualitative Choice')]


def _limit_spec(line):
    unit = line.unit or ''
    if line.result_type == 'qualitative':
        return _('Expected: %s') % (line.allowed_answers or '')
    if line.apply_min and line.apply_max:
        text = '%g – %g' % (line.standard_min, line.standard_max)
    elif line.apply_min:
        text = _('Min %g') % line.standard_min
    elif line.apply_max:
        text = _('Max %g') % line.standard_max
    else:
        text = _('Record only')
    return ('%s %s' % (text, unit)).strip()


class DdfscQcLogTemplate(models.Model):
    _name = 'ddfsc.qc.log.template'
    _description = 'QC Log Sheet Template'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    form_no = fields.Char(string='Form No.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    frequency = fields.Selection(FREQUENCIES, required=True, default='shift')
    area = fields.Char(string='Sent To', help='Division the results are reported to, e.g. Pasta Production.')
    instruction = fields.Text()
    line_ids = fields.One2many('ddfsc.qc.log.template.line', 'template_id', string='Rows', copy=True)


class DdfscQcLogTemplateLine(models.Model):
    _name = 'ddfsc.qc.log.template.line'
    _description = 'QC Log Sheet Template Row'
    _order = 'sequence, id'

    template_id = fields.Many2one('ddfsc.qc.log.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    subject = fields.Char(required=True, help='What is measured, e.g. "Die 115288 – Pre-dryer".')
    result_type = fields.Selection(RESULT_TYPES, default='numeric', required=True)
    apply_min = fields.Boolean(string='Use minimum')
    standard_min = fields.Float(string='Minimum')
    apply_max = fields.Boolean(string='Use maximum')
    standard_max = fields.Float(string='Maximum')
    unit = fields.Char()
    allowed_answers = fields.Char(help='Comma-separated acceptable answers, e.g. Absent.')
    specification = fields.Char(string='Standard', compute='_compute_specification')

    @api.depends('result_type', 'apply_min', 'standard_min', 'apply_max', 'standard_max', 'unit', 'allowed_answers')
    def _compute_specification(self):
        for line in self:
            line.specification = _limit_spec(line)

    @api.constrains('result_type', 'allowed_answers', 'apply_min', 'standard_min', 'apply_max', 'standard_max')
    def _check_rule(self):
        for line in self:
            if line.result_type == 'qualitative' and not line.allowed_answers:
                raise ValidationError(_('Enter the acceptable answer for "%s".') % line.subject)
            if line.apply_min and line.apply_max and line.standard_min > line.standard_max:
                raise ValidationError(_('The minimum is above the maximum for "%s".') % line.subject)

    def _log_line_values(self):
        self.ensure_one()
        return {
            'sequence': self.sequence, 'subject': self.subject, 'result_type': self.result_type,
            'apply_min': self.apply_min, 'standard_min': self.standard_min,
            'apply_max': self.apply_max, 'standard_max': self.standard_max,
            'unit': self.unit, 'allowed_answers': self.allowed_answers,
        }


class DdfscQcLog(models.Model):
    _name = 'ddfsc.qc.log'
    _description = 'QC Log Sheet'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(default='New', readonly=True, copy=False)
    template_id = fields.Many2one('ddfsc.qc.log.template', required=True, ondelete='restrict',
                                  readonly=True, tracking=True)
    form_no = fields.Char(related='template_id.form_no')
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    shift_id = fields.Many2one('ddfsc.shift', string='Shift', tracking=True)
    state = fields.Selection([('draft', 'Recording'), ('submitted', 'Awaiting Check'), ('checked', 'Checked')],
                             default='draft', required=True, tracking=True, copy=False)
    line_ids = fields.One2many('ddfsc.qc.log.line', 'log_id', string='Results', copy=False)
    result_state = fields.Selection([('pending', 'Pending'), ('pass', 'Within Standard'), ('fail', 'Out of Standard')],
                                    compute='_compute_result_state', store=True)
    out_of_standard_count = fields.Integer(compute='_compute_result_state', store=True)
    remark = fields.Text()
    recorded_by_id = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    checked_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    checked_date = fields.Datetime(readonly=True, copy=False)

    @api.depends('line_ids.result')
    def _compute_result_state(self):
        for log in self:
            results = log.line_ids.mapped('result')
            log.out_of_standard_count = results.count('fail')
            if 'fail' in results:
                log.result_state = 'fail'
            elif not results or 'pending' in results:
                log.result_state = 'pending'
            else:
                log.result_state = 'pass'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('ddfsc.qc.log') or 'New'
        logs = super().create(vals_list)
        for log in logs.filtered(lambda item: not item.line_ids):
            log.line_ids = [(0, 0, row._log_line_values()) for row in log.template_id.line_ids]
        return logs

    @api.constrains('template_id', 'shift_id', 'date')
    def _check_shift(self):
        for log in self:
            if log.template_id.frequency == 'shift' and not log.shift_id:
                raise ValidationError(_('%s is recorded every shift: choose the shift.') % log.template_id.name)
            # One sheet per template, date and shift (an empty shift counts as one value).
            if self.search_count([('id', '!=', log.id), ('template_id', '=', log.template_id.id),
                                  ('date', '=', log.date), ('shift_id', '=', log.shift_id.id)]):
                raise ValidationError(_('This log sheet is already open for that date and shift.'))

    def action_submit(self):
        for log in self:
            if log.state != 'draft':
                raise UserError(_('Only a log being recorded can be submitted.'))
            if log.result_state == 'pending':
                raise UserError(_('Enter every row before submitting %s.') % log.name)
            if log.result_state == 'fail' and not (log.remark or '').strip():
                raise UserError(_('Some results are out of standard: write the action taken in the remark.'))
            log.state = 'submitted'
        return True

    def action_check(self):
        if not self.env.user.has_group('ddfsc_quality.group_ddfsc_quality_manager'):
            raise AccessError(_('The QC head (Quality Manager) checks the log sheets.'))
        for log in self:
            if log.state != 'submitted':
                raise UserError(_('Submit the log before it is checked.'))
            log.write({'state': 'checked', 'checked_by_id': self.env.user.id,
                       'checked_date': fields.Datetime.now()})
        return True

    def action_reopen(self):
        if not self.env.user.has_group('ddfsc_quality.group_ddfsc_quality_manager'):
            raise AccessError(_('Only the QC head can send a log back for correction.'))
        self.write({'state': 'draft', 'checked_by_id': False, 'checked_date': False})
        return True


class DdfscQcLogLine(models.Model):
    _name = 'ddfsc.qc.log.line'
    _description = 'QC Log Sheet Result'
    _order = 'sequence, id'

    log_id = fields.Many2one('ddfsc.qc.log', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    subject = fields.Char(required=True, readonly=True)
    result_type = fields.Selection(RESULT_TYPES, default='numeric', readonly=True)
    apply_min = fields.Boolean(readonly=True)
    standard_min = fields.Float(readonly=True)
    apply_max = fields.Boolean(readonly=True)
    standard_max = fields.Float(readonly=True)
    unit = fields.Char(readonly=True)
    allowed_answers = fields.Char(readonly=True)
    specification = fields.Char(string='Standard', compute='_compute_specification')
    value = fields.Float(string='Result')
    text_value = fields.Char(string='Observed')
    is_measured = fields.Boolean(string='Done')
    result = fields.Selection([('pending', 'Pending'), ('pass', 'OK'), ('fail', 'Out')],
                              compute='_compute_result', store=True)

    @api.depends('result_type', 'apply_min', 'standard_min', 'apply_max', 'standard_max', 'unit', 'allowed_answers')
    def _compute_specification(self):
        for line in self:
            line.specification = _limit_spec(line)

    @api.depends('is_measured', 'value', 'text_value', 'result_type', 'allowed_answers',
                 'apply_min', 'standard_min', 'apply_max', 'standard_max')
    def _compute_result(self):
        for line in self:
            if not line.is_measured:
                line.result = 'pending'
            elif line.result_type == 'qualitative':
                accepted = {answer.strip().casefold() for answer in (line.allowed_answers or '').split(',') if answer.strip()}
                line.result = 'pass' if (line.text_value or '').strip().casefold() in accepted else 'fail'
            else:
                ok = (not line.apply_min or line.value >= line.standard_min) and \
                     (not line.apply_max or line.value <= line.standard_max)
                line.result = 'pass' if ok else 'fail'

    @api.onchange('value', 'text_value')
    def _onchange_value(self):
        self.is_measured = True

    def write(self, values):
        if {'value', 'text_value', 'is_measured'}.intersection(values):
            if self.mapped('log_id').filtered(lambda log: log.state != 'draft'):
                raise UserError(_('This log sheet is submitted. Ask the QC head to reopen it.'))
            if ('value' in values or 'text_value' in values) and 'is_measured' not in values:
                values = dict(values, is_measured=True)
        return super().write(values)
