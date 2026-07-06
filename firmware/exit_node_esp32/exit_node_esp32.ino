#include <SPI.h>
#include <Wire.h>
#include <string.h>
#include <Adafruit_PN532.h>

// ---- Lane 3: Valenzuela (KM 23) — own dedicated pins ----
#define LANE3_SCK   (18)
#define LANE3_MISO  (19)
#define LANE3_MOSI  (23)
#define LANE3_SS    (5)
#define LANE3_RST   (4)
#define LANE3_ID    "3"

// ---- Lane 4: Meycauayan (KM 27) — own dedicated pins ----
#define LANE4_SCK   (14)
#define LANE4_MISO  (27)
#define LANE4_MOSI  (26)
#define LANE4_SS    (25)
#define LANE4_RST   (33)
#define LANE4_ID    "4"

#define GATE_TYPE "EXIT"

Adafruit_PN532 nfcLane3(LANE3_SCK, LANE3_MISO, LANE3_MOSI, LANE3_SS);
Adafruit_PN532 nfcLane4(LANE4_SCK, LANE4_MISO, LANE4_MOSI, LANE4_SS);

const uint32_t SCAN_COOLDOWN = 2000;
uint32_t lastScanTimeLane3 = 0;
uint32_t lastScanTimeLane4 = 0;

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

  pinMode(LANE3_RST, OUTPUT); digitalWrite(LANE3_RST, HIGH);
  pinMode(LANE4_RST, OUTPUT); digitalWrite(LANE4_RST, HIGH);

  selfTestPn532(nfcLane3, "PN532 Lane 3 (Valenzuela)");
  selfTestPn532(nfcLane4, "PN532 Lane 4 (Meycauayan)");

  Serial.println("[EXIT NODE 1] Ready — Valenzuela & Meycauayan exits.");
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

  // ---- Lane 3: Valenzuela ----
  if (currentTime - lastScanTimeLane3 >= SCAN_COOLDOWN) {
    uint8_t uid[7]; uint8_t uidLength;
    if (nfcLane3.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
      lastScanTimeLane3 = currentTime;
      Serial.print("@SCAN," GATE_TYPE "," LANE3_ID ",");
      printUidHex(uid, uidLength);
      Serial.println();
    }
  }

  // ---- Lane 4: Meycauayan ----
  if (currentTime - lastScanTimeLane4 >= SCAN_COOLDOWN) {
    uint8_t uid[7]; uint8_t uidLength;
    if (nfcLane4.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
      lastScanTimeLane4 = currentTime;
      Serial.print("@SCAN," GATE_TYPE "," LANE4_ID ",");
      printUidHex(uid, uidLength);
      Serial.println();
    }
  }
}
