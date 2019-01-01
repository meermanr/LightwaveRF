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

Edit the serial number of the entry named "Boiler switch" to match the device that controls your boiler, and add/remove other entries as desired.

The serial is easiest to find from the [LightwaveRF Manager web-app](https://manager.lightwaverf.com/heating-device-list), assuming you have been using one of LightwaveRF's apps (etc.) to manage your heating. You can login using the same credentials used with their mobile app.  The device listing will show its serial when you tap on it, e.g. 9993FE.
