#!/usr/bin/python2.7
"""
Monitoring tool for LightwaveRF Heating, based on the API published at
https://api.lightwaverf.com/introduction_basic_comms.html

This tool requires a LightwaveRF Link to bridge the UDP/IP network on which
this tool runs, and the LightwaveRF devices (which do not use WiFI).
"""

import logging

logging.basicConfig(
    format="%(asctime)-15s %(levelname)-7s %(message)s ",
    level=logging.INFO)
sLog = logging.getLogger('LightwaveLink')

COMMAND = "!R{RoomNo}D{DeviceNo}F{FunctionType}P{Parameter}|{Line1}|{Line2}"

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
    """
    LIGHTWAVE_LINK_COMMAND_PORT = 9760    # Send to this address...
    LIGHTWAVE_LINK_RESPONSE_PORT = 9761   # ... and get response on this one
    COMMAND_TIMEOUT_SECONDS = 1

    def __init__(self):
        self.sSock = self.create_socket()
        self.rAddress = "255.255.255.255"
        self.siTransactionNumber = self.sequence_generator()
        self.sResponses = self.create_listener(self.sSock)

    def create_socket(self, rAddress=None):
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
            iInt = int(time.time())
        while True:
            yield iInt
            iInt += 1

    def send_command(self, rPayload, iTransactionNumber=None):
        if iTransactionNumber is None:
            iTransactionNumber = self.siTransactionNumber.next()
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
        try:
            dResponse = self.sResponses.get(True, self.COMMAND_TIMEOUT_SECONDS)
            return dResponse
        except self.sResponses.Empty:
            return {}

    def create_listener(self, sSock):
        import threading
        import Queue as queue
        sQueue = queue.Queue()
        sQueue.Empty = queue.Empty
        def run():
            import json
            # nonlocal sSock
            # nonlocal sQueue
            iTransactionNumber = 0
            while True:
                rMessage = sSock.recv(1024)
                sLog.log(5, "RAW response: %s", rMessage)
                if rMessage.startswith("*!{"):
                    rJSON = rMessage[len("*!"):]
                    dMessage = json.loads(rJSON)
                    iResponseTrans = int(dMessage.get("trans", 0))
                    if iResponseTrans > iTransactionNumber:
                        iTransactionNumber = iResponseTrans
                        sQueue.put(dMessage)
                    else:
                        sLog.log(5, "Discarding duplicate trans: %s", iResponseTrans)
                else:
                    sLog.warning(
                        "Discarding non-JSON response: %s",
                        rMessage)
        sThread = threading.Thread(
            target=run,
            name="LightwaveLink Listener"
            )
        sThread.daemon = True   # Do not prevent process exit()
        sThread.start()
        return sQueue

    def test_connectivity(self):
        import time
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
        else:
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
                    sLog.info("Pairing request sent. Please push button with "
                        "flashing light on Lightwave Link to complete "
                        "pairing. (Or press ^C to give up)")
                    time.sleep(3)
                elif dResponse.get("msg") == "success":
                    sLog.info("Successfully paired!")
                    return True
        except KeyboardInterrupt:
            sLog.warn("Aborting registration process due to SIGINT")
            return False

def main():
    import time
    import json
    import pprint

    import prometheus_client
    sCounter = prometheus_client.Counter(
        "lwl_response_count",
        "Number of distinct JSON message recieved from the Lightwave Link",
        )
    prometheus_client.start_http_server(9191)

    sLink = LightwaveLink()
    sLink.test_connectivity()

    # Do nothing using an interruptible system call, so signals can be
    # delivered.
    while True:
        dResponse = sLink.sResponses.get(True, 3600)
        pprint.pprint(dResponse)
        sCounter.inc()

if __name__ == "__main__":
    main()
