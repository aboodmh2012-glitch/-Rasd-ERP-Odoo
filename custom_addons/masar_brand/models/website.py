# Part of MASAR.
from odoo import models


class Website(models.Model):
    _inherit = "website"

    def _default_masar_name(self):
        return "MASAR"
