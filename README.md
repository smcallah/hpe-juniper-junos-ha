# Junos NETCONF for Home Assistant

`junos_netconf` is a Home Assistant custom integration for read-only monitoring
of Juniper/HPE Junos devices over NETCONF SSH using Junos PyEZ.

This MVP performs operational RPC reads plus a small filtered, read-only
configuration lookup. It does not implement any write, configuration change,
commit, rollback, or action service.

## Directory tree

Place the integration here:

```text
/config/custom_components/junos_netconf/
|-- __init__.py
|-- binary_sensor.py
|-- config_flow.py
|-- const.py
|-- coordinator.py
|-- exceptions.py
|-- junos_client.py
|-- manifest.json
|-- sensor.py
|-- strings.json
`-- translations/
    `-- en.json
```

## Entities

The MVP creates these entities:

- `sensor.uptime`
- `sensor.routing_engine_cpu_idle`
- `sensor.routing_engine_memory_usage`
- `binary_sensor.chassis_alarm_present`
- `sensor.chassis_alarm_count`
- `binary_sensor.ssh_service_enabled`
- `binary_sensor.netconf_ssh_service_enabled`
- `binary_sensor.dhcp_local_server_enabled`
- `binary_sensor.https_web_management_enabled`

Configured-service entities remain present when a service is disabled and
report `off`. If configuration data is temporarily unavailable, they report
unknown instead of incorrectly reporting `off`.

Hostname, model, serial number, and Junos version are used as Home Assistant
device registry metadata, not exposed as standalone sensors.

Per-interface entities are disabled by default. Add exact interface names to
the integration options to create interface entities. For each selected
interface, the integration creates only:

- `binary_sensor.<interface>_link_up`
- `sensor.<interface>_rx_mbps`
- `sensor.<interface>_tx_mbps`
- `sensor.<interface>_input_errors`
- `sensor.<interface>_output_errors`

Internal/system interfaces are skipped unless explicitly allowlisted by exact
name, including `lo0`, `jsrv`, `dsc`, `gre`, `ipip`, `mtun`, `pimd`, `pime`,
`tap`, `vlan`, `irb`, `lsi`, `pp`, `demux`, `pfe`, `pfh`, `cbp`, `em`, `fxp`,
`mt`, `sp`, `fab`, and `rbeb`.

The first device model is based on the real SRX320 `banana` configuration from
the companion `juniper-configs` repository. It expects NETCONF over SSH, SSH,
DHCP local server, HTTPS web management, SRX flow/session telemetry, route
engine health, chassis alarms, and the configured WAN/trust/IRB/dialer
interfaces from that device.

Entity IDs may include the configured device name or Home Assistant suffixes if
there are naming conflicts.

## Junos setup

Enable NETCONF over SSH:

```text
set system services netconf ssh
```

Example read-only user configuration:

```text
set system login class ha-monitor permissions [ view view-configuration ]
set system login class ha-monitor allow-commands "(show system information|show system uptime|show chassis routing-engine|show chassis alarms|show security flow session summary|show interfaces .* extensive|show configuration system services|show configuration interfaces)"
set system login user ha-monitor uid 2001
set system login user ha-monitor class ha-monitor
set system login user ha-monitor authentication plain-text-password
commit
```

Depending on platform and Junos release, the built-in `view` and
`view-configuration` permissions may be enough by themselves. The
`allow-commands` example documents the intended blast radius: operational show
access plus read-only configuration visibility for system services and
interfaces.

## Install

1. Copy `custom_components/junos_netconf` to
   `/config/custom_components/junos_netconf`.
2. Restart Home Assistant.
3. Go to **Settings > Devices & services > Add Integration**.
4. Search for **Junos NETCONF**.
5. Enter:
   - host
   - port, default `830`
   - username
   - password
   - timeout, default `15`
   - host-key verification preference
   - polling interval, default `60`

## Host-key verification

Leave **Require pre-trusted SSH host key** unchecked unless the Junos device's
SSH host key is already trusted by the Home Assistant environment. This option
does not fetch or accept a new host key interactively. If it is enabled before
the host key is trusted, the SSH session can fail before username/password
authentication.

For initial setup and lab use, keep it unchecked. After the integration works,
you can pre-load the device host key into the environment used by Home Assistant
and then enable this option.

If Junos later rejects the stored username or password, Home Assistant starts a
reauthentication flow so the credentials can be replaced without removing and
re-adding the integration.

## RPCs used

The PyEZ client opens a NETCONF session with `Device(...).open()`, runs these
read-only RPCs, and closes the session in a `finally` block:

```text
get-system-information
get-system-uptime-information
get-route-engine-information
get-alarm-information
get-flow-session-information summary
get-ipsec-security-associations-information
get-chassis-cluster-status
get-configuration (committed database, filtered to system services and allowlisted interfaces)
get-interface-information extensive (allowlisted interfaces only)
```

Blocking PyEZ calls run through Home Assistant's executor via
`DataUpdateCoordinator`, so the Home Assistant event loop is not blocked.

## Home Assistant test checklist

- Confirm Home Assistant starts without custom component import errors.
- Add the integration through the config flow UI.
- Confirm invalid credentials produce an auth error instead of a crash.
- Confirm an unreachable host produces a connection error instead of a crash.
- Confirm all MVP sensors and the chassis alarm binary sensor are created.
- Confirm values refresh after the default 60-second polling interval.
- Trigger or simulate a chassis alarm and confirm alarm count and binary sensor
  change state.
- Leave the interface allowlist blank and confirm no per-interface entities are
  created.
- Add one physical interface such as `ge-0/0/0` to the allowlist and confirm
  only link, RX Mbps, TX Mbps, input errors, and output errors are created for
  that interface.
