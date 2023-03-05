# -*- coding: utf-8 -*-

import time
import datetime
import calendar
import logging       
from odoo import api, fields, models
from jinja2 import Environment, FileSystemLoader, Template

import base64
from io import BytesIO
import os
import itertools

from openerp.addons.l10n_ec_ein.xades.sri import DocumentXML, SriService
from openerp.addons.l10n_ec_ein.xades.xades import Xades
from openerp.addons.l10n_ec_ein.models import utils
from odoo.exceptions import Warning as UserError
import os.path
from os import path

sign = '/tmp/sign.p12'

_logger = logging.getLogger('account.edocument')

class RefGuideReason(models.Model):
    """Motivos del traslado"""
    _name = 'stock.picking.move.reason'
    _description = __doc__

    name = fields.Char('Razón')
class Picking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'account.edocument']
    _logger = logging.getLogger('account.edocument')
    
    SriServiceObj = SriService()

    sri_authorization = fields.Many2one('sri.authorization', copy=False)
    sri_payment_type = fields.Many2one('sri.payment_type', copy=False)
    sri_authorization_date = fields.Char(string='Fecha autorización',
                            related='sri_authorization.sri_authorization_date')
    auth_number_prov = fields.Char(u'Número de autorización')
    
    def _default_authorisation(self):
        journal = self.env['account.journal'].search([('sri_doctype', '=', '06')],limit=1)
        return journal.id
    
    TEMPLATE = 'erefguide.xml'
    STATES_VALUE = {'draft': [('readonly', False)]}
    
    carrier_id = fields.Many2one('res.partner', 'Transportista')
    carrier_plate = fields.Char('Placa')
    max_date = fields.Date('Fecha máxima de entrega')
    reason_id = fields.Many2one('stock.picking.move.reason', 'Motivo de traslado')
    route = fields.Char('Ruta')
    journal_id = fields.Many2one(
        'account.journal',
        'Autorizacion',
        states=STATES_VALUE,
        domain=[('sri_doctype', '=', '06')],
        default=_default_authorisation
        )
    picking_number = fields.Char(
        'Número',
        size=64,
        readonly=True,
        states=STATES_VALUE,
        copy=False
    )
    invoice_number = fields.Many2one(
        'account.move',
        'Número Factura',
        readonly=True,
        states=STATES_VALUE,
        copy=False
    )
    picking_number_total = fields.Char(
        'Número Guia',
        size=64,
        readonly=True,
        states=STATES_VALUE,
        copy=False
    )
    other_street = fields.Boolean(
        'Otra Direccion',
        states=STATES_VALUE,
    )
    dest_street = fields.Char(
        'Direccion Destino',
        size=64,
    )
    
    def button_validate(self):
        res = super(Picking, self).button_validate()
        if self.picking_type_id.code == 'outgoing':
            for picking in self:
                sequence = picking.journal_id.sequence_id
                if picking.picking_type_id.code == 'outgoing' and not picking.picking_number:
                    sequence_number = str(sequence.next_by_id())
                    picking.write({'picking_number_total': sequence_number})
                    picking.write({'picking_number': sequence_number[6:15]})
        return res
    
    def action_number(self):
        if not self.picking_number:
            for picking in self:
                sequence = picking.journal_id.sequence_id
                if picking.picking_type_id.code == 'outgoing' and not picking.picking_number:
                    sequence_number = str(sequence.next_by_id())
                    picking.write({'picking_number_total': sequence_number})
                    picking.write({'picking_number': sequence_number[6:15]})
        return True
        
    def do_authorize_sri(self):
        for obj in self:
            if not obj.journal_id.is_electronic_document:
                return True
            #obj.min_date = obj.date
            #obj.action_number()
            obj.action_generate_document()
    
    def render_authorized_document(self, autorizacion):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        edocument_tmpl = env.get_template('authorized_erefguide.xml')
        auth_xml = {
            'estado': autorizacion.estado,
            'numeroAutorizacion': autorizacion.numeroAutorizacion,
            'ambiente': autorizacion.ambiente,
            'fechaAutorizacion': str(autorizacion.fechaAutorizacion.strftime("%d/%m/%Y %H:%M:%S")),  # noqa
            'comprobante': autorizacion.comprobante
        }
        auth_withdrawing = edocument_tmpl.render(auth_xml)
        return auth_withdrawing        
    
    def add_attachment(self, xml_element, auth, id_guia):
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
                'res_id': id_guia,
                'type': 'binary'
            },
        )
        return attach
    
    def action_send_cliente(self):
        for obj in self:
            if obj.picking_type_id.code == 'outgoing':
                continue
        to_process = self.env['sri.authorization'].search([
            ('guia_id', '=', self.id)
        ])
        for data in to_process:
            ambientepp = str(data.sri_authorization_code[23])
            if not data.processed:
                xml = DocumentXML()
                id_guia = data.guia_id.id
                auth, m = xml.request_authorization(data.sri_authorization_code)
                if not auth:
                    msg = ' '.join(list(itertools.chain(*m)))
                    raise UserError(msg)
                data.write({'sri_authorization_date': auth['fechaAutorizacion']})
                data.write({'processed': True})
                auth_document = self.render_authorized_document(auth)
                attach = self.add_attachment(auth_document, auth, id_guia)
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
                data.guia_id.message_post(body=message, attachments=[str(auth)])
            else:
                inv_name = str(data.sri_authorization_code) + '.xml'
                attach = self.env['ir.attachment'].search([('name', '=',
                                                        inv_name)], limit=1)

            template_id = self.env.ref('l10n_ec_einvoice_picking.email_template_erefguide').id
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
            
    def check_date(self, date_invoice):
        """
        Validar que el envío del comprobante electrónico
        se realice dentro de las 24 horas posteriores a su emisión
        """
        LIMIT_TO_SEND = 60
        MESSAGE_TIME_LIMIT = u' '.join([
            u'Los comprobantes electrónicos deben',
            u'enviarse con máximo 24h desde su emisión.']
        )
        dt = datetime.strptime(date_invoice, '%Y-%m-%d %H:%M:%S')
        days = (datetime.now() - dt).days

    def _info_guia(self, erefguide):
        """
        """
        company = erefguide.company_id
        carrier = erefguide.carrier_id
        infoGuiaRemision = {
            'dirEstablecimiento': erefguide.picking_type_id.warehouse_id.partner_id.street2,
            'dirPartida': company.street2,
            'razonSocialTransportista': carrier.name,  # noqa
            'tipoIdentificacionTransportista': carrier.taxid_type.code,
            'rucTransportista': carrier.vat,
            'obligadoContabilidad': 'SI',
            'fechaIniTransporte': erefguide.scheduled_date.strftime("%d/%m/%Y"),
            'fechaFinTransporte': erefguide.max_date.strftime("%d/%m/%Y") if erefguide.max_date else erefguide.scheduled_date.strftime("%d/%m/%Y"),
            'placa': erefguide.carrier_plate,
        }
        return infoGuiaRemision
        
    def _destinatarios(self, erefguide):
        """
        """
        def fix_chars(code):
            special = [
                [u'%', ' '],
                [u'º', ' '],
                [u'Ñ', 'N'],
                [u'ñ', 'n'],
                [u'\n', ' ']
            ]
            for f, r in special:
                code = code.replace(f, r)
            return code

        def fix_date(date):
            d = time.strftime('%d/%m/%Y', time.strptime(date, '%Y-%m-%d'))
            return d

        destinatarios = []
        partner = erefguide.partner_id
        invoice = self.env['account.move']
        if not self.invoice_number:
           invoice = self.env['account.move'].search([('invoice_origin', '=', self.origin)])
           if invoice:
               if not invoice.sri_authorization:
                   raise UserError(u'Verificar que la Factura se encuentre generada y autorizada por el SRI')
           inv_number = '{0}-{1}-{2}'.format(invoice.name[:3], invoice.name[4:7], invoice.name[8:])
           erefguide.write({'invoice_number': invoice.id})
        if self.invoice_number:
           invoice = self.invoice_number
           if not invoice.sri_authorization:
               raise UserError(u'Verificar que la Factura se encuentre generada y autorizada por el SRI')
           inv_number = '{0}-{1}-{2}'.format(invoice.name[:3], invoice.name[4:7], invoice.name[8:])
        if self.other_street == True:
            street = self.dest_street
        else:
            street = invoice.partner_id.street
        destinatario = {
            'identificacionDestinatario': partner.vat,
            'razonSocialDestinatario': partner.name,
            'dirDestinatario': street,
            'motivoTraslado': erefguide.reason_id.name if erefguide.reason_id else '',
            'ruta': erefguide.route,
            'codDocSustento': utils.tipoDocumento[invoice.type],
            'numDocSustento': inv_number,
            #'numAutDocSustento' : '0902202101060407722200110010070000000137722200115', #Example
            'numAutDocSustento': invoice.sri_authorization.sri_authorization_code,
            'fechaEmisionDocSustento': invoice.invoice_date.strftime("%d/%m/%Y")
        }
        detalles = []
        for line in erefguide.move_lines:
            detalle = {
                'codigoInterno': line.product_id.name[1:25],
                'codigoAdicional': line.product_id.default_code,
                'descripcion': line.product_id.name,
                'cantidad': line.product_qty
            }
            detalles.append(detalle)
        destinatario.update({'detalles': detalles})
        destinatarios.append(destinatario)
        return {'destinatarios': destinatarios}
        
    def _info_adicional(self, erefguide):
        infoAdicional = {
            'informacionAdicional': 'ND'
        }
        return infoAdicional
        
    def render_document(self, erefguide, access_key, emission_code):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        erefguide_tmpl = env.get_template(self.TEMPLATE)
        data = {}
        data.update(self._info_tributaria_guia(erefguide, access_key, emission_code))
        data.update(self._info_guia(erefguide))
        destinatarios = self._destinatarios(erefguide)
        data.update(self._info_adicional(erefguide))
        data.update(destinatarios)
        erefguide = erefguide_tmpl.render(data)
        logging.error("Archivo XML GUIA")
        logging.error(erefguide)
        return erefguide
        
    def render_authorized_eerefguide(self, autorizacion):
        tmpl_path = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(tmpl_path))
        erefguide_tmpl = env.get_template('authorized_erefguide.xml')
        auth_xml = {
            'estado': autorizacion.estado,
            'numeroAutorizacion': autorizacion.numeroAutorizacion,
            'ambiente': autorizacion.ambiente,
            'fechaAutorizacion': str(autorizacion.fechaAutorizacion.strftime("%d/%m/%Y %H:%M:%S")),  # noqa
            'comprobante': autorizacion.comprobante
        }
        auth_refguide = erefguide_tmpl.render(auth_xml)
        return auth_refguide
        
    def action_generate_document(self):
        """
        Metodo de generacion de guia de remision electronica
        TODO: usar celery para enviar a cola de tareas
        la generacion de la factura y envio de email
        """
        for obj in self:
            access_key, emission_code = self._get_codes(name='stock.picking')
            logging.error('Clave de Acceso')
            logging.error(access_key)
            erefguide = self.render_document(obj, access_key, emission_code)
            inv_xml = DocumentXML(erefguide, 'stock_picking')
            if not inv_xml.validate_xml():
                raise UserError("Not Valid Schema")
            xades = self.env['sri.key.type'].search([
                ('company_id', '=', self.company_id.id)
            ])
            x_path = "/tmp/ComprobantesGenerados/"
            if not path.exists(x_path):
                os.mkdir(x_path)
            to_sign_file = open(x_path+'GUIA_REMISION_SRI_'+self.picking_number_total+".xml", 'w')
            to_sign_file.write(erefguide)
            to_sign_file.close()
            signed_document = xades.action_sign(to_sign_file)
            logging.error("Archivo XML Firmado Guia Remision")
            logging.error(signed_document)
            ok, errores = inv_xml.send_receipt(signed_document)
            if not ok:
                raise UserError(errores)
            sri_auth = self.env['sri.authorization'].create({
                'sri_authorization_code': access_key,
                'sri_create_date': self.write_date,
                'guia_id': self.id,
                'env_service': self.company_id.env_service
            })
            self.invoice_number.write({'picking_id': self.id})
            self.invoice_number.write({'picking_number_total': self.picking_number_total})
            self.write({'sri_authorization': sri_auth.id})
