"""UI smoke test: every Helpdesk view must open without a client-side error."""

# pylint: disable=import-error
# odoo is not installed in the isolated pylint-odoo pre-commit environment.
import odoo.tests
from odoo.tests.common import new_test_user

from .common import make_mon_fri_calendar


@odoo.tests.tagged("post_install", "-at_install")
class TestHelpdeskUiViews(odoo.tests.HttpCase):
    """Click through every Helpdesk menu and view switch as admin.

    Regression test for the 19.0 kanban port: get_views() validates arch
    XML but never executes client-side OWL rendering, so a mismatched
    kanban template name (kanban-box vs card) passed server-side install
    and only surfaced as a browser OwlError. This drives the real web
    client the way a user would and fails on any error dialog or JS error.
    """

    @classmethod
    def setUpClass(cls):  # pylint: disable=invalid-name
        """Grant admin manager rights so the crawl can reach every menu."""
        super().setUpClass()
        # A fresh admin has no helpdesk_community_pro group by default (same as any
        # real install): grant manager rights so the crawl can actually
        # reach every menu, including the manager-gated Configuration one.
        cls.env.ref("base.user_admin").group_ids = [
            (4, cls.env.ref("helpdesk_community_pro.group_helpdesk_manager").id)
        ]

    def test_click_everywhere_helpdesk(self):
        """Open every Helpdesk menu and switch every available view."""
        self.browser_js(
            "/odoo",
            "odoo.loader.modules.get('@web/webclient/clickbot/clickbot_loader')"
            ".startClickEverywhere('helpdesk_community_pro.helpdesk_menu_root');",
            "odoo.isReady === true",
            login="admin",
            timeout=180,
            success_signal="clickbot test succeeded",
        )

    def test_ticket_form_shows_sla_fields(self):
        """A ticket with a matched SLA policy shows the SLA group on its
        form (sla_id/sla_deadline/sla_status) without a client-side error.

        The generic clickbot crawl above only exercises menus, filters and
        list/kanban view switches -- it never opens an individual record,
        so it can't catch a broken form arch (e.g. a bad invisible
        expression on the new SLA group). Opened directly via the action
        service, the same hook clickbot itself uses to reach app state.
        """
        calendar = make_mon_fri_calendar(self.env, name="SLA form check calendar")
        team = self.env["helpdesk.team"].create(
            {"name": "SLA Form Check", "calendar_id": calendar.id}
        )
        self.env["helpdesk.sla"].create(
            {"name": "Form check SLA", "team_id": team.id, "target_hours": 40}
        )
        ticket = self.env["helpdesk.ticket"].create(
            {"name": "SLA form check", "team_id": team.id}
        )
        self.assertTrue(ticket.sla_id)

        self.browser_js(
            "/odoo",
            f"""
                (async () => {{
                    await odoo.__WOWL_DEBUG__.root.env.services.action.doAction({{
                        type: "ir.actions.act_window",
                        res_model: "helpdesk.ticket",
                        res_id: {ticket.id},
                        views: [[false, "form"]],
                    }});
                    await new Promise((r) => setTimeout(r, 500));
                    if (document.querySelector(".o_error_dialog")) {{
                        console.error("error dialog present on ticket form");
                        return;
                    }}
                    const slaField = '.o_field_widget[name="sla_status"]';
                    if (!document.querySelector(slaField)) {{
                        console.error("sla_status field not found on ticket form");
                        return;
                    }}
                    console.log("test successful");
                }})();
            """,
            "odoo.isReady === true",
            login="admin",
            timeout=60,
        )

    def test_portal_home_shows_tickets_card(self):
        """The portal home page (/my) shows a visible "Tickets" card.

        portal.portal_docs_entry renders its card with a d-none class
        unless it's placed inside one of portal_my_home's t-if-gated
        category containers (portal_client_category etc.) with that
        category's own *_enable flag set -- a card added directly under
        o_portal_docs (outside every category container) still parses
        and appears in the rendered HTML, so a plain response.content
        assertion can't distinguish "present" from "actually visible".
        Only a real browser reveals the CSS-hidden state, which is
        exactly the bug this regression-tests.
        """
        portal_user = new_test_user(
            self.env, login="portal_home_check", groups="base.group_portal"
        )
        team = self.env["helpdesk.team"].create({"name": "Portal Home Check Team"})
        self.env["helpdesk.ticket"].create(
            {
                "name": "Portal home check ticket",
                "team_id": team.id,
                "partner_id": portal_user.partner_id.id,
            }
        )

        self.browser_js(
            "/my",
            """
                (async () => {
                    await new Promise((r) => setTimeout(r, 500));
                    const link = [...document.querySelectorAll("a")].find(
                        (a) => a.getAttribute("href") === "/my/tickets"
                    );
                    if (!link) {
                        console.error("no /my/tickets link found on portal home");
                        return;
                    }
                    const card = link.closest(".o_portal_index_card");
                    if (!card) {
                        console.error("tickets link not wrapped in a portal card");
                        return;
                    }
                    if (card.classList.contains("d-none")) {
                        console.error("tickets card is present but hidden (d-none)");
                        return;
                    }
                    if (card.offsetParent === null) {
                        console.error("tickets card is present but not visible");
                        return;
                    }
                    console.log("test successful");
                })();
            """,
            login="portal_home_check",
            timeout=60,
        )
