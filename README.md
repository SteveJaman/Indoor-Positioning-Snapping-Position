# CPE 4800 F25 - Senior Design: The Smart Delivery Cart

## 🛒 Project Overview

The **Smart Delivery Cart** is a compact, all-in-one hardware solution designed to drastically improve the efficiency of grocery delivery personnel. It integrates advanced technology to make the in-store shopping process faster and easier through two primary features:

1.  **Self-Checkout Capability:** Streamlining the payment and inventory process using **RFID**.
2.  **Live In-Store Position Tracking:** Providing real-time user location within the store layout using **BLE IPS**.

## 👥 Team & Roles

| Team Name | Members |
| :--- | :--- |
| **SyntaxError** | Margarita, Thi, Carter, Steven, Anthony |

| Core Sub-System | Team Members |
| :--- | :--- |
| **Indoor Positioning System (IPS)** | Steven and Anthony |
| **Front End Graphical User Interface Design** | Margaritha and Thi |
| **Hardware Design and 3D Modeling** | Carter |

---

## ⚙️ System Architecture & Data Flow

The project is built on a modular architecture that manages both location tracking and inventory. The entire system relies on **MQTT** as the central message bus for seamless, real-time communication. 

### 1. Central Server (`Server.py`)

* **Role:** Acts as the central hub for data management and routing.
* **Backend Software:** Handles data persistence, user authentication, and API endpoints for the client.
* **MQTT Broker:** The server hosts the MQTT broker, receiving position data from the ESP32 and broadcasting updates to the Client Application.

### 2. Client Application (`Client.py` - User Interface)

* **Role:** The primary interface used by the delivery personnel (built with Kivy).
* **Functionality:**
    * **Live Map Plotting:** Subscribes to the MQTT position topic to **live-plot the user's location** on a store map grid.
    * **Self-Checkout Interface:** Displays scanned items, manages the cart inventory list, and handles the checkout process.

### 3. RFID Code (`RFID.py` - Self-Checkout)

* **Role:** Manages the inventory scanning and tracking on the cart.
* **Code:** Developed to interface with the RFID reader hardware. It reads RFID tags attached to products, transmits the tag IDs to the server for item lookup, and manages the temporary cart inventory list.

---

## 📍 Indoor Positioning System (IPS) Technical Description

This project implements an advanced Indoor Positioning System (IPS) using **Bluetooth Low Energy (BLE) trilateration** and sophisticated filtering techniques on an **ESP32 microcontroller**.

### Architecture & Data Flow
The system is designed for a defined 6x6 meter area and operates as follows:

1.  **Scanning & Distance Calculation:** The ESP32 continuously scans for four fixed BLE beacons. It calculates the distance to each beacon based on the **Received Signal Strength Indicator (RSSI)**.
2.  **Signal Filtering:** A **Median Filter** is applied to the raw RSSI data to mitigate transient noise and ensure a stable distance calculation.
3.  **Position Estimation:** An **Inverse Distance Weighted (IDW) Multilateration** technique is used to calculate a raw, estimated position. 
4.  **Motion Tracking & Smoothing:** The raw position is fed into a **Kalman Filter** and a **Particle Filter** to achieve effective noise reduction and stable motion tracking, resulting in a smoothed final location.
5.  **Grid Snapping & Output:** The final smoothed location is **snapped to a grid** for map compatibility before being published to an **MQTT broker** over Wi-Fi for real-time client application tracking.

### Key Technologies Used

| Category | Technology | Purpose |
| :--- | :--- | :--- |
| **Microcontroller** | ESP32 | BLE scanning and Wi-Fi connectivity. |
| **Communication Protocol**| MQTT | Real-time data transmission to the server. |
| **Positioning** | BLE Beacons | Fixed reference points for signal strength measurement. |
| **Filtering (Noise)** | Median Filter | Smooths raw RSSI data. |
| **Positioning Algorithm**| IDW Multilateration | Calculates raw position estimate. |
| **Filtering (Motion)** | Kalman Filter, Particle Filter | Provides noise reduction and motion stability. |

