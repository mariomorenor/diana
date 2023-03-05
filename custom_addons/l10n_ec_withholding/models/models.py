# -*- coding: utf-8 -*-
import time
import datetime
import calendar
import logging       
from odoo import api, fields, models
_logger = logging.getLogger('account.edocument')
class AccountWithdrawing(models.Model):
    """ Implementacion de documento de retencion """
    STATES_VALUE = {'draft': [('readonly', False)]}
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin']
    _name = 'account.retention'
    _description = 'Withdrawing Documents'
    _order = 'date DESC'
    
    @api.depends('tax_ids.amount')
    def _compute_total(self):
        """
        TODO
        """
        self.amount_total = sum(tax.amount for tax in self.tax_ids)
    
    def _default_type(self):
        context = self._context
        return context.get('type', 'out_invoice')
    
    def _get_in_type(self):
        context = self._context
        return context.get('in_type', 'ret_out_invoice')
    
    def _default_currency(self):
        company = self.env['res.company']._company_default_get('account.move')  # noqa
        return company.currency_id
    
    def _default_authorisation(self):
        if self.env.context.get('in_type') == 'ret_in_invoice':
            journal = self.env['account.journal'].search([('sri_doctype', '=', '07')],limit=1)
            return journal.id
    name = fields.Char(
        'Número',
        size=64,
        readonly=True,
        states=STATES_VALUE,
        copy=False
        )
    internal_number = fields.Char(
        'Número Interno',
        size=64,
        readonly=True,
        copy=False
        )
    manual = fields.Boolean(
        'Numeración Manual',
        readonly=True,
        states=STATES_VALUE,
        default=True
        )
    type = fields.Selection(
        related='invoice_id.type',
        string='Tipo Comprobante',
        readonly=True,
        store=True,
        default=_default_type
        )
    in_type = fields.Selection(
        [
            ('ret_in_invoice', u'Retención a Proveedor'),
            ('ret_out_invoice', u'Retención de Cliente')
        ],
        string='Tipo',
        readonly=True,
        default=_get_in_type
        )
    date = fields.Date(
        'Fecha Emision',
        readonly=True,
        states={'draft': [('readonly', False)]}, required=True
    )
    tax_ids = fields.One2many(
        'account.invoice.tax',
        'retention_id',
        'Detalle de Impuestos',
        readonly=True,
        states=STATES_VALUE,
        copy=False
        )
    invoice_id = fields.Many2one(
        'account.move',
        string='Documento',
        required=False,
        readonly=True,
        states=STATES_VALUE,
        domain=[('state', '=', 'open')],
        copy=False
        )
    partner_id = fields.Many2one(
        'res.partner',
        string='Empresa',
        required=True,
        readonly=True,
        states=STATES_VALUE
        )
    state = fields.Selection(
        [
            ('draft', 'Borrador'),
            ('done', 'Validado'),
            ('cancel', 'Anulado')
        ],
        readonly=True,
        string='Estado',
        default='draft'
        )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=_default_currency
    )
    journal_id = fields.Many2one(
        'account.journal',
        'Autorizacion',
        readonly=True,
        states=STATES_VALUE,
        domain=[('sri_doctype', '=', '07')],
        default=_default_authorisation
        )
    amount_total = fields.Monetary(
        compute='_compute_total',
        string='Total',
        store=True,
        readonly=True
        )
    to_cancel = fields.Boolean(
        string='Para anulación',
        readonly=True,
        states=STATES_VALUE
        )
    company_id = fields.Many2one(
        'res.company',
        'Company',
        required=True,
        change_default=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        default=lambda self: self.env['res.company']._company_default_get('account.move')  # noqa
        )
    def action_cancel(self):
        """
        Método para cambiar de estado a cancelado el documento
        """
        self.write({'state': 'cancel'})
        return True
        
    def action_number(self, number):
        for wd in self:
            if wd.to_cancel:
                raise UserError('El documento fue marcado para anular.')

            sequence = wd.journal_id.sequence_id
            if self.type != 'out_invoice' and not number:
                number = sequence.next_by_id()
                #number = '{0}{1}{2}'.format(sequence.prefix,'-',number)
            wd.write({'name': number})
        return True
    
    def action_validate(self, number=None):
        """
        @number: Número para usar en el documento
        """
        self.action_number(number)
        return self.write({'state': 'done'})
        
    def action_draft(self):
        self.write({'state': 'draft'})
        return True
    
    def create_move(self):
        """
        Generacion de asiento contable para aplicar como
        pago a factura relacionada
        """
        for ret in self:
            inv = ret.invoice_id
            move_data = {
                'journal_id': inv.journal_id.id,
                'ref': ret.name,
                'date': ret.date
            }
            total_counter = 0
            lines = []
            for line in ret.tax_ids:
                if not line.manual:
                    continue
                if self.type == 'in_invoice':
                    lines.append((0, 0, {
                    'partner_id': ret.partner_id.id,
                    'account_id': line.account_id.id,
                    'name': ret.name,
                    'debit': 0.00,
                    'credit': abs(line.amount)
                    }))
                else:
                    lines.append((0, 0, {
                    'partner_id': ret.partner_id.id,
                    'account_id': line.account_id.id,
                    'name': ret.name,
                    'debit': abs(line.amount),
                    'credit': 0.00
                    }))

                total_counter += abs(line.amount)

            if self.type == 'in_invoice':
                    lines.append((0, 0, {
                'partner_id': ret.partner_id.id,
                'account_id': inv.account_id.id,
                'name': ret.name,
                'debit': total_counter,
                'credit': 0.00
                }))
            else:
                lines.append((0, 0, {
                'partner_id': ret.partner_id.id,
                'account_id': inv.partner_id.property_account_receivable_id.id,
                'name': ret.name,
                'debit': 0.00,
                'credit': total_counter
                }))
            move_data.update({'line_ids': lines})
            move = self.env['account.move'].create(move_data)
            acctype = self.type == 'in_invoice' and 'payable' or 'receivable'
            inv_lines = inv.line_ids
            acc2rec = inv_lines.filtered(lambda l: l.account_id.internal_type == acctype)  # noqa
            acc2rec += move.line_ids.filtered(lambda l: l.account_id.internal_type == acctype)  # noqa
            acc2rec.auto_reconcile_lines()
            #ret.write({'move_ret_id': move.id})
            move.post()
        return True    
    
    def button_validate(self):
        """
        Botón de validación de Retención que se usa cuando
        se creó una retención manual, esta se relacionará
        con la factura seleccionada.
        """
        for ret in self:
            if not ret.tax_ids:
                raise UserError('No ha aplicado impuestos.')
            self.action_validate(self.name)
            if ret.manual:
                ret.invoice_id.write({'retention_id': ret.id})
                if ret.in_type == 'ret_out_invoice':
                    self.create_move()
        return True
                
