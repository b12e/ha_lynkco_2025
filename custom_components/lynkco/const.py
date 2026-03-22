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

# Polling
DEFAULT_SCAN_INTERVAL = 900  # 15 minutes

# Config keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_DEVICE_ID = "device_id"
