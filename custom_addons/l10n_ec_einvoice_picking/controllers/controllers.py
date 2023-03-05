# -*- coding: utf-8 -*-
# from odoo import http


# class L10nEcEinvoicePicking(http.Controller):
#     @http.route('/l10n_ec_einvoice_picking/l10n_ec_einvoice_picking/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/l10n_ec_einvoice_picking/l10n_ec_einvoice_picking/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('l10n_ec_einvoice_picking.listing', {
#             'root': '/l10n_ec_einvoice_picking/l10n_ec_einvoice_picking',
#             'objects': http.request.env['l10n_ec_einvoice_picking.l10n_ec_einvoice_picking'].search([]),
#         })

#     @http.route('/l10n_ec_einvoice_picking/l10n_ec_einvoice_picking/objects/<model("l10n_ec_einvoice_picking.l10n_ec_einvoice_picking"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('l10n_ec_einvoice_picking.object', {
#             'object': obj
#         })
