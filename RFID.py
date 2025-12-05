import sys

sys.path.append('/usr/lib/python3/dist-packages')



import time

import spidev

from gpiozero import DigitalOutputDevice

import paho.mqtt.client as mqtt

import random



# ----------------- MQTT CONFIGURATION -----------------

MQTT_BROKER = "192.168.137.8"

MQTT_PORT = 1883

CHECKOUT_TOPIC = "indoor/checkout"  # Topic for sending payment signals

CLIENT_ID = f"RFID_Reader_Client_{random.randint(1000, 9999)}"



def setup_mqtt():

    """Initializes and connects the MQTT client for publishing."""

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)

    try:

        client.connect(MQTT_BROKER, MQTT_PORT, 60)

        client.loop_start()

        print("MQTT connected for publishing.")

        return client

    except Exception as e:

        print(f"MQTT connection failed: {e}")

        return None



# ----------------- MFRC522_Pi5 CLASS -----------------

class MFRC522_Pi5:

    NRSTPD = 22



    MAX_LEN = 16



    PCD_IDLE = 0x00

    PCD_AUTHENT = 0x0E

    PCD_RECEIVE = 0x08

    PCD_TRANSMIT = 0x04

    PCD_TRANSCEIVE = 0x0C

    PCD_RESETPHASE = 0x0F

    PCD_CALCCRC = 0x03



    PICC_REQIDL = 0x26

    PICC_REQALL = 0x52

    PICC_ANTICOLL = 0x93

    PICC_SElECTTAG = 0x93

    PICC_AUTHENT1A = 0x60

    PICC_AUTHENT1B = 0x61

    PICC_READ = 0x30

    PICC_WRITE = 0xA0

    PICC_DECREMENT = 0xC0

    PICC_INCREMENT = 0xC1

    PICC_RESTORE = 0xC2

    PICC_TRANSFER = 0xB0

    PICC_HALT = 0x50



    MI_OK = 0

    MI_NOTAGERR = 1

    MI_ERR = 2



    Reserved00 = 0x00

    CommandReg = 0x01

    CommIEnReg = 0x02

    DivlEnReg = 0x03

    CommIrqReg = 0x04

    DivIrqReg = 0x05

    ErrorReg = 0x06

    Status1Reg = 0x07

    Status2Reg = 0x08

    FIFODataReg = 0x09

    FIFOLevelReg = 0x0A

    WaterLevelReg = 0x0B

    ControlReg = 0x0C

    BitFramingReg = 0x0D

    CollReg = 0x0E

    Reserved01 = 0x0F



    Reserved10 = 0x10

    ModeReg = 0x11

    TxModeReg = 0x12

    RxModeReg = 0x13

    TxControlReg = 0x14

    TxAutoReg = 0x15

    TxSelReg = 0x16

    RxSelReg = 0x17

    RxThresholdReg = 0x18

    DemodReg = 0x19

    Reserved11 = 0x1A

    Reserved12 = 0x1B

    MifareReg = 0x1C

    Reserved13 = 0x1D

    Reserved14 = 0x1E

    SerialSpeedReg = 0x1F



    Reserved20 = 0x20

    CRCResultRegM = 0x21

    CRCResultRegL = 0x22

    Reserved21 = 0x23

    ModWidthReg = 0x24

    Reserved22 = 0x25

    RFCfgReg = 0x26

    GsNReg = 0x27

    CWGsPReg = 0x28

    ModGsPReg = 0x29

    TModeReg = 0x2A

    TPrescalerReg = 0x2B

    TReloadRegH = 0x2C

    TReloadRegL = 0x2D

    TCounterValueRegH = 0x2E

    TCounterValueRegL = 0x2F



    Reserved30 = 0x30

    TestSel1Reg = 0x31

    TestSel2Reg = 0x32

    TestPinEnReg = 0x33

    TestPinValueReg = 0x34

    TestBusReg = 0x35

    AutoTestReg = 0x36

    VersionReg = 0x37

    AnalogTestReg = 0x38

    TestDAC1Reg = 0x39

    TestDAC2Reg = 0x3A

    TestADCReg = 0x3B

    Reserved31 = 0x3C

    Reserved32 = 0x3D

    Reserved33 = 0x3E

    Reserved34 = 0x3F



    serNum = []



    def __init__(self, bus=0, device=0, speed=1000000, pin_rst=22):

        self.pin_rst = DigitalOutputDevice(pin_rst)

        self.pin_rst.off()  # Reset the reader

        time.sleep(0.1)

        self.pin_rst.on()

        time.sleep(0.1)

        

        self.spi = spidev.SpiDev()

        self.spi.open(bus, device)

        self.spi.max_speed_hz = speed

        self.MFRC522_Init()



    def MFRC522_Reset(self):

        self.Write_MFRC522(self.CommandReg, self.PCD_RESETPHASE)



    def Write_MFRC522(self, addr, val):

        self.spi.xfer2([(addr << 1) & 0x7E, val])



    def Read_MFRC522(self, addr):

        val = self.spi.xfer2([((addr << 1) & 0x7E) | 0x80, 0])

        return val[1]



    def SetBitMask(self, reg, mask):

        tmp = self.Read_MFRC522(reg)

        self.Write_MFRC522(reg, tmp | mask)



    def ClearBitMask(self, reg, mask):

        tmp = self.Read_MFRC522(reg)

        self.Write_MFRC522(reg, tmp & (~mask))



    def AntennaOn(self):

        temp = self.Read_MFRC522(self.TxControlReg)

        if (~(temp & 0x03)):

            self.SetBitMask(self.TxControlReg, 0x03)



    def AntennaOff(self):

        self.ClearBitMask(self.TxControlReg, 0x03)



    def MFRC522_ToCard(self, command, sendData):

        backData = []

        backLen = 0

        status = self.MI_ERR

        irqEn = 0x00

        waitIRq = 0x00

        lastBits = None

        n = 0



        if command == self.PCD_AUTHENT:

            irqEn = 0x12

            waitIRq = 0x10

        if command == self.PCD_TRANSCEIVE:

            irqEn = 0x77

            waitIRq = 0x30



        self.Write_MFRC522(self.CommIEnReg, irqEn | 0x80)

        self.ClearBitMask(self.CommIrqReg, 0x80)

        self.SetBitMask(self.FIFOLevelReg, 0x80)



        self.Write_MFRC522(self.CommandReg, self.PCD_IDLE)



        for i in range(len(sendData)):

            self.Write_MFRC522(self.FIFODataReg, sendData[i])



        self.Write_MFRC522(self.CommandReg, command)



        if command == self.PCD_TRANSCEIVE:

            self.SetBitMask(self.BitFramingReg, 0x80)



        i = 2000

        while True:

            n = self.Read_MFRC522(self.CommIrqReg)

            i -= 1

            if ~((i != 0) and ~(n & 0x01) and ~(n & waitIRq)):

                break



        self.ClearBitMask(self.BitFramingReg, 0x80)



        if i != 0:

            if (self.Read_MFRC522(self.ErrorReg) & 0x1B) == 0x00:

                status = self.MI_OK



                if n & irqEn & 0x01:

                    status = self.MI_NOTAGERR



                if command == self.PCD_TRANSCEIVE:

                    n = self.Read_MFRC522(self.FIFOLevelReg)

                    lastBits = self.Read_MFRC522(self.ControlReg) & 0x07

                    if lastBits != 0:

                        backLen = (n - 1) * 8 + lastBits

                    else:

                        backLen = n * 8



                    if n == 0:

                        n = 1

                    if n > self.MAX_LEN:

                        n = self.MAX_LEN



                    for i in range(n):

                        backData.append(self.Read_MFRC522(self.FIFODataReg))

            else:

                status = self.MI_ERR



        return (status, backData, backLen)



    def MFRC522_Request(self, reqMode):

        status = None

        backBits = None

        TagType = []



        self.Write_MFRC522(self.BitFramingReg, 0x07)



        TagType.append(reqMode)

        (status, backData, backBits) = self.MFRC522_ToCard(self.PCD_TRANSCEIVE, TagType)



        if ((status != self.MI_OK) | (backBits != 0x10)):

            status = self.MI_ERR



        return (status, backBits)



    def MFRC522_Anticoll(self):

        backData = []

        serNumCheck = 0



        serNum = []



        self.Write_MFRC522(self.BitFramingReg, 0x00)



        serNum.append(self.PICC_ANTICOLL)

        serNum.append(0x20)



        (status, backData, backBits) = self.MFRC522_ToCard(self.PCD_TRANSCEIVE, serNum)



        if (status == self.MI_OK):

            if len(backData) == 5:

                for i in range(4):

                    serNumCheck = serNumCheck ^ backData[i]

                if serNumCheck != backData[4]:

                    status = self.MI_ERR

            else:

                status = self.MI_ERR



        return (status, backData)



    def MFRC522_Init(self):

        self.MFRC522_Reset()

        

        self.Write_MFRC522(self.TModeReg, 0x8D)

        self.Write_MFRC522(self.TPrescalerReg, 0x3E)

        self.Write_MFRC522(self.TReloadRegL, 30)

        self.Write_MFRC522(self.TReloadRegH, 0)

        

        self.Write_MFRC522(self.TxAutoReg, 0x40)

        self.Write_MFRC522(self.ModeReg, 0x3D)

        self.AntennaOn()



    # Alias methods to match original library

    def Request(self, reqMode):

        return self.MFRC522_Request(reqMode)

    

    def Anticoll(self):

        return self.MFRC522_Anticoll()



