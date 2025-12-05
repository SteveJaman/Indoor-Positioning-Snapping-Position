import paho.mqtt.client as mqtt
import time
import json
from PIL import Image
import numpy as np
import threading
import os
from datetime import datetime

# Kivy imports
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Ellipse, Triangle, Line, RoundedRectangle
from kivy.clock import Clock
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.core.window import Window
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

from kivy.config import Config
Config.set('input', 'mouse', 'mouse, disable_on_activity')
Config.write()

# RFID imports
import sys
sys.path.append('/usr/lib/python3/dist-packages')
# import spidev
# from gpiozero import DigitalOutputDevice

# ----------------- RFID READER CLASS -----------------
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
    TReloadRegL = 0x2C
    TReloadRegH = 0x2D
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

# ----------------- CONFIGURATION -----------------
MQTT_BROKER = "192.168.137.8"
MQTT_POSITION_TOPIC = "indoor/position"
MQTT_CLIENT_TOPIC = "indoor/client"
CLIENT_ID = "Position_Visualizer_Client"
MQTT_ITEM_TOPIC = "indoor/items"

# Proximity Check Configuration
PROXIMITY_THRESHOLD = 0.3
total_items_count = 0
# map and grid parameters
MAP_SIZE = 7.0
GRID_SIZE = 1.0
# beacon locations
BEACONS = [
    (0.0, 0.0, "B1"),
    (7.0, 0.0, "B2"),
    (0.0, 7.0, "B3"),
    (7.0, 7.0, "B4")
]

# item locations (will be populated from MQTT)
ITEMS = []

# store references to plotted item markers and labels
item_markers = []
item_labels = []

# shared variables
current_position = [0.5, 0.5]
last_update_time = time.time()
last_item_update_time = 0
items_loaded = False

# defined forbidden positions so that the items are not marked in odd positions
FORBIDDEN_POSITIONS = [
    (1.5, 1.5), (1.5, 2.5), (1.5, 3.5), (1.5, 4.5), (1.5, 5.5),
    (3.5, 1.5), (3.5, 2.5), (3.5, 3.5), (3.5, 4.5), (3.5, 5.5),
    (5.5, 1.5), (5.5, 2.5), (5.5, 3.5), (5.5, 4.5), (5.5, 5.5)
]

# ----------------- MQTT CALLBACKS ----------------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT Connected successfully.")
        print(f"Subscribed to: {MQTT_POSITION_TOPIC}, {MQTT_ITEM_TOPIC}")
        client.subscribe(MQTT_POSITION_TOPIC)
        client.subscribe(MQTT_ITEM_TOPIC)
    else:
        print(f"Connection failed with result code {rc}")

def is_valid_position(x, y):
    # checking the validity of the position
    for forbidden_x, forbidden_y in FORBIDDEN_POSITIONS:
        if abs(x - forbidden_x) < 0.1 and abs(y - forbidden_y) < 0.1:
            return False
    return True

def on_message_position(client, userdata, msg):
    global current_position, last_update_time
    try:
        payload = msg.payload.decode().strip()
        parts = payload.split(',')

        if len(parts) < 2:
            raise ValueError(f"Incomplete payload: {payload}")

        new_x = float(parts[0])
        new_y = float(parts[1])

        # checking if the position is not apart of the forbidden list
        if is_valid_position(new_x, new_y):
            current_position[0] = new_x
            current_position[1] = new_y
            last_update_time = time.time()
            print(f" POSITION UPDATE: ({new_x:.2f}, {new_y:.2f})")
        else:
            print(f"Received Invalid Position (filtered out): X={new_x:.2f}, Y={new_y:.2f}")
    except Exception as e:
        print(f"Error parsing POSITION MQTT payload: {e}")

def on_message_items(client, userdata, msg):
    global ITEMS, last_item_update_time, items_loaded, total_items_count
    try:
        payload = msg.payload.decode().strip()
        print(f" RAW ITEM MESSAGE: {payload}")  # DEBUG

        data = json.loads(payload)
        if data.get("type") == "items_update":
            new_items = []
            for item in data["items"]:
                x = item["x"]
                y = item["y"]
                name = item["name"]
                new_items.append((x, y, name))
                print(f" Loaded/Updated item: {name} at ({x}, {y}) - Types: {type(x)}, {type(y)}")  # DEBUG

            ITEMS.clear()
            ITEMS.extend(new_items)
            total_items_count = len(ITEMS)
            last_item_update_time = time.time()
            items_loaded = True
            print(f" Received {len(ITEMS)} items from server")
            print(f"Items: {[name for _, _, name in ITEMS]}")

    except json.JSONDecodeError as e:
        print(f" Error parsing ITEMS MQTT JSON: {e}")
    except Exception as e:
        print(f" Error processing ITEMS MQTT message: {e}")

# ----------------- SEARCH FUNCTIONALITY -----------------
class VirtualKeyboard(BoxLayout):
    def __init__(self, search_input, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = 5
        self.size_hint_y = None
        self.height = 415
        self.search_input = search_input

        self.caps_enabled = False
        self.shift_mode = "off"
        
        with self.canvas.before:
            Color(0.4509, 0.4705, 0.5, 1)
            self.keyboard_bg = RoundedRectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_keyboard_bg, size=self.update_keyboard_bg)

        keys_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
            ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
            ['z', 'x', 'c', 'v', 'b', 'n', 'm', '@', '.', '_'],
            ['CAPS', 'CLEAR', 'SPACE', 'DELETE']
        ]

        for row_keys in keys_layout:
            row_layout = BoxLayout(
                orientation='horizontal',
                spacing=7,
                size_hint_y=None,
                height=80
            )

            for key in row_keys:
                if key in ['CLEAR', 'SPACE', 'DELETE']:
                    size_hint_x = 2.5
                else:
                    size_hint_x = 1.0

                btn = Button(
                    text=key,
                    size_hint_x=size_hint_x,
                    size_hint_y=None,
                    background_normal='',
                    height=70,
                    background_color=(0.8, 0.831, 0.85490, 0.65),
                    color=(0, 0, 0, 1),
                    font_size='20sp'
                )
                btn.bind(on_press=self.on_key_press)
                row_layout.add_widget(btn)

            self.add_widget(row_layout)

    def update_keyboard_bg(self, *args):
        self.keyboard_bg.pos = self.pos
        self.keyboard_bg.size = self.size

    def on_key_press(self, instance):
        key = instance.text
        
        if key == 'CAPS':
            self.caps_enabled = not self.caps_enabled
            self.rebuild_keyboard()
        elif key == 'DELETE':
            self.search_input.text = self.search_input.text[:-1]
        elif key == 'CLEAR':
            self.search_input.text = ''
        elif key == 'SPACE':
            self.search_input.text += ' '
        else:
            self.search_input.text += key

    def rebuild_keyboard(self):
        # Remove all existing widgets
        self.clear_widgets()

        # Recreate key layout with caps applied
        keys_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M', '@', '.', '_'],
            ['CAPS', 'CLEAR', 'SPACE', 'DELETE']
        ]

        # Lowercase if caps is OFF
        if not self.caps_enabled:
            for r in range(1, 5):  # only letter rows
                keys_layout[r] = [k.lower() if len(k) == 1 else k for k in keys_layout[r]]

        # Rebuild the widgets
        for row_keys in keys_layout:
            row_layout = BoxLayout(
                orientation='horizontal',
                spacing=7,
                size_hint_y=None,
                height=80
            )

            for key in row_keys:
                if key in ['CLEAR', 'SPACE', 'DELETE']:
                    size_hint_x = 2.5
                else:
                    size_hint_x = 1.0

                btn = Button(
                    text=key,
                    size_hint_x=size_hint_x,
                    size_hint_y=None,
                    background_normal='',
                    height=70,
                    background_color=(0.8, 0.831, 0.85490, 0.65),
                    color=(0, 0, 0, 1),
                    font_size='20sp'
                )
                btn.bind(on_press=self.on_key_press)
                row_layout.add_widget(btn)

            self.add_widget(row_layout)


