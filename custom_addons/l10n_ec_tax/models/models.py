# -*- coding: utf-8 -*-
import time
from datetime import datetime
import calendar

from odoo import api, fields, models
from odoo import tools

class AccountMoveTax(models.Model):
   _name = "account.move.tax"
   _description = "Move Tax"
   _order = 'sequence'

# class l10n_ec_tax(models.Model):
#     _name = 'l10n_ec_tax.l10n_ec_tax'
#     _description = 'l10n_ec_tax.l10n_ec_tax'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
