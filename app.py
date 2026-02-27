"""
AIR CRE PDF Form Filler API
Hosted on Render.com free tier.
Accepts JSON listing data, returns a filled AIR CRE PDF as base64.
"""

import os
import base64
import tempfile
from flask import Flask, request, jsonify
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, DictionaryObject, create_string_object

app = Flask(__name__)

# ── SECURITY ──────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("AIRCRE_API_KEY", "change-me-in-render-env-vars")

# ── FORM TYPE → TEMPLATE FILENAME ────────────────────────────────────────────
FORM_TEMPLATES = {
    "industrial-lease":            "1_22-Industrial-For-Lease-Form.pdf",
    "industrial-sale":             "1_22-Industrial-For-Sale-Form.pdf",
    "industrial-sublease":         "1_22-Industrial-For-Sublease-Form.pdf",
    "industrial-lease-sale":       "1_22-Industrial-For-Lease-For-Sale-Form.pdf",
    "industrial-condo-lease":      "1_22-Industrial-Condo-For-Lease-Form.pdf",
    "industrial-condo-sale":       "1_22-Industrial-Condo-For-Sale-Form.pdf",
    "industrial-condo-sublease":   "1_22-Industrial-Condo-For-Sublease-Form.pdf",
    "industrial-condo-lease-sale": "1_22-Industrial-Condo-For-Lease-For-Sale-Form.pdf",
    "land-lease":                  "1_22-Land-For-Lease-Form.pdf",
    "land-sale":                   "1_22-Land-For-Sale-Form.pdf",
    "land-sublease":               "1_22-Land-For-Sublease-Form.pdf",
    "land-lease-sale":             "1_22-Land-For-Lease-For-Sale-Form.pdf",
}

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

CHOICE_OPTIONS = {
    "Lease Type":         ["FSG", "Gross", "IG", "MG", "Net", "NNN"],
    "Specific Use":       ["Warehouse/Distribution", "Warehouse/Office", "Flex/R&D",
                           "Manufacturing", "Self Storage", "Cold Storage",
                           "Truck Terminal/Cross Dock", "Mixed Use",
                           "Industrial", "Retail", "Office", "Multi-Family"],
    "Yard":               ["Paved", "Fenced", "Fenced/Paved", "Possible", "Unfenced", "Unpaved"],
    "Rail Service":       ["No", "Possible", "Yes", "Yes – Atchison Topeka", "Yes – S Pacific",
                           "Yes – Union Pacific", "Yes – Ventura County", "Yes – LA Junction",
                           "Yes – Burlington North Santa Fe", "Yes – Unknown"],
    "Construction Type":  ["Brick", "Concrete", "Framed", "Glass", "Masonry",
                           "Metal", "Steel", "Stucco", "Tilt-wall", "Wood"],
    "Construction Status":["Existing", "Proposed", "Under Construction"],
    "Possession":         ["Now", "30 Days", "60 Days", "90 Days", "Close of Escrow", "Completion"],
    "Vacant":             ["Yes", "No", "N/A"],
    "To Show":            ["Call Broker", "Lock Box", "Open", "See Notes", "See Tenant"],
    "Sprinklered":        ["No", "Yes", "ESFR"],
    "Whse HVAC":          ["Yes", "No", "Partial"],
    "Office HVAC":        ["Yes", "No", "Partial"],
    "Inc in Avail 1":     ["Yes", "No"],
    "Inc in Avail 2":     ["Yes", "No"],
    "Agreement Type":     ["OAA", "AOAA"],
    "Phase":              ["1", "2", "3"],
    "Wire":               ["Single", "Three"],
    "Gas":                ["Yes", "No", "Available", "Not Available"],
    "Water":              ["Yes", "No", "Available", "Not Available"],
    "Sewer":              ["Yes", "No", "Available", "Not Available"],
    "Electric":           ["Yes", "No", "Available", "Not Available"],
    "Fiber":              ["Yes", "No", "Available", "Not Available"],
}

ALL_HASHTAGS = [
    "#Automotive", "#Cannabis", "#Clarifier", "#CleanRoom", "#ContractorsYard",
    "#Cooler", "#Creative", "#CrossDock", "#ESFR", "#ExtraLand", "#ExtraParking",
    "#FloorDrains", "#FoodProcessingFacility", "#FreewayFrontage", "#Freezer",
    "#FreightElevator", "#HeavyPower", "#HVAC", "#LabSpace", "#LargeYard",
    "#LoftArea", "#PadSite", "#PartOfIndustrialPark", "#PavedYard",
    "#ReinforcedCement", "#RetailPotential", "#Truckwell", "#WetLab",
]


