# LightwaveRF call-for-heat controller

This project is intended to control the heating in my LightwaveRF enabled house by communicating with the LightwaveRF heating devices (thermostatic radiator valves and an electric switch which controls my one and only boiler) to implement "call for heat".

It was written because Lightwave's own implementation was just *awful*, it rarely switched the boiler on when needed, or off when not needed, and the graphs available on the LightwaveRF manager website (https://manager.lightwaverf.com/) don't help debug this.

## Real-world Requirements

1. Raspberry Pi 3 (model B)
2. [Lightwave Link](https://lightwaverf.com/collections/control-connect-series/products/jsjslw930-lightwaverf-wifi-link-wi-fi-link-lightwave-link) to bridge RF and your (WiFi) network. Not the plus version, I have both but have not played with the plus after a very bad first impression
3. One or more [LightwaveRF Thermostatic Radiator Valves (TRVs)](https://lightwaverf.com/products/wireless-radiator-valves)
4. A [LightwaveRF Electric Switch](https://lightwaverf.com/products/electric-switch) which controls your boiler

## What the controller does

Monitors all the TRVs that are known ("linked") to your Lightwave Link, and when *any* reports it has an open valve it instructs the "Boiler Switch" (as defined in `config.yml`) to switch on. When *all* TRVs report their valves are closed, it switches it off.

## Technologies

* Python
* Docker (to provide Python environment without polluting my system)
* Docker Compose (to codify `docker run` parameters required, e.g. `--network=host` to ensure we receive UDP broadcast traffic)
* SystemD (to launch the Docker Compose project on boot)

## Monitoring

Includes prometheus to log target temperatures, actual temperatures, and unlike the official website also logs battery levels and valve ("output") levels.

# Usage

```
docker-compose up
```

The first time this is run it will have to build the project's docker images, which can take minutes.

## First run

Some setup is required the first time the service is launched:

1. Push the LINK button on the Lightwave Link (to authorise your host)
2. Edit `config.yml` (to configure service)

### Register your host with the Lightwave Link

When the service starts it broadcasts UDP traffic to find the Lightwave Link on your network.

The first time this happens the Lightwave Link will respond with a "Not registered" error, indicating it does not recognise the MAC address of your host as authorised to issue commands to it. The service responds to this error by attempting to register with the Lightwave Link (... in an endless loop!). The Lightwave Link's one and only button will begin flashing its LED - go push it to authorise the MAC address of your host to issue commands.

If all is well, the service will log the following:

```
lightwaverf_1  | 2019-01-01 11:06:20,025 INFO    Checking if this host is registered with Lightwave Link...
lightwaverf_1  | 2019-01-01 11:06:20,059 INFO    This device is registered.
```

### Edit `config.yml`

Edit the serial and room number of the entry named "Boiler switch" to match the device that controls your boiler.

The serial is easiest to find from the [LightwaveRF Manager web-app](https://manager.lightwaverf.com/heating-device-list), assuming you have been using one of LightwaveRF's apps (etc.) to manage your heating. You can login using the same credentials used with their mobile app.  The device listing will show its serial when you tap on it, e.g. 9993FE.

The room number is much harder to find...

At launch, we query the Lightwave Link's so-called "slots" where linked energy and heating devices  are stored. The slot number is called "room" in commands and status reports. 

Every device reported by the Lightwave Link is sent a command to report its current status:

```
lightwaverf_1  | 2019-01-01 11:06:20,059 INFO    Query LightwaveLink for list of known devices ('rooms')...
lightwaverf_1  | 2019-01-01 11:06:24,046 INFO    8 devices
lightwaverf_1  | 2019-01-01 11:06:24,048 INFO    Asking device #0 (room 1) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:26,032 INFO    Asking device #1 (room 2) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:29,032 INFO    Asking device #2 (room 3) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:32,034 INFO    Asking device #3 (room 4) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:35,035 INFO    Asking device #4 (room 5) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:38,038 INFO    Asking device #5 (room 6) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:38,154 WARNING Discarding non-JSON response: 46340786,ERR,6,"Transmit fail"
lightwaverf_1  |
lightwaverf_1  | 2019-01-01 11:06:41,038 INFO    Asking device #6 (room 7) to provide status update...
lightwaverf_1  | 2019-01-01 11:06:44,039 INFO    Asking device #7 (room 9) to provide status update...
```

Notes:

- Room numbers are not sequential! Device 7 is in room 9!
- No action is taken in response to the "Transmit fail" error

The responses are then shown in the order recieved. Annoyingly, the response data does not include the device's room number, so you'll have to associate it with a room number request (above) yourself...

```
lightwaverf_1  | 2019-01-01 11:06:47,053 INFO    TRVStatus(Front door):
lightwaverf_1  |      batt: 64%         2.76V (2.4-3.0V)
lightwaverf_1  |     cTarg: 17.0°C      17.0
lightwaverf_1  |     cTemp: 16.5°C
lightwaverf_1  |     nSlot: 18:00
lightwaverf_1  |     nTarg: 0%           50.0
lightwaverf_1  |    output: 10%
lightwaverf_1  |      prof: Tuesday     2
lightwaverf_1  |    serial: 47C702
lightwaverf_1  |     state: man
lightwaverf_1  |      time: 1546340799
lightwaverf_1  |     trans: 41
```

(Note that the name in the top line ("Front door") is read from `config.yml`.


