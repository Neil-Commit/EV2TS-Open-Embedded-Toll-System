#include <SPI.h>
#include <Wire.h>
#include <string.h>
#include <Adafruit_PN532.h>

// ---- Lane 3: Marilao (KM 23) — own dedicated pins ----
#define LANE5_SCK   (18)
#define LANE5_MISO  (19)
#define LANE5_MOSI  (23)
#define LANE5_SS    (5)
#define LANE5_RST   (4)
#define LANE5_ID    "5"

// ---- Lane 4: Bocaue (KM 27) — own dedicated pins ----
#define LANE6_SCK   (14)
#define LANE6_MISO  (27)
#define LANE6_MOSI  (26)
#define LANE6_SS    (25)
#define LANE6_RST   (33)
#define LANE6_ID    "6"

#define GATE_TYPE "EXIT"

Adafruit_PN532 nfcLane5(LANE5_SCK, LANE5_MISO, LANE5_MOSI, LANE5_SS);
Adafruit_PN532 nfcLane6(LANE6_SCK, LANE6_MISO, LANE6_MOSI, LANE6_SS);

const uint32_t SCAN_COOLDOWN = 2000; // ms
uint32_t lastScanTimeLane5 = 0;
uint32_t lastScanTimeLane6 = 0;

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
    Serial.print("BARRIER WOULD OPEN (");
    Serial.print(reason);
    Serial.println(")");
  } else {
    Serial.print("BARRIER STAYS CLOSED -- ");
    Serial.println(reason);
  }
}

void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);

  pinMode(LANE5_RST, OUTPUT); digitalWrite(LANE5_RST, HIGH);
  pinMode(LANE6_RST, OUTPUT); digitalWrite(LANE6_RST, HIGH);

  selfTestPn532(nfcLane5, "PN532 Lane 5 (Marilao)");
  selfTestPn532(nfcLane6, "PN532 Lane 6 (Bocaue)");

  Serial.println("[EXIT NODE 2] Ready — Marilao & Bocaue exits.");
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

  // ---- Lane 5: Marilao ----
  if (currentTime - lastScanTimeLane5 >= SCAN_COOLDOWN) {
    uint8_t uid[7]; uint8_t uidLength;
    if (nfcLane3.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
      lastScanTimeLane5 = currentTime;
      Serial.print("@SCAN," GATE_TYPE "," LANE5_ID ",");
      printUidHex(uid, uidLength);
      Serial.println();
    }
  }

  // ---- Lane 6: Bocaue ----
  if (currentTime - lastScanTimeLane6 >= SCAN_COOLDOWN) {
    uint8_t uid[7]; uint8_t uidLength;
    if (nfcLane4.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
      lastScanTimeLane6 = currentTime;
      Serial.print("@SCAN," GATE_TYPE "," LANE6_ID ",");
      printUidHex(uid, uidLength);
      Serial.println();
    }
  }
}
