# Dev Email Setup — Real Gmail End-to-End Test

This documents how to wire a real Gmail account to a local `dev17` (or `dev19`)
instance to manually verify email-to-ticket end-to-end: an inbound email
becomes a ticket, the customer gets an acknowledgement, and their reply
threads back into the same ticket.

**Never commit real credentials.** Everywhere below, `you@gmail.com` and
`YOUR_APP_PASSWORD` are placeholders — fill them in directly in the Odoo UI
(they end up in the database, not in any file this repo tracks).

## 1. Get a Gmail App Password

Odoo authenticates as a normal SMTP/IMAP client, so it needs an **App
Password**, not your regular Gmail password (Google blocks plain-password
SMTP/IMAP login on personal accounts, and an app password can't get into a
repo by accident the way a real password reused elsewhere might).

1. Turn on 2-Step Verification on the Gmail account, if not already on:
   `myaccount.google.com/security` → "2-Step Verification".
2. Generate an app password: `myaccount.google.com/apppasswords` → app
   "Mail", device "Other" (name it e.g. "helpdesk-pro-dev") → Generate.
3. Copy the 16-character password somewhere local (a password manager, not
   this repo). You'll paste it into two places in Odoo below.

## 2. Outgoing mail (SMTP) — so Odoo can send the acknowledgement email

In Odoo: **Settings → Technical → Email → Outgoing Mail Servers → New**
(enable developer mode first if "Technical" isn't visible: Settings →
scroll to bottom → Activate the developer mode).

| Field | Value |
|---|---|
| Description | Gmail dev |
| Priority | 10 |
| SMTP Server | `smtp.gmail.com` |
| SMTP Port | `587` |
| Connection Security | `TLS (STARTTLS)` |
| Username | `you@gmail.com` |
| Password | `YOUR_APP_PASSWORD` |

Save, then click **Test Connection**. It should succeed immediately — if it
doesn't, the app password or 2FA setup is the first thing to recheck.

## 3. Incoming mail (IMAP) — so Odoo can create tickets from inbound email

**Settings → Technical → Email → Incoming Mail Servers → New**

| Field | Value |
|---|---|
| Name | Gmail dev |
| Server Type | `IMAP Server` |
| Server Name | `imap.gmail.com` |
| Port | `993` |
| SSL/TLS | checked |
| Username | `you@gmail.com` |
| Password | `YOUR_APP_PASSWORD` |
| Actions to Perform on Incoming Mails | **leave "Create a New Record" empty** |

Leaving "Create a New Record" empty is deliberate, not an oversight: that
field is only a *fallback* model for mail that doesn't match any configured
alias (see `message_process`'s own docstring — "the fallback model to use
if the message does not match any of the currently configured mail
aliases"). Our routing is entirely alias-based (§4 below), so there's
nothing to fall back to; leaving it empty means mail that doesn't match any
team's alias is safely ignored instead of landing on some arbitrary model.

Save, then **Test & Confirm**. This also sets the server to "Confirmed"
state, which is required for the fetch cron to actually run it.

## 4. Point a team's alias at your Gmail address (plus-addressing)

A personal `@gmail.com` account only has one real inbox, but Gmail's
**plus-addressing** lets you route distinct alias names to it: mail sent to
`you+support@gmail.com` and `you+billing@gmail.com` both land in
`you@gmail.com`, with the original address preserved in the `To:` header —
which is exactly what Odoo's alias matching reads.

1. **Settings → Technical → Email → Alias Domains** → make sure a domain
   record exists with Domain Name `gmail.com`, and it's the default for
   your company (Settings → General Settings → Discuss section → Alias
   Domain).
2. Open the Helpdesk team you want to test (**Helpdesk → Teams**, manager
   access) → the **Email Alias** section on the form:
   - "Create tickets by sending an email to": type `you+support` (i.e. the
     local part **including** the `+support` tag) in the alias field, and
     select `gmail.com` in the domain field next to it.
3. Save. The field switches to read-only and shows
   `you+support@gmail.com` — that's the address to send test mail to.

Repeat with a different tag (`you+billing`, etc.) for a second team, if you
want to confirm routing actually depends on the tag and not just landing in
the same inbox.

## 5. Run the test

1. From any **other** email account (not the Gmail one you configured —
   you're simulating a customer), send an email to `you+support@gmail.com`
   with a subject and a short body.
2. Trigger the fetch manually rather than waiting for the cron: **Settings
   → Technical → Automation → Scheduled Actions** → find "Mail: Fetchmail
   Service" → **Run Manually**.
3. Check **Helpdesk → Tickets**: a new ticket should exist, subject
   matching your email, in the team's first stage, with the customer's
   email/name captured.
4. Check the sender's inbox (the "customer" account from step 1): it
   should receive the "We received your request (TKT/…)" acknowledgement,
   sent from `you@gmail.com`.
5. **Reply** to that acknowledgement email from the customer account.
6. Run the fetchmail action again (step 2). The reply should appear in the
   ticket's chatter, threaded into the **same** ticket — not a new one.
7. From the ticket in Odoo, post a chatter reply as the agent (use "Send
   message", not "Log note") and confirm the customer receives it by email
   too.
8. To test the reopen behavior: move the ticket to a closed stage (Solved
   or Cancelled), have the customer reply again, re-run fetchmail, and
   confirm the ticket moved back to the first open stage.

## Troubleshooting

- **Test Connection fails on the outgoing server**: almost always the app
  password, not the code — regenerate it and make sure 2FA is genuinely
  on.
- **Fetchmail runs but no ticket appears**: check the alias's local part
  matches **exactly**, including the `+tag` — Odoo does not strip or
  normalize plus-addressing itself, it's a raw string compare against
  `alias_name`. Also confirm the incoming server shows "Confirmed" state,
  not just "Draft".
- **Ticket created but no acknowledgement email**: check **Settings →
  Technical → Email → Emails** for a queued/failed `mail.mail` — failures
  usually mean the outgoing server test above didn't actually pass.
- **Reply creates a new ticket instead of threading**: the reply's mail
  client must preserve the `References`/`In-Reply-To` headers from the
  acknowledgement email (nearly all normal mail clients do this
  automatically on "Reply" — this only breaks if you compose a fresh email
  instead of using Reply).