def set_field(writer, name, value):
    if not value and value != 0:
        return
    val_str = str(value)
    for page in writer.pages:
        if "/Annots" not in page:
            continue
        for annot in page["/Annots"]:
            obj = annot.get_object()
            if obj.get("/T") != name:
                continue
            ft = obj.get("/FT", "")
            if ft in ("/Tx", "/Ch"):
                obj[NameObject("/V")] = create_string_object(val_str)
                obj[NameObject("/AP")] = DictionaryObject()
            elif ft == "/Btn":
                if val_str.lower() in ("yes", "true", "1", "on"):
                    obj[NameObject("/V")] = NameObject("/Yes")
                    obj[NameObject("/AS")] = NameObject("/Yes")
                else:
                    obj[NameObject("/V")] = NameObject("/Off")
                    obj[NameObject("/AS")] = NameObject("/Off")
            return


def set_choice(writer, name, value):
    if not value:
        return
    valid = CHOICE_OPTIONS.get(name, [])
    if valid and value not in valid:
        match = next((v for v in valid if v.lower() == value.lower()), None)
        if match:
            value = match
    set_field(writer, name, value)


def detect_form_type(data):
    if "form_type" in data and data["form_type"] not in ("", "auto"):
        return data["form_type"]
    is_land  = data.get("is_land", False)
    is_condo = data.get("is_condo", False)
    is_sub   = data.get("is_sublease", False)
    has_lease = bool(data.get("lease_rate_mo") or data.get("lease_rate_sf") or data.get("lease_term"))
    has_sale  = bool(data.get("sale_price") or data.get("sale_price_sf"))
    if is_land:
        if is_sub:                  return "land-sublease"
        if has_lease and has_sale:  return "land-lease-sale"
        if has_lease:               return "land-lease"
        return "land-sale"
    prefix = "industrial-condo" if is_condo else "industrial"
    if is_sub:                      return f"{prefix}-sublease"
    if has_lease and has_sale:      return f"{prefix}-lease-sale"
    if has_lease:                   return f"{prefix}-lease"
    return f"{prefix}-sale"


