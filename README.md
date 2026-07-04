# IoT Access Control System

An IoT-based Access Control System developed as the final project for the Embedded and Real-Time Systems course.

The project simulates a smart laboratory access control system using an ESP32 microcontroller, RFID authentication, PIN verification, a Flask backend server, SQLite database, and a web-based management dashboard.

---

## Features

- RFID-based user authentication
- PIN verification using a keypad
- Automatic card locking after multiple failed PIN attempts
- Unknown card detection
- Access log management
- User management dashboard
- Emergency Override functionality
- Secure communication between ESP32 and Flask server
- Cloud deployment using PythonAnywhere

---

## Hardware

- ESP32 DevKit V1
- MFRC522 RFID Reader
- LCD 16×2 (I2C)
- 4×3 Matrix Keypad

Simulation Platform:

- Wokwi

---

## Software Stack

- Python
- Flask
- SQLite
- HTML
- CSS
- JavaScript
- ESP32 Arduino Framework

---

## Project Structure

```
ESP32/
Server/
Dashboard/
Database/
Images/
Report/
```

---

## System Architecture

RFID Card
→ ESP32
→ Flask Server
→ SQLite Database
→ Dashboard

---

## Dashboard

The dashboard provides:

- System Overview
- Access Logs
- Locked Cards Management
- User Management
- Emergency Override
- Analytics and Statistics

---

## Online Demo

PythonAnywhere:

https://empsallehi.pythonanywhere.com

---

## Author

Khatere Salehi Tabar

Embedded & Real-Time Systems Course

2026
