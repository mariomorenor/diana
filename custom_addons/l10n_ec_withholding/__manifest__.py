# -*- coding: utf-8 -*-
{
    'name': "l10n_ec_withholding",

    'summary': """
        Retenciones Ecuador""",

    'description': """
        Rerenciones Localizacion Ecuador
    """,

    'author': "G13Enterprise",
    'website': "http://www.g13enterprise.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','account'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'data/account.ats.doc.csv',
        #'data/account.account.template.csv',
        #'data/account_chart_template_configure_data.xml',
        #'data/account_chart_template_data.xml',
        #'data/account_chart_template_setup_accounts.xml',
        #'data/account_fiscal_position_template.xml',
        #'data/account_group_data.xml',
        #'data/account_tax_group_data.xml',
        #'data/account_tax_tag_data.xml',
        #'data/account_tax_template_vat_data.xml',
        #'data/account_tax_template_withhold_profit_data.xml',
        #'data/account_tax_template_withhold_vat_data.xml'
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
