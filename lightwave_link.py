#!/usr/bin/python2.7
# encoding: utf8
"""
Monitoring tool for LightwaveRF Heating, based on the API published at
https://api.lightwaverf.com/introduction_basic_comms.html

This tool requires a LightwaveRF Link to bridge the UDP/IP network on which
this tool runs, and the LightwaveRF devices (which do not use WiFI).
"""

# pylint: disable=invalid-name,trailing-whitespace,missing-docstring

import sys
import logging
import prometheus_client

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)-15s %(levelname)-7s %(message)s ",
    level=logging.INFO)
sLog = logging.getLogger('LightwaveLink')

COMMAND = "!R{RoomNo}D{DeviceNo}F{FunctionType}P{Parameter}|{Line1}|{Line2}"

# =============================================================================
class ProtectedAttribute(object):
    """
    Descriptor which protects all data access (get, set) with its host
    instance's `sLock` attribute.
    """
    def __get__(self, sHostInstance, clsType=None):
        del clsType
        with sHostInstance.sLock:
            return self.mValue
    def __set__(self, sHostInstance, mNewValue):
        with sHostInstance.sLock:
            self.mValue = mNewValue

# =============================================================================
class LightwaveLink(object):
    """
    :IVariables:
        sSock : socket.socket
            UDP/IP socket used for both transmitting commands to the Lightwave
            Link and receiving responses. Note that responses are received on a
            different port number than commands are sent on.
        rAddress : str
            IPv4 dotted decimal representation of the Lightwave Link's IP
            address if known. Initially set to the broadcast address,
            `255.255.255.255`.
        siTransactionNumber : int generator
            Generator object which yields integers with monotonically
            increasing values. These are used to give every command transmitted
            a unique transaction number. Experiment has shown the Lightwave
            Link will not respond, at all, if the command lacks a transaction
            number.
        sResponses : queue.Queue
            Sequence of messages received from the Lightwave Link. Note that
            because the Lightwave Link broadcasts all its responses, the
            responses may not be related to any commands sent by us.
        sLock : threading.RLock
            Mutual exclusion (mutex) lock that guards access to attributes.
        fLastCommandTime : float
            Unixtime when last command was issued. Used to implement rate
            limiting.
        iLastTransactionNumber : int
            Most recently transmitted transaction number sent by
            `send_command`.
        rLastCommand : str
            Most recently transmitted command string sent by `send_command`.
            Used to retransmit in response to "Transmit fail" errors from the
            Lightwave Link.
    """
    LIGHTWAVE_LINK_COMMAND_PORT = 9760    # Send to this address...
    LIGHTWAVE_LINK_RESPONSE_PORT = 9761   # ... and get response on this one
    MIN_SECONDS_BETWEEN_COMMANDS = 3.0
    COMMAND_TIMEOUT_SECONDS = 5

    fLastCommandTime = ProtectedAttribute()
    iLastTransactionNumber = ProtectedAttribute()
    rLastCommand = ProtectedAttribute()

    sPResponseDelay = prometheus_client.Gauge(
        "lwl_response_delay_seconds",
        "Time between command being issued and response being recieved",
        ["fn",],
        )
    sPResponseCounter = prometheus_client.Counter(
        "lwl_responses",
        "Number of distinct JSON message received",
        ["fn",],
        )

    def __init__(self):
        import threading
        self.sSock = self.create_socket()
        self.rAddress = "255.255.255.255"
        self.siTransactionNumber = self.sequence_generator()
        self.sResponses = self.create_listener(self.sSock)
        self.sLock = threading.RLock()
        self.fLastCommandTime = 0.0
        self.iLastTransactionNumber = 0
        self.rLastCommand = ""
        self.sThead = None

    def create_socket(self):
        """Create a listening socket to receive UDP messages from the Lightwave
        Link"""
        import socket
        sSock = socket.socket(
            socket.AF_INET, 
            socket.SOCK_DGRAM)
        tLocalAddress = (
            "0.0.0.0",
            self.LIGHTWAVE_LINK_RESPONSE_PORT)
        sSock.bind(tLocalAddress)
        sSock.setsockopt(
            socket.SOL_SOCKET, 
            socket.SO_BROADCAST,
            1)
        return sSock

    @staticmethod
    def sequence_generator(iInt=None):
        import time
        if not iInt:
            iInt = 100
        while True:
            yield iInt
            iInt += 1

    def send_command(self, rPayload, iTransactionNumber=None):
        import time

        # Rate-limit
        fNow = time.time()
        fNext = self.fLastCommandTime + self.MIN_SECONDS_BETWEEN_COMMANDS
        fWait = fNext - fNow
        if fWait > 0.0:
            sLog.log(5, "Rate limit send_command(): %s", fWait)
            time.sleep(fWait)

        if iTransactionNumber is None:
            iTransactionNumber = self.siTransactionNumber.next()

        with self.sLock:
            self.iLastTransactionNumber = iTransactionNumber
            self.fLastCommandTime = time.time()
            self.rLastCommand = rPayload

        rCommand = "{},{}".format(
            iTransactionNumber,
            rPayload)
        tDestinationAddress = (
            self.rAddress,
            self.LIGHTWAVE_LINK_COMMAND_PORT)
        sLog.debug(
            "send_command(%s, %s)",
            rCommand,
            tDestinationAddress)
        self.sSock.sendto(
            rCommand, 
            tDestinationAddress)

    def get_response(self):
        import time
        try:
            fTimeout = (
                        self.COMMAND_TIMEOUT_SECONDS
                        + time.time() 
                        - self.fLastCommandTime 
                        )
            dResponse = self.sResponses.get(True, fTimeout)
            fDelay = time.time() - self.fLastCommandTime
            rFn = dResponse.get("fn", "")
            self.sPResponseDelay.labels(rFn).set(fDelay)
            self.sPResponseCounter.labels(rFn).inc()
            return dResponse
        except self.sResponses.Empty:
            return {}

    def create_listener(self, sSock):
        import threading
        import Queue as queue
        sQueue = queue.Queue()
        sQueue.Empty = queue.Empty
        def run():
            """Responses are send twice, once unicast and another broadcast.
            This makes duplicate messages very common."""
            import json
            import collections
            # nonlocal sSock
            # nonlocal sQueue
            iTransactionNumber = 0
            lPreviousMessages = collections.deque(maxlen=10)
            while True:
                rMessage = sSock.recv(1024)
                if rMessage in lPreviousMessages:
                    sLog.log(1, "Ignoring duplicate JSON message")
                    continue
                lPreviousMessages.appendleft(rMessage)
                sLog.log(2, "RAW response: %s", rMessage)
                if rMessage.startswith("*!{"):
                    rJSON = rMessage[len("*!"):]
                    dMessage = json.loads(rJSON)
                    iResponseTrans = int(dMessage.get("trans", 0))
                    if iResponseTrans > iTransactionNumber:
                        iTransactionNumber = iResponseTrans
                        sQueue.put(dMessage)
                    else:
                        sLog.log(
                            1, 
                            "Discarding duplicate trans: %s", 
                            iResponseTrans)
                elif rMessage.strip().endswith(",OK"):
                    sLog.log(1, "Ignoring acknowledgement")
                else:
                    sLog.warning(
                        "Discarding non-JSON response: %s",
                        rMessage)
        def runner():
            # nonlocal run
            # nonlocal sLog
            while True:
                # pylint: disable=bare-except
                try:
                    run()
                except:
                    sLog.error(
                        "Exception from Lightwave Listener thread",
                        exc_info=True)

        self.sThread = threading.Thread(
            target=runner,
            name="LightwaveLink Listener"
            )
        self.sThread.daemon = True   # Do not prevent process exit()
        self.sThread.start()
        return sQueue

    def test_connectivity(self):
        sLog.info("Checking if this host is registered with Lightwave Link...")
        self.send_command("@H") # Hub call
        dResponse = self.get_response()

        # Sample successful response from hub-call:
        """
        {"trans":160,           "mac":"20:3B:85",
         "time":1545002320,     "pkt":"system",
         "fn":"hubCall",        "type":"hub",
         "prod":"lwl",          "fw":"N2.94D",
         "uptime":23376,        "timeZone":0,
         "lat":52.48,           "long":-1.89,
         "tmrs":0,              "evns":0,
         "run":0,               "macs":3,
         "ip":"192.168.167.114","devs":2}
        """
        # Sample not-registered error:
        """
        {"trans":21,            "mac":"20:3B:85",
        "time":1544985980,      "pkt":"error",
        "fn":"nonRegistered", 
        "payload":"Not yet registered. See LightwaveLink"}
        """

        if dResponse.get("fn") == "hubCall":
            sLog.info("This device is registered.")
            return True
        elif dResponse.get("fn") == "nonRegistered":
            return self.register()

        sLog.debug("Unexpected response: %s", dResponse)
        return False

    def register(self):
        """
        We send (note transaction number of 0)::

            0,!F*p

        If already registered / authorised, a single (unicast) response is
        received::

            0,?V="N2.94D"

        Otherwise (i.e. not registered), three responses are received. First
        response (broadcast)::

            0,ERR,2,"Not yet registered. See LightwaveLink"

        Second and third responses (only listed once here) are identical, once
        via unicast and the other via broadcast. Note the `trans` number has no
        relation to the transaction number in our command::

            *!{"trans":21, "mac":"20:3B:85", "time":1544985980, "pkt":"error",
            "fn":"nonRegistered", "payload":"Not yet registered. See
            LightwaveLink"}

        After a user physically pushes the flashing button on the Lightwave
        Link to authorise a new device, another message is received::

            *!{"trans":22, "mac":"20:3B:85", "time":1544985990, "type":"link",
            "prod":"lwl", "pairType":"local", "msg":"success", "class":"",
            "serial":""}
        """
        import time
        try:
            while True:
                self.send_command("!F*p")
                dResponse = self.get_response()
                if dResponse.get("fn") == "nonRegistered":
                    sLog.info(
                        "Pairing request sent. Please push button with "
                        "flashing light on Lightwave Link to complete "
                        "pairing. (Or press ^C to give up)")
                    time.sleep(3)
                elif dResponse.get("msg") == "success":
                    sLog.info("Successfully paired!")
                    return True
        except KeyboardInterrupt:
            sLog.warn("Aborting registration process due to SIGINT")
            return False

    def scan_devices(self):
        sLog.info("Query LightwaveLink for list of known devices...")
        while True:
            try:
                lRooms = self.enumerate_devices()
                break
            except KeyError:
                # Indicates the response was not understood
                pass
        sLog.info("%s devices", len(lRooms))
        for i, iDevice in enumerate(lRooms):
            sLog.info("Asking device #%s to provide status update...", i)
            # Get device info (serial + room in same JSON response!)
            self.send_command("@?R{}".format(iDevice))
            # Request status report from device
            self.send_command("!R{}F*r".format(iDevice))

    def enumerate_devices(self):
        self.send_command("@R")
        dResponse = self.get_response()
        """ Sample response:
        {u'fn': u'summary',
         u'mac': u'20:3B:85',
         u'pkt': u'room',
         u'stat0': 127,     u'stat1': 1,
         u'stat2': 0,       u'stat3': 0,
         u'stat4': 0,       u'stat5': 0,
         u'stat6': 0,       u'stat7': 0,
         u'stat8': 0,       u'stat9': 0,
         u'time': 1545144155,
         u'trans': 1473}
        """
        lRooms = []
        for i in range(10):
            rKey = "stat{}".format(i)
            iBits = dResponse[rKey]
            p = 1
            while p <= 8:
                if not iBits:
                    break
                if iBits & 1:
                    iRoom = (i*8) + p
                    lRooms.append(iRoom)
                p += 1
                iBits >>= 1
        sLog.debug("Rooms known to hub: %s", lRooms)
        return lRooms

