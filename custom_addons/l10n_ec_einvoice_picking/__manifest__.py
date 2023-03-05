# -*- coding: utf-8 -*-
{
    'name': "l10n_ec_einvoice_picking",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "G13Enterprise",
    'website': "http://www.g13enterprise.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','account','stock','l10n_ec_ein','l10n_ec_reports'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'data/stock.picking.move.reason.csv',
        'views/edocument_layouts.xml',
        'views/report_erefguide.xml',
        'edi/erefguide_edi.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
