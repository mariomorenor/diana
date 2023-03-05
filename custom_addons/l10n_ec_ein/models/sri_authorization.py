from odoo import fields, models, api


class SriAuthorization (models.Model):
    _name = 'sri.authorization'
    _description = 'SRI Authorization'

    sri_authorization_code = fields.Char()
    sri_create_date = fields.Datetime()
    sri_authorization_date = fields.Char()
    processed = fields.Boolean(default=False)
    env_service = fields.Selection(
        [
            ('1', 'Test'),
            ('2', 'Production')
        ],
        string='Environment Type',
        required=True,
        )

    account_move = fields.Many2one('account.move', string='Invoice Related')
    retention_id = fields.Many2one('account.retention', string='Retencion Relacionada')
    guia_id = fields.Many2one('stock.picking', string='Guìa Relacionada')
    error_code = fields.Selection(
        [
            ('2', 'RUC del emisor NO se encuentra ACTIVO'),
            ('2', 'Production')
        ],
        string='Environment Type',
        required=False,
    )

    def name_get(self):
        result = []
        for record in self:
            name = record.sri_authorization_code
            result.append((record.id, name))
        return result

    