class TRVStatus(object):
    """
    Sample status from 868R Thermostatic Radiator Valve (TRV)::

        {u'batt': 2.69,
         u'cTarg': 21.0,
         u'cTemp': 22.0,
         u'fn': u'statusPush',
         u'mac': u'20:3B:85',
         u'nSlot': u'18:00',
         u'nTarg': 50.0,
         u'output': 0,
         u'pkt': u'868R',
         u'prod': u'valve',
         u'prof': 2,
         u'serial': u'DBC302',
         u'state': u'man',
         u'time': 1545130654,
         u'trans': 982,
         u'type': u'temp',
         u'ver': 58}

    Sample description of device from Lightwave Link ("hub")::

       {"trans":357,
        "mac":"20:3B:85",
        "time":1546366407,
        "pkt":"room",
        "fn":"read",
        "slot":1,
        "serial":"DCC302",
        "prod":"valve"}

    """
    # pylint: disable=too-many-instance-attributes

    sPbatt = prometheus_client.Gauge(
        "lwl_battery_volts",
        "Battery voltage, in range 0.0-4.0 (inc.). 2.4V is considered "
        "'low', 3.0V+ is considered full'",
        ['serial', 'name', 'product'],
        )
    sPcTargC = prometheus_client.Gauge(
        "lwl_target_celsius",
        "0.0-40.0 current target temperature",
        ['serial', 'name', 'product'],
        )
    sPcTargR = prometheus_client.Gauge(
        "lwl_target_ratio",
        "0.0-1.0 current target valve output",
        ['serial', 'name', 'product'],
        )
    sPcTemp = prometheus_client.Gauge(
        "lwl_current_celsius",
        "0.0-60.0 current temperature",
        ['serial', 'name', 'product'],
        )
    sPoutput = prometheus_client.Gauge(
        "lwl_output_ratio",
        "0.0-1.0 where 0=valve fully closed, 1=valve fully open",
        ['serial', 'name', 'product'],
        )
    sPtime = prometheus_client.Gauge(
        "lwl_time",
        "Unixtime of most recently received status update",
        ['serial', 'name', 'product'],
        )

    def __init__(self, rName):
        # Local data
        self.rName = rName

        # Data from Lightwave Link statusPush messages
        self.batt = None
        self.cTarg = None
        self.cTemp = None
        self.fn = None
        self.mac = None
        self.nSlot = None
        self.nTarg = None
        self.output = None
        self.pkt = None
        self.prod = None
        self.prof = None
        self.serial = None
        self.state = None
        self.time = None
        self.trans = None
        self.type = None
        self.ver = None

        # Data unique to room messages (query device info from hub)
        self.slot = None

    def update(self, dStatus):
        for rKey, mValue in dStatus.iteritems():
            setattr(self, rKey, mValue)

        if dStatus["fn"] == "read":
            # Do not update prometheus metrics - not a status update
            return

        tLabels = (self.serial, self.rName, self.prod)
        self.sPbatt.labels(*tLabels).set(self.batt)
        self.sPcTemp.labels(*tLabels).set(self.cTemp)
        self.sPoutput.labels(*tLabels).set(self.output / 100.0)

        # We treat target temperature and target output as different metrics
        # because their units are different.
        if self.cTarg < 50.0:
            self.sPcTargC.labels(*tLabels).set(self.cTarg)
            self.sPcTargR.labels(*tLabels).set(float("NaN"))
        else:
            fRatio = (self.cTarg - 50) / (60-50)
            self.sPcTargC.labels(*tLabels).set(float("NaN"))
            self.sPcTargR.labels(*tLabels).set(fRatio)

        self.sPtime.labels(*tLabels).set(self.time)

    def get_battery_level_str(self):
        fBatt = self.batt

        fLo = 2.4
        fHi = 3.0

        # Get battery percentage
        # Note that we want fLo to be ~10%, not 0%!
        fLo10 = fLo - ((fHi - fLo)/10)
        rBatt = "{:.0%}".format((fBatt - fLo10) / (fHi-fLo10))

        return rBatt

    @staticmethod
    def format_temperature(fTemp):
        if 0.0 <= fTemp < 50.0:
            return "{:.1f}°C".format(fTemp)

        # 50.0 = Valve closed
        # 60.0 = Valve open
        fValve = (fTemp - 50) / (60-50)
        return "{:.0%}".format(fValve)

    @staticmethod
    def format_prof(iProf):
        return {
            1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
            7: "Sunday",
            }.get(iProf, "(?)")

    def __str__(self):
        import textwrap

        # Data only available if we've received a status update, otherwise may
        # raise AttributeError.
        if not self.batt:
            return textwrap.dedent("""\
                TRVStatus({self.rName}):
                     prod: {self.prod}
                   serial: {self.serial}
                     slot: {self.slot}
                     time: {self.time}
                    trans: {self.trans}
                """.format(
                    self=self,
                    ))

        # pylint: disable=unused-variable
        rBatt = self.get_battery_level_str()
        rcTarg = self.format_temperature(self.cTarg)
        rnTarg = self.format_temperature(self.nTarg)
        rProf = self.format_prof(self.prof)

        dLocals = locals()

        return textwrap.dedent("""\
            TRVStatus({self.rName}):
                 batt: {rBatt:<10}  {self.batt}V (2.4-3.0V)
                cTarg: {rcTarg:<10}   {self.cTarg}
                cTemp: {self.cTemp}°C
                nSlot: {self.nSlot}
                nTarg: {rnTarg:<10}   {self.nTarg}
               output: {self.output}%
                 prof: {rProf:<10}  {self.prof}
                 prod: {self.prod}
               serial: {self.serial}
                 slot: {self.slot}
                state: {self.state}
                 time: {self.time}
                trans: {self.trans}
                 type: {self.type}
                  ver: {self.ver}
            """.format(
                **dLocals
                ))

