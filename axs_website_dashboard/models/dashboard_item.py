import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.safe_eval import datetime as safe_datetime, safe_eval

from .compat import can_read, group_data
from .date_filters import DATE_FILTERS, date_range, previous_range, range_domain

_logger = logging.getLogger(__name__)

ITEM_TYPES = [
    ('tile', 'Tile'),
    ('kpi', 'KPI'),
    ('bar', 'Bar Chart'),
    ('hbar', 'Horizontal Bar Chart'),
    ('stacked_bar', 'Stacked Bar Chart'),
    ('line', 'Line Chart'),
    ('area', 'Area Chart'),
    ('pie', 'Pie Chart'),
    ('doughnut', 'Doughnut Chart'),
    ('polar', 'Polar Area Chart'),
    ('radar', 'Radar Chart'),
    ('gauge', 'Gauge'),
    ('list', 'List'),
    ('todo', 'To-Do'),
    ('text', 'Text'),
]
CHART_TYPES = ('bar', 'hbar', 'stacked_bar', 'line', 'area', 'pie', 'doughnut', 'polar', 'radar')
DATA_TYPES = CHART_TYPES + ('tile', 'kpi', 'gauge', 'list')
INTERVALS = [('day', 'Day'), ('week', 'Week'), ('month', 'Month'), ('quarter', 'Quarter'), ('year', 'Year')]
ICONS = [
    ('chart', 'Chart'), ('money', 'Money'), ('cart', 'Cart'), ('users', 'People'), ('user', 'Person'),
    ('box', 'Box'), ('truck', 'Truck'), ('invoice', 'Invoice'), ('target', 'Target'), ('calendar', 'Calendar'),
    ('star', 'Star'), ('heart', 'Heart'), ('check', 'Check'), ('clock', 'Clock'), ('mail', 'Mail'),
    ('phone', 'Phone'), ('globe', 'Globe'), ('tag', 'Tag'), ('trophy', 'Trophy'), ('bolt', 'Bolt'),
    ('building', 'Building'), ('ticket', 'Ticket'), ('wallet', 'Wallet'), ('trend', 'Trend'),
]
GROUPABLE = ('many2one', 'selection', 'char', 'boolean', 'date', 'datetime', 'integer')
MAX_GROUPS = 2000


