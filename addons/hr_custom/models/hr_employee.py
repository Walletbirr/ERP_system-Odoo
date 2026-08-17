from odoo import fields, models

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    guarantee_document = fields.Binary(string="Guarantee Document", attachment=True)
    guarantee_document_filename = fields.Char(string="Guarantee Document Filename")

    resume_file = fields.Binary(string="Resume/CV", attachment=True)
    resume_file_filename = fields.Char(string="Resume Filename")

    guarantor_id_document = fields.Binary(string="Guarantee ID", attachment=True)
    guarantor_id_document_filename = fields.Char(string="Guarantee ID Filename")