class ProductCard(BoxLayout):
    def __init__(self, name, price, quantity, barcode, search_app=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 80
        self.padding = 10
        self.spacing = 15
        self.name = name
        self.barcode = barcode
        self.search_app = search_app

        with self.canvas.before:
            Color(0, 0, 0, 1)
            self.outline_rect = RoundedRectangle(
                pos=(self.pos[0] - 1, self.pos[1] - 1),
                size=(self.size[0] + 2, self.size[1] + 2),
                radius=[10]
            )

            Color(0.8901, 0.94901, 1, 0.86)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])

        self.bind(pos=self.update_rect, size=self.update_rect)

        # Name label
        name_label = Label(
            text=name,
            size_hint_x=0.8,
            font_size='24sp',
            halign='left',
            valign='middle',
            padding_x=20,
            color='black'
        )
        name_label.bind(
            width=lambda *x: name_label.setter('text_size')(name_label, (name_label.width, None))
        )
        self.add_widget(name_label)

        # PIN button only
        action_btn = Button(
            text='PIN',
            bold=True,
            font_size='20sp',
            size_hint_x=0.25,
            background_normal='',
            background_color=(1, 0, 0.176, 0.3),
            color='black'
        )

        with action_btn.canvas.before:
            Color(1, 0.533, 0.6235, 1)
            action_btn.rect = RoundedRectangle(
                pos=action_btn.pos,
                size=action_btn.size,
                radius=[15]
            )

        action_btn.bind(pos=self.update_button_rect, size=self.update_button_rect)
        action_btn.bind(on_press=self.on_pin_pressed)
        self.add_widget(action_btn)

    def update_rect(self, *args):
        self.outline_rect.pos = (self.pos[0] - 1, self.pos[1] - 1)
        self.outline_rect.size = (self.size[0] + 2, self.size[1] + 2)
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def update_button_rect(self, button, *args):
        button.rect.pos = button.pos
        button.rect.size = button.size

    def on_pin_pressed(self, instance):
        """Handle PIN button press - send notification to server"""
        print(f" PIN pressed for: {self.name} (Barcode: {self.barcode})")

        if self.search_app:
            if self.search_app.main_app and self.search_app.main_app.is_item_already_pinned(self.name):
                self.search_app.main_app.show_already_pinned_warning(self.name)
                return

            notification_message = f"PIN_ITEM:{self.name}:{self.barcode}"
            response = self.search_app.send_command(notification_message)
            print(f" PIN notification sent: {notification_message}")
            print(f" Server response: {response}")

            if "ITEM_PINNED:" in response:
                if ':' in response:
                    actual_response = response.split(':', 1)[1]
                else:
                    actual_response = response

                parts = actual_response.split(":")
                if len(parts) >= 4 and parts[2] == "SUCCESS":
                    location_str = parts[3]
                    try:
                        coords_str = location_str.replace("Location(", "").replace(")", "")
                        x_str, y_str = coords_str.split(",")
                        x = float(x_str.strip())
                        y = float(y_str.strip())
                        print(f" Server provided location: ({x}, {y})")

                        if hasattr(self.search_app, 'main_app') and self.search_app.main_app:
                            self.search_app.main_app.display_pinned_item_locally(self.name, x, y)
                    except Exception as e:
                        print(f" Error parsing location: {e}")
                else:
                    print(f" PIN failed: {actual_response}")
            else:
                print(f" Unexpected response format: {response}")
        else:
            print(" Cannot send PIN notification: No search app reference")

class ShoppingSearchApp(BoxLayout):
    def __init__(self, main_app=None, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 10
        self.spacing = 8
        self.host = 'localhost'
        self.port = 1883
        self.mqtt_client = None
        self.all_products = []
        self.popup = None
        self.response_received = threading.Event()
        self.last_response = None
        self.client_id = f"search_client_{time.time()}"
        self.main_app = main_app
        self.has_searched = False

        print(" Search function initialized")
        self.create_widgets()
        self.load_all_products()

    def create_widgets(self):
        # header with exit button
        header_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=50,
            padding=[10, 5, 10, 5]
        )
        header_layout.add_widget(Label(size_hint_x=0.7))

        exit_button = Button(
            text='Exit to Map',
            size_hint_y=2,
            size_hint_x=0.15,
            background_normal='',
            background_color=(1, 0, 0.176, 0.3),
            color=(1, 1, 1, 1),
            font_size='16sp',
            bold=True
        )
        exit_button.bind(on_press=self.exit_to_map)
        header_layout.add_widget(exit_button)

        self.add_widget(header_layout)

        # Search bar
        search_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=10)

        self.search_input = TextInput(
            hint_text='Type to search products...',
            font_size='20sp',
            size_hint_x=0.8,
            multiline=False,
            background_normal='',
            background_color=(0.8745, 0.90196, 0.9294, 0.79)
        )
        self.search_input.bind(text=self.on_search_text)
        search_layout.add_widget(self.search_input)

        self.add_widget(search_layout)

        self.results_label = Label(
            size_hint_y=None,
            height=25,
            color=(0, 0, 0, 1)
        )
        self.add_widget(self.results_label)

        # Products scroll view
        self.scroll_view = ScrollView()
        self.products_layout = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=15,
            padding=5
        )
        self.products_layout.bind(minimum_height=self.products_layout.setter('height'))
        self.scroll_view.add_widget(self.products_layout)
        self.add_widget(self.scroll_view)

        # Virtual Keyboard
        self.keyboard = VirtualKeyboard(self.search_input)
        self.add_widget(self.keyboard)

    def exit_to_map(self, instance):
        if self.popup:
            self.popup.dismiss()
        else:
            for widget in self.walk():
                if isinstance(widget, Popup):
                    widget.dismiss()
                    break

    def connect_to_server(self):
        try:
            print(f" Connecting to MQTT broker at {self.host}:{self.port}")
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
            self.mqtt_client.on_connect = self.on_connect
            self.mqtt_client.on_message = self.on_message
            self.mqtt_client.connect(self.host, self.port, 60)
            self.mqtt_client.loop_start()

            time.sleep(2)
            return self.mqtt_client.is_connected()
        except Exception as e:
            print(f" MQTT connection error: {e}")
            return False

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(" Connected to MQTT broker")
            client.subscribe("shopping_app/responses")
        else:
            print(f" Failed to connect, return code {rc}")

    def on_message(self, client, userdata, msg):
        print(f" Received response: {msg.payload.decode()}")
        self.last_response = msg.payload.decode()
        self.response_received.set()

    def send_command(self, command):
        try:
            if not self.mqtt_client:
                if not self.connect_to_server():
                    return "ERROR: Cannot connect to MQTT broker"

            self.response_received.clear()
            self.last_response = None

            full_command = f"{self.client_id}:{command}"
            print(f" Sending command: {full_command}")
            self.mqtt_client.publish("shopping_app/commands", full_command)

            if self.response_received.wait(timeout=5.0):
                return self.last_response
            else:
                return "ERROR: No response from server"

        except Exception as e:
            self.mqtt_client = None
            return f"ERROR: {str(e)}"

    def load_all_products(self):
        print(" Loading all products...")
        threading.Thread(target=self.fetch_all_products, daemon=True).start()

    def fetch_all_products(self):
        print(" Fetching products from server...")

        stock_response = self.send_command("STOCK")
        prices_response = self.send_command("PRICES")

        print(f" Stock response: {stock_response}")
        print(f" Prices response: {prices_response}")

        if ":" in stock_response and ":" in prices_response:
            products = []
            stock_data = {}

            def strip_client_id(response):
                if ':' in response:
                    return response.split(':', 1)[1]
                return response

            stock_clean = strip_client_id(stock_response)
            prices_clean = strip_client_id(prices_response)

            # Parse stock data
            for line in stock_clean.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        item = parts[0].strip()
                        qty = parts[1].strip()
                        stock_data[item] = qty
                    else:
                        print(f"  Skipping invalid stock line: {line}")

            # Parse prices data
            for line in prices_clean.split('\n'):
                line = line.strip()
                if line and ':' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        item = parts[0].strip()
                        price = parts[1].strip()
                        if item in stock_data:
                            barcode_response = self.send_command(f"GET_BARCODE:{item}")
                            print(f" Barcode for {item}: {barcode_response}")
                            barcode = "N/A"
                            if barcode_response.startswith("BARCODE:"):
                                barcode_parts = barcode_response.split(':')
                                if len(barcode_parts) >= 3:
                                    barcode = barcode_parts[2]
                                else:
                                    barcode = "N/A"

                            products.append({
                                'name': item,
                                'price': price,
                                'quantity': stock_data[item],
                                'barcode': barcode
                            })
                    else:
                        print(f"  Skipping invalid price line: {line}")

            Clock.schedule_once(lambda dt: self.set_all_products(products))
        else:
            print(" Error fetching products")
            Clock.schedule_once(lambda dt: setattr(self.results_label, 'text', "Error loading products from server"))

    def set_all_products(self, products):
        self.all_products = products
        print(f" Loaded {len(products)} products into memory")

    def on_search_text(self, instance, value):
        if not self.has_searched and len(value) > 0:
            self.has_searched = True

        if len(value) >= 1:
            self.filter_products(value)
        elif len(value) == 0 and self.has_searched:
            self.display_products([])
        elif len(value) == 0:
            self.products_layout.clear_widgets()

    def filter_products(self, query):
        filtered = []
        query_lower = query.lower()

        for product in self.all_products:
            name_match = query_lower in product['name'].lower()
            barcode_match = query_lower in product['barcode'].lower()
            
            if name_match or barcode_match:
                filtered.append(product)
            #if (query_lower in product['name'].lower() or
            #        query_lower in product['barcode'].lower()):
            #    filtered.append(product)

        self.display_products(filtered)

    def display_products(self, products):
        self.products_layout.clear_widgets()

        if not products:
            if self.has_searched:
                self.results_label.text = ""
            return

        for product in products:
            card = ProductCard(
                name=product['name'],
                price=product['price'],
                quantity=product['quantity'],
                barcode=product['barcode'],
                search_app=self
            )
            self.products_layout.add_widget(card)

