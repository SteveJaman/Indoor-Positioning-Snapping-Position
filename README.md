CPE 4800 F25 - Senior Design
============================
|          Readme          |
============================
**Design Project**
The compact, all-in-one cart built specifically for grocery delivery personnel. 
It features integrated Self-Checkout and Live In-Store Position Tracking to make shopping faster and easier.

**Team**
SyntaxError

**Members**
Margarita, Thi, Carter, Steven, Anthony

**Indoor Position Team**
Steven and Anthony

**Description**
This ESP32 code implements an advanced indoor positioning system using Bluetooth Low Energy (BLE) trilateration and sophisticated filtering 
to track a device's position within a defined 6x6 meter area, then transmits the result via MQTT. The system works by continuously scanning 
for four fixed BLE beacons, calculating the distance to each beacon based on a median-filtered Received Signal Strength Indicator (RSSI), 
and then using an Inverse Distance Weighted (IDW) Multilateration technique to estimate a raw position. This raw position is then fed into 
both a Kalman Filter and a Particle Filter for noise reduction and motion tracking to generate a stable, smoothed final location, which is 
finally snapped to a grid before being published to an MQTT broker over Wi-Fi for real-time tracking.
