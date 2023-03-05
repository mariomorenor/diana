import base64
from io import BytesIO
import os
import itertools
from datetime import datetime
import logging

from odoo.addons.account.models.account_payment import MAP_INVOICE_TYPE_PARTNER_TYPE
from jinja2 import Environment, FileSystemLoader, Template

from odoo import api, models, fields
from odoo.exceptions import Warning as UserError

from odoo.addons.account_test import report
from odoo.addons.base.models.ir_attachment import IrAttachment
from odoo.tools import safe_eval

from . import utils
from . import edocument

MAP_INVOICE_TYPE_PARTNER_TYPE.update({'liq_purchase': 'supplier'})
from ..xades.sri import DocumentXML, SriService
from ..xades.xades import Xades
import os.path
from os import path

sign = '/tmp/sign.p12'


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'account.edocument']
    _logger = logging.getLogger('account.edocument')
    TEMPLATES = {
        'out_invoice': 'out_invoice.xml',
        'out_refund': 'out_refund.xml',
        'liq_purchase': 'liq_purchase.xml',
        'out_debit': 'debit_note.xml'
    }
        
    type = fields.Selection(selection_add=[('liq_purchase', 'Liquidacion Compra')])

    SriServiceObj = SriService()

    sri_authorization = fields.Many2one('sri.authorization', copy=False)
    sri_payment_type = fields.Many2one('sri.payment_type', copy=False)
    sri_authorization_date = fields.Char(string='Fecha autorización',
                            related='sri_authorization.sri_authorization_date')
    auth_number_prov = fields.Char(u'Número de autorización')
    is_liquidation = fields.Boolean(string='Es Liquidacion', default=False)
    
    total_invoice = fields.Monetary(string='Total Factura', store=True, readonly=True,
        compute='_compute_total_invoice', currency_field='company_currency_id') 
    
    def button_draft(self):
        super(AccountMove, self).button_draft()
        for ref in self:
           if ref.type_doc.code == '03':
               ref.write({'type': 'in_invoice'})
    
    @api.depends(
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.currency_id',
        'line_ids.amount_currency',
        'line_ids.amount_residual',
        'line_ids.amount_residual_currency',
        'line_ids.payment_id.state')
    def _compute_total_invoice(self):
        total = 0.00
        for line in self.line_ids:
            if line.price_subtotal > 0:
                total = total + line.price_subtotal
        self.total_invoice = total
    def _info_adicional(self, invoice):
        """
        """
        infoAdicional = {
            'informacionAdicional': 'Adicional'
        }
        return infoAdicional
    
    def _info_liquidacion_compra(self, invoice):
        """
        """
        def fix_date(date):
            d = time.strftime('%d/%m/%Y',
                              time.strptime(date, '%Y-%m-%d'))
            return d

        company = invoice.company_id
        partner = invoice.partner_id
        infoLiquidacion = {
            'fechaEmision': self.invoice_date.strftime("%d/%m/%Y"),
            'dirEstablecimiento': partner.street,
            'obligadoContabilidad': 'SI',
            'tipoIdentificacionProveedor': partner.taxid_type.code,  # noqa
            'razonSocialProveedor': partner.name,
            'identificacionProveedor': partner.vat,
            'direccionProveedor': partner.street,
            'totalSinImpuestos': '%.2f' % (self.amount_untaxed),
            'totalDescuento': '0.00',
            'importeTotal': '{:.2f}'.format(self.total_invoice),
            'moneda': 'USD',
            'formaPago': self.sri_payment_type.code
        }
        totalConImpuestos = []
        for lines in self.invoice_line_ids:
            for tax in lines.tax_ids:
                if tax.sri_code.code in ['2', '3']:
                    totalImpuesto = {
                        'codigo': tax.sri_code.code,
                        'codigoPorcentaje': tax.sri_rate.code,
                        'baseImponible': '{:.2f}'.format(lines.price_subtotal),
                        'tarifa': tax.amount,
                        'valor': '{:.2f}'.format(lines.price_subtotal * (tax.amount / 100))
                        }  
                    totalConImpuestos.append(totalImpuesto)

        infoLiquidacion.update({'totalConImpuestos': totalConImpuestos})
        return infoLiquidacion

    def render_document_liquidacion(self, invoice, access_key, emission_code):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        #formato de plantilla para gasolinera o normal
        einvoice_tmpl = env.get_template(self.TEMPLATES[self.type])
        data = {}
        data.update(self._info_tributaria(invoice, access_key, emission_code))
        data.update(self._info_liquidacion_compra(invoice))
        detalles = self._detalles_liquidation(invoice)
        data.update(detalles)
        data.update(self._info_adicional(invoice))
        data.update(self._compute_discount(detalles))
        einvoice = einvoice_tmpl.render(data)
        logging.error(einvoice)
        logging.error("Archivo XML LIQUIDACION")
        logging.error(einvoice)
        return einvoice
        
    def action_generate_eliquidacion(self):
        """
        Metodo de generacion de liquidacion electronica
        TODO: usar celery para enviar a cola de tareas
        la generacion de la factura y envio de email
        """
        for obj in self:
            if obj.type not in ['out_invoice', 'out_refund','liq_purchase'] and not obj.journal_id.is_electronic_document:
                continue
            access_key, emission_code = self._get_codes(name='account.move')
            einvoice = self.render_document_liquidacion(obj, access_key, emission_code)
            inv_xml = DocumentXML(einvoice, obj.type)
            if not inv_xml.validate_xml():
                raise UserError("Not Valid Schema")

            xades = self.env['sri.key.type'].search([
                ('company_id', '=', self.company_id.id)
            ])
            x_path = "/tmp/ComprobantesGenerados/"
            if not path.exists(x_path):
                os.mkdir(x_path)
            if obj.type == 'liq_purchase':
               to_sign_file = open(x_path+'LIQUIDACION_SRI_'+self.name+".xml", 'w')
            to_sign_file.write(einvoice)
            to_sign_file.close()
            signed_document = xades.action_sign(to_sign_file)
            ok, errores = inv_xml.send_receipt(signed_document)
            if not ok:
                raise UserError(errores)

            sri_auth = self.env['sri.authorization'].create({
                'sri_authorization_code': access_key,
                'sri_create_date': self.write_date,
                'account_move': self.id,
                'env_service': self.company_id.env_service
            })
            self.write({'sri_authorization': sri_auth.id})
    
    def _info_invoice(self):
        """
        """
        company = self.company_id
        partner = self.partner_id
        infoFactura = {
            'fechaEmision': self.invoice_date.strftime("%d/%m/%Y"),
            'dirEstablecimiento': company.street,
            'obligadoContabilidad': company.is_force_keep_accounting,
            'tipoIdentificacionComprador': partner.taxid_type.code,
            'razonSocialComprador': partner.name,
            'identificacionComprador': partner.vat,
            'direccionComprador': partner.street,
            'totalSinImpuestos': '%.2f' % (self.amount_untaxed),
            'totalDescuento': '0.00',
            'propina': '0.00',
            'importeTotal': '{:.2f}'.format(self.amount_total),
            'valorTotal': '{:.2f}'.format(self.amount_total),
            'moneda': 'USD',
            'formaPago': self.sri_payment_type.code,
            'valorRetIva': '0.00',
            'valorRetRenta': '0.00',
            'contribuyenteEspecial': company.is_special_taxpayer
        }

        totalConImpuestos = []
        for lines in self.invoice_line_ids:
            totalImpuesto = {
                'codigo': lines.tax_ids.sri_code.code,
                'codigoPorcentaje': lines.tax_ids.sri_rate.code,
                'baseImponible': '{:.2f}'.format(lines.price_subtotal),
                'tarifa': lines.tax_ids.amount,
                'valor': '{:.2f}'.format(lines.price_subtotal * (lines.tax_ids.amount / 100))
            }
            totalConImpuestos.append(totalImpuesto)

        infoFactura.update({'totalConImpuestos': totalConImpuestos})

        if self.type == 'out_refund':
            #inv = self.search([('name', '=', self.ref)], limit=1)
            inv = self.search([('id', '=', self.reversed_entry_id.id)], limit=1)
            inv_number = inv.name
            notacredito = {
                'codDocModificado': utils.tipoDocumento[inv.type], #Modificar
                'numDocModificado': inv_number,
                'motivo': self.name,
                'fechaEmisionDocSustento': inv.invoice_date.strftime("%d/%m/%Y"),
                'valorModificacion': self.amount_total
            }
            infoFactura.update(notacredito)
        if self.debit_origin_id:
            inv = self.search([('id', '=', self.debit_origin_id.id)], limit=1)
            inv_number = inv.name
            notadebito = {
                'codDocModificado': '01', #Modificar
                'numDocModificado': inv_number,
                'motivo': self.ref,
                'fechaEmisionDocSustento': inv.invoice_date.strftime("%d/%m/%Y"),
            }
            infoFactura.update(notadebito)
        return infoFactura
    def _motivos(self, invoice):
        """
        """
        def fix_chars(code):
            special = [
                [u'%', ' '],
                [u'º', ' '],
                [u'Ñ', 'N'],
                [u'ñ', 'n']
            ]
            for f, r in special:
                code = code.replace(f, r)
            return code
        motivos = []
        for line in invoice.invoice_line_ids:
            motivo = {
                'razon': fix_chars(line.name.strip()),
                'valor': '%.2f' % line.price_subtotal,
            }
        motivos.append(motivo)
        return {'motivos': motivos}
    def _detalles(self, invoice):
        """
        """
        def fix_chars(code):
            special = [
                [u'%', ' '],
                [u'º', ' '],
                [u'Ñ', 'N'],
                [u'ñ', 'n']
            ]
            for f, r in special:
                code = code.replace(f, r)
            return code

        detalle_adicional = {
            'nombre': 'Unidad',
            'valor': 1
        }

        detalles = []
        for line in invoice.invoice_line_ids:
            codigoPrincipal = line.product_id and \
                              line.product_id.default_code and \
                              fix_chars(line.product_id.default_code) or '001'
            priced = line.price_unit * (1 - (line.discount or 0.00) / 100.0)
            discount = (line.price_unit - priced) * line.quantity
            detalle = {
                'codigoPrincipal': codigoPrincipal,
                'descripcion': fix_chars(line.name.strip()),
                'cantidad': '%.6f' % line.quantity,
                'precioUnitario': '%.6f' % line.price_unit,
                'descuento': '%.2f' % discount,
                'precioTotalSinImpuesto': '%.2f' % line.price_subtotal,
                'detalle_adicional': detalle_adicional
            }
            impuestos = []
            for tax_line in line:
                percent = int(tax_line.tax_ids.amount)
                impuesto = {
                    'codigo': tax_line.tax_ids.sri_code.code,
                    'codigoPorcentaje': tax_line.tax_ids.sri_rate.code,
                    'tarifa': percent,
                    'baseImponible': '{:.2f}'.format(tax_line.price_subtotal),
                    'valor': '{:.2f}'.format(tax_line.price_subtotal * (tax_line.tax_ids.amount / 100))
                }
                impuestos.append(impuesto)
        detalle.update({'impuestos': impuestos})
        detalles.append(detalle)
        return {'detalles': detalles}
        
        
    def _detalles_liquidation(self, invoice):
        """
        """
        def fix_chars(code):
            special = [
                [u'%', ' '],
                [u'º', ' '],
                [u'Ñ', 'N'],
                [u'ñ', 'n']
            ]
            for f, r in special:
                code = code.replace(f, r)
            return code

        detalle_adicional = {
            'nombre': 'Unidad',
            'valor': 1
        }

        detalles = []
        for line in invoice.invoice_line_ids:
            codigoPrincipal = line.product_id and \
                              line.product_id.default_code and \
                              fix_chars(line.product_id.default_code) or '001'
            priced = line.price_unit * (1 - (line.discount or 0.00) / 100.0)
            discount = (line.price_unit - priced) * line.quantity
            detalle = {
                'codigoPrincipal': codigoPrincipal,
                'descripcion': fix_chars(line.name.strip()),
                'cantidad': '%.6f' % line.quantity,
                'precioUnitario': '%.6f' % line.price_unit,
                'descuento': '%.2f' % discount,
                'precioTotalSinImpuesto': '%.2f' % line.price_subtotal,
                'detalle_adicional': detalle_adicional
            }
            impuestos = []
            for lines in self.invoice_line_ids:
                for tax in lines.tax_ids:
                    if tax.sri_code.code in ['2', '3']:
                        percent = int(tax.amount)
                        impuesto = {
                            'codigo': tax.sri_code.code,
                            'codigoPorcentaje': tax.sri_rate.code,
                            'tarifa': percent,
                            'baseImponible': '{:.2f}'.format(lines.price_subtotal),
                            'valor': '{:.2f}'.format(lines.price_subtotal * (tax.amount / 100))
                        }
                        impuestos.append(impuesto)
        detalle.update({'impuestos': impuestos})
        detalles.append(detalle)
        return {'detalles': detalles}

    def fecha_factura(self):
        """
        """
        def fix_date(date):
            d = date.strftime("%d/%m/%Y")
            #d = time.strftime('%d/%m/%Y',
                              #time.strptime(date, '%Y-%m-%d'))
            return d

        if self.type == 'out_refund':
            #inv = self.search([('name', '=', self.ref)], limit=1)
            inv = self.search([('id', '=', self.reversed_entry_id.id)], limit=1)
            fecha = fix_date(inv.invoice_date)
        if self.debit_origin_id:
            #inv = self.search([('name', '=', self.ref)], limit=1)
            inv = self.search([('id', '=', self.debit_origin_id.id)], limit=1)
            fecha = fix_date(inv.invoice_date)
        return fecha
        
    def render_authorized_einvoice(self, autorizacion):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        einvoice_tmpl = env.get_template('authorized_einvoice.xml')
        auth_xml = {
            'estado': autorizacion.estado,
            'numeroAutorizacion': autorizacion.numeroAutorizacion,
            'ambiente': autorizacion.ambiente,
            'fechaAutorizacion': str(autorizacion.fechaAutorizacion),
            'comprobante': autorizacion.comprobante
        }
        auth_invoice = einvoice_tmpl.render(auth_xml)
        return auth_invoice

    def action_generate_edebit(self):
        for obj in self:
            if obj.type not in ['out_invoice', 'out_refund'] and not obj.journal_id.is_electronic_document:
                continue
            access_key, emission_code = self._get_codes(name='account.debit')
            einvoice = self.render_document_debit(obj, access_key, emission_code)
            inv_xml = DocumentXML(einvoice, 'out_debit')
            if not inv_xml.validate_xml():
                raise UserError("Not Valid Schema")

            xades = self.env['sri.key.type'].search([
                ('company_id', '=', self.company_id.id)
            ])
            x_path = "/tmp/ComprobantesGenerados/"
            if not path.exists(x_path):
                os.mkdir(x_path)
            if obj.type == 'out_invoice':
               to_sign_file = open(x_path+'NOTA_DEBITO_SRI_'+self.name+".xml", 'w')
            to_sign_file.write(einvoice)
            to_sign_file.close()
            signed_document = xades.action_sign(to_sign_file)
            ok, errores = inv_xml.send_receipt(signed_document)
            if not ok:
                raise UserError(errores)

            sri_auth = self.env['sri.authorization'].create({
                'sri_authorization_code': access_key,
                'sri_create_date': self.write_date,
                'account_move': self.id,
                'env_service': self.company_id.env_service
            })
            self.write({'sri_authorization': sri_auth.id})
    
    
    def action_generate_einvoice(self):
        for obj in self:
            if obj.type not in ['out_invoice', 'out_refund'] and not obj.journal_id.is_electronic_document:
                continue
            access_key, emission_code = self._get_codes(name='account.move')
            einvoice = self.render_document(obj, access_key, emission_code)
            inv_xml = DocumentXML(einvoice, obj.type)
            if not inv_xml.validate_xml():
                raise UserError("Not Valid Schema")

            xades = self.env['sri.key.type'].search([
                ('company_id', '=', self.company_id.id)
            ])
            x_path = "/tmp/ComprobantesGenerados/"
            if not path.exists(x_path):
                os.mkdir(x_path)
            if obj.type == 'out_invoice':
               to_sign_file = open(x_path+'FACTURA_SRI_'+self.name+".xml", 'w')
            if obj.type == 'out_refund':
               to_sign_file = open(x_path+'NOTA_CREDITO_SRI_'+self.name+".xml", 'w')
            to_sign_file.write(einvoice)
            to_sign_file.close()
            signed_document = xades.action_sign(to_sign_file)
            ok, errores = inv_xml.send_receipt(signed_document)
            if not ok:
                raise UserError(errores)

            sri_auth = self.env['sri.authorization'].create({
                'sri_authorization_code': access_key,
                'sri_create_date': self.write_date,
                'account_move': self.id,
                'env_service': self.company_id.env_service
            })
            self.write({'sri_authorization': sri_auth.id})

    def get_auth(self):
        to_process = self.env['sri.authorization'].search([
            ('processed', '=', False)
        ])

        for data in to_process:

            xml = DocumentXML()
            id_move = data.account_move.id
            auth, m = xml.request_authorization(data.sri_authorization_code)
            if not auth:
                msg = ' '.join(list(itertools.chain(*m)))
                raise UserError(msg)
            data.write({'sri_authorization_date': auth['fechaAutorizacion']})
            data.write({'processed': True})
            auth_einvoice = self.render_authorized_einvoice(auth)
            attach = self.add_attachment(auth_einvoice, auth, id_move)
            message = """
                        DOCUMENTO ELECTRONICO GENERADO <br><br>
                        CLAVE DE ACCESO: %s <br>
                        NUMERO DE AUTORIZACION %s <br>
                        FECHA AUTORIZACION: %s <br>
                        ESTADO DE AUTORIZACION: %s <br>
                        AMBIENTE: %s <br>
                        """ % (
                                auth['numeroAutorizacion'],
                                auth['numeroAutorizacion'],
                                auth['fechaAutorizacion'],
                                auth['estado'],
                                'PRUEBAS' if self.company_id.env_service == '1' else 'PRODUCCION'
            )
            #template_id = self.env.ref(
            #    'l10n_ec_ein.email_template_einvoice').id
            #template = self.env['mail.template'].browse(template_id)
            #template.attachment_ids = [(6, 0, [attach.id])]
            #template.send_mail(self.id, force_send=True)

    def add_attachment(self, xml_element, auth, id_move):
        buf = BytesIO()
        buf.write(xml_element.encode('utf-8'))
        document = base64.encodebytes(buf.getvalue())
        buf.close()
        ctx = self.env.context.copy()
        ctx.pop('default_type', False)
        attach = self.env['ir.attachment'].with_context(ctx).create(
            {
                'name': '{0}.xml'.format(auth['numeroAutorizacion']),
                'datas': document,
                'db_datas': document,
                'res_model': self._name,
                'res_id': id_move,
                'type': 'binary'
            },
        )
        return attach

    def send_document(self, attachments=None, tmpl=False):
        self.ensure_one()
        self._logger.info('Enviando documento electronico por correo')
        tmpl = self.env.ref(tmpl)
        tmpl.send_mail(  # noqa
            self.id,
            #email_values={'attachment_ids': attachments}
        )
        self.sent = True
        return True

    def _compute_discount(self, detalles):
        total = sum([float(det['descuento']) for det in detalles['detalles']])
        return {'totalDescuento': total}

    def render_document(self, invoice, access_key, emission_code):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        einvoice_tmpl = env.get_template(self.TEMPLATES[self.type])
        data = {}
        data.update(self._info_tributaria(invoice, access_key, emission_code))
        data.update(self._info_invoice())
        detalles = self._detalles(invoice)

        data.update(detalles)
        data.update(self._compute_discount(detalles))
        einvoice = einvoice_tmpl.render(data)
        logging.error("Archivo XML")
        logging.error(einvoice)
        return einvoice
        
        
    def render_document_debit(self, invoice, access_key, emission_code):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        einvoice_tmpl = env.get_template(self.TEMPLATES['out_debit'])
        data = {}
        data.update(self._info_tributaria(invoice, access_key, emission_code))
        data.update(self._info_invoice())
        detalles = self._detalles(invoice)
        motivos = self._motivos(invoice)
        data.update(detalles)
        data.update(motivos)
        #data.update(self._compute_discount(detalles))
        einvoice = einvoice_tmpl.render(data)
        logging.error("Archivo XML")
        logging.error(einvoice)
        return einvoice

    def action_send_cliente(self):
        for obj in self:
            if obj.type not in ['out_invoice', 'out_refund', 'liq_purchase']:
                continue
        to_process = self.env['sri.authorization'].search([
            ('account_move', '=', self.id)
        ])
        for data in to_process:
            # estab_code = str(data.sri_authorization_code[24:27])
            # punto_code = str(data.sri_authorization_code[27:30])
            # factura_code = str(data.sri_authorization_code[30:39])
            # pdf_name = "FACTURA_" + estab_code + "-" + punto_code + "-" \
            #            + factura_code + '.pdf'
            # attach_pdf = self.env['ir.attachment'].search([('name', '=',
            #                                         pdf_name)], limit=1)
            ambientepp = str(data.sri_authorization_code[23])
            if not data.processed:
                xml = DocumentXML()
                id_move = data.account_move.id
                auth, m = xml.request_authorization(data.sri_authorization_code)
                if not auth:
                    msg = ' '.join(list(itertools.chain(*m)))
                    raise UserError(msg)
                data.write({'sri_authorization_date': auth['fechaAutorizacion']})
                data.write({'processed': True})
                auth_einvoice = self.render_authorized_einvoice(auth)
                attach = self.add_attachment(auth_einvoice, auth, id_move)
                message = """
                        DOCUMENTO ELECTRONICO GENERADO <br><br>
                        CLAVE DE ACCESO: %s <br>
                        NUMERO DE AUTORIZACION %s <br>
                        FECHA AUTORIZACION: %s <br>
                        ESTADO DE AUTORIZACION: %s <br>
                        AMBIENTE: %s <br>
                        """ % (
                                auth['numeroAutorizacion'],
                                auth['numeroAutorizacion'],
                                auth['fechaAutorizacion'],
                                auth['estado'],
                                'PRUEBAS' if ambientepp == '1' else 'PRODUCCION'
                        )
                data.account_move.message_post(body=message, attachments=[str(auth)])
            else:
                inv_name = str(data.sri_authorization_code) + '.xml'
                attach = self.env['ir.attachment'].search([('name', '=',
                                                        inv_name)], limit=1)

            if self.type == 'out_invoice' and not self.debit_origin_id: 
               template_id = self.env.ref('l10n_ec_ein.email_template_einvoice').id
            if self.type == 'out_refund':
               template_id = self.env.ref('l10n_ec_ein.email_template_enotacredito').id
            if self.type == 'liq_purchase':
               template_id = self.env.ref('l10n_ec_ein.email_template_eliquidation').id
            if self.type == 'out_invoice' and self.debit_origin_id: 
               template_id = self.env.ref('l10n_ec_ein.email_template_enotadebito').id
            template = self.env['mail.template'].browse(template_id)
            template.attachment_ids = [(6, 0, [attach.id])]
            if template.send_mail(self.id, force_send=True):
                view = self.env.ref('sh_message.sh_message_wizard')
                view_id = view and view.id or False
                context = dict(self._context or {})
                context['message'] = "Correo enviado satisfactoriamente"
                return{
                    'name': 'Comunicado',
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'sh.message.wizard',
                    'views': [(view.id, 'form')],
                    'view_id': view.id,
                    'target': 'new',
                    'context': context,
                }

    @staticmethod
    def _read_template(type):
        with open(os.path.join(os.path.dirname(__file__), 'templates', type + ".xml")) as template:
            return template

    @staticmethod
    def render(self, template_path, **kwargs):
        return Template(
            self._read_template(template_path)
        ).substitute(**kwargs)
    
    @api.onchange('type_doc')
    def _onchange_type_doc(self):
        if self.type_doc.code == '03':
            self.is_liquidation = True
    
    def action_post(self):
        super(AccountMove, self).action_post()
        for ref in self:
           if ref.type_doc.code == '03':
               ref.write({'type': 'liq_purchase'})
        return True 
