import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RasdSymbologyStandard(models.Model):
    _name = "rasd.symbology.standard"
    _description = "RASD Symbology Standard"
    _order = "name"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    edition = fields.Char(required=True)
    active = fields.Boolean(default=True)
    description = fields.Text()

    _sql_constraints = [
        ("rasd_symbology_standard_code_uniq", "unique(code)", "Symbology standard code must be unique."),
    ]


class RasdTrack(models.Model):
    _name = "rasd.track"
    _description = "RASD Track"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_observed_at desc, id desc"

    name = fields.Char(required=True, tracking=True)
    track_uid = fields.Char(required=True, index=True, tracking=True)

    entity_type = fields.Selection(
        [
            ("aircraft", "Aircraft"),
            ("vessel", "Vessel"),
            ("vehicle", "Vehicle"),
            ("person", "Person"),
            ("unit", "Unit"),
            ("site", "Site / Facility"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
        required=True,
        tracking=True,
        index=True,
    )
    affiliation = fields.Selection(
        [
            ("pending", "Pending"),
            ("unknown", "Unknown"),
            ("assumed_friend", "Assumed Friend"),
            ("friend", "Friend"),
            ("neutral", "Neutral"),
            ("suspect", "Suspect"),
            ("hostile", "Hostile"),
        ],
        default="pending",
        required=True,
        tracking=True,
        index=True,
        help="Classification result. Unknown or suspect must not be treated as hostile automatically.",
    )
    track_state = fields.Selection(
        [
            ("tentative", "Tentative"),
            ("confirmed", "Confirmed"),
            ("tracking", "Tracking"),
            ("identified", "Identified"),
            ("stale", "Stale"),
            ("lost", "Lost"),
            ("archived", "Archived"),
        ],
        default="tentative",
        required=True,
        tracking=True,
        index=True,
    )
    risk_state = fields.Selection(
        [
            ("normal", "Normal"),
            ("watch", "Watch"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        default="normal",
        required=True,
        tracking=True,
        index=True,
    )
    data_state = fields.Selection(
        [
            ("live", "Live"),
            ("delayed", "Delayed"),
            ("stale", "Stale"),
            ("lost", "Lost"),
        ],
        default="live",
        required=True,
        index=True,
    )

    latitude = fields.Float(digits=(16, 7), tracking=True)
    longitude = fields.Float(digits=(16, 7), tracking=True)
    altitude_m = fields.Float(string="Altitude (m)")
    speed_mps = fields.Float(string="Speed (m/s)")
    heading_deg = fields.Float(string="Heading (deg)")
    observed_at = fields.Datetime(index=True)
    last_observed_at = fields.Datetime(index=True)

    track_confidence = fields.Float(default=0.0)
    position_confidence = fields.Float(default=0.0)
    identity_confidence = fields.Float(default=0.0)
    affiliation_confidence = fields.Float(default=0.0)
    source_confidence = fields.Float(default=0.0)

    symbology_standard_id = fields.Many2one("rasd.symbology.standard", ondelete="restrict")
    sidc = fields.Char(
        string="SIDC",
        index=True,
        help="20-character numeric Symbol Identification Code for supported APP-6E symbology datasets.",
    )
    symbol_set = fields.Char(index=True)
    entity_code = fields.Char(index=True)
    modifier_1 = fields.Char()
    modifier_2 = fields.Char()

    evidence_ids = fields.One2many("rasd.identity.evidence", "track_id", string="Identity Evidence")
    classification_reason = fields.Text(tracking=True)

    _sql_constraints = [
        ("rasd_track_uid_uniq", "unique(track_uid)", "Track UID must be unique."),
    ]

    @api.constrains("latitude", "longitude")
    def _check_coordinates(self):
        for record in self:
            if record.latitude < -90 or record.latitude > 90:
                raise ValidationError("Latitude must be between -90 and 90 degrees.")
            if record.longitude < -180 or record.longitude > 180:
                raise ValidationError("Longitude must be between -180 and 180 degrees.")

    @api.constrains(
        "track_confidence",
        "position_confidence",
        "identity_confidence",
        "affiliation_confidence",
        "source_confidence",
    )
    def _check_confidence_values(self):
        fields_to_check = (
            "track_confidence",
            "position_confidence",
            "identity_confidence",
            "affiliation_confidence",
            "source_confidence",
        )
        for record in self:
            for field_name in fields_to_check:
                value = record[field_name]
                if value < 0 or value > 100:
                    raise ValidationError(f"{field_name} must be between 0 and 100.")

    @api.constrains("heading_deg")
    def _check_heading(self):
        for record in self:
            if record.heading_deg < 0 or record.heading_deg >= 360:
                raise ValidationError("Heading must be between 0 (inclusive) and 360 (exclusive).")

    @api.constrains("sidc")
    def _check_sidc(self):
        for record in self:
            if record.sidc and not re.fullmatch(r"\d{20}", record.sidc):
                raise ValidationError("SIDC must contain exactly 20 numeric characters.")


class RasdIdentityEvidence(models.Model):
    _name = "rasd.identity.evidence"
    _description = "RASD Identity Evidence"
    _order = "observed_at desc, id desc"

    track_id = fields.Many2one("rasd.track", required=True, ondelete="cascade", index=True)
    source_type = fields.Selection(
        [
            ("asset_registry", "Asset Registry"),
            ("trusted_identifier", "Trusted Identifier"),
            ("declared_identifier", "Declared Identifier"),
            ("sensor_correlation", "Sensor Correlation"),
            ("operator", "Operator Verification"),
            ("external_feed", "External Feed"),
            ("other", "Other"),
        ],
        required=True,
        index=True,
    )
    source_reference = fields.Char(index=True)
    observed_at = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    confidence = fields.Float(default=0.0)
    supports_affiliation = fields.Selection(
        [
            ("unknown", "Unknown"),
            ("assumed_friend", "Assumed Friend"),
            ("friend", "Friend"),
            ("neutral", "Neutral"),
            ("suspect", "Suspect"),
            ("hostile", "Hostile"),
        ]
    )
    is_conflicting = fields.Boolean(default=False, index=True)
    details = fields.Text()

    @api.constrains("confidence")
    def _check_confidence(self):
        for record in self:
            if record.confidence < 0 or record.confidence > 100:
                raise ValidationError("Evidence confidence must be between 0 and 100.")
