"""Helpdesk team: agent group that owns a queue of tickets."""

import ast

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import fields, models

RATING_SCORE = {"good": 100, "okay": 50, "bad": 0}


class HelpdeskTeam(models.Model):  # pylint: disable=too-few-public-methods
    """A support team: members, working calendar and ticket queue."""

    _name = "helpdesk.team"
    _description = "Helpdesk Team"
    _inherit = ["mail.alias.mixin"]
    _order = "name"

    name = fields.Char(required=True, translate=True)
    alias_id = fields.Many2one(
        help="Incoming emails to this address become tickets for this "
        "team; replies thread into the ticket's chatter."
    )
    ticket_count = fields.Integer(compute="_compute_ticket_count")
    csat_enabled = fields.Boolean(
        default=True,
        help="Send a satisfaction rating email when a ticket from this "
        "team is closed.",
    )
    csat_avg = fields.Float(
        string="CSAT",
        compute="_compute_csat_avg",
        help="Average satisfaction score (Good=100 / Okay=50 / Bad=0) "
        "over this team's rated tickets.",
    )
    sla_compliance = fields.Float(
        string="SLA Compliance",
        compute="_compute_sla_compliance",
        help="Percentage of this team's SLA-tracked, closed tickets that "
        "met their deadline.",
    )
    avg_resolution_hours = fields.Float(
        string="Avg. Resolution (h)",
        compute="_compute_avg_resolution_hours",
        help="Average calendar-aware working hours from creation to close "
        "over this team's closed tickets.",
    )
    member_ids = fields.Many2many(
        "res.users",
        string="Team Members",
        domain=[("share", "=", False)],
    )
    calendar_id = fields.Many2one(
        "resource.calendar",
        string="Working Hours",
        required=True,
        default=lambda self: self.env.company.resource_calendar_id,
        help="Working calendar used to compute SLA deadlines for this team.",
    )
    color = fields.Integer(string="Color Index")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)

    def _compute_ticket_count(self):
        # pylint: disable=protected-access
        data = self.env["helpdesk.ticket"]._read_group(
            [("team_id", "in", self.ids)], ["team_id"], ["__count"]
        )
        counts = {team.id: count for team, count in data}
        for team in self:
            team.ticket_count = counts.get(team.id, 0)

    def _compute_csat_avg(self):
        # pylint: disable=protected-access
        groups = self.env["helpdesk.ticket"]._read_group(
            [("team_id", "in", self.ids), ("rating", "!=", False)],
            ["team_id", "rating"],
            ["__count"],
        )
        totals = {}
        for team, rating, count in groups:
            score_sum, ticket_count = totals.setdefault(team.id, [0, 0])
            totals[team.id] = [
                score_sum + RATING_SCORE[rating] * count,
                ticket_count + count,
            ]
        for team in self:
            score_sum, ticket_count = totals.get(team.id, (0, 0))
            team.csat_avg = (score_sum / ticket_count) if ticket_count else 0.0

    def _compute_sla_compliance(self):
        # pylint: disable=protected-access
        groups = self.env["helpdesk.ticket"]._read_group(
            [
                ("team_id", "in", self.ids),
                ("sla_id", "!=", False),
                ("close_date", "!=", False),
            ],
            ["team_id", "sla_reached"],
            ["__count"],
        )
        totals = {}
        for team, sla_reached, count in groups:
            met, total = totals.setdefault(team.id, [0, 0])
            totals[team.id] = [met + (count if sla_reached else 0), total + count]
        for team in self:
            met, total = totals.get(team.id, (0, 0))
            team.sla_compliance = (met / total * 100) if total else 0.0

    def _compute_avg_resolution_hours(self):
        # pylint: disable=protected-access
        groups = self.env["helpdesk.ticket"]._read_group(
            [("team_id", "in", self.ids), ("close_date", "!=", False)],
            ["team_id"],
            ["resolution_hours:avg"],
        )
        averages = {team.id: avg for team, avg in groups}
        for team in self:
            team.avg_resolution_hours = averages.get(team.id, 0.0)

    def action_view_tickets(self):
        """Open this team's tickets, pre-filtered to this team."""
        self.ensure_one()
        # pylint: disable=protected-access
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "helpdesk_community_pro.helpdesk_ticket_action"
        )
        action["domain"] = [("team_id", "=", self.id)]
        action["context"] = {"default_team_id": self.id}
        return action

    def _alias_get_creation_values(self):
        """Route this team's alias to helpdesk.ticket, defaulting team_id."""
        values = super()._alias_get_creation_values()
        # pylint: disable=protected-access
        values["alias_model_id"] = self.env["ir.model"]._get("helpdesk.ticket").id
        if self.id:
            defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults["team_id"] = self.id
            values["alias_defaults"] = defaults
        return values