def fill_form(data):
    form_type = detect_form_type(data)
    filename = FORM_TEMPLATES.get(form_type)
    if not filename:
        raise ValueError(f"Unknown form type: {form_type}")

    template_path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {filename}")

    reader = PdfReader(template_path)
    writer = PdfWriter()
    writer.append(reader)

    g = data.get

    # Common fields
    set_field(writer, "Property Name",   g("property_name", ""))
    set_field(writer, "Address",         g("address", ""))
    set_field(writer, "Cross Streets",   g("cross_streets", ""))
    set_field(writer, "Comments",        g("comments", ""))
    set_field(writer, "Listing Company", g("listing_company", ""))
    set_field(writer, "Agents",          g("agents", ""))
    set_field(writer, "Broker Notes",    g("broker_notes", ""))
    set_field(writer, "Available SF",    g("available_sf", ""))
    set_field(writer, "Building SF",     g("building_sf", ""))
    set_field(writer, "APN",             g("apn", ""))
    set_field(writer, "Zoning",          g("zoning", ""))
    set_choice(writer, "Specific Use",   g("specific_use", ""))
    set_choice(writer, "Yard",           g("yard", ""))
    set_choice(writer, "Rail Service",   g("rail_service", ""))
    set_choice(writer, "Agreement Type", g("agreement_type", ""))
    set_choice(writer, "Market/Submarket", g("market_submarket", ""))

    is_land = "land" in form_type

    if not is_land:
        set_field(writer, "Lease Rate per Mo",    g("lease_rate_mo", ""))
        set_field(writer, "Lease Rate per SF",    g("lease_rate_sf", ""))
        set_field(writer, "Operating Expenses",   g("operating_expenses", ""))
        set_field(writer, "Term",                 g("lease_term", ""))
        set_field(writer, "Minimum SF",           g("minimum_sf", ""))
        set_field(writer, "Sale Price",           g("sale_price", ""))
        set_field(writer, "Sale Price per SF",    g("sale_price_sf", ""))
        set_field(writer, "Year Built",           g("year_built", ""))
        set_field(writer, "Year Renovated",       g("year_renovated", ""))
        set_field(writer, "Min Clear Height",     g("clear_height_min", ""))
        set_field(writer, "Max Clear Height",     g("clear_height_max", ""))
        set_field(writer, "GL Doors",             g("gl_doors", ""))
        set_field(writer, "GL Dim",               g("gl_dim", ""))
        set_field(writer, "DH Doors",             g("dh_doors", ""))
        set_field(writer, "DH Dim",               g("dh_dim", ""))
        set_field(writer, "Office SF",            g("office_sf", ""))
        set_field(writer, "Restrooms",            g("restrooms", ""))
        set_field(writer, "Finished Mezzanine",   g("finished_mezzanine", ""))
        set_field(writer, "Unfinished Mezzanine", g("unfinished_mezzanine", ""))
        set_field(writer, "Parking Spaces",       g("parking_spaces", ""))
        set_field(writer, "Parking Ratio",        g("parking_ratio", ""))
        set_field(writer, "Volts",                g("volts", ""))
        set_field(writer, "Amps",                 g("amps", ""))
        set_field(writer, "Taxes",                g("taxes", ""))
        set_field(writer, "Tax Year",             g("tax_year", ""))
        set_field(writer, "Acres",                g("lot_acres", ""))
        set_field(writer, "Lot Size SF",          g("lot_sf", ""))
        set_field(writer, "Developer",            g("developer", ""))
        set_field(writer, "Former Tenant",        g("former_tenant", ""))
        set_field(writer, "Completion Date",      g("completion_date", ""))
        set_field(writer, "Date Vacant",          g("date_vacant", ""))
        set_choice(writer, "Lease Type",          g("lease_type", ""))
        set_choice(writer, "Sprinklered",         g("sprinklered", ""))
        set_choice(writer, "Construction Type",   g("construction_type", ""))
        set_choice(writer, "Construction Status", g("construction_status", "Existing"))
        set_choice(writer, "Whse HVAC",           g("whse_hvac", ""))
        set_choice(writer, "Office HVAC",         g("office_hvac", ""))
        set_choice(writer, "Possession",          g("possession", "Now"))
        set_choice(writer, "Vacant",              g("vacant", "Yes"))
        set_choice(writer, "To Show",             g("to_show", "Call Broker"))
        set_choice(writer, "Inc in Avail 1",      g("finished_mezz_in_avail", ""))
        set_choice(writer, "Inc in Avail 2",      g("unfinished_mezz_in_avail", ""))
        set_choice(writer, "Phase",               g("electric_phase", ""))
        set_choice(writer, "Wire",                g("electric_wire", ""))
    else:
        set_field(writer, "Available Acres",   g("available_acres", ""))
        set_field(writer, "Terms",             g("lease_term", ""))
        set_field(writer, "Lease Rate per Mo", g("lease_rate_mo", ""))
        set_field(writer, "Lease Rate per SF", g("lease_rate_sf", ""))
        set_field(writer, "Sale Price",        g("sale_price", ""))
        set_field(writer, "Sale Price per SF", g("sale_price_sf", ""))
        set_choice(writer, "Lease Type",       g("lease_type", ""))
        set_choice(writer, "Gas",              g("gas", ""))
        set_choice(writer, "Water",            g("water", ""))
        set_choice(writer, "Sewer",            g("sewer", ""))
        set_choice(writer, "Electric",         g("electric", ""))
        set_choice(writer, "Fiber",            g("fiber", ""))

    # Hashtags
    hashtags = set()
    for h in g("hashtags", []):
        h = h.strip()
        hashtags.add(h if h.startswith("#") else f"#{h}")
    for tag in ALL_HASHTAGS:
        set_field(writer, tag, "Yes" if tag in hashtags else "Off")

    # Remove draft watermark
    set_field(writer, "Draft Name", "")

    # Write to temp file and return bytes
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        writer.write(tmp)
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()
    os.unlink(tmp_path)

    return pdf_bytes, form_type


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "templates": list(FORM_TEMPLATES.keys())})


@app.route("/fill-form", methods=["POST"])
def fill_form_endpoint():
    # Auth check
    auth = request.headers.get("X-API-Key", "")
    if auth != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    try:
        pdf_bytes, form_type = fill_form(data)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

    # Return base64-encoded PDF + metadata
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    property_name = data.get("property_name", "listing").replace(" ", "_")

    return jsonify({
        "success": True,
        "form_type": form_type,
        "filename": f"AIR_CRE_{form_type}_{property_name}.pdf",
        "pdf_base64": pdf_b64,
        "size_bytes": len(pdf_bytes),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
