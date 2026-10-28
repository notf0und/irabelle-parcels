"""Constants for the Irabelle Parcels integration."""

DOMAIN = "irabelle_parcels"
NAME = "Irabelle Parcels"

CONF_COUNTRY = "country"
CONF_POSTAL_CODE = "postal_code"
CONF_LOCALE = "locale"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_AUTO_ARCHIVE = "auto_archive_after"

DEFAULT_LOCALE = "en"
DEFAULT_SCAN_INTERVAL = 1800
MIN_SCAN_INTERVAL = 300
# Archive delivered parcels after 2 days (0 = never archive automatically).
# Stored as a duration dict, e.g. {"days": 2}.
DEFAULT_AUTO_ARCHIVE = {"days": 2}

API_BASE = "https://parcelsapp.com/api/v1/parcels/"
PLATFORM = "android"
UA = "okhttp/3.12.1"
APP_VERSION = "3.0.11"
SEED = 978

# Optional per-install device fingerprint override. Leave unset to have the
# integration generate a well-formed fingerprint automatically (recommended).
CONF_FINGERPRINT = "fingerprint"

AUTO_DETECT = "Auto Detect"

# Event fired whenever a tracked parcel gets a new tracking event.
EVENT_NEW_EVENT = f"{DOMAIN}_event"

# Dispatcher signal sent whenever the parcel list or any parcel changes.
SIGNAL_PARCELS_UPDATED = f"{DOMAIN}_updated"

# The Lovelace cards shipped with the integration.
FRONTEND_URL = f"/{DOMAIN}/frontend"
CARD_FILE = "irabelle-parcels-card.js"

# API status values mapped to a stable sensor state.
STATUS_MAP = {
    "transit": "transit",
    "arrived": "arrived",
    "pickup": "pickup",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "returned": "returned",
    "archive": "delivered",
    "no_data": "no_data",
    "error": "error",
    "unknown": "unknown",
}

# States after which a parcel is archived automatically (once the
# auto-archive time has passed).
FINAL_STATES = ("delivered",)

ICON_MAP = {
    "transit": "mdi:truck-delivery",
    "arrived": "mdi:airplane-landing",
    "pickup": "mdi:store-marker",
    "delivered": "mdi:package-variant-closed-check",
    "cancelled": "mdi:cancel",
    "returned": "mdi:package-variant-closed-remove",
    "no_data": "mdi:help-circle",
    "error": "mdi:alert-circle",
    "unknown": "mdi:help-circle",
}

MAX_STATUSES = 50

# Country names exactly as the tracking API expects them.
COUNTRIES = {
    "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina",
    "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Åland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium",
    "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi",
    "BJ": "Benin", "BL": "Saint Barthélemy", "BM": "Bermuda", "BN": "Brunei",
    "BO": "Bolivia", "BQ": "Bonaire, Sint Eustatius and Saba", "BR": "Brazil",
    "BS": "Bahamas", "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana",
    "BY": "Belarus", "BZ": "Belize", "CA": "Canada", "CC": "Cocos (Keeling) Islands",
    "CD": "Congo", "CF": "Central African Republic", "CH": "Switzerland",
    "CI": "Cote D'Ivoire", "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon",
    "CN": "China", "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba",
    "CV": "Cape Verde", "CW": "Curaçao", "CX": "Christmas Island",
    "CY": "Cyprus", "CZ": "Czech Republic", "DE": "Germany", "DJ": "Djibouti",
    "DK": "Denmark", "DM": "Dominica", "DO": "Dominican Republic", "DZ": "Algeria",
    "EC": "Ecuador", "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara",
    "ER": "Eritrea", "ES": "Spain", "ET": "Ethiopia", "FI": "Finland",
    "FJ": "Fiji", "FK": "Falkland Islands (Malvinas)", "FM": "Micronesia",
    "FO": "Faroe Islands", "FR": "France", "GA": "Gabon", "GB": "United Kingdom",
    "GD": "Grenada", "GE": "Georgia", "GF": "French Guiana", "GG": "Guernsey",
    "GH": "Ghana", "GI": "Gibraltar", "GL": "Greenland", "GM": "Gambia",
    "GN": "Guinea", "GP": "Guadeloupe", "GQ": "Equatorial Guinea",
    "GR": "Greece", "GS": "South Georgia and the South Sandwich Islands",
    "GT": "Guatemala", "GU": "Guam", "GW": "Guinea-Bissau", "GY": "Guyana",
    "HK": "Hong Kong", "HM": "Heard Island and Mcdonald Islands",
    "HN": "Honduras", "HR": "Croatia", "HT": "Haiti", "HU": "Hungary",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man",
    "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq",
    "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JE": "Jersey",
    "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya",
    "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros",
    "KN": "Saint Kitts and Nevis", "KP": "Korea", "KR": "South Korea",
    "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan",
    "LA": "Laos", "LB": "Lebanon", "LC": "Saint Lucia", "LI": "Liechtenstein",
    "LK": "Sri Lanka", "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania",
    "LU": "Luxembourg", "LV": "Latvia", "LY": "Libyan Arab Jamahiriya",
    "MA": "Morocco", "MC": "Monaco", "MD": "Moldova", "ME": "Montenegro",
    "MF": "Saint Martin (French part)", "MG": "Madagascar", "MH": "Marshall Islands",
    "MK": "Macedonia", "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia",
    "MO": "Macao", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia",
    "MZ": "Mozambique", "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger",
    "NF": "Norfolk Island", "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands",
    "NO": "Norway", "NP": "Nepal", "NR": "Nauru", "NU": "Niue",
    "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PM": "Saint Pierre and Miquelon",
    "PN": "Pitcairn", "PR": "Puerto Rico", "PS": "Palestinian Territory, Occupied",
    "PT": "Portugal", "PW": "Palau", "PY": "Paraguay", "QA": "Qatar",
    "RE": "Reunion", "RO": "Romania", "RS": "Serbia", "RU": "Russia",
    "RW": "Rwanda", "SA": "Saudi Arabia", "SB": "Solomon Islands",
    "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SH": "Saint Helena", "SI": "Slovenia", "SJ": "Svalbard and Jan Mayen",
    "SK": "Slovakia", "SL": "Sierra Leone", "SM": "San Marino", "SN": "Senegal",
    "SO": "Somalia", "SR": "Suriname", "SS": "South Sudan", "ST": "Sao Tome and Principe",
    "SV": "El Salvador", "SX": "Sint Maarten (Dutch part)", "SY": "Syrian Arab Republic",
    "SZ": "Swaziland", "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand",
    "TJ": "Tajikistan", "TK": "Tokelau", "TL": "Timor-Leste", "TM": "Turkmenistan",
    "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey", "TT": "Trinidad and Tobago",
    "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania", "UA": "Ukraine",
    "UG": "Uganda", "UM": "United States Minor Outlying Islands", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VA": "Holy See (Vatican City State)",
    "VC": "Saint Vincent and the Grenadines", "VE": "Venezuela",
    "VG": "Virgin Islands, British", "VI": "U.S. Virgin Islands", "VN": "Viet Nam",
    "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa", "XK": "Kosovo",
    "YE": "Yemen", "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia",
    "ZW": "Zimbabwe",
}

DEFAULT_COUNTRY = "New Zealand"
