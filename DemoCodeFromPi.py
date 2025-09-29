from octorest import OctoRest
from gpiozero import Motor
from time import sleep

import gpiod

chip = gpiod.Chip('gpiochip4')
pin_one = 23
pin_two = 24

motor = Motor(forward = pin_one, backward = pin_two)

def client(url, apikey):
     """Creates and returns an instance of the OctoRest client.

     Args:
         url - the url to the OctoPrint server
         apikey - the apikey from the OctoPrint server found in settings
     """
     try:
         client = OctoRest(url=url, apikey=apikey)
         return client
     except ConnectionError as ex:
         # Handle exception as you wish
         print(ex)

def toggle_home(client):
     """Toggles the current print (if printing it pauses and
     if paused it starts printing) and then homes all of
     the printers axes.

     Args:
         client - the OctoRest client
     """

     print("Homing your 3d printer...")
     client.home()

def full_home():
    theclient = client("http://192.168.86.130:5000","vXUq-MOmzAclkDo8Eh7dScOVOrrYJMvJMxmdYAfG-p8")

    toggle_home(theclient)

def demo_motor():

    print("started")

    motor.forward()

    sleep(5)

    motor.stop()
    motor.close

    print("stopped")

def main():
    print("Started")
        


main()
