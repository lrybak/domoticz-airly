# domoticz-airly
A Python plugin for Domoticz to access airly api for smog data in Poland

## Installation
* Plugin works with Domoticz stable v4.9700. If you face any bug please don't hesistate to report an issue.
* Make sure your Domoticz instance supports Domoticz Plugin System - see more https://www.domoticz.com/wiki/Using_Python_plugins
* Register at https://developer.airly.eu/ and get your free API key
* Get plugin data into DOMOTICZ/plugins directory
```
cd YOUR_DOMOTICZ_PATH/plugins
git clone https://github.com/tschaban/domoticz-airly.git -b smartnydom.pl
```
* Restart Domoticz
* Go to Setup > Hardware and create new Hardware with type: domoticz-airly
	* Enter name (it's up to you), API key and sensor id would like to monitor. You can map particular sensor to id on https://map.airly.eu/ - just click the particular station and get the sensor id from the URL
	* Check every x minutes - how often plugin will check for new data. Consider API daily query limit limitation!

Plugin comunicates via Domoticz logs. Check logs in case of issues. After first API lookup plugin will create all the devices
You can add more station to lookup - create another plugin (hardware) instance

## Update
```
cd YOUR_DOMOTICZ_PATH/plugins/domoticz-airly
git pull
```
* Restart Domoticz

## Troubleshooting
In case of issues, mostly plugin not visible on plugin list, check logs if plugin system is working correctly.
See Domoticz wiki for resolution of most typical installation issues http://www.domoticz.com/wiki/Linux#Problems_locating_Python

## Contribute
Feel free to test and report issues or other improvements.
If you want to add another language, contact me or prepare pull request with the required change.
