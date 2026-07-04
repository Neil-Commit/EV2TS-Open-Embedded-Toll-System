#include <SPI.h>
#include <Wire.h>
#include <string.h>
#include <Adafruit_PN532.h>

// ---- Shared SPI bus ----
#define SPI_SCK   (18)
#define SPI_MISO  (19)
#define SPI_MOSI  (23)

// ---- Per-reader CS and RST ----
#define L1_SS   (5)
#define L1_RST  (4)
#define L2_SS   (16)
#define L2_RST  (17)
#define L3_SS   (21)
#define L3_RST  (22)
#define L4_SS   (32)
#define L4_RST  (33)

#define GATE_TYPE "EXIT"

// All four instances share the same SCK/MISO/MOSI pins.
// Each gets a unique SS pin -- that's what isolates them on the bus.
Adafruit_PN532 nfc1(SPI_SCK, SPI_MISO, SPI_MOSI, L1_SS); // Valenzuela
Adafruit_PN532 nfc2(SPI_SCK, SPI_MISO, SPI_MOSI, L2_SS); // Meycauayan
Adafruit_PN532 nfc3(SPI_SCK, SPI_MISO, SPI_MOSI, L3_SS); // Marilao
Adafruit_PN532 nfc4(SPI_SCK, SPI_MISO, SPI_MOSI, L4_SS); // Bocaue

const uint32_t SCAN_COOLDOWN = 2000;
uint32_t lastScan1 = 0, lastScan2 = 0, lastScan3 = 0, lastScan4 = 0;

void printUidHex(uint8_t* uid, uint8_t len) {
  for (uint8_t i = 0; i < len; i++) {
    if (uid[i] < 0x10) Serial.print("0");
    Serial.print(uid[i], HEX);
  }
}

// THE CRITICAL BUS-SHARING FIX (GitHub issue #61):
// Drive ALL CS pins HIGH before calling begin() on any reader.
// Without this, every CS is LOW by default (selected), and begin()
// on one reader broadcasts to all of them simultaneously, corrupting
// every transaction that follows.
void deassertAllCS() {
  pinMode(L1_SS, OUTPUT); digitalWrite(L1_SS, HIGH);
  pinMode(L2_SS, OUTPUT); digitalWrite(L2_SS, HIGH);
  pinMode(L3_SS, OUTPUT); digitalWrite(L3_SS, HIGH);
  pinMode(L4_SS, OUTPUT); digitalWrite(L4_SS, HIGH);
}

bool selfTest(Adafruit_PN532 &nfc, const char* label) {
  nfc.begin();
  uint32_t v = nfc.getFirmwareVersion();
  if (!v) {
    Serial.print("[ERROR] "); Serial.print(label);
    Serial.println(" not found. Check CS/RST wiring, DIP switches (I1=0, I2=1), and 5V power.");
    return false;
  }
  Serial.print("[OK] "); Serial.print(label);
  Serial.print(" firmware "); Serial.print((v >> 24) & 0xFF);
  Serial.print("."); Serial.println((v >> 16) & 0xFF);
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
    Serial.print("BARRIER WOULD OPEN ("); Serial.print(reason); Serial.println(")");
  } else {
    Serial.print("BARRIER STAYS CLOSED -- "); Serial.println(reason);
  }
}

void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);

  // Pulse RST HIGH on all readers
  pinMode(L1_RST, OUTPUT); digitalWrite(L1_RST, HIGH);
  pinMode(L2_RST, OUTPUT); digitalWrite(L2_RST, HIGH);
  pinMode(L3_RST, OUTPUT); digitalWrite(L3_RST, HIGH);
  pinMode(L4_RST, OUTPUT); digitalWrite(L4_RST, HIGH);

  // CRITICAL: deassert ALL CS lines before the first begin()
  deassertAllCS();

  // Now it's safe to init each reader in turn --
  // only the target CS goes LOW during each begin(), the rest stay HIGH
  selfTest(nfc1, "PN532 L1 (Valenzuela)");  deassertAllCS();
  selfTest(nfc2, "PN532 L2 (Meycauayan)");  deassertAllCS();
  selfTest(nfc3, "PN532 L3 (Marilao)");     deassertAllCS();
  selfTest(nfc4, "PN532 L4 (Bocaue)");      deassertAllCS();

  Serial.println("[EXIT NODE] Ready — Valenzuela / Meycauayan / Marilao / Bocaue");
}

// Helper: poll one reader, emit @SCAN if a card is found
void pollLane(Adafruit_PN532 &nfc, const char* laneId,
              uint32_t &lastScanTime, uint32_t currentTime) {
  if (currentTime - lastScanTime < SCAN_COOLDOWN) return;
  uint8_t uid[7]; uint8_t uidLen;
  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLen, 100)) {
    lastScanTime = currentTime;
    deassertAllCS(); // re-deassert after transaction -- defensive, good practice
    Serial.print("@SCAN," GATE_TYPE ",");
    Serial.print(laneId);
    Serial.print(",");
    printUidHex(uid, uidLen);
    Serial.println();
  }
}

void loop(void) {
  // Listen for @ACTION replies from the Python gateway
  static char buf[64];
  static int bufIdx = 0;
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (bufIdx > 0) { buf[bufIdx] = '\0'; handleActionLine(buf); bufIdx = 0; }
    } else if (bufIdx < 63) {
      buf[bufIdx++] = c;
    }
  }

  uint32_t now = millis();
  pollLane(nfc1, "1", lastScan1, now); // Valenzuela
  pollLane(nfc2, "2", lastScan2, now); // Meycauayan
  pollLane(nfc3, "3", lastScan3, now); // Marilao
  pollLane(nfc4, "4", lastScan4, now); // Bocaue
}
