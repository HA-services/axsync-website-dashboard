"""Ready-made dashboards, offered for the apps installed in the database."""
from odoo import _, api, fields, models
from odoo import _ as _odoo_t
from odoo.exceptions import UserError


def _templates(env):
    _ = getattr(env, '_', None) or _odoo_t  # noqa: F811 (env._ on Odoo 18+)
    sold = "[('state', 'in', ['sale', 'done'])]"
    invoices = "[('move_type', '=', 'out_invoice'), ('state', '=', 'posted')]"
    opportunities = "[('type', '=', 'opportunity')]"
    return {
        'sales': {
            'name': _("Sales Overview"),
            'model': 'sale.order',
            'theme': 'axsync',
            'items': [
                dict(name=_("Revenue"), item_type='kpi', model='sale.order', domain=sold, date_field='date_order',
                     measure_type='sum', measure_field='amount_untaxed', icon='money', color='#3a6ea5',
                     number_format='compact', decimals=1, x=0, y=0, w=3, h=2),
                dict(name=_("Orders"), item_type='tile', model='sale.order', domain=sold, date_field='date_order',
                     icon='cart', color='#5b8c5a', tile_style='solid', x=3, y=0, w=3, h=2),
                dict(name=_("Average Order"), item_type='tile', model='sale.order', domain=sold,
                     date_field='date_order', measure_type='avg', measure_field='amount_untaxed', icon='wallet',
                     color='#c8553d', decimals=0, x=6, y=0, w=3, h=2),
                dict(name=_("Open Quotations"), item_type='tile', model='sale.order',
                     domain="[('state', 'in', ['draft', 'sent'])]", date_field='date_order', icon='invoice',
                     color='#8e6c8a', tile_style='accent', x=9, y=0, w=3, h=2),
                dict(name=_("Revenue by Month"), item_type='bar', model='sale.order', domain=sold,
                     date_field='date_order', measure_type='sum', measure_field='amount_untaxed',
                     group_field='date_order', group_interval='month', drill_field='user_id',
                     number_format='compact', decimals=1, x=0, y=2, w=8, h=4),
                dict(name=_("Revenue by Salesperson"), item_type='doughnut', model='sale.order', domain=sold,
                     date_field='date_order', measure_type='sum', measure_field='amount_untaxed',
                     group_field='user_id', sort_order='value_desc', limit=6, show_percent=True,
                     number_format='compact', decimals=1, x=8, y=2, w=4, h=4),
                dict(name=_("Top Customers"), item_type='hbar', model='sale.order', domain=sold,
                     date_field='date_order', measure_type='sum', measure_field='amount_untaxed',
                     group_field='partner_id', sort_order='value_desc', limit=8, show_others=False,
                     number_format='compact', decimals=1, show_values=True, x=0, y=6, w=6, h=4),
                dict(name=_("Cumulative Revenue"), item_type='area', model='sale.order', domain=sold,
                     date_field='date_order', measure_type='sum', measure_field='amount_untaxed',
                     group_field='date_order', group_interval='month', cumulative=True,
                     number_format='compact', decimals=1, x=6, y=6, w=6, h=4),
                dict(name=_("Latest Orders"), item_type='list', model='sale.order', domain=sold,
                     date_field='date_order', list_fields=['name', 'partner_id', 'date_order', 'user_id',
                                                           'amount_total'],
                     list_order='date_order', page_size=8, x=0, y=10, w=12, h=5),
            ],
        },
        'crm': {
            'name': _("CRM Pipeline"),
            'model': 'crm.lead',
            'theme': 'ocean',
            'items': [
                dict(name=_("Open Opportunities"), item_type='tile', model='crm.lead', domain=opportunities,
                     date_field='create_date', date_filter_mode='none', icon='target', color='#1d6fa3',
                     tile_style='solid', x=0, y=0, w=3, h=2),
                dict(name=_("Expected Revenue"), item_type='tile', model='crm.lead', domain=opportunities,
                     date_field='create_date', date_filter_mode='none', measure_type='sum',
                     measure_field='expected_revenue', icon='money', color='#2a9d8f', number_format='compact',
                     decimals=1, x=3, y=0, w=3, h=2),
                dict(name=_("New Leads"), item_type='kpi', model='crm.lead', date_field='create_date',
                     icon='users', color='#e9c46a', x=6, y=0, w=3, h=2),
                dict(name=_("Average Probability"), item_type='gauge', model='crm.lead', domain=opportunities,
                     date_filter_mode='none', measure_type='avg', measure_field='probability', target_value=100,
                     suffix='%', color='#264653', x=9, y=0, w=3, h=3),
                dict(name=_("Pipeline by Stage"), item_type='bar', model='crm.lead', domain=opportunities,
                     date_filter_mode='none', measure_type='sum', measure_field='expected_revenue',
                     group_field='stage_id', drill_field='user_id', number_format='compact', decimals=1,
                     show_values=True, x=0, y=2, w=9, h=4),
                dict(name=_("Leads by Source"), item_type='pie', model='crm.lead', date_field='create_date',
                     group_field='source_id', sort_order='value_desc', limit=6, show_percent=True,
                     x=9, y=3, w=3, h=4),
                dict(name=_("Opportunities by Salesperson"), item_type='stacked_bar', model='crm.lead',
                     domain=opportunities, date_filter_mode='none', group_field='user_id',
                     series_field='stage_id', x=0, y=6, w=6, h=4),
                dict(name=_("Hot Opportunities"), item_type='list', model='crm.lead',
                     domain="[('type', '=', 'opportunity'), ('probability', '>=', 50)]", date_filter_mode='none',
                     list_fields=['name', 'partner_id', 'expected_revenue', 'probability', 'stage_id'],
                     list_order='expected_revenue', page_size=6, x=6, y=7, w=6, h=4),
            ],
        },
        'invoicing': {
            'name': _("Invoicing"),
            'model': 'account.move',
            'theme': 'forest',
            'items': [
                dict(name=_("Invoiced"), item_type='kpi', model='account.move', domain=invoices,
                     date_field='invoice_date', measure_type='sum', measure_field='amount_untaxed_signed',
                     icon='invoice', color='#2d6a4f', number_format='compact', decimals=1, x=0, y=0, w=4, h=2),
                dict(name=_("Due"), item_type='tile', model='account.move',
                     domain="[('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), "
                            "('payment_state', 'in', ['not_paid', 'partial'])]",
                     date_filter_mode='none', measure_type='sum', measure_field='amount_residual_signed',
                     icon='clock', color='#bc4749', tile_style='solid', number_format='compact', decimals=1,
                     x=4, y=0, w=4, h=2),
                dict(name=_("Invoices"), item_type='tile', model='account.move', domain=invoices,
                     date_field='invoice_date', icon='check', color='#52796f', x=8, y=0, w=4, h=2),
                dict(name=_("Invoiced by Month"), item_type='line', model='account.move', domain=invoices,
                     date_field='invoice_date', measure_type='sum', measure_field='amount_untaxed_signed',
                     group_field='invoice_date', group_interval='month', number_format='compact', decimals=1,
                     x=0, y=2, w=8, h=4),
                dict(name=_("Payment Status"), item_type='doughnut', model='account.move', domain=invoices,
                     date_field='invoice_date', group_field='payment_state', show_percent=True,
                     x=8, y=2, w=4, h=4),
            ],
        },
        'inventory': {
            'name': _("Inventory"),
            'model': 'stock.picking',
            'theme': 'sunset',
            'items': [
                dict(name=_("Ready to Process"), item_type='tile', model='stock.picking',
                     domain="[('state', '=', 'assigned')]", date_filter_mode='none', icon='box',
                     color='#e76f51', tile_style='solid', x=0, y=0, w=4, h=2),
                dict(name=_("Waiting"), item_type='tile', model='stock.picking',
                     domain="[('state', 'in', ['waiting', 'confirmed'])]", date_filter_mode='none', icon='clock',
                     color='#f4a261', x=4, y=0, w=4, h=2),
                dict(name=_("Done"), item_type='kpi', model='stock.picking', domain="[('state', '=', 'done')]",
                     date_field='date_done', icon='truck', color='#2a9d8f', x=8, y=0, w=4, h=2),
                dict(name=_("Transfers by Type"), item_type='bar', model='stock.picking',
                     date_field='scheduled_date', group_field='picking_type_id', series_field='state',
                     x=0, y=2, w=8, h=4),
                dict(name=_("Transfers by Status"), item_type='polar', model='stock.picking',
                     date_field='scheduled_date', group_field='state', x=8, y=2, w=4, h=4),
            ],
        },
        'contacts': {
            'name': _("Contacts"),
            'model': 'res.partner',
            'theme': 'berry',
            'items': [
                dict(name=_("Companies"), item_type='tile', model='res.partner', domain="[('is_company', '=', True)]",
                     date_filter_mode='none', icon='building', color='#8e44ad', tile_style='solid',
                     x=0, y=0, w=4, h=2),
                dict(name=_("Individuals"), item_type='tile', model='res.partner',
                     domain="[('is_company', '=', False)]", date_filter_mode='none', icon='user',
                     color='#c0392b', x=4, y=0, w=4, h=2),
                dict(name=_("New Contacts"), item_type='kpi', model='res.partner', date_field='create_date',
                     icon='users', color='#16a085', x=8, y=0, w=4, h=2),
                dict(name=_("Contacts by Country"), item_type='hbar', model='res.partner', date_filter_mode='none',
                     group_field='country_id', sort_order='value_desc', limit=10, show_values=True,
                     x=0, y=2, w=6, h=5),
                dict(name=_("New Contacts by Month"), item_type='line', model='res.partner',
                     date_field='create_date', group_field='create_date', group_interval='month',
                     x=6, y=2, w=6, h=5),
            ],
        },
        'employees': {
            'name': _("Employees"),
            'model': 'hr.employee',
            'theme': 'mono',
            'items': [
                dict(name=_("Employees"), item_type='tile', model='hr.employee', date_filter_mode='none',
                     icon='users', color='#34495e', tile_style='solid', x=0, y=0, w=4, h=2),
                dict(name=_("Departments"), item_type='tile', model='hr.department', date_filter_mode='none',
                     icon='building', color='#7f8c8d', x=4, y=0, w=4, h=2),
                dict(name=_("Employees by Department"), item_type='bar', model='hr.employee',
                     date_filter_mode='none', group_field='department_id', show_values=True, x=0, y=2, w=8, h=4),
                dict(name=_("Employees by Job"), item_type='pie', model='hr.employee', date_filter_mode='none',
                     group_field='job_id', limit=6, x=8, y=2, w=4, h=4),
            ],
        },
    }