---

## 🖥️ Hardware & Peripherals (The Cart Build)

The Smart Delivery Cart integrates several key hardware components to fulfill its dual functions.

| Component | Purpose | Details |
| :--- | :--- | :--- |
| **Main Processor** | ESP32 | Used for both BLE-IPS processing and communication (MQTT/Wi-Fi). |
| **Localization Hardware** | 4 x BLE Beacons (Fixed) | Transmit signals used as reference points for the IPS calculation. |
| **Self-Checkout Hardware**| **RFID Reader Module** | Scans product tags for inventory management. |
| **User Interface** | Tablet/Display Mount | Runs the Client Application interface for mapping and checkout. |
| **Housing** | **3D Printed/Custom Enclosure** | Provides a compact, all-in-one chassis for protection and mounting. |
| **Power System** | Battery/Power Management | Ensures reliable, portable power for all on-cart components. |

---

## 💻 Code Structure & Usage

The project's software is split into two main sections: the **Embedded C++** code for the IPS sensor node, and three interconnected **Python** applications for the backend, inventory, and user interface.

### Python Application Components

| Component | File | Role & Interaction |
| :--- | :--- | :--- |
| **Backend Server** | `Server.py` | The central component. It hosts the MQTT broker/client logic, receives raw position data from the ESP32, validates RFID scans, manages the product database, and relays necessary information to the Client. |
| **Client Application**| `Client.py` | The user-facing application (UI/GUI). It subscribes to the MQTT position topic to enable **live plotting** of the cart on the store map and handles the entire **self-checkout** user experience. |
| **RFID Reader Logic**| `RFID.py` | Runs the hardware interface for the RFID scanner. It continuously reads product tags and publishes the scanned IDs (via MQTT or direct network call) to the `Server.py` for item lookup and inventory updating. |

### Prerequisites & Setup

#### **Embedded C++ Dependencies (ESP32 IPS Code)**

The following libraries are necessary for compiling the IPS code on the ESP32 (typically installed via Arduino IDE or PlatformIO Library Manager):

| Library | Purpose |
| :--- | :--- |
| **`WiFi`** | Standard library for establishing Wi-Fi connectivity. |
| **`PubSubClient`** | Enables MQTT client functionality on the ESP32. |
| **`BLEDevice`** | For scanning and interacting with Bluetooth Low Energy devices (beacons). |
| **`Arduino_JSON`** | Used to format the position data before publishing via MQTT. |
| **Custom Filter Library** | Required header files for the Kalman Filter and Particle Filter implementations. |

#### **Python Dependencies (Server, Client, and RFID)**

The following external dependencies are required to run the Python application components:

| Dependency | Purpose | Components Used In |
| :--- | :--- | :--- |
| **`paho-mqtt`** | Core library for connecting to and communicating with the MQTT broker. | Server, Client, RFID |
| **`kivy`** | The framework used to build the cross-platform Graphical User Interface (GUI) of the Client. | Client |
| **`Pillow`** | Python Imaging Library (PIL), used for handling images and visualizations in the client. | Client |
| **`numpy`** | Numerical library for efficient array manipulation (common for positioning math). | Client |
| **`reportlab`** | Used by the Client application to generate PDF receipts. | Client |
| **`spidev`** / **`gpiozero`** | Linux/Raspberry Pi specific libraries for SPI communication (RFID) and GPIO control. | RFID, Client |

**Installation:**
To install the core Python dependencies (MQTT, GUI, Visualization, and Reports), run the following command:

```bash
pip install paho-mqtt kivy pillow numpy reportlab

# Installation for Raspberry Pi GPIO/SPI libraries
sudo apt install python3-rpi.gpio python3-spidev
pip install gpiozero