# ----------------- CHECKOUT FUNCTIONALITY -----------------
def generate_pdf_receipt(cart_items, total, filename="CyberKart_Receipt.pdf"):
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter
    y = height - 60

    # Header
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, y, "CyberKart")
    y -= 30

    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, y, "Kennesaw State University")
    y -= 15
    c.drawCentredString(width / 2, y, "1100 S Marietta Pkwy SE, Marietta, GA 30060")
    y -= 15
    c.drawCentredString(width / 2, y, "Phone: (470) 578-6000")
    y -= 30

    # Transaction Info
    now = datetime.now().strftime("%m/%d/%y   Time %I:%M %p")
    transaction_num = f"Trans {int(datetime.now().timestamp()) % 10000}"
    c.setFont("Helvetica", 11)
    c.drawString(80, y, f"{transaction_num}     Date {now}")
    y -= 30

    # Column Headers
    c.setFont("Helvetica-Bold", 12)
    c.drawString(80, y, "Item")
    c.drawString(300, y, "Qty")
    c.drawString(360, y, "Price")
    c.drawString(430, y, "Amount")
    y -= 15
    c.line(70, y, 520, y)
    y -= 20

    # Item List
    c.setFont("Helvetica", 11)
    for item in cart_items:
        item_name = item['name']
        qty = str(item['quantity'])
        price = f"${item['price']:.2f}"
        amount = f"${item['price'] * item['quantity']:.2f}"

        c.drawString(80, y, item_name)
        c.drawString(310, y, qty)
        c.drawString(365, y, price)
        c.drawString(435, y, amount)
        y -= 18

        if y < 100:
            c.showPage()
            y = height - 100

    y -= 10
    c.line(70, y, 520, y)
    y -= 25

    # Totals
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(510, y, f"Total: ${total:.2f}")
    y -= 40

    # Payment Info
    c.setFont("Helvetica", 11)
    c.drawString(80, y, "Payment Method: VISA **** 1234")
    y -= 15
    c.drawString(80, y, f"Transaction Type: Sale")
    y -= 15
    c.drawString(80, y, f"Entry Method: Contactless")
    y -= 15
    c.drawString(80, y, f"Auth Time: {datetime.now().strftime('%I:%M %p')}")
    y -= 15
    c.drawString(80, y, f"Trace Number: 46640501")
    y -= 30

    # Footer
    c.setFont("Helvetica-Oblique", 11)
    c.drawCentredString(width / 2, y, "Thank you for shopping with CyberKart!")
    y -= 20
    c.drawCentredString(width / 2, y, "Please come again.")

    c.showPage()
    c.save()
    return os.path.abspath(filename)


class CartItem(BoxLayout):
    def __init__(self, item_data, remove_callback, add_callback, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(70)
        self.spacing = dp(10)
        self.padding = [dp(10), dp(5)]

        self.item_data = item_data
        self.remove_callback = remove_callback
        self.add_callback = add_callback

        # Create the light blue background with black border
        with self.canvas.before:
            #NO Border color
            Color(0, 0, 0, 0)
            self.outline_rect = RoundedRectangle(
                pos=(self.pos[0] - 1, self.pos[1] - 1),
                size=(self.size[0] + 2, self.size[1] + 2),
                radius=[dp(10)]
            )

            # Light blue background (matching old ProductCard)
            Color(1,1,1,1)  # Light blue with transparency
            self.bg_rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(10)]
            )

        self.bind(pos=self.update_rect, size=self.update_rect)
        self.setup_ui()

    def update_rect(self, *args):
        """Update the background rectangles when widget moves/resizes"""
        # Update border rectangle
        self.outline_rect.pos = (self.pos[0] - 1, self.pos[1] - 1)
        self.outline_rect.size = (self.size[0] + 2, self.size[1] + 2)

        # Update background rectangle
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def setup_ui(self):
        # Product info layout
        info_layout = BoxLayout(orientation='vertical', size_hint_x=0.5, spacing=dp(2))

        name_label = Label(
            text=self.item_data['name'],
            size_hint_y=0.6,
            halign='left',
            valign='middle',
            text_size=(None, None),
            color=(0, 0, 0, 1),  # Black text
            font_size='20sp',
            bold=True
        )
        name_label.bind(
            width=lambda *x: name_label.setter('text_size')(name_label, (name_label.width, None))
        )

        price_label = Label(
            text=f"${self.item_data['price']:.2f}",
            size_hint_y=0.4,
            color=(0.3, 0.3, 0.3, 1),  # Dark gray text
            font_size='20sp'
        )

        info_layout.add_widget(name_label)
        info_layout.add_widget(price_label)

        # Quantity layout
        qty_layout = BoxLayout(orientation='vertical', size_hint_x=0.2, spacing=dp(2))

        qty_label = Label(
            text=f"Qty: {self.item_data['quantity']}",
            size_hint_y=0.5,
            color=(0.2, 0.4, 0.6, 1),  # Blue text
            font_size='20sp'
        )

        total_label = Label(
            text=f"${self.item_data['price'] * self.item_data['quantity']:.2f}",
            size_hint_y=0.5,
            color=(0.1, 0.6, 0.3, 1),  # Green text
            font_size='20sp',
            bold=True
        )

        qty_layout.add_widget(qty_label)
        qty_layout.add_widget(total_label)

        # Button layout
        button_layout = BoxLayout(
            orientation='horizontal',
            size_hint_x=0.3,
            spacing=dp(5)
        )

        remove_btn = Button(
            text="-",
            background_color=(0.9, 0.3, 0.3, 1),  # Red button
            color=(1, 1, 1, 1),  # White text
            background_normal='',
            font_size='60sp',
            size_hint_x=0.5
        )
        remove_btn.bind(on_press=self.remove_item)

        add_btn = Button(
            text="+",
            background_color=(0.3, 0.8, 0.3, 1),  # Green button
            color=(1, 1, 1, 1),  # White text
            background_normal='',
            font_size='40sp',
            size_hint_x=0.5
        )
        add_btn.bind(on_press=self.add_item)

        button_layout.add_widget(remove_btn)
        button_layout.add_widget(add_btn)

        self.add_widget(info_layout)
        self.add_widget(qty_layout)
        self.add_widget(button_layout)

    def remove_item(self, instance):
        self.remove_callback(self.item_data['barcode'])

    def add_item(self, instance):
        self.add_callback(self.item_data['barcode'])

