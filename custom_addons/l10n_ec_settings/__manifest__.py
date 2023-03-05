# -*- coding: utf-8 -*-
# © <2020> <Renan Nazate>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Adicional Local F.E',
    'version': '13.0.0.0.0',
    'category': 'Localization',
    'author': 'Renan Nazate',
    'website': 'http://www.sitio.com',
    'license': 'AGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'views/company.xml',
        'views/partner.xml',
        #'views/menu.xml',
    ],
    'qweb': ['static/src/xml/base_web.xml'],
}
