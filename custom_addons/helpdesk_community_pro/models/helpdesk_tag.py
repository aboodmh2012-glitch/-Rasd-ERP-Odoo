"""Helpdesk tag: free-form label applied to tickets."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import fields, models


class HelpdeskTag(models.Model):  # pylint: disable=too-few-public-methods
    """A free-form label that can be applied to helpdesk tickets."""

    _name = "helpdesk.tag"
    _description = "Helpdesk Ticket Tag"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string="Color Index")

    # PORT-19: _sql_constraints is replaced by the models.Constraint API.
    _name_uniq = models.Constraint(
        "unique(name)",
        "A tag with this name already exists.",
    )
