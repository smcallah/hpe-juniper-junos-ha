"""Constants for the Junos NETCONF integration."""

from datetime import timedelta

DOMAIN = "junos_netconf"
PLATFORMS = ["sensor", "binary_sensor"]

CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TIMEOUT = "timeout"
CONF_VERIFY_HOSTKEY = "verify_hostkey"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_NETCONF_PORT = 830
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_TIMEOUT = 15
MIN_SCAN_INTERVAL = 30
MIN_TIMEOUT = 5

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
