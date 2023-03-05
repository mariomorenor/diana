# -*- coding: utf-8 -*-
# from odoo import http


# class L10nEcWithholding(http.Controller):
#     @http.route('/l10n_ec_withholding/l10n_ec_withholding/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/l10n_ec_withholding/l10n_ec_withholding/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('l10n_ec_withholding.listing', {
#             'root': '/l10n_ec_withholding/l10n_ec_withholding',
#             'objects': http.request.env['l10n_ec_withholding.l10n_ec_withholding'].search([]),
#         })

#     @http.route('/l10n_ec_withholding/l10n_ec_withholding/objects/<model("l10n_ec_withholding.l10n_ec_withholding"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('l10n_ec_withholding.object', {
#             'object': obj
#         })
