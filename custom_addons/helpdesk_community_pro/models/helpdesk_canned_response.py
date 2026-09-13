"""Helpdesk canned response: a reusable reply template for agents."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import fields, models


class HelpdeskCannedResponse(models.Model):  # pylint: disable=too-few-public-methods
    """A reusable reply template, optionally scoped to specific teams."""

    _name = "helpdesk.canned.response"
    _description = "Helpdesk Canned Response"
    _order = "name"

    name = fields.Char(required=True)
    body = fields.Html(required=True)
    team_ids = fields.Many2many(
        "helpdesk.team",
        string="Teams",
        help="Leave empty to make this response available to every team.",
    )
    active = fields.Boolean(default=True)
