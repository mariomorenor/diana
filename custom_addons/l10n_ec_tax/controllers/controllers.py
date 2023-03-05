# -*- coding: utf-8 -*-
# from odoo import http


# class L10nEcTax(http.Controller):
#     @http.route('/l10n_ec_tax/l10n_ec_tax/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/l10n_ec_tax/l10n_ec_tax/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('l10n_ec_tax.listing', {
#             'root': '/l10n_ec_tax/l10n_ec_tax',
#             'objects': http.request.env['l10n_ec_tax.l10n_ec_tax'].search([]),
#         })

#     @http.route('/l10n_ec_tax/l10n_ec_tax/objects/<model("l10n_ec_tax.l10n_ec_tax"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('l10n_ec_tax.object', {
#             'object': obj
#         })