class AxsDashboardTemplateWizard(models.TransientModel):
    _name = 'axs.dashboard.template.wizard'
    _description = 'Create a Dashboard from a Template'

    @api.model
    def _template_selection(self):
        return [(key, tpl['name']) for key, tpl in _templates(self.env).items() if tpl['model'] in self.env]

    template = fields.Selection('_template_selection', required=True)
    name = fields.Char('Dashboard Name')
    publish = fields.Boolean('Publish on the Website')

    @api.onchange('template')
    def _onchange_template(self):
        if self.template:
            self.name = _templates(self.env)[self.template]['name']

    @api.model
    def _item_vals(self, spec):
        """Item values of a template entry, or None when the app or a field is missing in this database."""
        Fields = self.env['ir.model.fields']
        model = self.env['ir.model']._get(spec['model'])
        if not model:
            return None

        def field(name):
            if not name:
                return False
            rec = Fields._get(spec['model'], name)
            if not rec or not rec.store:
                raise LookupError(name)
            return rec.id

        try:
            vals = {
                'name': spec['name'], 'item_type': spec['item_type'], 'model_id': model.id,
                'domain': spec.get('domain', '[]'),
                'date_field_id': field(spec.get('date_field')),
                'date_filter_mode': spec.get('date_filter_mode', 'dashboard' if spec.get('date_field') else 'none'),
                'measure_type': spec.get('measure_type', 'count'),
                'measure_field_id': field(spec.get('measure_field')),
                'group_field_id': field(spec.get('group_field')),
                'group_interval': spec.get('group_interval', 'month'),
                'series_field_id': field(spec.get('series_field')),
                'drill_field_id': field(spec.get('drill_field')),
                'list_order_field_id': field(spec.get('list_order')),
                'list_field_ids': [(6, 0, [field(n) for n in spec.get('list_fields', [])])],
            }
        except LookupError:
            return None
        for key in ('icon', 'color', 'tile_style', 'number_format', 'decimals', 'sort_order', 'limit',
                    'show_others', 'show_values', 'show_percent', 'cumulative', 'target_value', 'suffix',
                    'page_size'):
            if key in spec:
                vals[key] = spec[key]
        vals.update(grid_x=spec['x'], grid_y=spec['y'], grid_w=spec['w'], grid_h=spec['h'])
        return vals

    def action_create(self):
        self.ensure_one()
        template = _templates(self.env).get(self.template)
        if not template or template['model'] not in self.env:
            raise UserError(_("This template needs an app that is not installed."))
        items = [vals for vals in (self._item_vals(spec) for spec in template['items']) if vals]
        if not items:
            raise UserError(_("This template cannot be used with the installed apps."))
        dashboard = self.env['axs.dashboard'].create({
            'name': self.name or template['name'],
            'theme': template['theme'],
            'website_published': self.publish,
            'item_ids': [(0, 0, vals) for vals in items],
        })
        return dashboard.action_open_dashboard()


class AxsDashboardImportWizard(models.TransientModel):
    _name = 'axs.dashboard.import.wizard'
    _description = 'Import Dashboards'

    file = fields.Binary(required=True)
    filename = fields.Char()

    def action_import(self):
        import json
        from .compat import binary_read
        self.ensure_one()
        try:
            data = json.loads(binary_read(self.file))
        except Exception as e:
            raise UserError(_("The file could not be read: %s", e)) from e
        dashboards = self.env['axs.dashboard']._import_data(data)
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'axs.dashboard',
            'name': _("Imported Dashboards"),
            'domain': [('id', 'in', dashboards.ids)],
            'view_mode': 'kanban,form',
        }
        return action
