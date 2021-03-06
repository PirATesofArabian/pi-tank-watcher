#! /usr/bin/python3

import argparse
import datetime
import random
import loggers
import time

PUMP_ON = 1
PUMP_OFF = 0


class AbstractPump:
    """Monitor of a sump pump. Logs when pump is activated/de-activated"""

    def __init__(self, pin):
        """Setup a pump watcher on the specific GPIO pin"""

        # list of loggers (to allow >1)
        self.loggers = []

        # store the pin for use in the callback
        self.pin = pin

        # used to prevent duplicate events (pull-down resistor does not fix it)
        self.prev_status = None

    def event(self, *_args):
        """
        Callback to log an event change to the configured loggers.
        Uses variable args because different GPIO libraries invoke with different parameters
        """
        status = self.get_status(self.pin)
        print("%s: Status on pin %d --> %s" % (datetime.datetime.now(), self.pin, status))

        if status == self.prev_status:
            print("Status did not change. Skipping.")
            return

        for l in self.loggers:
            if l:  # ignore empty loggers
                l.log([status])
        self.prev_status = status

    @staticmethod
    def get_status(_pin):
        """Default implementation to return status. Always return -1."""
        return -1

    def add_listener(self, new_logger):
        """
        Add a listener to be called when the pump is enabled/disabled.
        Can add multiple listeners to be called in sequence.
        :param new_logger the logger to add
        """
        print("Registering listener")
        self.loggers.append(new_logger)

    def cleanup(self):
        pass


def gen_random_samples(length):
    """
    Generate random sample data for the pump. Simulate occasional lost readings.

    :param length: number of entries to generate
    :return list of lists of the form [[timestamp, sample_id, 0/1]...]
    """
    data = []

    ts = datetime.datetime.utcnow()
    sample_id = 1
    while sample_id <= length:

        # get a PUMP_ON event
        event = gen_mainly_on()
        if event == PUMP_ON:
            # timestamp is assumed to be at least 45 mins since last PUMP_OFF + random(100 minutes)
            ts += datetime.timedelta(0, 45 * 60) + datetime.timedelta(0, random.randint(0, 100 * 60))
            data.append([ts.strftime("%Y-%m-%d %H:%M:%S UTC"), sample_id, event])
            sample_id += 1
        else:
            # print("missed pump PUMP_ON")
            pass

        event = gen_mainly_off()
        if event == PUMP_OFF:
            # pump is assumed to be on for random(10 minutes)
            ts = ts + datetime.timedelta(0, random.randint(0, 10 * 60))
            data.append((ts.strftime("%Y-%m-%d %H:%M:%S UTC"), sample_id, event))
            sample_id += 1
        else:
            # print("missed pump PUMP_OFF")
            pass

    # events are potentially appended in pairs, meaning we may exceed the requested length
    return data[:length]


def gen_random_event(threshold):
    """
    Generate a random event (PUMP_ON or PUMP_OFF).
    The event is chosen randomly, but the threshold defines the probability. 1 means always off, 0 means always on.

    :param threshold: the value used to determine the generated event type. Values < threshold = PUMP_OFF; Values >= threshold = PUMP_ON
    :return PUMP_ON or PUMP_OFF
    """
    r = random.random()
    if r >= threshold:
        return PUMP_ON
    return PUMP_OFF


def gen_mainly_on():
    """Generate an event - most likely a PUMP_ON event."""
    return gen_random_event(0.2)


def gen_mainly_off():
    """Generate an event - most likely a PUMP_OFF event."""
    return gen_random_event(0.8)


if __name__ == '__main__':
    gpio_disabled = False

    # read command-line args
    parser = argparse.ArgumentParser(
        description="Monitor the on/off switching of a sump pump")
    parser.add_argument("gpio_pin", help="GPIO pin connected to the pump", type=int)
    parser.add_argument("--thingspeak", dest="thing_speak_api",
                        help="API key to write new sensor readings to thingspeak.com channel")
    parser.add_argument("--healthchecks", dest="healthchecks_url",
                        help="healthchecks.io URL to ping when pump is activated")
    parser.add_argument("--gpio", help="GPIO library to use implementation", type=str, choices=["RPi.GPIO", "wiringpi"],
                        dest="gpio_lib", default=None)
    args = parser.parse_args()
    print(args)

    # --- Setup where to log the data
    all_loggers = []

    # add a logger to ThingSpeak if defined
    if args.thing_speak_api:
        print("Adding ThingSpeak logger (API key %s)" % args.thing_speak_api)
        all_loggers.append(loggers.ThingSpeak(args.thing_speak_api))
    else:
        print("Adding console logger")
        all_loggers.append(loggers.ConsoleLogger())

    # add a logger to HealthChecks.io if defined
    if args.healthchecks_url:
        print("Adding HealthChecks logger (URL %s)" % args.healthchecks_url)
        all_loggers.append(loggers.HealthChecks(args.healthchecks_url))

    print("Connecting to pin %s" % args.gpio_pin)

    # --- Create the pump monitor
    pump = None
    if args.gpio_lib:
        if args.gpio_lib == "RPi.GPIO":
            import pump_rpio_gpio

            print("Using RPi.GPIO library")
            pump = pump_rpio_gpio.RpiGpioPump(args.gpio_pin)
        elif args.gpio_lib == "wiringpi":
            import pump_wiringpi

            print("Using wiringpi library")
            pump = pump_wiringpi.WiringPiPump(args.gpio_pin)
    else:
        print("GPIO disabled")
        pump = AbstractPump(args.gpio_pin)

    # add all the loggers setup previously
    for logger in all_loggers:
        pump.add_listener(logger)

    try:
        print("Waiting for events...")
        while True:
            time.sleep(86400)  # sleep 1 day
    finally:
        pump.cleanup()
