RESTful-RfCat
=============

Several types of devices can easily be controlled by sending a radio command from a radio remote control. The [RfCat USB device](https://smile.amazon.com/dp/B01N3TR4AA/?tag=lumtubo-20&linkCode=as2&linkId=dd8f1d837836925830b5ac693eb5f60d) allows computers to transmit arbitrary radio commands, which RESTful-RfCat uses to provide a unified interface to send commands to a variety of devices. This can be used as a component in home automation systems such as OpenHAB or Home Assistant to gain control over these devices with Alexa or Apple Homekit.

Features
--------

- Simple REST interface to get and set the state of rfcat-controllable devices
- Eavesdropping on physical remotes to detect external state changes
- Publishing state changes through HTTP Server-Sent Events, MQTT, and Redis
- Accepts commands through the MQTT bus
- Automatic integration into HomeAssistant with [MQTT Discovery](https://home-assistant.io/docs/mqtt/discovery/)

Installation
------------

1. `git clone https://github.com/hufman/restful_rfcat.git restful_rfcat`
2. `cd restful_rfcat`
3. `virtualenv --python=/usr/bin/python2.7 venv`
4. `venv/bin/pip install -r requirements.txt`
5. `cp restful_rfcat/localconfig.py.example restful_rfcat/localconfig.py`
6. `$EDITOR restful_rfcat/localconfig.py`

Configuration
-------------

The main purpose of `config.py` is to populate a list of `DEVICES` with objects from `drivers.py`. The object constructor will take parameters specific to the device, like an address code of some sort, as well as a name for URL resources and label for display.

There is also an option to run various background `THREADS`, which add abilities such as listening for radio transmissions to update device state or handle state change requests over MQTT.

Device state is persisted to a configurable set of locations, such as a simple file or Redis. An MQTT adapter is provided for integration with home automation systems.

Supported Devices
-----------------

The following remote-controlled devices have been successfully tested, similar devices of the same brand may also work.

- Hunter Universal 3 Speed Ceiling Fan Model 99600  [FCC ID](https://fccid.io/IN2TX28)
- Hampton Bay Windward IV 52-WWDIV  [FCC ID](https://fccid.io/RGB-52WWDIVS)
- Feit Electric String Lights  [FCC ID](https://fccid.io/2AIH2RF20160226B)

Additionally, there is basic support for parsing LIRC remote control configurations. Most basic devices can be configured as an LIRC description instead of needing to write a custom Python module, for example the [Hampton Bay UC7078T](http://lirc.sourceforge.net/remotes/hampton_bay/UC7078T).

Development
-----------

A standard SDR can be used to investigate the radio transmission from other remotes and figure out the transmission protocol. There are a few [resources](https://blog.compass-security.com/2016/09/software-defied-radio-sdr-and-decoding-on-off-keying-ook/) available online to help. Typically the device will be sending an On-Off-Keyed modulated signal, perhaps with an extra PCM encoding of the logical bits.

Once the baudrate and modulation is discovered, a Python script can be written to record data from the RfCat with those settings. Several examples are in the `test_scripts` directory. This script would be used to show the command that was sent from the remote, and make it easy to record the commands for every button on the remote.

After all of the buttons have been pressed, a module in the `drivers` package can be written to encapsulate that knowledge and expose the device through the framework.
