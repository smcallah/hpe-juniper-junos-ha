# Junos NETCONF for Home Assistant

`junos_netconf` is a Home Assistant custom integration for read-only monitoring
of Juniper/HPE Junos devices over NETCONF SSH using Junos PyEZ.

This MVP performs operational RPC reads only. It does not implement any write,
configuration, commit, rollback, or action service.

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

- `sensor.hostname`
- `sensor.model`
- `sensor.serial_number`
- `sensor.junos_version`
- `sensor.uptime`
- `sensor.routing_engine_cpu_idle`
- `sensor.routing_engine_memory_usage`
- `binary_sensor.chassis_alarm_present`
- `sensor.chassis_alarm_count`

Entity IDs may include the configured device name or Home Assistant suffixes if
there are naming conflicts.

## Junos setup

Enable NETCONF over SSH:

```text
set system services netconf ssh
```

Example read-only user configuration:

```text
set system login class ha-monitor permissions view
set system login class ha-monitor allow-commands "(show system information|show chassis routing-engine|show chassis alarms)"
set system login user ha-monitor uid 2001
set system login user ha-monitor class ha-monitor
set system login user ha-monitor authentication plain-text-password
commit
```

Depending on platform and Junos release, the built-in `view` permission may be
enough by itself. The `allow-commands` example documents the intended blast
radius: operational show/RPC access only.

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

## RPCs used

The PyEZ client opens a NETCONF session with `Device(...).open()`, runs these
read-only RPCs, and closes the session in a `finally` block:

```text
get-system-information
get-route-engine-information
get-alarm-information
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
