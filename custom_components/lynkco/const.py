"""Constants for the Lynk & Co integration."""

DOMAIN = "lynkco"
MANUFACTURER = "Lynk & Co"

# Azure AD B2C
CLIENT_ID = "c3e13a0c-8ba7-4ea5-9a21-ecd75830b9e9"
TENANT = "lynkcoprod.onmicrosoft.com"
LOGIN_B2C_URL = f"https://login.lynkco.com/{TENANT}/b2c_1a_signin_mfa/"
SCOPE = (
    f"https://{TENANT}/mobile-app-web-api/mobile.read "
    f"https://{TENANT}/mobile-app-web-api/mobile.write "
    "profile offline_access"
)
REDIRECT_URI = "msauth://prod.lynkco.app.crisp.prod/2jmj7l5rSw0yVb%2FvlWAYkK%2FYBwk%3D"

# API
API_BASE = "https://agw.mobile-app.lynkco.biz"
LOVE_BASE = f"{API_BASE}/mobile-app/love/v1"
COMMAND_BASE = f"{API_BASE}/mobile-app/love-remote-command/v1"
IAM_BASE = f"{API_BASE}/mobile-app/iamservice/v1"

# Signature
SIGNATURE_VERSION = "v2"
SIGNATURE_BASE_URLS = [
    f"{API_BASE}/mobile-app/love/v1/",
    f"{API_BASE}/mobile-app/love-remote-command/v1/",
    f"{API_BASE}/mobile-app/car-guide/v1/api/v1/",
    f"{API_BASE}/mobile-app/car-sharing/v1/",
]

# Model code (vehicle.model) → human-readable name. The app knows exactly these
# four codes plus UNKNOWN; CX11_A1 is the original 01, CX11_A3 the 2025 facelift.
MODEL_NAMES = {
    "CX11_A1": "Lynk & Co 01 (pre-2025)",
    "CX11_A3": "Lynk & Co 01 (2025)",
    "E335": "Lynk & Co 02",
    "DX11": "Lynk & Co 08",
}

# Guide type (GET vehicle/{vin}/vehicle_guide) → human-readable name. This is the
# most precise identity the API offers: model year for pre-2025 01s, equipment
# level (Core / More) for everything newer.
GUIDE_TYPE_NAMES = {
    "CX11_2021_HEV": "Lynk & Co 01 HEV (2021)",
    "CX11_2021_PHEV": "Lynk & Co 01 PHEV (2021)",
    "CX11_2022": "Lynk & Co 01 (2022)",
    "CX11_2023": "Lynk & Co 01 (2023)",
    "CX11_CORE": "Lynk & Co 01 Core (2025)",
    "CX11_MORE": "Lynk & Co 01 More (2025)",
    "E335_CORE": "Lynk & Co 02 Core",
    "E335_MORE": "Lynk & Co 02 More",
    "DX11_CORE": "Lynk & Co 08 Core",
    "DX11_MORE": "Lynk & Co 08 More",
}
PRE_2025_GUIDE_TYPES = {"CX11_2021_HEV", "CX11_2021_PHEV", "CX11_2022", "CX11_2023"}

ISSUE_TRACKER = "https://github.com/b12e/ha_lynkco_2025"
MODEL_REPORT_URL = f"{ISSUE_TRACKER}/issues/new?template=model_report.yml"

# Live permission flags in vehicle_data that gate an action at call time
LIVE_PERMISSION_FLAGS = {
    "flash_lights": "flashingPermitted",
    "honk_horn": "honkingPermitted",
}

# Polling

DEFAULT_SCAN_INTERVAL = 900  # 15 minutes
DRIVING_SCAN_INTERVAL = 60  # 1 minute when car is running
CLIMATE_SCAN_INTERVAL = 60  # 1 minute while climate/conditioning is active

# Config keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_DEVICE_ID = "device_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DRIVING_INTERVAL = "driving_interval"
