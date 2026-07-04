#include <SPI.h>
#include <Wire.h>
#include <string.h>
#include <Adafruit_PN532.h>

// ---- Lane 1: own dedicated pins ----
#define LANE1_SCK   (18)
#define LANE1_MISO  (19)
#define LANE1_MOSI  (23)
#define LANE1_SS    (5)
#define LANE1_RST   (4)
#define LANE1_ID    "1"

// ---- Lane 2: own dedicated pins (nothing shared with Lane 1) ----
#define LANE2_SCK   (14)
#define LANE2_MISO  (27)
#define LANE2_MOSI  (26)
#define LANE2_SS    (25)
#define LANE2_RST   (33)
#define LANE2_ID    "2"

#define GATE_TYPE "ENTRY"

Adafruit_PN532 nfcLane1(LANE1_SCK, LANE1_MISO, LANE1_MOSI, LANE1_SS);
Adafruit_PN532 nfcLane2(LANE2_SCK, LANE2_MISO, LANE2_MOSI, LANE2_SS);

const uint32_t SCAN_COOLDOWN = 2000; // ms, same cooldown style as cppcode.md
uint32_t lastScanTimeLane1 = 0;
uint32_t lastScanTimeLane2 = 0;

void printUidHex(uint8_t* uid, uint8_t len) {
  for (uint8_t i = 0; i < len; i++) {
    if (uid[i] < 0x10) Serial.print("0");
    Serial.print(uid[i], HEX);
  }
}

// Self-test one PN532: must pass before card-tap detection can ever work.
// If it fails, it's a wiring/power/SPI-mode problem, not a "card not
// read" problem.
bool selfTestPn532(Adafruit_PN532 &nfc, const char* label) {
  nfc.begin();
  uint32_t versiondata = nfc.getFirmwareVersion();
  if (!versiondata) {
    Serial.print("[ERROR] ");
    Serial.print(label);
    Serial.println(" not found. Check its SCK/MISO/MOSI/CS/RST wiring, the "
                    "SPI DIP switches (I1=0, I2=1), and that VCC has solid 5V.");
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

// Parses an incoming @ACTION,<LANE_ID>,<STATUS>,<REASON> line from the gateway
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

  pinMode(LANE1_RST, OUTPUT);
  digitalWrite(LANE1_RST, HIGH);
  pinMode(LANE2_RST, OUTPUT);
  digitalWrite(LANE2_RST, HIGH);

  selfTestPn532(nfcLane1, "PN532 Lane 1");
  selfTestPn532(nfcLane2, "PN532 Lane 2");

  Serial.println("[ENTRANCE NODE] Ready. Tap a card on either lane.");
}

void loop(void) {
  // Listen for @ACTION replies coming back down from the Python gateway
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

  // ---- Lane 1 ----
  if (currentTime - lastScanTimeLane1 >= SCAN_COOLDOWN) {
    uint8_t uid[7];
    uint8_t uidLength;
    if (nfcLane1.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
      lastScanTimeLane1 = currentTime;
      Serial.print("@SCAN," GATE_TYPE "," LANE1_ID ",");
      printUidHex(uid, uidLength);
      Serial.println();
    }
  }

  // ---- Lane 2 ----
  if (currentTime - lastScanTimeLane2 >= SCAN_COOLDOWN) {
    uint8_t uid[7];
    uint8_t uidLength;
    if (nfcLane2.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 100)) {
      lastScanTimeLane2 = currentTime;
      Serial.print("@SCAN," GATE_TYPE "," LANE2_ID ",");
      printUidHex(uid, uidLength);
      Serial.println();
    }
  }
}
