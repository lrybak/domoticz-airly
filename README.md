# domoticz-airly
A Python plugin for Domoticz to access airly api for smog data in Poland

## Installation
* Make sure your Domoticz instance supports Domoticz Plugin System - see more https://www.domoticz.com/wiki/Using_Python_plugins
* Register at https://apiportal.airly.eu/ and get your API key
* Get plugin data into DOMOTICZ/plugins directory
```
cd YOUR_DOMOTICZ_PATH/plugins
git clone https://github.com/lrybak/domoticz-airly
```
* Restart Domoticz
* Go to Setup > Hardware and create new Hardware with type: domoticz-airly
	* Enter name (it's up to you), API key and sensor id would like to monitor. You can map particular sensor to id on https://map.airly.eu/
	* Check every x minutes - how often plugin will check for new data. Consider API daily query limit limitation!

Plugin comunicates via Domoticz logs. Check logs in case of issues. After first API lookup plugin will create all the devices
You can add more station to lookup - create another plugin (hardware) instance

## Troubleshooting
In case of issues, mostly plugin not visible on plugin list, check logs if plugin system is working correctly.
See Domoticz wiki for resolution of most typical installation issues http://www.domoticz.com/wiki/Linux#Problems_locating_Python

## Contribute
Feel free to test and report issues or other improvements.
Plugin uses gettext for translation, currently english and polish are available.
If you want to add another language, use included messages.pot template and prepare translation