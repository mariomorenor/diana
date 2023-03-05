# -*- coding: utf-8 -*-
# © <2020> <Renan Nazate>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _, exceptions
from random import randint
from odoo.exceptions import ValidationError


class Company(models.Model):
    _inherit = 'res.company'

    vat = fields.Char(required=True)
    agente_retencion = fields.Boolean(string='Agente retención')
    val_agente_retencion = fields.Char(string='.')
    is_special_taxpayer = fields.Selection(
        [
            ('284', 'Yes'),
            ('000', 'No')
        ],
        string='Special TaxPayer',
        required='True',
        default='000'
    )


class ResPartnerVal(models.Model):
    _inherit = 'res.partner'

    vat = fields.Char(required=True)
    street = fields.Char(required=True)
    email = fields.Char(required=True)
