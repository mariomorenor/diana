# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Local - Reportes',
    'version': '13.0.0.0',
    'summary': 'Administración de reportes electrónicos',
    'description': "",
    'website': 'http://defhelp.tk',
    'depends': ['account'],
    'category': 'Facturas',
    'sequence': 13,
    'data': [
        'report/report_einvoice.xml',
        'report/edocument_layouts.xml',
        'report/eretention_layouts.xml',
        'report/report_eretention.xml',
        'report/enotacredito_layouts.xml',
        'report/report_enotacredito.xml',
        'report/eliquidation_layouts.xml',
        'report/report_eliquidation.xml',
        'report/enotadebito_layouts.xml',
        'report/report_enotadebito.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
