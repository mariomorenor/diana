# -*- coding: utf-8 -*-
import time
import datetime
import calendar
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

from ..xades.sri import DocumentXML, SriService
from ..xades.xades import Xades
import os.path
from os import path

sign = '/tmp/sign.p12'

class AccountWithdrawing(models.Model):
    """ Implementacion de documento electronico de retencion """
    _name = 'account.retention'
    _inherit = ['account.retention', 'account.edocument']
    _logger = logging.getLogger('account.edocument')
    
    SriServiceObj = SriService()

    sri_authorization = fields.Many2one('sri.authorization', copy=False)
    sri_payment_type = fields.Many2one('sri.payment_type', copy=False)
    sri_authorization_date = fields.Char(string='Fecha autorización',
                            related='sri_authorization.sri_authorization_date')
    auth_number_prov = fields.Char(u'Número de autorización')
        
    def get_secuencial(self):
        return getattr(self, 'name')[6:15]
        
    def _info_withdrawing(self, withdrawing):
        """
        """
        # generar infoTributaria
        company = withdrawing.company_id
        partner = withdrawing.invoice_id.partner_id
        infoCompRetencion = {
            'fechaEmision': withdrawing.date.strftime("%d/%m/%Y"),  # noqa
            'dirEstablecimiento': company.street,
            'obligadoContabilidad': 'SI',
            'tipoIdentificacionSujetoRetenido': partner.taxid_type.code,  # noqa
            'razonSocialSujetoRetenido': partner.name,
            'identificacionSujetoRetenido': partner.vat,
            'periodoFiscal': withdrawing.date.strftime('%m/%Y')
            }
        #if company.company_registry:
            #infoCompRetencion.update({'contribuyenteEspecial': company.company_registry})  # noqa
        return infoCompRetencion
    
    def _impuestos(self, retention):
        """
        """
        def get_codigo_retencion(linea):
            if linea.tax_id.tax_group_id.code in ['ret_vat_b', 'ret_vat_srv']:
                return utils.tabla21[linea.tax_id.percent_report]
            else:
                code = linea.tax_id.description   # noqa
                return code

        impuestos = []
        for line in retention.tax_ids:
            impuesto = {
                'codigo': utils.tabla20[line.tax_id.tax_group_id.code],
                'codigoRetencion': get_codigo_retencion(line),
                'baseImponible': '%.2f' % (line.base),
                'porcentajeRetener': str(line.tax_id.percent_report),
                'valorRetenido': '%.2f' % (abs(line.amount)),
                'codDocSustento': retention.invoice_id.type_doc.code,
                'numDocSustento': retention.invoice_id.ref,
                'fechaEmisionDocSustento': retention.invoice_id.invoice_date.strftime("%d/%m/%Y") # noqa
            }
            impuestos.append(impuesto)
        return {'impuestos': impuestos}

    def render_document(self, document, access_key, emission_code):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        ewithdrawing_tmpl = env.get_template('ewithdrawing.xml')
        data = {}
        data.update(self._info_tributaria_retencion(document, access_key, emission_code))
        data.update(self._info_withdrawing(document))
        data.update(self._impuestos(document))
        edocument = ewithdrawing_tmpl.render(data)
        logging.error("Archivo XML Retencion")
        logging.error(edocument)
        return edocument

    def render_authorized_document(self, autorizacion):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        edocument_tmpl = env.get_template('authorized_withdrawing.xml')
        auth_xml = {
            'estado': autorizacion.estado,
            'numeroAutorizacion': autorizacion.numeroAutorizacion,
            'ambiente': autorizacion.ambiente,
            'fechaAutorizacion': str(autorizacion.fechaAutorizacion.strftime("%d/%m/%Y %H:%M:%S")),  # noqa
            'comprobante': autorizacion.comprobante
        }
        auth_withdrawing = edocument_tmpl.render(auth_xml)
        return auth_withdrawing
           
    def render_authorized_document(self, autorizacion):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        edocument_tmpl = env.get_template('authorized_withdrawing.xml')
        auth_xml = {
            'estado': autorizacion.estado,
            'numeroAutorizacion': autorizacion.numeroAutorizacion,
            'ambiente': autorizacion.ambiente,
            'fechaAutorizacion': str(autorizacion.fechaAutorizacion.strftime("%d/%m/%Y %H:%M:%S")),  # noqa
            'comprobante': autorizacion.comprobante
        }
        auth_withdrawing = edocument_tmpl.render(auth_xml)
        return auth_withdrawing
    
    def get_auth(self):
        to_process = self.env['sri.authorization'].search([
            ('processed', '=', False)
        ])

        for data in to_process:

            xml = DocumentXML()
            id_retention = data.retention_id.id
            auth, m = xml.request_authorization(data.sri_authorization_code)
            if not auth:
                msg = ' '.join(list(itertools.chain(*m)))
                raise UserError(msg)
            data.write({'sri_authorization_date': auth['fechaAutorizacion']})
            data.write({'processed': True})
            auth_document = self.render_authorized_document(auth)
            attach = self.add_attachment(auth_document, auth, id_retention)
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
    
    def add_attachment(self, xml_element, auth, id_retention):
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
                'res_id': id_retention,
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
    def action_send_cliente(self):
        for obj in self:
            if obj.type not in ['out_invoice', 'out_refund', 'liq_purchase']:
                continue
        to_process = self.env['sri.authorization'].search([
            ('retention_id', '=', self.id)
        ])
        for data in to_process:
            ambientepp = str(data.sri_authorization_code[23])
            if not data.processed:
                xml = DocumentXML()
                id_retention = data.retention_id.id
                auth, m = xml.request_authorization(data.sri_authorization_code)
                if not auth:
                    msg = ' '.join(list(itertools.chain(*m)))
                    raise UserError(msg)
                data.write({'sri_authorization_date': auth['fechaAutorizacion']})
                data.write({'processed': True})
                auth_document = self.render_authorized_document(auth)
                attach = self.add_attachment(auth_document, auth, id_retention)
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
                data.retention_id.message_post(body=message, attachments=[str(auth)])
            else:
                inv_name = str(data.sri_authorization_code) + '.xml'
                attach = self.env['ir.attachment'].search([('name', '=',
                                                        inv_name)], limit=1)

            template_id = self.env.ref('l10n_ec_ein.email_template_eretention').id
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
    def action_generate_document(self):
        for obj in self:
            #if obj.type not in ['out_invoice', 'out_refund'] and not obj.journal_id.is_electronic_document:
                #continue
            access_key, emission_code = self._get_codes(name='account.retention')
            ewithdrawing = self.render_document(obj, access_key, emission_code)
            inv_xml = DocumentXML(ewithdrawing, 'withdrawing')
            logging.error("ARCHIVO XML")
            logging.error(inv_xml)
            if not inv_xml.validate_xml():
                raise UserError("Not Valid Schema")

            xades = self.env['sri.key.type'].search([
                ('company_id', '=', self.company_id.id)
            ])
            x_path = "/tmp/ComprobantesGenerados/"
            if not path.exists(x_path):
                os.mkdir(x_path)
            to_sign_file = open(x_path+'RETENCION_SRI_'+self.name+".xml", 'w')
            to_sign_file.write(ewithdrawing)
            to_sign_file.close()
            signed_document = xades.action_sign(to_sign_file)
            logging.error("Archivo XML Firmado Retencion")
            logging.error(signed_document)
            ok, errores = inv_xml.send_receipt(signed_document)
            if not ok:
                raise UserError(errores)

            sri_auth = self.env['sri.authorization'].create({
                'sri_authorization_code': access_key,
                'sri_create_date': self.write_date,
                'retention_id': self.id,
                'env_service': self.company_id.env_service
            })
            self.write({'sri_authorization': sri_auth.id})