def load_config():
    import yaml
    with file("config.yml", "r") as sFH:
        dConfig = yaml.load(sFH)
    return dConfig

def call_for_heat(sLink, dStatus):
    lCalling = are_calling_for_heat(dStatus)

    for sDevice in dStatus.itervalues():
        if sDevice.rName == "Boiler switch":
            break
    else:
        sLog.error(
            "No device named 'Boiler switch' present in configuration "
            "file, unable to call for (lack of) heat!")
        return

    # pylint: disable=undefined-loop-variable

    rCommandTemplate = "!R{}F*tP{}"
    OFF = 50.0
    ON = 60.0
    if lCalling:
        rCommand = rCommandTemplate.format(sDevice.slot, ON)
    else:
        rCommand = rCommandTemplate.format(sDevice.slot, OFF)

    if bool(sDevice.output) == bool(lCalling):
        sLog.info("Call for heat: NOOP (heating: %s)", bool(sDevice.output))
        return

    lNames = [x.rName for x in lCalling]
    sLog.info("Call for heat: %s (command: %s)", lNames, rCommand)
    sLink.send_command(rCommand)

def are_calling_for_heat(dStatus):
    lCalling = []
    for sDevice in dStatus.itervalues():
        if sDevice.prod != "valve":
            continue
        if sDevice.output:
            lCalling.append(sDevice)

    return lCalling

