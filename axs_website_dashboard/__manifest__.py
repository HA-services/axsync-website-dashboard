{
    'name': 'Website Dashboard Pro | Live Dashboards for Website, Portal and Back End',
    'version': '17.0.1.0.0',
    'summary': 'Build dashboards with tiles, KPIs, charts, lists and to-dos, and publish them on your website '
               'for visitors, portal customers or your team.',
    'description': """
Website Dashboard Pro by AXSync
===============================
Design dashboards in Odoo and publish them on your website, in the customer portal and in the back end:
tiles, KPIs with comparison, gauges, ten chart types, lists, to-do lists and text, a drag and drop grid,
date filters, drill down, per-dashboard access, viewer or shared data, embeds, templates, export and import.
""",
    'category': 'Website',
    'author': 'AXSync',
    'website': 'https://axsync.com',
    'support': 'hunain@axsync.com',
    'license': 'OPL-1',
    'price': 119.99,
    'currency': 'USD',
    'depends': ['website'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'axs_website_dashboard/static/src/scss/dashboard.scss',
            'axs_website_dashboard/static/src/js/format.js',
            'axs_website_dashboard/static/src/js/icons.js',
            'axs_website_dashboard/static/src/js/charts.js',
            'axs_website_dashboard/static/src/js/dashboard_engine.js',
            'axs_website_dashboard/static/src/js/frontend.js',
        ],
        'web.assets_backend': [
            'axs_website_dashboard/static/src/scss/dashboard.scss',
            'axs_website_dashboard/static/src/js/format.js',
            'axs_website_dashboard/static/src/js/icons.js',
            'axs_website_dashboard/static/src/js/charts.js',
            'axs_website_dashboard/static/src/js/dashboard_engine.js',
            'axs_website_dashboard/static/src/js/backend_action.js',
            'axs_website_dashboard/static/src/xml/backend_action.xml',
        ],
        'web.assets_web_dark': [
            'axs_website_dashboard/static/src/scss/dashboard_dark.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'uninstall_hook': '_uninstall_hook',
    'installable': True,
    'application': True,
}
