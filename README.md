# LightwaveRF call-for-heat controller

This project is intended to control the heating in my LightwaveRF enabled house
by communicating with the LightwaveRF heating devices (thermostatic radiator
valves and a master "boiler switch") to implement "call for heat".

It was written because Lightwave's own implementation was just *awful*, it
rarely switched the main boiler switch on when needed, or off when not needed,
and the graphs available on the LightwaveRF manager website
(https://manager.lightwaverf.com/) don't help debug this.

## Real-world Requirements

1. Raspberry Pi 3 (model B)
2. [Lightwave Link](https://lightwaverf.com/collections/control-connect-series/products/jsjslw930-lightwaverf-wifi-link-wi-fi-link-lightwave-link). Not the plus version, I have both but have not played with the plus after a very bad first impression
3. One or more [LightwaveRF Thermostatic Radiator Valves (TRVs)](https://lightwaverf.com/products/wireless-radiator-valves)
4. A [LightwaveRF Electric Switch](https://lightwaverf.com/products/electric-switch) which controls your boiler

## What the controler does

Monitors all the TRVs that are known ("linked") to your Lightwave Link, and
when *any* reports it has an open valve it instructs the "Boiler Switch" (as
defined in `config.yml`) to switch on. When *all* TRVs report their valves are
closed, it instructs the switch off.

## Technologies

* Python
* Docker (to provide Python environment without polluting my system)
* Docker Compose (to codify `docker run` parameters reuqired, e.g. `--network=host` to ensure we get UDP broadcast traffic)
* SystemD (to launch the Docker Compose project on boot)

# Bonus

Includes prometheus to log target temperatures, actual temperatures, and unlike
the official website also logs battery levels and valve ("output") levels.