def scan_stale_devices(dStatus, sLink):
    # Generator which _may_ scan stale devices, if it hasn't done so recently
    import time

    STALE_THRESHOLD_SECONDS   = 3*60*60  # 3h
    MIN_SCAN_INTERVAL_SECONDS =   30*60  # 30m

    iNextScanTime = 0

    while True:
        iNow = time.time()
        if iNow < iNextScanTime:
            # Not yet time to scan, wait until next opportunity
            sLog.debug(
                "Stale scan skipped, MIN_SCAN_INTERVAL_SECONDS not yet lapsed")
            yield
        else:
            iNextScanTime = iNow + MIN_SCAN_INTERVAL_SECONDS
            sLog.debug("Stale scan started")

        for sDevice in dStatus.values():
            if sDevice.nSlot is None:
                # Not addressable, cannot ask for an update
                sLog.debug("Device %s is not addressable", sDevice.rName)
                continue
            if not sDevice.time or (iNow - sDevice.time >STALE_THRESHOLD_SECONDS):
                sLog.info(
                    "%s status is stale, requesting update...",
                    sDevice.rName)
                sLink.send_command("!R{}F*r".format(sDevice.nSlot))

        yield

def main():
    dConfig = load_config()

    prometheus_client.start_http_server(9191)

    sLink = LightwaveLink()
    sLink.test_connectivity()
    sLink.scan_devices()

    dStatus = {}    # rSerial: TRVStatus
    siStaleScanner = scan_stale_devices(dStatus, sLink)

    while True:
        try:
            # Avoid entering an unblockable system call, as that would prevent
            # signals like SIGINT (KeyboardInterrupt) being delivered
            dResponse = sLink.sResponses.get(True, 3600)
        except sLink.sResponses.Empty:
            continue

        if dResponse.get("fn") in (
                "read", "statusPush", "statusOn", "statusOff"):
            rSerial = dResponse["serial"]
            if rSerial not in dStatus:
                if rSerial not in dConfig:
                    sLog.warn(
                        "Device with serial %s not present in config file",
                        rSerial)
                rName = dConfig.get(rSerial, rSerial)
                dStatus[rSerial] = TRVStatus(rName)
            dStatus[rSerial].update(dResponse)
            sLog.info(str(dStatus[rSerial]))

            # Try to avoid hysteria following sLink.scan_devices()
            if sLink.sResponses.empty():
                call_for_heat(sLink, dStatus)
        elif dResponse.get("fn") in (
                "ack",
                "getStatus",
                "home",
                "hubCall",
                "off",      # Human pushed button on TRV
                "on",       # Human pushed button on TRV
                "setTarget",
                "setTime",
            ):
            pass
        elif dResponse.get("type") == "log":
            pass
        else:
            sLog.warn("Unhandled response:\n%s", dResponse)

        # Request status updates from devices we've not seen for a while.
        # Self-limits how often it performs scans.
        siStaleScanner.next()

if __name__ == "__main__":
    main()
