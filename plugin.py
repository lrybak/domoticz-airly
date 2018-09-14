# A Python plugin for Domoticz to access airly api for smog information in Poland
#
# Author: fisher
#
# TODO: Update text sensors only when changed
#
#
# v0.1.0 - initial version, fetching data from airly sensor
# v0.1.1 - response body decode - error handling, minor language corrections
# v0.1.2 - removed gettext based translations - it caused plugin instability
# v0.2   - added support for GIOS stations, fixed a bug where the update was suspended in the event of a response decode error
# v0.2.1 - pm25 & pm10 percentage indicator
# v0.2.2 - better exception handling
# v0.3.0 - airly APIv2 support, airly logo added to pm1/10/2.5 sensors
#
"""
<plugin key="AIRLY" name="domoticz-airly" author="fisher" version="0.3.0" wikilink="https://www.domoticz.com/wiki/Plugins/domoticz-airly.html" externallink="https://github.com/lrybak/domoticz-airly">
    <params>
		<param field="Mode1" label="Airly API key" default="" width="400px" required="true"  />
        <param field="Mode2" label="Airly installation id" width="40px" default="" required="true" />
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
import datetime
import json
from http.client import HTTPSConnection
from urllib.parse import urlparse
from urllib.parse import urlencode
import socket

L10N = {
    'pl': {
        "Air Quality Index":
            "Jakość powietrza",
        "PM1":
            "PM1",
        "PM2,5":
            "PM2,5",
        "PM10":
            "PM10",
        "PM2,5 Norm":
            "PM2,5 Norma",
        "PM10 Norm":
            "PM10 Norma",
        "Air pollution Level":
            "Zanieczyszczenie powietrza",
        "Advice":
            "Wskazówki",
        "Temperature":
            "Temperatura",
        "Air pressure":
            "Ciśnienie powietrza",
        "Humidity":
            "Wilgotność",
        "Installation information":
            "Informacje o stacji",
        "Device Unit=%(Unit)d; Name='%(Name)s' already exists":
            "Urządzenie Unit=%(Unit)d; Name='%(Name)s' już istnieje",
        "Creating device Name=%(Name)s; Unit=%(Unit)d; ; TypeName=%(TypeName)s; Used=%(Used)d":
            "Tworzę urządzenie Name=%(Name)s; Unit=%(Unit)d; ; TypeName=%(TypeName)s; Used=%(Used)d",
        "%(Vendor)s - %(Address)s, %(Locality)s<br/>Station founder: %(sensorFounder)s":
            "%(Vendor)s - %(Address)s, %(Locality)s<br/>Sponsor stacji: %(sensorFounder)s",
        "%(Vendor)s - %(Locality)s %(StreetNumber)s<br/>Station founder: %(sensorFounder)s":
            "%(Vendor)s - %(Locality)s %(StreetNumber)s<br/>Sponsor stacji: %(sensorFounder)s",
        "Sensor id (%(installation_id)d) not exists":
            "Sensor (%(installation_id)d) nie istnieje",
        "Not authorized":
            "Brak autoryzacji",
        "Starting device update":
            "Rozpoczynanie aktualizacji urządzeń",
        "Update unit=%d; nValue=%d; sValue=%s":
            "Aktualizacja unit=%d; nValue=%d; sValue=%s",
        "Bad air today!":
            "Zła jakość powietrza",
        "Enter correct airly API key - get one on https://developer.airly.eu":
            "Wprowadź poprawny klucz api -  pobierz klucz na stronie https://developer.airly.eu",
        "Awaiting next poll: %s":
            "Oczekiwanie na następne pobranie: %s",
        "Next poll attempt at: %s":
            "Następna próba pobrania: %s",
        "Connection to airly api failed: %s":
            "Połączenie z airly api nie powiodło się: %s",
        "Unrecognized error: %s":
            "Nierozpoznany błąd: %s"
    },
    'en': { }
}

def _(key):
    try:
        return L10N[Settings["Language"]][key]
    except KeyError:
        return key

class UnauthorizedException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class SensorNotFoundException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class TooManyRequestsException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class ConnectionErrorException(Exception):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class BasePlugin:
    enabled = False

    def __init__(self):
        # Consts
        self.version = "0.3.0"
        self.airly_api_user_agent = "domoticz-airly/%s" % self.version
        # Api v2
        self.api_v2_installation_measurements = "https://airapi.airly.eu/v2/measurements/installation"
        self.api_v2_installation_info = "https://airapi.airly.eu/v2/installations/%(installationId)d"

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
        self.UNIT_AIR_POLLUTION_ADVICE  = 10

        self.UNIT_PM25_PERCENTAGE       = 11
        self.UNIT_PM10_PERCENTAGE       = 12

        self.UNIT_PM25_NORM             = 25
        self.UNIT_PM10_NORM             = 50

        # Icons
        self.iconName = "airly"

        self.nextpoll = datetime.datetime.now()
        return


    def onStart(self):
        Domoticz.Debug("onStart called")
        if Parameters["Mode6"] == 'Debug':
            self.debug = True
            Domoticz.Debugging(1)
            DumpConfigToLog()
        else:
            Domoticz.Debugging(0)

        Domoticz.Heartbeat(20)
        self.pollinterval = int(Parameters["Mode3"]) * 60

        if self.iconName not in Images: Domoticz.Image('icons.zip').Create()
        iconID = Images[self.iconName].ID

        self.variables = {
            self.UNIT_AIR_QUALITY_INDEX: {
                "Name":     _("Air Quality Index"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "CAQI"},
                "Image":    iconID,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM1: {
                "Name":     _("PM1"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    iconID,
                "Used":     0,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM25: {
                "Name":     _("PM2,5"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    iconID,
                "Used":     1,
                "nValue":   0,
                "sValue":   None,
            },
            self.UNIT_PM10: {
                "Name":     _("PM10"),
                "TypeName": "Custom",
                "Options":  {"Custom": "1;%s" % "µg/m³"},
                "Image":    iconID,
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
            self.UNIT_AIR_POLLUTION_ADVICE: {
                "Name":     _("Advice"),
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
            self.UNIT_PM25_PERCENTAGE: {
                "Name": _("PM2,5 Norm"),
                "TypeName": "Percentage",
                "Used": 1,
                "nValue": 0,
                "sValue": None,
            },
            self.UNIT_PM10_PERCENTAGE: {
                "Name": _("PM10 Norm"),
                "TypeName": "Percentage",
                "Used": 1,
                "nValue": 0,
                "sValue": None,
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

    def postponeNextPool(self, seconds=3600):
        self.nextpoll = (datetime.datetime.now() + datetime.timedelta(seconds=seconds))
        return self.nextpoll

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
        Domoticz.Debug("onHeartbeat called")
        now = datetime.datetime.now()

        if fetch == False:
            if self.inProgress or (now < self.nextpoll):
                Domoticz.Debug(_("Awaiting next pool: %s") % str(self.nextpoll))
                return

        # Set next pool time
        self.postponeNextPool(seconds=self.pollinterval)

        # First call, lets query API for sensor location data
        try:
            if fetch:
                res = self.installation_info(Parameters["Mode2"])
                address = ""
                if "street" in res["address"] and res["address"]["street"] is not None:
                    address = res["address"]["street"]
                    if "number" in res["address"] and res["address"]["number"] is not None:
                        address = address + " " + res["address"]["number"]
                if len(address) > 0:
                    self.variables[self.UNIT_STATION_LOCATION]['sValue'] = _("%(Address)s, %(City)s<br/>Station founder: %(sensorFounder)s") % {
                        "Address": address,
                        "City": res["address"]["city"],
                        "sensorFounder": res["sponsor"]["name"],
                    }
                else:
                    self.variables[self.UNIT_STATION_LOCATION]['sValue'] = _("%(City)s<br/>Station founder: %(sensorFounder)s") % {
                        "City": res["address"]["city"],
                        "sensorFounder": res["sponsor"]["name"],
                    }
                self.doUpdate()

        except UnauthorizedException as ue:
            Domoticz.Error(ue.message)
            Domoticz.Error(_("Enter correct airly API key - get one on https://developer.airly.eu"))
            return
        except TooManyRequestsException as tmre:
            Domoticz.Error(tmre.message)
            # postpone next pool to tomorrow
            next_attempt = self.postponeNextPool()
            Domoticz.Error(_("Next pool attempt at: %s") % str(next_attempt))
            return
        except ConnectionErrorException as cee:
            Domoticz.Error(_("Connection to airly api failed: %s") % str(cee.message))
            return
        except Exception as e:
            Domoticz.Error(e.message)
            return

        try:
            # check if another thread is not running
            # and time between last fetch has elapsed
            self.inProgress = True

            res = self.installation_measurement(Parameters["Mode2"])

            # iterate through values map
            values={}
            for item in res["values"]:
                try:
                    values[item['name']] = item['value']
                except KeyError:
                    pass  # No key/value

            try:
                self.variables[self.UNIT_PM10]['sValue'] = values["PM10"]
                self.variables[self.UNIT_PM10_PERCENTAGE]['sValue'] = (values["PM10"]/self.UNIT_PM10_NORM) * 100
            except KeyError:
                pass  # No pm10 value

            try:
                self.variables[self.UNIT_PM25]['sValue'] = values["PM25"]
                self.variables[self.UNIT_PM25_PERCENTAGE]['sValue'] = (values["PM25"] / self.UNIT_PM25_NORM) * 100
            except KeyError:
                pass  # No pm25 value

            try:
                self.variables[self.UNIT_PM1]['sValue'] = values["PM1"]
            except KeyError:
                pass  # No pm1 value

            try:
                self.variables[self.UNIT_AIR_QUALITY_INDEX]['sValue'] = res["indexes"][0]["value"]
            except KeyError:
                pass  # No airQualityIndex value

            try:
                if res["indexes"][0]["level"] == "VERY_LOW":
                    pollutionLevel = 1  # green
                elif res["indexes"][0]["level"] == "LOW":
                    pollutionLevel = 1  # green
                elif res["indexes"][0]["level"] == "MEDIUM":
                    pollutionLevel = 2  # yellow
                elif res["indexes"][0]["level"] == "HIGH":
                    pollutionLevel = 3  # orange
                elif res["indexes"][0]["level"] == "EXTREME":
                    pollutionLevel = 4  # red
                elif res["indexes"][0]["level"] == "AIRMAGEDDON":
                    pollutionLevel = 4  # red
                else:
                    pollutionLevel = 0
                
                pollutionDescription = res["indexes"][0]["description"]
                pollutionAdvice = res["indexes"][0]["advice"]

                self.variables[self.UNIT_AIR_POLLUTION_LEVEL]['nValue'] = pollutionLevel
                self.variables[self.UNIT_AIR_POLLUTION_LEVEL]['sValue'] = pollutionDescription
                
                self.variables[self.UNIT_AIR_POLLUTION_ADVICE]['nValue'] = pollutionLevel
                self.variables[self.UNIT_AIR_POLLUTION_ADVICE]['sValue'] = pollutionAdvice
                
            except KeyError:
                pass  # No air pollution value

            try:
                humidity = int(round(values["HUMIDITY"]))
                if humidity < 40:
                    humidity_status = 2  # dry HUMIDITY
                elif 40 <= humidity <= 60:
                    humidity_status = 0  # normal HUMIDITY
                elif 40 < humidity <= 70:
                    humidity_status = 1  # comfortable HUMIDITY
                else:
                    humidity_status = 3  # wet HUMIDITY

                self.variables[self.UNIT_HUMIDITY]['nValue'] = humidity
                self.variables[self.UNIT_HUMIDITY]['sValue'] = str(humidity_status)
            except KeyError:
                pass  # No humidity value

            try:
                self.variables[self.UNIT_TEMPERATURE]['sValue'] = values["TEMPERATURE"]
            except KeyError:
                pass  # No temperature value

            try:
                # in hpa + normal forecast
                self.variables[self.UNIT_BAROMETER]['sValue'] = str(values["PRESSURE"]) + ";0"
            except KeyError:
                pass  # No pressure value

            self.doUpdate()
        except SensorNotFoundException as snfe:
            Domoticz.Error(_("Sensor id (%(installation_id)d) not exists") % {'installation_id': int(Parameters["Mode2"])})
            return
        except UnauthorizedException as ue:
            Domoticz.Error(ue.message)
            Domoticz.Error(_("Enter correct airly API key - get one on https://developer.airly.eu"))
            return
        except TooManyRequestsException as tmre:
            Domoticz.Error(tmre.message)
            # postpone next pool to tomorrow
            next_attempt = self.postponeNextPool()
            Domoticz.Error(_("Next pool attempt at: %s") % str(next_attempt))
            return
        except ConnectionErrorException as cee:
            Domoticz.Error(_("Connection to airly api failed: %s") % str(cee.message))
            return
        except Exception as e:
            Domoticz.Error(_("Unrecognized error: %s") % str(e))
        finally:
            self.inProgress = False


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
                if unit in Devices:
                    Domoticz.Log(_("Update unit=%d; nValue=%d; sValue=%s") % (unit, nV, sV))
                    Devices[unit].Update(nValue=nV, sValue=sV)

    def api_airly_headers(self):
        """return http request headers"""

        self.airly_api_headers['apikey'] = Parameters['Mode1']
        self.airly_api_headers['User-Agent'] = self.airly_api_user_agent
        self.airly_api_headers['User-Agent'] = self.airly_api_user_agent
        self.airly_api_headers['Accept-Language'] = Settings["Language"]
        
        return self.airly_api_headers

    def installation_measurement(self, installation_id):
        """current sensor measurements"""

        installation_id = int(installation_id)
        airly_api = urlparse(self.api_v2_installation_measurements)
        params = urlencode({
            'installationId': installation_id,
            'indexType': 'AIRLY_CAQI'
            })
        

        try:
            conn = HTTPSConnection(airly_api.netloc)
            conn.request(
                method="GET",
                url=airly_api.path + "?" + params,
                headers=self.api_airly_headers(),
            )
            response = conn.getresponse()
            response_object = {}
            response_body = response.read()
        except Exception as e:
            raise ConnectionErrorException('', str(e))

        try:
            response_object = json.loads(response_body.decode("utf-8"))
        except UnicodeDecodeError as ude:
            Domoticz.Error(str(ude.message))
            # reset nextpool datestamp to force running in next run
            self.postponeNextPool(seconds=0)

        if response.status == 200:
            if "current" in response_object and len(response_object['current']) > 0:
                return response_object['current']
            else:
                raise SensorNotFoundException(installation_id, "")
            return response_object
        elif response.status in (401, 403, 404):
            raise UnauthorizedException(
                response.status,
                response_object['message'] if "message" in response_object else 'UnauthorizedException'
            )
        elif response.status == 429:
            raise TooManyRequestsException(
                response.status,
                response_object['message'] if "message" in response_object else 'TooManyRequestsException1'
            )
        else:
            Domoticz.Error(
                str(response.status) + ": " +
                response_object['message'] if "message" in response_object else 'UnknownError'
            )

    def installation_info(self, installation_id):
        """Station's info with coordinates, address and current pollution level"""

        installation_id = int(installation_id)
        airly_api = urlparse(self.api_v2_installation_info)

        try:
            conn = HTTPSConnection(airly_api.netloc)
            conn.request(
                method="GET",
                url=airly_api.path % {'installationId': installation_id},
                headers=self.api_airly_headers(),
            )
            response = conn.getresponse()
            response_object = {}
            response_body = response.read()
        except Exception as e:
            raise ConnectionErrorException('', str(e))

        try:
            response_object = json.loads(response_body.decode("utf-8"))
        except UnicodeDecodeError as ude:
            Domoticz.Error(ude.message)
            # reset nextpool datestamp to force running in next run
            self.nextpoll = datetime.datetime.now()
            return response_object

        if response.status == 200:
            return response_object
        elif response.status == 301:
            Domoticz.Error(
                str(response.status) + ": " +
                response_object['message'] if "message" in response_object else 'UnknownError'
            )
        elif response.status in (403, 404):
            raise UnauthorizedException(
                response.status,
                response_object['message'] if "message" in response_object else 'UnauthorizedException'
            )
        elif response.status == 429:
            raise TooManyRequestsException(
                response.status,
                response_object['message'] if "message" in response_object else 'TooManyRequestsException2'
            )
        else:
            Domoticz.Error(
                str(response.status) + ": " +
                response_object['message'] if "message" in response_object else 'UnknownError'
            )

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