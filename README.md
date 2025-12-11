# CPE 4800 F25 - Senior Design: The Smart Delivery Cart

## 🛒 Project Overview

The **Smart Delivery Cart** is a compact, all-in-one hardware solution designed to drastically improve the efficiency of grocery delivery personnel. It integrates advanced technology to make the in-store shopping process faster and easier through two primary features:

1.  **Self-Checkout Capability:** Streamlining the payment and inventory process.
2.  **Live In-Store Position Tracking:** Providing real-time user location within the store layout.

## 👥 Team & Roles

| Team Name | Members |
| :--- | :--- |
| **SyntaxError** | Margarita, Thi, Carter, Steven, Anthony |

| Core Sub-System | Team Members |
| :--- | :--- |
| **Indoor Positioning System (IPS)** | Steven and Anthony |

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

## 💻 Code Structure & Usage

*(This section is a placeholder. You should fill this in with actual setup instructions for a developer.)*

### Prerequisites
* Arduino IDE or VS Code with PlatformIO
* ESP32 Board Support Package
* Required libraries: `[List key libraries like PubSubClient, Kalman, etc.]`

### Setup Instructions
1.  Clone the repository: `git clone [Your Repo URL]`
2.  Configure Wi-Fi credentials and MQTT broker details in `config.h`.
3.  Upload the code to the ESP32.

## 🛠️ Development Status

**Status:** Completed (Final Report Submitted)

**Report File:** `CPE 4850 Final report(4).docx` (Located in the root directory for reference)
