"""Public CSAT rating endpoint: no login required, signed-token access."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
from odoo import http
from odoo.http import request

VALID_RATINGS = ("good", "okay", "bad")


class HelpdeskRating(http.Controller):  # pylint: disable=too-few-public-methods
    """One-click satisfaction rating, reached from the CSAT email."""

    @http.route(
        ["/helpdesk/rate/<int:ticket_id>/<string:token>/<string:rating>"],
        type="http",
        auth="public",
        website=True,
    )
    def rate_ticket(self, ticket_id, token, rating, **kw):
        # pylint: disable=unused-argument
        # **kw absorbs stray query-string params so an unexpected one
        # doesn't turn into a TypeError on this public route.
        """Validate the signed token and record the customer's rating.

        No record id from the URL is trusted without a check: the token is
        an hmac of ticket_id itself (helpdesk.ticket._get_rating_token), so
        a token can never be replayed against a different ticket_id.
        """
        ticket = request.env["helpdesk.ticket"].sudo().browse(ticket_id).exists()
        # pylint: disable=protected-access
        if (
            not ticket
            or rating not in VALID_RATINGS
            or not ticket._rating_token_is_valid(token)
        ):
            return request.render(
                "helpdesk_community_pro.rating_feedback_page", {"state": "invalid"}
            )

        if not ticket._apply_rating(rating):
            return request.render(
                "helpdesk_community_pro.rating_feedback_page",
                {"state": "locked", "ticket": ticket},
            )

        return request.render(
            "helpdesk_community_pro.rating_feedback_page",
            {"state": "thanks", "ticket": ticket, "rating_label": rating.capitalize()},
        )