class ShoppingCartApp(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = dp(10)
        self.padding = [dp(15), dp(15)]

        # Add background color to the entire checkout section
        with self.canvas.before:
            Color(0.8901, 0.94901, 1, 0.86)  # Light gray background
            self.background_rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self.update_background, size=self.update_background)

        # MQTT Configuration
        self.MQTT_BROKER = "192.168.137.8"
        self.MQTT_PORT = 1883
        self.MQTT_COMMANDS_TOPIC = "shopping_app/commands"
        self.MQTT_RESPONSES_TOPIC = "shopping_app/responses"
        self.CLIENT_ID = f"checkout_client_{int(time.time())}"

        # MQTT Client
        self.mqtt_client = None
        self.connected = False

        # PDF generation after checkout
        self.pending_cart_items = []
        self.pending_total = 0.0

        # Store products from server
        self.server_products = {}

        # RFID payment functionality
        self._cancel_event = None
        self.rfid_reader = None
        self._last_rfid_read_time = 0
        self._rfid_debounce_sec = 1.0

        self.cart_items = []
        self.setup_mqtt()
        self.setup_ui()
        self.initialize_rfid()

    def initialize_rfid(self):
        """Initialize the RFID reader"""
        try:
            print(" Initializing RFID reader...")
            self.rfid_reader = MFRC522_Pi5()
            print(" RFID Reader initialized successfully")
        except Exception as e:
            print(f" Failed to initialize RFID reader: {e}")
            self.rfid_reader = None

    def setup_mqtt(self):
        self.mqtt_client = mqtt.Client(client_id=self.CLIENT_ID)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message

        try:
            self.mqtt_client.connect(self.MQTT_BROKER, self.MQTT_PORT, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            print(f"MQTT Connection failed: {e}")

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe(self.MQTT_RESPONSES_TOPIC)
            client.subscribe("indoor/checkout") # Subscribe to RFID payments
            print("Connected to MQTT and subscribed to RFID payments")
        else:
            print(f"Failed to connect to MQTT, return code {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            
            print(f"MQTT Message received - Topic: {topic}, Payload: {payload}")
            
            if topic == self.MQTT_RESPONSES_TOPIC:
                if ':' in payload:
                    client_id, response = payload.split(':', 1)
                    if client_id == self.CLIENT_ID or client_id == "default":
                        Clock.schedule_once(lambda dt: self.process_server_response(response), 0)
                else:
                    Clock.schedule_once(lambda dt: self.process_server_response(payload), 0)

            # Handle RFID payment messages
            elif topic == "indoor/checkout":
                if payload.startswith("PAYMENT_COMPLETE:"):
                    tag_id = payload.replace("PAYMENT_COMPLETE:", "").strip()
                    print(f"RFID Payment detected via MQTT! Tag ID: {tag_id}")
                    Clock.schedule_once(lambda dt: self._handle_rfid_payment(tag_id), 0)
                    
        except Exception as e:
            print(f"Error processing MQTT message: {e}")

    def _handle_rfid_payment(self, tag_id):
        # Handle RFID payment received via MQTT
        if not hasattr(self, 'payment_popup') or not self.payment_popup:
            print(" Received RFID payment but no payment popup is open")
            return
            
        # Update the status label in the payment popup
        if hasattr(self, 'rfid_status_label'):
            Clock.schedule_once(lambda dt: setattr(
                self.rfid_status_label, 'text', 
                f"Payment successful! Tag ID: {tag_id}"
            ), 0)
        # Process the payment
        Clock.schedule_once(lambda dt: self._payment_success(tag_id), 0)
    
    def process_server_response(self, response):
        if response.startswith("ERROR:"):
            error_msg = response.replace("ERROR:", "").strip()
            self.show_error_popup(f"Error: {error_msg}")

        elif response.startswith("ITEM:"):
            parts = response.split(":")
            if len(parts) >= 4:
                barcode = parts[1]
                item_name = parts[2]
                price = float(parts[3])

                self.server_products[barcode] = {
                    "name": item_name,
                    "price": price
                }

                self.add_to_cart_from_server(barcode, item_name, price)

    def send_command(self, command):
        if self.mqtt_client and self.connected:
            full_command = f"{self.CLIENT_ID}:{command}"
            self.mqtt_client.publish(self.MQTT_COMMANDS_TOPIC, full_command)
        else:
            self.show_error_popup("Not connected to server")

    def show_error_popup(self, message):
        def show_popup(dt):
            content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
            content.add_widget(Label(text=message))
            close_btn = Button(text='Close', size_hint_y=None, height=dp(50))
            popup = Popup(
                title='Error',
                content=content,
                size_hint=(0.6, 0.3)
            )
            close_btn.bind(on_press=popup.dismiss)
            content.add_widget(close_btn)
            popup.open()

        Clock.schedule_once(show_popup, 0)

    def setup_ui(self):
        self.barcode_input = TextInput(
            size_hint_y=None,
            height=dp(50),
            multiline=False,
            hint_text="Scan barcode here...",
            font_size='20sp',
            padding=[dp(15), dp(15)]
        )
        self.barcode_input.bind(on_text_validate=self.process_barcode)
        self.add_widget(self.barcode_input)

        self.scroll_view = ScrollView()
        self.cart_items_layout = GridLayout(
            cols=1,
            size_hint_y=None,
            spacing=dp(8)
        )
        self.cart_items_layout.bind(minimum_height=self.cart_items_layout.setter('height'))
        self.scroll_view.add_widget(self.cart_items_layout)
        self.add_widget(self.scroll_view)

        action_layout = BoxLayout(
            size_hint_y=None,
            height=dp(50),
            spacing=dp(10)
        )

        self.total_label = Label(
            text="Total: $0.00",
            size_hint_x=0.4,
            font_size='30sp',
            bold=True,
            color="black"
        )

        clear_btn = Button(
            text="Clear",
            size_hint_x=0.3,
            font_size='30sp',
            background_color=(0.8, 0.3, 0.3, 1),
            background_normal=''
        )
        clear_btn.bind(on_press=self.assurance)

        checkout_btn = Button(
            text="Checkout",
            size_hint_x=0.3,
            font_size='30sp',
            background_color=(0.2, 0.7, 0.3, 1),
            background_normal=''
        )
        checkout_btn.bind(on_press=self.checkout)

        action_layout.add_widget(self.total_label)
        action_layout.add_widget(clear_btn)
        action_layout.add_widget(checkout_btn)

        self.add_widget(action_layout)

    def assurance(self, instance):
        content = BoxLayout(
            orientation='vertical',
            spacing=dp(15),
            padding=[dp(20), dp(15), dp(20), dp(15)]
        )

        message_label = Label(
            text="Are you sure you want to clear your entire cart?",
            font_size='25sp',
            halign='center',
            valign='middle',
            text_size=(dp(280), None),
            size_hint_y=None,
            height=dp(40),
            color=(0.2, 0.2, 0.2, 1)
        )
        content.add_widget(message_label)

        warning_label = Label(
            text="This action cannot be undone",
            font_size='20sp',
            halign='center',
            color=(0.6, 0.2, 0.2, 1),
            italic=True,
            size_hint_y=None,
            height=dp(30)
        )
        content.add_widget(warning_label)

        btn_layout = BoxLayout(
            spacing=dp(15),
            size_hint_y=None,
            height=dp(50)
        )

        no_btn = Button(
            text="Cancel",
            background_color=(0.5, 0.5, 0.5, 1),
            background_normal='',
            font_size='25sp',
            color=(1, 1, 1, 1)
        )
        no_btn.bind(on_press=lambda x: self.confirmation_popup.dismiss())

        yes_btn = Button(
            text="Clear Cart",
            background_color=(0.8, 0.2, 0.2, 1),
            background_normal='',
            font_size='25sp',
            color=(1, 1, 1, 1)
        )
        yes_btn.bind(on_press=self.clear_cart)

        btn_layout.add_widget(no_btn)
        btn_layout.add_widget(yes_btn)
        content.add_widget(btn_layout)

        self.confirmation_popup = Popup(
            title='Clear Cart',
            title_size='16sp',
            title_align='center',
            content=content,
            size_hint=(0.75, 0.4),
            auto_dismiss=False,
            separator_color=(0.8, 0.2, 0.2, 1),
            background=''
        )

        no_btn.bind(on_press=lambda x: self.confirmation_popup.dismiss())
        yes_btn.bind(on_press=lambda x: self.confirmation_popup.dismiss())

        self.confirmation_popup.open()

    def process_barcode(self, instance):
        barcode = self.barcode_input.text.strip()
        if barcode:
            self.send_command(f"GET_ITEM:{barcode}")
            self.barcode_input.text = ""

    def add_to_cart_from_server(self, barcode, name, price):
        item_found = False
        for item in self.cart_items:
            if item['barcode'] == barcode:
                item['quantity'] += 1
                item_found = True
                break

        if not item_found:
            self.cart_items.append({
                'barcode': barcode,
                'name': name,
                'price': price,
                'quantity': 1
            })

        self.update_display()

    def update_display(self):
        self.cart_items_layout.clear_widgets()

        if not self.cart_items:
            empty_label = Label(
                text="Cart is empty. Scan items to add them.",
                size_hint_y=None,
                height=dp(80),
                color=(0.5, 0.5, 0.5, 1)
            )
            self.cart_items_layout.add_widget(empty_label)
        else:
            for item in self.cart_items:
                cart_item_widget = CartItem(item, self.remove_item, self.add_item_quantity)
                self.cart_items_layout.add_widget(cart_item_widget)

        total = sum(item['price'] * item['quantity'] for item in self.cart_items)
        self.total_label.text = f"Total: ${total:.2f}"

    def remove_item(self, barcode):
        for item in self.cart_items:
            if item['barcode'] == barcode:
                if item['quantity'] > 1:
                    item['quantity'] -= 1
                else:
                    self.cart_items = [i for i in self.cart_items if i['barcode'] != barcode]
                break
        self.update_display()

    def add_item_quantity(self, barcode):
        for item in self.cart_items:
            if item['barcode'] == barcode:
                item['quantity'] += 1
                break
        self.update_display()

    # -------- checkout & payment ----------
    def checkout(self, instance):
        if not self.cart_items:
            content = BoxLayout(
                orientation='vertical',
                spacing=dp(15),
                padding=[dp(20), dp(15), dp(20), dp(15)]
            )

            message_label = Label(
                text="Your cart is empty",
                font_size='25sp',
                halign='center',
                valign='middle',
                text_size=(dp(280), None),
                size_hint_y=None,
                height=dp(40),
                color=(0.2, 0.2, 0.2, 1)
            )
            content.add_widget(message_label)

            info_label = Label(
                text="Please scan items before checkout",
                font_size='20sp',
                halign='center',
                color=(0.2, 0.4, 0.6, 1),
                italic=True,
                size_hint_y=None,
                height=dp(30)
            )
            content.add_widget(info_label)

            btn_layout = BoxLayout(
                spacing=dp(15),
                size_hint_y=None,
                height=dp(50)
            )

            ok_btn = Button(
                text="OK",
                background_color=(0.2, 0.6, 0.8, 1),
                background_normal='',
                font_size='25sp',
                color=(1, 1, 1, 1)
            )
            ok_btn.bind(on_press=lambda x: empty_cart_popup.dismiss())

            btn_layout.add_widget(ok_btn)
            content.add_widget(btn_layout)

            empty_cart_popup = Popup(
                title='',
                content=content,
                size_hint=(0.75, 0.35),
                auto_dismiss=False,
                separator_height=0,
                background=''
            )

            ok_btn.bind(on_press=lambda x: empty_cart_popup.dismiss())
            empty_cart_popup.open()
            return

        self._pending_total = sum(item['price'] * item['quantity'] for item in self.cart_items)
        self.pending_cart_items = self.cart_items.copy()
        
        # Create payment popup
        box = BoxLayout(orientation='vertical', spacing=dp(15), padding=dp(20))
        box.add_widget(Label(
            text=f"Total: ${self._pending_total:.2f}", 
            font_size='24sp',
            bold=True,
            color=(0, 0, 0, 1)
        ))
        
        # Add RFID status label
        self.rfid_status_label = Label(
            text="RFID Reader Ready. Tap a card to make payment.",
            font_size='16sp',
            color=(0.2, 0.4, 0.6, 1),
            size_hint_y=None,
            height=dp(40),
            text_size=(None, None),
            halign='center'
        )
        box.add_widget(self.rfid_status_label)
        
        # Add manual confirmation button for testing
        manual_btn = Button(
            text="Manual Confirm Payment", 
            size_hint_y=None, 
            height=dp(50),
            background_color=(0.8, 0.6, 0.2, 1),
            font_size='18sp'
        )
        manual_btn.bind(on_press=lambda x: self._manual_payment_confirm())
        box.add_widget(manual_btn)
        
        cancel_btn = Button(
            text="Cancel Payment", 
            size_hint_y=None, 
            height=dp(50),
            background_color=(0.8, 0.2, 0.2, 1),
            font_size='18sp'
        )
        box.add_widget(cancel_btn)
        
        self.payment_popup = Popup(
            title="Waiting for Payment",
            content=box, 
            size_hint=(0.8, 0.6),
            auto_dismiss=False
        )
        
        # Bind cancel button
        cancel_btn.bind(on_press=self._cancel_payment)
        
        self.payment_popup.open()
        
        # Start RFID detection in background
        self._cancel_event = threading.Event()
        threading.Thread(target=self._rfid_wait_thread, daemon=True).start()

    def _manual_payment_confirm(self):
        """Manual payment confirmation for testing"""
        print(" Manual payment confirmation triggered")
        self._payment_success("MANUAL_CONFIRMATION")

    def _rfid_wait_thread(self):
        """Background worker: wait for RFID tag using actual RFID reader"""
        try:
            print(" Waiting for RFID payment...")
            
            # Check if RFID reader is properly initialized
            if not self.rfid_reader:
                print(" RFID reader is not available - waiting for manual confirmation")
                return
            
            print(" RFID reader is available, starting detection...")
            
            # Wait for RFID with timeout
            start_time = time.time()
            
            while time.time() - start_time < 60:  # 60 second timeout
                if self._cancel_event and self._cancel_event.is_set():
                    print(" Payment cancelled by user")
                    Clock.schedule_once(lambda dt: self._payment_failed("cancelled"), 0)
                    return
                
                # Use the same detection logic as the working standalone code
                try:
                    # Request for tag - using PICC_REQIDL like the working code
                    (status, TagType) = self.rfid_reader.Request(self.rfid_reader.PICC_REQIDL)
                    
                    if status == self.rfid_reader.MI_OK:
                        print(" Card detected, reading UID...")
                        (status, uid) = self.rfid_reader.Anticoll()
                        
                        if status == self.rfid_reader.MI_OK:
                            current_time = time.time()
                            # Debounce check
                            if current_time - self._last_rfid_read_time >= self._rfid_debounce_sec:
                                tag_id_hex = "".join([f"{i:02X}" for i in uid])
                                print(f" RFID Payment successful! Tag ID: {tag_id_hex}")
                                self._last_rfid_read_time = current_time
                                
                                Clock.schedule_once(lambda dt: self._payment_success(tag_id_hex), 0)
                                break
                            else:
                                print(" Debouncing: ignoring duplicate read")
                        else:
                            print(" Could not read UID from card")
                    else:
                        # No card detected, continue waiting
                        pass
                        
                except Exception as e:
                    print(f"   RFID reading error: {e}")
                    # Continue trying despite errors
                    
                time.sleep(0.1)  # Small delay between detection attempts
                
            # Timeout reached
            print(" RFID payment timeout reached - still waiting for manual confirmation")
            
        except Exception as e:
            print(f" RFID thread error: {e}")

    def _cancel_payment(self, instance):
        if self._cancel_event:
            self._cancel_event.set()
        if getattr(self, "payment_popup", None):
            self.payment_popup.dismiss()
        
        # Show cancellation message
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
        content.add_widget(Label(text="Payment cancelled."))
        ok_btn = Button(text='OK', size_hint_y=None, height=dp(50))
        popup = Popup(
            title='Payment Cancelled',
            content=content,
            size_hint=(0.6, 0.3)
        )
        ok_btn.bind(on_press=popup.dismiss)
        content.add_widget(ok_btn)
        popup.open()

    def _payment_failed(self, msg):
        if getattr(self, "payment_popup", None):
            self.payment_popup.dismiss()
        
        # Show error message
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
        content.add_widget(Label(text=f"Payment failed: {msg}"))
        ok_btn = Button(text='OK', size_hint_y=None, height=dp(50))
        popup = Popup(
            title='Payment Error',
            content=content,
            size_hint=(0.6, 0.3)
        )
        ok_btn.bind(on_press=popup.dismiss)
        content.add_widget(ok_btn)
        popup.open()
    
    def _payment_success(self, tag_id):
        # 1. Dismiss initial payment method popup if it exists
        if getattr(self, "payment_popup", None):
            self.payment_popup.dismiss()

        # 2. Store cart items and total for receipt generation (BEFORE clearing)
        self.pending_cart_items = self.cart_items.copy()
        self.pending_total = getattr(self, "_pending_total", 0.0)

        # 3. Send checkout command to server
        checkout_items = [f"{item['barcode']}:{item['quantity']}" for item in self.cart_items]
        self.send_command("CHECKOUT " + " ".join(checkout_items))

        # 4. Show success message popup
        success_content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))

        if tag_id == "MANUAL_CONFIRMATION":
            success_content.add_widget(Label(text="Payment confirmed manually!"))
        else:
            success_content.add_widget(Label(text="RFID Payment successful!"))
            success_content.add_widget(Label(text=f"Card: {tag_id}"))

        success_content.add_widget(Label(text="Thank you for your purchase!"))

        success_ok_btn = Button(text='OK', size_hint_y=None, height=dp(50))
        success_content.add_widget(success_ok_btn)

        success_popup = Popup(
            title='Payment Successful',
            content=success_content,
            size_hint=(0.6, 0.4)
        )

        # 5. When 'OK' is pressed, dismiss this popup and show the email popup.
        def show_email_and_dismiss(instance):
            success_popup.dismiss()
            # open email popup which handles clearing the cart
            self.show_email_popup()

        success_ok_btn.bind(on_press=show_email_and_dismiss)
        success_popup.open()


    def show_email_popup(self):
        """
        Shows a popup to collect an email for receipt.
        The handlers below correctly close the popup and then clear the cart.
        """

        # Widgets
        email_input = TextInput(
            hint_text="Enter your email for receipt",
            size_hint_y=None,
            height=dp(50),
            font_size='18sp',
            multiline=False
        )

        # Virtual keyboard (uses the same widget used elsewhere)
        email_keyboard = VirtualKeyboard(
            search_input=email_input,
            size_hint_y=None,
            height=dp(415)
        )

        popup_layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
        popup_layout.add_widget(Label(text="Enter your email to receive your receipt:"))
        popup_layout.add_widget(email_input)
        popup_layout.add_widget(email_keyboard)

        # Buttons
        send_btn = Button(
            text="Send Receipt",
            size_hint_y=None,
            height=dp(50),
            background_color=(0.2, 0.6, 0.8, 1),
            color=(1, 1, 1, 1)
        )

        cancel_btn = Button(
            text="Skip Email",
            size_hint_y=None,
            height=dp(50),
            background_color=(0.7, 0.7, 0.7, 1),
            color=(1, 1, 1, 1)
        )

        btn_layout = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(50))
        btn_layout.add_widget(cancel_btn)
        btn_layout.add_widget(send_btn)
        popup_layout.add_widget(btn_layout)

        # Create popup **before** defining handlers so handlers can reference email_popup
        email_popup = Popup(
            title="Email Receipt",
            content=popup_layout,
            size_hint=(0.9, 0.9),
            auto_dismiss=False
        )

        # Handler: send email then clear cart
        def send_email_receipt_handler(instance):
            email = email_input.text.strip()
            if email:
                try:
                    # generate_pdf_receipt returns a path
                    pdf_path = generate_pdf_receipt(self.pending_cart_items, self.pending_total)
                    # send a command to server to email the receipt (your server-side should handle)
                    self.send_command(f"EMAIL_RECEIPT:{email}:{pdf_path}")
                    self.show_success_popup(f"Receipt sent to {email}")
                except Exception as e:
                    # If PDF generation or sending failed, show an error but still finalize
                    self.show_error_popup(f"Failed to send receipt: {e}")
            else:
                # No email entered: show a small confirmation
                self.show_success_popup("Transaction complete. No email provided.")

            # Finalize: clear cart and update UI
            self.cart_items = []
            self.pending_cart_items = []
            self.update_display()
            self.total_label.text = "Total: $0.00"

            email_popup.dismiss()

        # Handler: skip email (clear cart & close)
        def skip_email_handler(instance):
            self.cart_items = []
            self.pending_cart_items = []
            self.update_display()
            self.total_label.text = "Total: $0.00"
            email_popup.dismiss()

        # Bind handlers (done once, outside the handler bodies)
        send_btn.bind(on_press=send_email_receipt_handler)
        cancel_btn.bind(on_press=skip_email_handler)

        # Open popup
        email_popup.open()

        send_btn.bind(on_press=send_email_receipt_handler)
        cancel_btn.bind(on_press=skip_email_handler)

    def show_success_popup(self, message):
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
        content.add_widget(Label(text=message))
        ok_btn = Button(text='OK', size_hint_y=None, height=dp(50))
        popup = Popup(
            title='Success',
            content=content,
            size_hint=(0.6, 0.3)
        )
        ok_btn.bind(on_press=popup.dismiss)
        content.add_widget(ok_btn)
        popup.open()

    def clear_cart(self, instance):
        self.cart_items = []
        self.pending_cart_items = []
        self.update_display()
        self.total_label.text = "Total: $0.00"
        if hasattr(self, 'confirmation_popup'):
            self.confirmation_popup.dismiss()


    def update_background(self, *args):
        """Update background when widget moves/resizes"""
        if hasattr(self, 'background_rect'):
            self.background_rect.pos = self.pos
            self.background_rect.size = self.size
