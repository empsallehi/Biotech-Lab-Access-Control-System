#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <WiFi.h>
#include <HTTPClient.h>

#define RST_PIN   4     
#define SS_PIN    5     

const byte ROWS = 4; 
const byte COLS = 3; 
char keys[ROWS][COLS] = {
  {'1','2','3'}, {'4','5','6'}, {'7','8','9'}, {'*','0','#'}
};
byte rowPins[ROWS] = {13, 12, 14, 27}; 
byte colPins[COLS] = {26, 25, 33}; 
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

const char* ssid = "Wokwi-GUEST";
const char* password = "";
// آدرس اصلی برای اسکن و آدرس جدید برای اضطراری
const char* serverUrl = "https://empsallehi.pythonanywhere.com/scan"; 
const char* emergencyUrl = "https://empsallehi.pythonanywhere.com/emergency_open";

LiquidCrystal_I2C lcd(0x27, 16, 2);
MFRC522 mfrc522(SS_PIN, RST_PIN);

String activeCardUID = "";
String inputPIN = "";
enum SystemState { READY_TO_SCAN, GETTING_PIN };
SystemState currentState = READY_TO_SCAN;

void showReadyMessage() {
  lcd.clear();
  lcd.setCursor(0, 0); lcd.print("Biotech Lab");
  lcd.setCursor(0, 1); lcd.print("Ready to Scan!");
}

void setup() {
  Serial.begin(115200);
  SPI.begin();
  mfrc522.PCD_Init();
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("Connecting WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    lcd.print(".");
  }
  showReadyMessage();
}

// تابع تغییر یافته برای پشتیبانی از URLهای مختلف
String sendToPython(String url, String uid, String pin) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    String jsonPayload = "{\"uid\":\"" + uid + "\",\"pin\":\"" + pin + "\"}";
    int httpResponseCode = http.POST(jsonPayload);
    if (httpResponseCode > 0) {
      String response = http.getString();
      http.end();
      return response;
    }
    http.end();
  }
  return "ERROR";
}

void loop() {
  if (currentState == READY_TO_SCAN) {
    // --- اضافه شده: بررسی کلید اضطراری ---
    char key = keypad.getKey();
    if (key == '#') { 
        lcd.clear();
        lcd.setCursor(0, 0); lcd.print("EMERGENCY EXIT!");
        sendToPython(emergencyUrl, "SYSTEM", "EMERGENCY");
        delay(2000);
        showReadyMessage();
        return; 
    }
    // -------------------------------------

    if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
      return;
    }
    
    activeCardUID = "";
    for (byte i = 0; i < mfrc522.uid.size; i++) {
      activeCardUID += String(mfrc522.uid.uidByte[i] < 0x10 ? "0" : "");
      activeCardUID += String(mfrc522.uid.uidByte[i], HEX);
    }
    activeCardUID.toUpperCase();
    
    lcd.clear();
    lcd.setCursor(0, 0); lcd.print("Verifying...");
    
    String res = sendToPython(serverUrl, activeCardUID, "");
    
    if (res == "P") {
      currentState = GETTING_PIN;
      inputPIN = "";
      lcd.clear();
      lcd.setCursor(0, 0); lcd.print("Enter PIN:");
      lcd.setCursor(0, 1); lcd.print("_");
    } else if (res == "U") {
      lcd.clear(); lcd.print("Unknown Card!");
      delay(3000); showReadyMessage();
    } else if (res == "L") {
      lcd.clear(); lcd.print("Card Locked!");
      delay(3000); showReadyMessage();
    } else {
      lcd.clear(); lcd.print("Conn Error!");
      delay(3000); showReadyMessage();
    }
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
  } 
  else if (currentState == GETTING_PIN) {
    char key = keypad.getKey();
    if (key) {
      if (key == '*') { 
        lcd.clear(); lcd.setCursor(0, 0); lcd.print("Checking PIN...");
        String res = sendToPython(serverUrl, activeCardUID, inputPIN);
        
        lcd.clear();
        if (res == "A") {
          lcd.print("Access Granted!");
          lcd.setCursor(0, 1); lcd.print("Welcome!");
          delay(3000);
          currentState = READY_TO_SCAN; showReadyMessage();
        } else if (res == "L") {
          lcd.print("Card Auto-Locked");
          delay(4000);
          currentState = READY_TO_SCAN; showReadyMessage();
        } else if (res == "W") {
          lcd.print("Wrong PIN!");
          delay(2000);
          inputPIN = "";
          lcd.clear();
          lcd.setCursor(0, 0); lcd.print("Enter PIN:");
          lcd.setCursor(0, 1); lcd.print("_");
        } else {
          lcd.clear(); lcd.print("Conn Error!");
          delay(3000);
          currentState = READY_TO_SCAN; showReadyMessage();
        }
      } 
      else if (key == '#') { 
        inputPIN = "";
        lcd.clear();
        lcd.setCursor(0, 0); lcd.print("Enter PIN:");
        lcd.setCursor(0, 1); lcd.print("_");
      } 
      else {
        inputPIN += key;
        lcd.setCursor(inputPIN.length() - 1, 1); lcd.print("*");
      }
    }
  }
}