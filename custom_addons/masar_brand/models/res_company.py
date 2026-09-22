# Part of MASAR.
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    masar_brand_name = fields.Char(
        string="Brand",
        default="MASAR",
        help="Public brand name used across MASAR surfaces.",
    )