class AccountInvoiceTax(models.Model):
    _name = "account.invoice.tax"
    _description = "Invoice Tax"
    _order = 'sequence'
    
    invoice_id = fields.Many2one('account.move', string='Invoice', ondelete='cascade', index=True)
    name = fields.Char(string='Tax Description', required=True)
    tax_id = fields.Many2one('account.tax', string='Tax', ondelete='restrict')
    #account_id = fields.Many2one('account.account', string='Tax Account', required=True, domain=[('deprecated', '=', False)])
    account_id = fields.Many2one('account.account', string='Tax Account', domain=[('deprecated', '=', False)])    
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic account')
    amount = fields.Monetary()
    manual = fields.Boolean(default=True)
    sequence = fields.Integer(help="Gives the sequence order when displaying a list of invoice tax.")
    company_id = fields.Many2one('res.company', string='Company', related='account_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='invoice_id.currency_id', store=True, readonly=True)
    base = fields.Monetary(string='Base', 
       #compute='_compute_base_amount'
       )
    retention_id = fields.Many2one(
        'account.retention',
        'Retención',
        index=True
    )
    fiscal_year = fields.Char(
        'Ejercicio Fiscal',
        size=4,
        default=time.strftime('%Y')
    )
    group_id = fields.Many2one(
        related='tax_id.tax_group_id',
        store=True,
        string='Grupo'
    )
    base = fields.Float('Base')
    code = fields.Char(
        related='tax_id.description',
        string='Código',
        store=True
    )
    percent_report = fields.Char(related='tax_id.percent_report')
    
    @api.onchange('tax_id')
    def _onchange_tax(self):
        account = self.env['account.account']
        tax = self.env['account.tax'].search([('id','=',self.tax_id.id)])
        if tax:
            self.name = tax.description
        for line in tax.invoice_repartition_line_ids:
            if line.repartition_type == 'tax':
                account = line.account_id
        if account:
            self.account_id = account.id
    
class AccountTax(models.Model):

    _inherit = 'account.tax'

    percent_report = fields.Char('% para Reportes')
    
    
class AccountMove(models.Model):

    _inherit = 'account.move'
    STATES_VALUE = {'draft': [('readonly', False)]}
    
    @api.depends('invoice_line_ids.tax_ids')
    def _check_retention(self):
        flag = 0
        for line in self.invoice_line_ids:
            for tax in line.tax_ids:
                if tax.tax_group_id.code in ['ret_vat_b', 'ret_vat_srv', 'ret_ir']:
                    flag = 1
        if flag == 1:
            self.has_retention = True

        #ret_taxes = self.invoice_line_ids.filtered(lambda l: l.tax_line_id.tax_group_id.code in ['ret_vat_b', 'ret_vat_srv', 'ret_ir'])  # noqa
        #if ret_taxes:
            #self.has_retention = True
        #TAXES = ['ret_vat_b', 'ret_vat_srv', 'ret_ir']  # noqa
        #for tax in self.tax_line_ids:
            #if tax.tax_id.tax_group_id.code in TAXES:
                #self.has_retention = True
        
                
    def _default_authorisation(self):
        if self.env.context.get('type') == 'in_invoice':
            journal = self.env['account.journal'].search([('sri_doctype', '=', '07')],limit=1)
            return journal.id
    retention_id = fields.Many2one(
        'account.retention',
        string='Retención de Impuestos',
        store=True, readonly=True,
        copy=False
    )
    
    type_doc = fields.Many2one(
        'account.ats.doc',
        string='Tipo de Documento',
        store=True,
        copy=False
    )
    journal_retention_id = fields.Many2one(
        'account.journal',
        'Diario de Retenciones',
        states=STATES_VALUE,
        domain=[('sri_doctype', '=', '07')],
        default=_default_authorisation
        )
    has_retention = fields.Boolean(
        compute='_check_retention',
        string="Tiene Retención en IR",
        store=True,
        readonly=True
        )
        
    # def add_retention(self):
        # context="{'invoice_id': email}"
        # context = dict(self._context or {})
        # view = self.env.ref('l10n_ec_withholding.view_account_retention_form')
        # view_id = view and view.id or False
        # return{
        # 'name': 'Retencion',
        # 'type': 'ir.actions.act_window',
        # 'view_type': 'form',
        # 'view_mode': 'form',
        # 'res_model': 'account.retention',
        # 'views': [(view.id, 'form')],
        # 'view_id': view.id,
        # 'target': 'new',
        # 'invoice_id': self.id,
        # 'context': context}
    
    def action_withholding_create(self):
        """
        Este método genera el documento de retencion en varios escenarios
        considera casos de:
        * Generar retencion automaticamente
        * Generar retencion de reemplazo
        * Cancelar retencion generada
        """
        TYPES_TO_VALIDATE = ['in_invoice', 'liq_purchase']
        TYPES_INTO_VALIDATE = ['out_invoice']
        wd_number = False
        for inv in self:
            if not self.has_retention:
                continue
            if inv.type in TYPES_TO_VALIDATE or inv.type in TYPES_INTO_VALIDATE:
               ret_taxes = inv.invoice_line_ids.filtered(lambda l: l.tax_line_id.tax_group_id.code in ['ret_vat_b', 'ret_vat_srv', 'ret_ir'])  # noqa
               journal = self.env['account.journal']
               if inv.type in TYPES_TO_VALIDATE:
                   journal = self.journal_retention_id
               if inv.type == 'out_invoice':
                   journal = inv.journal_id
               withdrawing_data = {
                   'partner_id': inv.partner_id.id,
                   'name': wd_number,
                   'invoice_id': inv.id,
                   'journal_id': journal.id,
                   'type': inv.type,
                   'in_type': 'ret_%s' % inv.type,
                   'date': inv.invoice_date,
                   'manual': False
               }
               withdrawing = self.env['account.retention'].create(withdrawing_data)  # noqa
               res = []
               lineas_movimiento = self.env['account.move.line'].search([('move_id','=',self.id)])
               for line in lineas_movimiento:
                   logging.error("Impuestos 1313")
                   logging.error(line.tax_line_id)
                   logging.error(line.price_total)
                   logging.error('Descripcion Impuesto')
                   logging.error(line.tax_line_id.description)
                   if line.price_total < 0 and line.tax_line_id:
                       base = 0.00
                       if line.tax_line_id.tax_group_id.code in ['ret_vat_b', 'ret_vat_srv']:
                           base = 100 * abs(line.price_subtotal) / abs(line.tax_line_id.amount)
                       else:
                           base = line.tax_base_amount
                       detalle = {
                         'tax_id': line.tax_line_id.id,
                         'name': line.tax_line_id.description,
                         'group_id': line.tax_line_id.tax_group_id.id,
                         'fiscal_year': inv.invoice_date.strftime('%Y'),
                         'manual': True,
                         'amount': '%.2f' % line.price_subtotal,
                         'base': '%.2f' % base,
                         'retention_id': withdrawing.id 
                       }
                       logging.error("Impuestos")
                       res.append((0,0, detalle))
               withdrawing.write({'tax_ids': res})
               if inv.type in TYPES_TO_VALIDATE:
                   withdrawing.action_validate()
               inv.write({'retention_id': withdrawing.id})
        return True
    def action_post(self):
        super(AccountMove, self).action_post()
        #if self.type in ['in_invoice', 'liq_purchase']:
           #self.action_withholding_create()
        self.action_withholding_create()
        return True
        
    def button_draft(self):
        super(AccountMove, self).button_draft()
        self.retention_id = False
        return True

class AccountTaxGroup(models.Model):
    _inherit = 'account.tax.group'
    code = fields.Char('Código')

class AccountAtsDoc(models.Model):
    _name = 'account.ats.doc'
    _description = 'Tipos Comprobantes Autorizados'

    code = fields.Char('Código', size=2, required=True)
    name = fields.Char('Tipo Comprobante', size=64, required=True)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    retention_id = fields.Many2one(
        'account.retention',
        'Retención',
        index=True
    )
