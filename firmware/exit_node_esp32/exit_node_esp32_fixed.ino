#include <SPI.h>
#include <Wire.h>
#include <string.h>
#include <Adafruit_PN532.h>

// Lane 1: Valenzuela (KM 15) 
#define LANE1_SCK   (18)
#define LANE1_MISO  (19)
#define LANE1_MOSI  (23)
#define LANE1_SS    (5)
#define LANE1_RST   (4)
#define LANE1_ID    "1"

// Lane 2: Meycauayan (KM 19)
#define LANE2_SCK   (14)
#define LANE2_MISO  (27)
#define LANE2_MOSI  (26)
#define LANE2_SS    (25)
#define LANE2_RST   (33)
#define LANE2_ID    "2"

#define GATE_TYPE "EXIT"

Adafruit_PN532 nfcLane1(LANE1_SCK, LANE1_MISO, LANE1_MOSI, LANE1_SS);
Adafruit_PN532 nfcLane2(LANE2_SCK, LANE2_MISO, LANE2_MOSI, LANE2_SS);

const uint32_t SCAN_COOLDOWN = 2000;
uint32_t lastScanTimeLane1 = 0;
uint32_t lastScanTimeLane2 = 0;

void printUidHex(uint8_t* uid, uint8_t len) {
  for (uint8_t i = 0; i < len; i++) {
    if (uid[i] < 0x10) Serial.print("0");
    Serial.print(uid[i], HEX);
  }
}

bool selfTestPn532(Adafruit_PN532 &nfc, const char* label) {
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.print("[ERROR] ");
    Serial.print(label);
    Serial.println(" not found. Check SCK/MISO/MOSI/CS/RST wiring, "
                    "DIP switches (I1=0, I2=1), and 5V power.");
    return false;
  }
  Serial.print("[OK] ");
  Serial.print(label);
  Serial.print(" found, firmware version ");
  Serial.print((versiondata >> 24) & 0xFF, DEC);
  Serial.print('.');
  Serial.println((versiondata >> 16) & 0xFF, DEC);
  nfc.SAMConfig();
  return true;
}

void handleActionLine(char* line) {
  if (strncmp(line, "@ACTION,", 8) != 0) return;
  char* body   = line + 8;
  char* lane   = strtok(body, ",");
  char* status = strtok(NULL, ",");
  char* reason = strtok(NULL, ",");
  if (!lane || !status || !reason) return;
  Serial.print("[GATE] Lane "); Serial.print(lane); Serial.print(": ");
  if (strcmp(status, "GRANT") == 0) {
    Serial.print("BARRIER WOULD OPEN (");     // Joke lang yung barrier
    Serial.print(reason);
    Serial.println(")");
  } else {
    Serial.print("BARRIER STAYS CLOSED -- ");
    Serial.println(reason);
  }
}

void pollLane(Adafruit_PN532 &nfc, const char* laneId,
              uint32_t &lastScanTime, uint32_t currentTime) {
  if (currentTime - lastScanTime < SCAN_COOLDOWN) return;
  uint8_t uid[7]; uint8_t uidLen;
  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen, 100)) {
    lastScanTime = currentTime;
    Serial.print("@SCAN," GATE_TYPE ",");
    Serial.print(laneId);
    Serial.print(",");
    printUidHex(uid, uidLen);
    Serial.println();
  }
}

void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);

  pinMode(LANE1_RST, OUTPUT); digitalWrite(LANE1_RST, HIGH);
  pinMode(LANE2_RST, OUTPUT); digitalWrite(LANE2_RST, HIGH);

  selfTestPn532(nfcLane1, "PN532 Lane 1 (Valenzuela)");
  selfTestPn532(nfcLane2, "PN532 Lane 2 (Meycauayan)");

  Serial.println("[EXIT NODE] Ready — Valenzuela & Meycauayan exits.");
}

void loop(void) {
  static char serialBuffer[64];
  static int bufferIndex = 0;
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (bufferIndex > 0) {
        serialBuffer[bufferIndex] = '\0';
        handleActionLine(serialBuffer);
        bufferIndex = 0;
      }
    } else if (bufferIndex < 63) {
      serialBuffer[bufferIndex++] = c;
    }
  }

  uint32_t currentTime = millis();
  pollLane(nfcLane1, LANE1_ID, lastScanTimeLane1, currentTime); // Valenzuela
  pollLane(nfcLane2, LANE2_ID, lastScanTimeLane2, currentTime); // Meycauayan
}