# ----------------- MAIN PROGRAM -----------------



# Initialize RFID reader and MQTT client

reader = MFRC522_Pi5()

mqtt_publisher = setup_mqtt()

print("RFID Reader Ready. Tap a card to make payment.")

last_read_time = 0



try:

    while True:

        (status, TagType) = reader.Request(reader.PICC_REQIDL)

        

        if status == reader.MI_OK:

            (status, uid) = reader.Anticoll()

            

            if status == reader.MI_OK:

                # Convert UID list to a readable hex string

                tag_id_hex = "".join([f"{i:02X}" for i in uid])

                

                # Simple debounce to prevent multiple triggers from one tap

                if time.time() - last_read_time > 1.0:

                    print(f"Payment successful! Tag ID: {tag_id_hex}")

                    

                    # --- MQTT PUBLISHING: Send signal to the main app ---

                    if mqtt_publisher:

                        # Payload format: PAYMENT_COMPLETE:<TAG_ID_HEX>

                        mqtt_publisher.publish(

                            CHECKOUT_TOPIC, 

                            f"PAYMENT_COMPLETE:{tag_id_hex}", 

                            qos=1

                        )

                        print(f"Published checkout signal to {CHECKOUT_TOPIC}")

                    # ----------------------------------------------------

                    

                    last_read_time = time.time()

                    

        time.sleep(0.1)



except KeyboardInterrupt:

    print("Program stopped by user")



finally:

    if mqtt_publisher:

        mqtt_publisher.loop_stop()

        mqtt_publisher.disconnect()

    

    # NOTE: You should ensure RPi.GPIO or gpiozero cleanup is handled correctly for your setup

    # GPIO.cleanup() # Uncomment if you need explicit RPi.GPIO cleanup

    print("Cleanup complete.")