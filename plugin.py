# A Python plugin for Domoticz to access burze.dzis.net API for weather/storm data
#
# Author: fisher
#
# TODO: Add support for GIOS sensor data
#
#
# v0.1.0 - initial version, fetching data from airly sensor
#
"""
<plugin key="AIRLY" name="domoticz-airly" author="fisher" version="0.1.0" wikilink="https://www.domoticz.com/wiki/Plugins/domoticz-airly.html" externallink="https://github.com/lrybak/domoticz-airly">
    <params>
		<param field="Mode1" label="Airly API key" default="51ad2ae957824c839d3645611e8c61f4" width="400px" required="true"  />
        <param field="Mode2" label="Airly sensor id" width="40px" default="" required="true" />
        <param field="Mode3" label="Check every x minutes" width="40px" default="15" required="true" />
		<param field="Mode6" label="Debug" width="75px">
			<options>
				<option label="True" value="Debug"/>
				<option label="False" value="Normal" default="true" />
			</options>
		</param>
    </params>
</plugin>
"""
import Domoticz
import os
import gettext
import locale
import datetime
import json
from http.client import HTTPSConnection
from urllib.parse import urlparse
from urllib.parse import urlencode


class UnauthorizedException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class SensorNotFoundException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class BasePlugin:
    enabled = False

    def __init__(self):
        # Consts
        self.version = "0.1.0"
        self.airly_api_user_agent = "domoticz-airly/%s" % self.version
        self.api_v1_sensor_measurements = "https://airapi.airly.eu/v1/sensor/measurements"
        self.api_v1_sensor_info = "https://airapi.airly.eu/v1/sensors/%(sensorId)d"
        self.airly_api_headers = {
            "User-Agent": self.airly_api_user_agent,
            "Accept": "application/json",
            "apikey": ""
        }

        self.EXCEPTIONS = {
            "SENSOR_NOT_FOUND":     1,
            "UNAUTHORIZED":         2,
        }

        self.debug = False
        self.inProgress = False

        # Do not change below UNIT constants!
        self.UNIT_AIR_QUALITY_INDEX     = 1
        self.UNIT_AIR_POLLUTION_LEVEL   = 2
        self.UNIT_PM1                   = 3
        self.UNIT_PM25                  = 4
        self.UNIT_PM10                  = 5
        self.UNIT_TEMPERATURE           = 6
        self.UNIT_BAROMETER             = 7
        self.UNIT_HUMIDITY              = 8
        self.UNIT_STATION_LOCATION      = 9


        self.lastDataFetch = datetime.datetime.now()
        return

    def onStart(self):
        # Start l18n
        init_localization()

        Domoticz.Debug("onStart called")
        if Parameters["Mode6"] == 'Debug':
            self.debug = True
            Domoticz.Debugging(1)
            DumpConfigToLog()
        else:
            Domoticz.Debugging(0)

        Domoticz.Heartbeat(20)


        self.variables = {
            self.UNIT_AIR_QUALITY_INDEX: {
                "Name":     _("Air Quality Index"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "CAQI"},
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM1: {
                "Name":     _("PM1"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM25: {
                "Name":     _("PM2,5"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM10: {
                "Name":     _("PM10"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_AIR_POLLUTION_LEVEL: {
                "Name":     _("Air pollution Level"),
                "TypeName": "Alert",
                "Image":    7,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_TEMPERATURE: {
                "Name":     _("Temperature"),
                "TypeName": "Temperature",
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_BAROMETER: {
                "Name":     _("Air pressure"),
                "TypeName": "Barometer",
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_HUMIDITY: {
                "Name":     _("Humidity"),
                "TypeName": "Humidity",
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_STATION_LOCATION: {
                "Name":     _("Sensor information"),
                "TypeName": "Text",
                "Image":    7,
                "Used":     0,
                "nValue":   0,
                "sValue":   None,
            },
        }

        self.onHeartbeat(fetch=True)


    def onStop(self):
        Domoticz.Log("onStop called")
        Domoticz.Debugging(0)

    def onConnect(self, Status, Description):
        Domoticz.Log("onConnect called")

    def onMessage(self, Data, Status, Extra):
        Domoticz.Log("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log(
            "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(
            Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self):
        Domoticz.Log("onDisconnect called")


    def createDevice(self, key=None):
        """create Domoticz virtual device"""

        def createSingleDevice(key):
            """inner helper function to handle device creation"""

            item = self.variables[key]
            _unit = key
            _name = item['Name']

            # skip if already exists
            if key in Devices:
                Domoticz.Debug(_("Device Unit=%(Unit)d; Name='%(Name)s' already exists") % {'Unit': key, 'Name': _name})
                return

            try:
                _options = item['Options']
            except KeyError:
                _options = {}

            _typename = item['TypeName']

            try:
                _used = item['Used']
            except KeyError:
                _used = 0

            try:
                _image = item['Image']
            except KeyError:
                _image = 0

            Domoticz.Debug(_("Creating device Name=%(Name)s; Unit=%(Unit)d; ; TypeName=%(TypeName)s; Used=%(Used)d") % {
                               'Name':     _name,
                               'Unit':     _unit,
                               'TypeName': _typename,
                               'Used':     _used,
                           })

            Domoticz.Device(
                Name=_name,
                Unit=_unit,
                TypeName=_typename,
                Image=_image,
                Options=_options,
                Used=_used
            ).Create()

        if key:
            createSingleDevice(key)
        else:
            for k in self.variables.keys():
                createSingleDevice(k)


    def onHeartbeat(self, fetch=False):
        Domoticz.Log("onHeartbeat called")

        if fetch == False:
            if self.inProgress or (
                        (datetime.datetime.now() - self.lastDataFetch).total_seconds() < int(Parameters["Mode3"]) * 60):
                return

        # First call, lets query API for sensor location data
        if fetch:
            res = self.sensor_info(Parameters["Mode2"])

            address = ""
            if "route" in res["address"]:
                address = res["address"]["route"]
                if "streetNumber" in res["address"]:
                    address = address + " " + res["address"]["streetNumber"]

            if len(address) > 0:
                self.variables[self.UNIT_STATION_LOCATION]['sValue'] = _("%(Vendor)s - %(Address)s, %(Locality)s<br/>Station founder: %(sensorFounder)s") % {
                    "Vendor": res["vendor"],
                    "Address": address,
                    "Locality": res["address"]["locality"],
                    "sensorFounder": res["name"],
                }
            else:
                pass
                self.variables[self.UNIT_STATION_LOCATION]['sValue'] = _("%(Vendor)s - %(Locality)s %(StreetNumber)s<br/>Station founder: %(sensorFounder)s") % {
                    "Vendor": res["vendor"],
                    "Locality": res["address"]["locality"],
                    "StreetNumber": res["address"]["streetNumber"] if "streetNumber" in res["address"] else "",
                    "sensorFounder": res["name"],
                }

            self.doUpdate()

        try:
            # check if another thread is not running
            # and time between last fetch has elapsed
            self.inProgress = True

            res = self.sensor_measurement(Parameters["Mode2"])

            self.variables[self.UNIT_PM10]['nValue'] = 4
            self.variables[self.UNIT_PM10]['sValue'] = res["pm10"]
            self.variables[self.UNIT_PM25]['sValue'] = res["pm25"]
            self.variables[self.UNIT_PM1]['sValue'] = res["pm1"]
            self.variables[self.UNIT_AIR_QUALITY_INDEX]['sValue'] = res["airQualityIndex"]

            if res["pollutionLevel"] == 1:
                pollutionLevel = 1  # green
                pollutionText = _("Great air quality")
            elif res["pollutionLevel"] == 2:
                pollutionLevel = 1  # green
                pollutionText = _("Good air auality")
            elif res["pollutionLevel"] == 3:
                pollutionLevel = 2  # yellow
                pollutionText = _("Average air quality")
            elif res["pollutionLevel"] == 4:
                pollutionLevel = 3  # orange
                pollutionText = _("Poor air quality")
            elif res["pollutionLevel"] == 5:
                pollutionLevel = 4  # red
                pollutionText = _("Bad air today!")
            elif res["pollutionLevel"] == 6:
                pollutionLevel = 4  # red
                pollutionText = _("Really bad air today!")
            else:
                pollutionLevel = 0

            self.variables[self.UNIT_AIR_POLLUTION_LEVEL]['nValue'] = pollutionLevel
            self.variables[self.UNIT_AIR_POLLUTION_LEVEL]['sValue'] = pollutionText

            try:
                humidity = int(round(res["humidity"]))
                if humidity < 40:
                    humidity_status = 2  # dry humidity
                elif 40 <= humidity <= 60:
                    humidity_status = 0  # normal humidity
                elif 40 < humidity <= 70:
                    humidity_status = 1  # comfortable humidity
                else:
                    humidity_status = 3  # wet humidity

                self.variables[self.UNIT_HUMIDITY]['nValue'] = humidity
                self.variables[self.UNIT_HUMIDITY]['sValue'] = str(humidity_status)
            except KeyError:
                pass  # No humidity value

            try:
                self.variables[self.UNIT_TEMPERATURE]['sValue'] = res["temperature"]
            except KeyError:
                pass  # No temperature value

            try:
                # in hpa + normal forecast
                self.variables[self.UNIT_BAROMETER]['sValue'] = str(round(res["pressure"]/100)) + ";0"
            except KeyError:
                pass  # No pressure value

            self.doUpdate()

            self.lastDataFetch = datetime.datetime.now()
            self.inProgress = False
        except SensorNotFoundException as snfe:
            Domoticz.Error(_("Sensor id (%(sensor_id)d) not exists") % {'sensor_id': int(Parameters["Mode2"])})
        except UnauthorizedException as ue:
            Domoticz.Error(_("Not authorized"))


    def doUpdate(self):
        Domoticz.Log(_("Starting device update"))
        for unit in self.variables:
            nV = self.variables[unit]['nValue']
            sV = self.variables[unit]['sValue']

            # cast float to str
            if isinstance(sV, float):
                sV = str(float("{0:.0f}".format(sV))).replace('.', ',')

            # Create device if required
            if sV:
                self.createDevice(key=unit)
                Domoticz.Log(_("Update unit=%d; nValue=%d; sValue=%s") % (unit, nV, sV))
                Devices[unit].Update(nValue=nV, sValue=sV)

    def api_airly_headers(self):
        """return http request headers"""

        self.airly_api_headers['apikey'] = Parameters['Mode1']
        self.airly_api_headers['User-Agent'] = self.airly_api_user_agent
        return self.airly_api_headers

    def sensor_measurement(self, sensor_id):
        """current sensor measurements"""

        sensor_id = int(sensor_id)
        airly_api = urlparse(self.api_v1_sensor_measurements)
        params = urlencode({'sensorId': sensor_id})

        conn = HTTPSConnection(airly_api.netloc)
        conn.request(
            method="GET",
            url=airly_api.path + "?" + params,
            headers=self.api_airly_headers(),
        )

        response = conn.getresponse()
        response_object = {}
        if response.status == 200:
            response_body = response.read()
            response_object = json.loads(response_body.decode("utf-8"))

            if len(response_object['currentMeasurements']) > 0:
                return response_object['currentMeasurements']
            else:
                raise SensorNotFoundException(sensor_id, "")

            return response_object
        elif response.status in (401, 403, 404):
            raise UnauthorizedException(response.status, response.reason)
        else:
            Domoticz.Log(str(response.status) + ": " + response.reason)

    def sensor_info(self, sensor_id):
        """Sensor's info with coordinates, address and current pollution level"""

        sensor_id = int(sensor_id)
        airly_api = urlparse(self.api_v1_sensor_info)
        conn = HTTPSConnection(airly_api.netloc)
        conn.request(
            method="GET",
            url=airly_api.path % {'sensorId': sensor_id},
            headers=self.api_airly_headers(),
        )

        response = conn.getresponse()
        response_object = {}
        if response.status == 200:
            response_body = response.read()
            response_object = json.loads(response_body.decode("utf-8"))
            return response_object
        elif response.status in (403, 404):
            raise UnauthorizedException(response.status, response.reason)
        else:
            Domoticz.Log(str(response.status) + ": " + response.reason)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Status, Description):
    global _plugin
    _plugin.onConnect(Status, Description)

def onMessage(Data, Status, Extra):
    global _plugin
    _plugin.onMessage(Data, Status, Extra)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect():
    global _plugin
    _plugin.onDisconnect()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return


def init_localization():
    '''prepare l10n'''

    locale.setlocale(locale.LC_ALL, '') # use user's preferred locale
    # take first two characters of country code
    loc = locale.getlocale()
    filename = os.path.dirname(os.path.realpath(__file__)) \
               + "/i18n/%s.mo" % Settings["Language"]

    try:
        Domoticz.Debug("Opening message file %s for locale %s", filename, loc[0] )
        trans = gettext.GNUTranslations(open( filename, "rb" ) )
    except IOError:
        Domoticz.Debug("Locale not found. Using default messages")
        trans = gettext.NullTranslations()

    trans.install()