# ----------------- POSITION VISUALIZATION -----------------
class PinnedItemMarker(Button):
    def __init__(self, item_name, x, y, **kwargs):
        super().__init__(**kwargs)
        
        self.graphics_instructions = []
        
        self.item_name = item_name
        self.x_coord = x
        self.y_coord = y

        self.text = f"{item_name}"
        self.size_hint = (None, None)
        self.size = (120, 50)
        self.background_color = (0.78, 0, 1, 0.9)
        self.color = (1, 1, 1, 1)
        self.font_size = '14sp'
        self.bold = True
        self.halign = 'center'

        self.bind(on_press=self.remove_pin)

    def remove_pin(self, instance):
        if self.parent and hasattr(self.parent, 'remove_pinned_marker'):
            self.parent.remove_pinned_marker(self)

class BackgroundWidget(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bg_texture = None
        self.load_background()
        self.bind(pos=self.update_background, size=self.update_background)

    def load_background(self):
        try:
            bg_image = Image.open('theMap.png')
            img_data = io.BytesIO()
            bg_image.save(img_data, format='png')
            img_data.seek(0)
            self.bg_texture = CoreImage(img_data, ext='png').texture
            print(" Background image 'theMap.png' loaded successfully")
        except FileNotFoundError:
            print(" Warning: Background image 'theMap.png' not found")
            self.bg_texture = None
        except Exception as e:
            print(f" Error loading background: {e}")
            self.bg_texture = None

    def update_background(self, *args):
        self.canvas.clear()
        if self.bg_texture:
            with self.canvas:
                Color(1, 1, 1, 1)
                Rectangle(texture=self.bg_texture, pos=self.pos, size=self.size)

class MapWidget(Widget):
    def __init__(self, main_app=None, **kwargs):
        super().__init__(**kwargs)
        
        self.pinned_markers = main_app.pinned_markers
        self.pinned_item_names = main_app.pinned_item_names
        
        self.main_app = main_app
        Clock.schedule_interval(self.update_dynamic_elements, 0.5)
        Clock.schedule_interval(self.debug_positions, 5.0)
        self.last_item_count = 0
        self.last_target = None

    def debug_positions(self, dt):
        print("\n" + "=" * 50)
        print(" DEBUG POSITION COMPARISON")
        print(f" TAG Position: ({current_position[0]:.3f}, {current_position[1]:.3f})")

        if ITEMS:
            for i, (item_x, item_y, name) in enumerate(ITEMS):
                distance = np.sqrt((current_position[0] - item_x) ** 2 + (current_position[1] - item_y) ** 2)
                print(f" Item '{name}': ({item_x:.3f}, {item_y:.3f}) - Distance: {distance:.4f}")

                if current_position[0] == item_x and current_position[1] == item_y:
                    print(f" EXACT MATCH FOUND for '{name}'!")
                elif distance < 0.001:
                    print(f"  Very close match for '{name}' - distance: {distance:.6f}")
        else:
            print("ÃƒÂ°Ã…Â¸Ã¢â‚¬Å“Ã‚Â¦ No items in ITEMS list")
        print("=" * 50 + "\n")

    def update_dynamic_elements(self, dt):
        if len(ITEMS) != self.last_item_count:
            print(f" ITEMS list changed: {self.last_item_count} -> {len(ITEMS)} items")
            self.last_item_count = len(ITEMS)

        self.canvas.clear()

        scale_x = self.width / MAP_SIZE
        scale_y = self.height / MAP_SIZE

        with self.canvas:
            # 1. User position marker
            x, y = current_position
            Color(1, 0, 0)
            Ellipse(pos=(self.x + x * scale_x - 6, self.y + y * scale_y - 6), size=(12, 12))

            # 2. Plot current items from MQTT (skip pinned items)
            for item_x, item_y, name in ITEMS:
                if self.main_app and name in self.main_app.pinned_item_names:
                    continue

                Color(0, 1, 0, 0.7)
                Triangle(points=[
                    self.x + item_x * scale_x, self.y + item_y * scale_y + 8,
                    self.x + item_x * scale_x - 6, self.y + item_y * scale_y - 4,
                    self.x + item_x * scale_x + 6, self.y + item_y * scale_y - 4
                ])

            # 3. Closest Item target
            if ITEMS:
                closest_index = None
                closest_distance = None
                for idx, item in enumerate(ITEMS):
                    item_x, item_y, item_name = item
                    dist = np.sqrt((x - item_x) ** 2 + (y - item_y) ** 2)
                    if closest_distance is None or dist < closest_distance:
                        closest_distance = dist
                        closest_index = idx

                if closest_index is not None:
                    target_x, target_y, target_name = ITEMS[closest_index]
                    if not (self.main_app and target_name in self.main_app.pinned_item_names):
                        Color(1, 1, 0)
                        Ellipse(pos=(self.x + target_x * scale_x - 9 / 2,
                                     self.y + target_y * scale_y - 9 / 2),
                                size=(9, 9))

                    if self.last_target != target_name:
                        target_type = "PINNED" if (self.main_app and target_name in self.main_app.pinned_item_names) else "REGULAR"
                        print(f" NEW TARGET: {target_name} at ({target_x:.1f}, {target_y:.1f}) [{target_type}]")
                        self.last_target = target_name

        self.check_proximity()

    def remove_pinned_marker_by_name(self, item_name):
        """
        Safely remove a pinned marker using only its name.
        This is required so MapWidget can request removals.
        """
        # Loop over copy because we may modify the list
        for marker in list(self.pinned_markers):
            if getattr(marker, "item_name", None) == item_name:
                self.remove_pinned_marker(marker)
                break

        # Ensure internal tracking stays in sync
        if item_name in self.pinned_item_names:
            self.pinned_item_names.remove(item_name)


    def check_proximity(self):
            x, y = current_position

            print(f" Proximity check - Position: ({x:.2f}, {y:.2f})")
            print(f" Checking {len(ITEMS)} items in ITEMS list")

            items_to_remove_indices = []
            for idx, item in enumerate(ITEMS):
                item_x, item_y, item_name = item
                dist = np.sqrt((x - item_x) ** 2 + (y - item_y) ** 2)

                print(f" Item {item_name} at ({item_x:.2f}, {item_y:.2f}) - Distance: {dist:.3f}")

                if dist < PROXIMITY_THRESHOLD:
                    print(f" REACHED ITEM: {item_name} - Removing!")
                    items_to_remove_indices.append(idx)

            if items_to_remove_indices:
                for idx in sorted(items_to_remove_indices, reverse=True):
                    removed_item = ITEMS.pop(idx)
                    item_name = removed_item[2]
                    print(f" Removed from ITEMS list: {item_name}")
                    
                    # Original removal call (which likely fails due to name mismatch)
                    self.main_app.remove_pinned_marker_by_name(item_name)
                    
                # --- NEW REFRESH CALL ---
                self.refresh_map_pins() # Force visual cleanup of any stuck pins

            else:
                print("   No items reached in this check")
                
    def refresh_map_pins(self):
        """
        Forces the map to clean up any PinnedMarker widgets that are visually present
        but have been removed from the internal tracking list (self.pinned_markers).
        """
        children_to_remove = []
        
        for child in self.children[:]:
            # Identify PinnedMarker widgets by their unique attributes
            if hasattr(child, 'item_name') and hasattr(child, 'canvas'): 
                
                # If the widget is a pin, and it is NOT in our tracking list, it's stuck.
                if child not in self.pinned_markers:
                    children_to_remove.append(child)
        for marker in children_to_remove:
            # 1. Explicitly clear the graphics instructions (Visual Fix)
            marker.canvas.clear()
            
            # 2. Remove the widget from the map's children (Structural Fix)
            self.remove_widget(marker)

class PositionVisualizer(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.pinned_markers = []
        self.pinned_item_names = set()

        self.background_widget = BackgroundWidget()
        self.add_widget(self.background_widget)

        self.map_widget = MapWidget(main_app=self)
        self.add_widget(self.map_widget)

        self.add_search_button()


    def remove_pinned_marker_by_name(self, item_name):
        # 1. Apply Extreme Sanitization to the incoming name
        #    This removes non-standard whitespace/control characters like \xa0, \r, \n.
        name_b = str(item_name).strip().lower().replace('\xa0', '').replace('\r', '').replace('\n', '')

        for marker in self.pinned_markers[:]:
            
            # 2. Apply the same sanitization to the stored marker name
            name_a = str(marker.item_name).strip().lower().replace('\xa0', '').replace('\r', '').replace('\n', '')
            
            # 3. Compare the fully sanitized strings
            if name_a == name_b:
                # Call the working removal function (which contains marker.canvas.clear())
                self.remove_pinned_marker(marker) 
                print(f"? Pin object removed for: {item_name}")
                return # Stop searching once found

    def add_search_button(self):
        search_button = Button(
            text='Search Store',
            size_hint=(0.15, 0.07),
            pos_hint={'x': 0.02, 'top': 0.98},
            background_color=(0.8901, 0.94901, 1, 0.86), #0.8901, 0.94901, 1, 0.86)
            color=(1, 1, 1, 1),
            font_size='24sp',
            bold=True
        )
        search_button.bind(on_press=self.open_search_popup)
        self.add_widget(search_button)

    def open_search_popup(self, instance):
        try:
            search_content = ShoppingSearchApp(main_app=self)
            popup = Popup(
                title='',
                content=search_content,
                size_hint=(0.95, 0.95),
                auto_dismiss=False,
                separator_height=0
            )
            search_content.popup = popup
            popup.open()
        except Exception as e:
            print(f" Error opening search: {e}")

    def is_item_already_pinned(self, item_name):
        return item_name in self.pinned_item_names

    def add_pinned_item_to_proximity_check(self, item_name, x, y):
        global ITEMS

        item_found = False
        for i, (existing_x, existing_y, existing_name) in enumerate(ITEMS):
            if existing_name == item_name:
                ITEMS[i] = (x, y, item_name)
                print(f" Updated position for {item_name} in ITEMS list: ({existing_x}, {existing_y}) -> ({x}, {y})")
                item_found = True
                break

        if not item_found:
            ITEMS.append((x, y, item_name))
            print(f" Added {item_name} to ITEMS list for proximity checking")

        print(f" ITEMS list now has {len(ITEMS)} items: {[name for _, _, name in ITEMS]}")

    def display_pinned_item_locally(self, item_name, x, y):
        print(f" Displaying pinned item locally: {item_name} at ({x}, {y})")

        if self.is_item_already_pinned(item_name):
            print(f" {item_name} is already pinned! Skipping duplicate.")
            self.show_already_pinned_warning(item_name)
            return

        screen_x = x / MAP_SIZE
        screen_y = y / MAP_SIZE

        pinned_marker = PinnedItemMarker(
            item_name=item_name,
            x=x,
            y=y,
            pos_hint={'center_x': screen_x, 'center_y': screen_y}
        )

        self.add_widget(pinned_marker)
        self.pinned_markers.append(pinned_marker)
        self.pinned_item_names.add(item_name)

        self.add_pinned_item_to_proximity_check(item_name, x, y)

        print(f" Pinned marker created for {item_name}. Total pins: {len(self.pinned_markers)}")
        self.show_pin_confirmation(item_name, x, y)

    def remove_pinned_marker(self, marker):
        if marker in self.pinned_markers:
            
            # 1. CRITICAL VISUAL FIX: Manually remove graphics instructions
            # This checks the marker for the instruction list we added and tries to remove them
            # from both the MapWidget's canvas (self.canvas) and the marker's canvas.
            if hasattr(marker, 'graphics_instructions') and marker.graphics_instructions:
                print(f"DEBUG: Attempting manual graphics cleanup for {marker.item_name}...")
                
                # Loop through the instructions saved in the pin object
                for instr in marker.graphics_instructions:
                    
                    # Check if the instruction is stuck on the MapWidget's canvas (most likely bug location)
                    if instr in self.canvas.children: 
                        self.canvas.remove(instr)
                        print(f"DEBUG: Removed instruction from MapWidget canvas.")
                    
                    # Check if the instruction is on the marker's own canvas (standard cleanup)
                    elif instr in marker.canvas.children:
                        marker.canvas.remove(instr)
                        print(f"DEBUG: Removed instruction from Marker canvas.")

            # 2. HIERARCHY CLEANUP: Remove the PinnedItemMarker widget from the map
            self.remove_widget(marker)
            
            # 3. TRACKING CLEANUP: Remove the marker object from the tracking lists
            self.pinned_markers.remove(marker)
            self.pinned_item_names.discard(marker.item_name)
            
            # 4. Global ITEMS cleanup
            global ITEMS
            for i, (x, y, name) in enumerate(ITEMS):
                if name == marker.item_name:
                    ITEMS.pop(i)
                    print(f" Also removed {marker.item_name} from ITEMS list to prevent generic icons")
                    break
            
            # 5. Force a final visual refresh
            self.canvas.ask_update()
            
            print(f" MANUAL GRAPHICS FIX: Pin successfully removed for {marker.item_name}.")

    def show_already_pinned_warning(self, item_name):
        warning_label = Label(
            text=f" {item_name} already pinned!",
            size_hint=(0.3, 0.05),
            pos_hint={'center_x': 0.5, 'top': 0.12},
            color=(1, 0, 0, 1),
            font_size='14sp',
            bold=True
        )
        self.add_widget(warning_label)
        Clock.schedule_once(lambda dt: self.remove_widget(warning_label), 2)

    def show_pin_confirmation(self, item_name, x, y):
        confirmation_label = Label(
            text=f" {item_name} pinned!",
            size_hint=(0.3, 0.05),
            pos_hint={'center_x': 0.5, 'top': 0.12},
            color=(0, 0.5, 0, 1),
            font_size='14sp',
            bold=True
        )
        self.add_widget(confirmation_label)
        Clock.schedule_once(lambda dt: self.remove_widget(confirmation_label), 2)

# ----------------- MAIN APPLICATION -----------------
class CombinedApp(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Set window size for side-by-side display
        #Window.size = (1920, 1080)
        Window.clearcolor = (1, 1, 1, 1)
        
        # Create position visualizer (left side - 60% width)
        self.position_app = PositionVisualizer()
        self.position_app.size_hint = (0.6, 1.0)
        self.position_app.pos_hint = {'x': 0, 'y': 0}
        self.add_widget(self.position_app)
        
        # Create shopping cart app (right side - 40% width)
        self.shopping_app = ShoppingCartApp()
        self.shopping_app.size_hint = (0.4, 1.0)
        self.shopping_app.pos_hint = {'x': 0.6, 'y': 0}
        self.add_widget(self.shopping_app)

class CombinedShoppingApp(App):
    def build(self):
        self.title = "CyberKart - Shopping Assistant"
        
        Window.fullscreen = True
        
        return CombinedApp()

# ----------------- MAIN EXECUTION -----------------
def main():
    print("Starting Combined Shopping Application")
    print("=" * 50)
    print(f"MQTT Broker: {MQTT_BROKER}")
    print(f"Position Topic: {MQTT_POSITION_TOPIC}")
    print(f"Item Topic: {MQTT_ITEM_TOPIC}")
    print("=" * 50)

    # Set up MQTT Client for position tracking
    client = mqtt.Client(client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.message_callback_add(MQTT_POSITION_TOPIC, on_message_position)
    client.message_callback_add(MQTT_ITEM_TOPIC, on_message_items)

    try:
        print(f"Connecting to MQTT broker at {MQTT_BROKER}...")
        client.connect(MQTT_BROKER, 1883, 60)
    except Exception as e:
        print(f"Could not connect to MQTT broker: {e}")
        return

    # Start the MQTT network loop in a non-blocking thread
    client.loop_start()

    # Start the combined Kivy application
    CombinedShoppingApp().run()
    
    # Cleanup
    client.loop_stop()

if __name__ == '__main__':
    main()