class AxsDashboardItem(models.Model):
    _name = 'axs.dashboard.item'
    _description = 'Dashboard Item'
    _order = 'dashboard_id, grid_y, grid_x, sequence, id'

    dashboard_id = fields.Many2one('axs.dashboard', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='dashboard_id.company_id', store=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Title', required=True, translate=True)
    description = fields.Text(translate=True, help="Shown under the title.")
    item_type = fields.Selection(ITEM_TYPES, 'Type', required=True, default='tile')

    # data
    model_id = fields.Many2one('ir.model', 'Model', ondelete='cascade',
                               domain="[('transient', '=', False)]")
    model_name = fields.Char(related='model_id.model', string='Model Name')
    domain = fields.Char(default='[]', help="Filter on the records. You can use uid, user, company_id and "
                                            "company_ids, for example [('user_id', '=', uid)].")
    date_field_id = fields.Many2one('ir.model.fields', 'Date Field', ondelete='set null',
                                    domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime')), "
                                           "('store', '=', True)]",
                                    help="Date used by the date filter of the dashboard.")
    date_filter_mode = fields.Selection([
        ('dashboard', 'Follow the dashboard'),
        ('fixed', 'Own period'),
        ('none', 'Ignore dates'),
    ], 'Date Filter', default='dashboard', required=True)
    fixed_date_filter = fields.Selection([f for f in DATE_FILTERS if f[0] != 'custom'], 'Own Period',
                                         default='this_month')
    measure_type = fields.Selection([
        ('count', 'Count'), ('sum', 'Sum'), ('avg', 'Average'), ('min', 'Minimum'), ('max', 'Maximum'),
    ], 'Measure', default='count', required=True)
    measure_field_id = fields.Many2one('ir.model.fields', 'Measure Field', ondelete='set null',
                                       domain="[('model_id', '=', model_id), "
                                              "('ttype', 'in', ('integer', 'float', 'monetary')), "
                                              "('store', '=', True)]")
    group_field_id = fields.Many2one('ir.model.fields', 'Group By', ondelete='set null',
                                     domain="[('model_id', '=', model_id), ('ttype', 'in', %s), "
                                            "('store', '=', True)]" % (GROUPABLE,))
    group_interval = fields.Selection(INTERVALS, 'Period', default='month')
    series_field_id = fields.Many2one('ir.model.fields', 'Series', ondelete='set null',
                                      domain="[('model_id', '=', model_id), ('ttype', 'in', %s), "
                                             "('store', '=', True)]" % (GROUPABLE,),
                                      help="Second grouping: one dataset per value (bar, line, area, radar).")
    series_interval = fields.Selection(INTERVALS, 'Series Period', default='month')
    drill_field_id = fields.Many2one('ir.model.fields', 'Drill Down By', ondelete='set null',
                                     domain="[('model_id', '=', model_id), ('ttype', 'in', %s), "
                                            "('store', '=', True)]" % (GROUPABLE,),
                                     help="Clicking a bar or a slice shows the selected group split by this field.")
    drill_interval = fields.Selection(INTERVALS, 'Drill Period', default='month')
    group_field_type = fields.Selection(related='group_field_id.ttype', string='Group By Type')
    series_field_type = fields.Selection(related='series_field_id.ttype', string='Series Type')
    drill_field_type = fields.Selection(related='drill_field_id.ttype', string='Drill Down Type')
    sort_order = fields.Selection([
        ('natural', 'Natural order'),
        ('value_desc', 'Highest value first'),
        ('value_asc', 'Lowest value first'),
        ('label_asc', 'Label A to Z'),
        ('label_desc', 'Label Z to A'),
    ], 'Sort', default='natural', required=True)
    limit = fields.Integer('Limit', default=0, help="Maximum number of groups (0 = all). "
                                                    "The other groups are summed into 'Others'.")
    show_others = fields.Boolean('Group the rest as Others', default=True)

    # number display
    multiplier = fields.Float(default=1.0)
    decimals = fields.Integer(default=0)
    number_format = fields.Selection([
        ('standard', 'Standard (1,234,567)'),
        ('compact', 'Compact (1.2M)'),
        ('indian', 'Indian (12,34,567)'),
        ('exact', 'Exact value'),
    ], default='standard', required=True)
    currency_id = fields.Many2one('res.currency', 'Currency')
    prefix = fields.Char()
    suffix = fields.Char()

    # charts
    show_values = fields.Boolean('Show Values', default=False)
    show_legend = fields.Boolean('Show Legend', default=True)
    cumulative = fields.Boolean(help="Running total over the groups (bar, line, area).")
    target_value = fields.Float('Target')
    show_percent = fields.Boolean('Show Percentages', help="Pie, doughnut and polar area charts.")

    # tile and KPI
    icon = fields.Selection(ICONS, default='chart')
    tile_style = fields.Selection([
        ('solid', 'Solid color'), ('light', 'Light'), ('outline', 'Outline'), ('accent', 'Accent bar'),
    ], 'Style', default='light', required=True)
    color = fields.Char(default='#3a6ea5', help="Main color (hexadecimal), for example #3a6ea5.")
    kpi_comparison = fields.Selection([
        ('previous', 'Previous period'), ('target', 'Target'), ('none', 'None'),
    ], 'Compare With', default='previous', required=True)

    # list
    list_field_ids = fields.Many2many('ir.model.fields', 'axs_dashboard_item_list_field_rel', 'item_id', 'field_id',
                                      'Columns', domain="[('model_id', '=', model_id), ('store', '=', True), "
                                                        "('ttype', 'not in', ('one2many', 'many2many', 'binary', "
                                                        "'html', 'properties', 'json'))]")
    list_order_field_id = fields.Many2one('ir.model.fields', 'Order By', ondelete='set null',
                                          domain="[('model_id', '=', model_id), ('store', '=', True)]")
    list_order_desc = fields.Boolean('Descending', default=True)
    page_size = fields.Integer('Rows per Page', default=10)

    # to-do and text
    todo_ids = fields.One2many('axs.dashboard.todo', 'item_id', 'Tasks', copy=True)
    content = fields.Html(translate=True, sanitize=True)

    # behaviour and layout
    link_url = fields.Char('Website Link', help="Opened when a website visitor clicks a tile or a KPI.")
    open_records = fields.Boolean('Open Records', default=True,
                                  help="In the back end, clicking the item opens the matching records.")
    grid_x = fields.Integer(default=0)
    grid_y = fields.Integer(default=0)
    grid_w = fields.Integer(default=3)
    grid_h = fields.Integer(default=2)

    @api.onchange('item_type')
    def _onchange_item_type(self):
        sizes = {'tile': (3, 2), 'kpi': (3, 2), 'gauge': (3, 3), 'list': (6, 4), 'todo': (4, 4), 'text': (4, 2)}
        self.grid_w, self.grid_h = sizes.get(self.item_type, (6, 4))

    @api.onchange('model_id')
    def _onchange_model_id(self):
        for fname in ('date_field_id', 'measure_field_id', 'group_field_id', 'series_field_id', 'drill_field_id',
                      'list_order_field_id'):
            if self[fname] and self[fname].model_id != self.model_id:
                self[fname] = False
        self.list_field_ids = self.list_field_ids.filtered(lambda f: f.model_id == self.model_id)
        if self.model_id and not self.date_field_id:
            Fields = self.env['ir.model.fields']
            for name in ('date_order', 'date', 'invoice_date', 'scheduled_date', 'date_deadline', 'create_date'):
                field = Fields._get(self.model_id.model, name)
                if field and field.store:
                    self.date_field_id = field
                    break

    @api.constrains('model_id', 'item_type', 'measure_type', 'measure_field_id', 'domain', 'grid_w', 'grid_h',
                    'color', 'group_field_id')
    def _check_item(self):
        for item in self:
            if item.item_type in DATA_TYPES and not item.model_id:
                raise ValidationError(_("The item '%s' needs a model.", item.name))
            if item.item_type in DATA_TYPES and item.measure_type != 'count' and not item.measure_field_id \
                    and item.item_type != 'list':
                raise ValidationError(_("The item '%s' needs a measure field for '%s'.", item.name,
                                        dict(self._fields['measure_type'].selection)[item.measure_type]))
            if item.item_type in CHART_TYPES and not item.group_field_id:
                raise ValidationError(_("The chart '%s' needs a Group By field.", item.name))
            if item.domain:
                try:
                    value = safe_eval(item.domain, item._eval_context())
                except Exception as e:
                    raise ValidationError(_("The filter of '%s' is not valid: %s", item.name, e)) from e
                if not isinstance(value, (list, tuple)):
                    raise ValidationError(_("The filter of '%s' must be a list of conditions.", item.name))
            if not (1 <= item.grid_w <= 12) or not (1 <= item.grid_h <= 12):
                raise ValidationError(_("Width and height must be between 1 and 12 columns or rows."))
            if item.color and not (len(item.color) in (4, 7) and item.color.startswith('#')
                                   and all(c in '0123456789abcdefABCDEF' for c in item.color[1:])):
                raise ValidationError(_("The color must be a hexadecimal value such as #3a6ea5."))

    # ------------------------------------------------------------------ evaluation helpers
    def _eval_context(self, user=None):
        user = user or self.env.user
        companies = self.env.companies if user == self.env.user else user.company_ids
        return {
            'uid': user.id,
            'user': user,
            'company_id': (self.env.company if user == self.env.user else user.company_id).id,
            'company_ids': companies.ids,
            'context_today': safe_datetime.date.today,
            'datetime': safe_datetime,
        }

    def _domain(self, Model):
        domain = safe_eval(self.domain or '[]', self._eval_context(Model.env.user))
        return list(domain)

    def _group_spec(self, field, interval):
        if field.ttype in ('date', 'datetime'):
            return '%s:%s' % (field.name, interval or 'month')
        return field.name

    def _aggregate(self):
        if self.measure_type == 'count' or not self.measure_field_id:
            return '__count'
        return '%s:%s' % (self.measure_field_id.name, self.measure_type)

    def _period_domain(self, Model, period, prev=False):
        """Date domain of this item for a dashboard period ``{'key', 'from', 'to', 'today', 'tz'}``."""
        if self.date_filter_mode == 'none' or not self.date_field_id:
            return [], None
        key = self.fixed_date_filter if self.date_filter_mode == 'fixed' else period.get('key')
        start, end = date_range(key, period['today'], period.get('from'), period.get('to'))
        if prev:
            start, end = previous_range(start, end)
            if not start:
                return None, None
        field = Model._fields.get(self.date_field_id.name)
        if not field or (not start and not end):
            return [], (start, end)
        return range_domain(field, start, end, period.get('tz')), (start, end)

    # ------------------------------------------------------------------ labels
    @api.model
    def _labels(self, Model, field_name, keys, interval):
        """Display labels for raw group keys of ``field_name``."""
        field = Model._fields[field_name]
        labels = {}
        if field.type == 'many2one':
            ids = [k for k in keys if k]
            names = dict((r.id, r.display_name) for r in Model.env[field.comodel_name].sudo().browse(ids))
            labels = {k: names.get(k, str(k)) for k in ids}
        elif field.type == 'selection':
            selection = dict(field._description_selection(Model.env))
            labels = {k: str(selection.get(k, k)) for k in keys if k}
        elif field.type == 'boolean':
            labels = {True: _("Yes"), False: _("No")}
        elif field.type in ('date', 'datetime'):
            for k in keys:
                if k:
                    labels[k] = self._period_label(k, interval)
        else:
            labels = {k: str(k) for k in keys if k not in (False, None)}
        return labels

    @api.model
    def _period_label(self, day, interval):
        months = [_('Jan'), _('Feb'), _('Mar'), _('Apr'), _('May'), _('Jun'), _('Jul'), _('Aug'), _('Sep'),
                  _('Oct'), _('Nov'), _('Dec')]
        if interval == 'day':
            return '%s %s %s' % (day.day, months[day.month - 1], day.year)
        if interval == 'week':
            return _('W%(week)s %(year)s', week=day.isocalendar()[1], year=day.isocalendar()[0])
        if interval == 'quarter':
            return 'Q%s %s' % ((day.month - 1) // 3 + 1, day.year)
        if interval == 'year':
            return str(day.year)
        return '%s %s' % (months[day.month - 1], day.year)

    def _key_domain(self, Model, field_name, key, interval):
        """Domain selecting the records of one group key (used for drill down and opening records)."""
        field = Model._fields[field_name]
        if field.type in ('date', 'datetime'):
            if not key:
                return [(field_name, '=', False)]
            import datetime as dt
            from dateutil.relativedelta import relativedelta
            start = dt.date.fromisoformat(key) if isinstance(key, str) else key
            step = {'day': relativedelta(days=1), 'week': relativedelta(weeks=1), 'month': relativedelta(months=1),
                    'quarter': relativedelta(months=3), 'year': relativedelta(years=1)}[interval or 'month']
            end = start + step - relativedelta(days=1)
            tz = self.env.context.get('tz') or self.env.user.tz
            return range_domain(field, start, end, tz)
        return [(field_name, '=', key)]

    # ------------------------------------------------------------------ data
    def _data_payload(self, data_env, period, drill=None, page=0, backend=False):
        """JSON data of one item, computed with ``data_env`` (the viewer or the shared data user)."""
        self.ensure_one()
        base = {'id': self.id}
        if self.item_type == 'todo':
            return dict(base, todos=[{'id': t.id, 'name': t.name, 'done': t.done} for t in self.todo_ids])
        if self.item_type == 'text':
            return dict(base, html=self.content or '')
        if not self.model_id or self.model_name not in data_env:
            return dict(base, error=_("The model of this item is not available."))
        Model = data_env[self.model_name]
        if not can_read(Model):
            return dict(base, error=_("You do not have access to this data."), no_access=True)
        try:
            domain = self._domain(Model)
            period_domain, rng = self._period_domain(Model, period)
            full_domain = (list(domain) + list(period_domain))
            if self.item_type in ('tile', 'kpi', 'gauge'):
                payload = self._single_value(Model, full_domain, period)
            elif self.item_type == 'list':
                payload = self._list_data(Model, full_domain, page)
            else:
                payload = self._chart_data(Model, full_domain, drill or [], backend=backend)
            if rng:
                payload['period'] = [d.isoformat() if d else None for d in rng]
            if backend:
                payload['domain'] = full_domain
            return dict(base, **payload)
        except AccessError:
            return dict(base, error=_("You do not have access to this data."), no_access=True)
        except Exception as e:  # noqa: BLE001 - one broken item must not break the whole dashboard
            _logger.warning("Dashboard item %s (%s) failed: %s", self.id, self.name, e)
            return dict(base, error=_("This item could not be computed: %s", e))

    def _scaled(self, value):
        return (value or 0) * (self.multiplier or 1.0)

    def _single_value(self, Model, domain, period):
        rows = group_data(Model, domain, [], self._aggregate())
        value = self._scaled(rows[0]['value'] if rows else 0)
        payload = {'value': value, 'count': rows[0]['count'] if rows else 0}
        if self.item_type == 'kpi' and self.kpi_comparison == 'previous':
            prev_domain, _rng = self._period_domain(Model, period, prev=True)
            if prev_domain:
                prev_rows = group_data(Model, (list(self._domain(Model)) + list(prev_domain)), [],
                                       self._aggregate())
                prev = self._scaled(prev_rows[0]['value'] if prev_rows else 0)
                payload['previous'] = prev
                payload['change'] = ((value - prev) / abs(prev) * 100.0) if prev else None
        if self.item_type in ('kpi', 'gauge') and self.target_value:
            payload['target'] = self.target_value
            payload['progress'] = value / self.target_value * 100.0
        return payload

    def _chart_data(self, Model, domain, drill, backend=False):
        group_field = self.group_field_id
        interval = self.group_interval
        series_field = self.series_field_id if self.item_type in ('bar', 'hbar', 'stacked_bar', 'line', 'area',
                                                                  'radar') else False
        drill_info = []
        if drill and self.drill_field_id:
            # one drill level: the clicked group of the main grouping, split by the drill field
            key = drill[0]
            domain = (list(domain) + list(self._key_domain(Model, group_field.name, key, interval)))
            labels = self._labels(Model, group_field.name, [self._parse_key(Model, group_field.name, key)], interval)
            drill_info = [{'key': key, 'label': list(labels.values())[0] if labels else _("None")}]
            group_field, interval, series_field = self.drill_field_id, self.drill_interval, False
        if group_field.name not in Model._fields:
            raise UserError(_("The field %s does not exist anymore.", group_field.name))
        groupby = [self._group_spec(group_field, interval)]
        if series_field:
            groupby.append(self._group_spec(series_field, self.series_interval))
        rows = group_data(Model, domain, groupby, self._aggregate(), limit=MAX_GROUPS)
        keys = []
        for row in rows:
            if row['keys'][0] not in keys:
                keys.append(row['keys'][0])
        labels = self._labels(Model, group_field.name, keys, interval)
        none_label = _("None")
        totals = {}
        for row in rows:
            totals[row['keys'][0]] = totals.get(row['keys'][0], 0) + row['value']
        # order and limit on the first grouping
        if self.sort_order == 'value_desc':
            keys.sort(key=lambda k: totals[k], reverse=True)
        elif self.sort_order == 'value_asc':
            keys.sort(key=lambda k: totals[k])
        elif self.sort_order in ('label_asc', 'label_desc'):
            keys.sort(key=lambda k: str(labels.get(k, none_label)).lower(), reverse=self.sort_order == 'label_desc')
        others = []
        if self.limit and len(keys) > self.limit:
            keys, others = keys[:self.limit], keys[self.limit:]
        series_keys = [None]
        series_labels = {None: self.name}
        if series_field:
            series_keys = []
            for row in rows:
                if row['keys'][1] not in series_keys:
                    series_keys.append(row['keys'][1])
            series_labels = self._labels(Model, series_field.name, series_keys, self.series_interval)
        matrix = {}
        for row in rows:
            k = row['keys'][0]
            s = row['keys'][1] if series_field else None
            target = k if k in keys else ('__others__' if self.show_others and others else None)
            if target is None:
                continue
            matrix[(target, s)] = matrix.get((target, s), 0) + row['value']
        out_keys = keys + (['__others__'] if others and self.show_others else [])
        datasets = []
        for s in series_keys:
            values = [self._scaled(matrix.get((k, s), 0)) for k in out_keys]
            if self.cumulative:
                running, cumulated = 0, []
                for v in values:
                    running += v
                    cumulated.append(running)
                values = cumulated
            datasets.append({'label': series_labels.get(s, none_label) if s is not None or series_field
                             else self.name, 'values': values})
        group_domains = []
        if backend:
            group_domains = [None if k == '__others__' else
                             list(domain) + self._key_domain(Model, group_field.name, k, interval) for k in out_keys]
        return {
            'group_domains': group_domains,
            'labels': [_("Others") if k == '__others__' else labels.get(k, none_label) for k in out_keys],
            'keys': [None if k == '__others__' else (k.isoformat() if hasattr(k, 'isoformat') else k)
                     for k in out_keys],
            'datasets': datasets,
            'drill': drill_info,
            'can_drill': bool(self.drill_field_id) and not drill,
            'target': self.target_value or None,
        }

    def _parse_key(self, Model, field_name, key):
        field = Model._fields[field_name]
        if field.type in ('date', 'datetime') and isinstance(key, str):
            import datetime as dt
            return dt.date.fromisoformat(key)
        return key

    def _list_data(self, Model, domain, page):
        if self.group_field_id:
            rows = group_data(Model, domain, [self._group_spec(self.group_field_id, self.group_interval)],
                              self._aggregate(), limit=MAX_GROUPS)
            keys = [r['keys'][0] for r in rows]
            labels = self._labels(Model, self.group_field_id.name, keys, self.group_interval)
            data = [{'label': labels.get(r['keys'][0], _("None")), 'value': self._scaled(r['value']),
                     'count': r['count']} for r in rows]
            if self.sort_order == 'value_desc':
                data.sort(key=lambda r: r['value'], reverse=True)
            elif self.sort_order == 'value_asc':
                data.sort(key=lambda r: r['value'])
            elif self.sort_order in ('label_asc', 'label_desc'):
                data.sort(key=lambda r: str(r['label']).lower(), reverse=self.sort_order == 'label_desc')
            if self.limit:
                data = data[:self.limit]
            measure = self.measure_field_id.field_description if self.measure_type != 'count' else _("Count")
            return {'grouped': True, 'columns': [self.group_field_id.field_description, measure], 'rows': data}
        fields_ = [f for f in self.list_field_ids if f.name in Model._fields] or \
            [f for f in self.env['ir.model.fields'].sudo().search(
                [('model', '=', self.model_name), ('name', '=', Model._rec_name)], limit=1)]
        size = max(1, min(self.page_size or 10, 200))
        total = Model.search_count(domain)
        page = max(0, min(int(page or 0), max(0, (total - 1) // size)))
        order = None
        if self.list_order_field_id and self.list_order_field_id.name in Model._fields:
            order = '%s %s, id desc' % (self.list_order_field_id.name, 'desc' if self.list_order_desc else 'asc')
        records = Model.search(domain, limit=size, offset=page * size, order=order)
        names = [f.name for f in fields_]
        values = records.read(names) if names else [{'id': r.id} for r in records]
        columns = [{'name': f.name, 'label': f.field_description, 'type': f.ttype} for f in fields_]
        rows = []
        for rec in values:
            row = {'id': rec['id'], 'cells': []}
            for col in columns:
                value = rec.get(col['name'])
                field = Model._fields[col['name']]
                if col['type'] == 'many2one':
                    value = value[1] if value else ''
                elif col['type'] == 'selection':
                    value = dict(field._description_selection(Model.env)).get(value, value or '')
                elif col['type'] in ('date', 'datetime'):
                    value = value and str(value)[:16 if col['type'] == 'datetime' else 10] or ''
                elif col['type'] == 'monetary' or col['type'] == 'float':
                    value = self._scaled(value)
                elif value is False:
                    value = ''
                row['cells'].append(value)
            rows.append(row)
        return {'grouped': False, 'columns': columns, 'rows': rows, 'total': total, 'page': page,
                'page_size': size}

    # ------------------------------------------------------------------ front-end description
    def _config_payload(self):
        self.ensure_one()
        currency = self.currency_id
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'type': self.item_type,
            'x': self.grid_x, 'y': self.grid_y, 'w': self.grid_w, 'h': self.grid_h,
            'icon': self.icon,
            'style': self.tile_style,
            'color': self.color or '#3a6ea5',
            'format': {
                'decimals': max(0, min(self.decimals or 0, 6)),
                'style': self.number_format,
                'prefix': self.prefix or '',
                'suffix': self.suffix or '',
                'currency': currency and {
                    'symbol': currency.symbol, 'position': currency.position,
                } or False,
            },
            'show_values': self.show_values,
            'show_legend': self.show_legend,
            'show_percent': self.show_percent,
            'comparison': self.kpi_comparison,
            'link_url': self.link_url or '',
            'open_records': self.open_records,
            'measure_label': self.measure_field_id.field_description if self.measure_type != 'count'
            else _("Count"),
            'model_name': self.model_name or '',
        }

    def action_edit_item(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'axs.dashboard.item',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }


class AxsDashboardTodo(models.Model):
    _name = 'axs.dashboard.todo'
    _description = 'Dashboard To-Do'
    _order = 'sequence, id'

    item_id = fields.Many2one('axs.dashboard.item', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Task', required=True)
    done = fields.Boolean()
