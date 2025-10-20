#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <math.h>
#include <array>
#include <algorithm>

// ----------------- Wi-Fi + MQTT Configuration (ACTIVE) -----------------
const char* ssid = "Steven's Galaxy S22";
const char* password = "zycb294^";
const char* mqtt_server = "10.19.148.3";
const char* mqtt_topic = "indoor/position";

WiFiClient espClient;
PubSubClient client(espClient);

// Advanced Calibration - TUNE THESE FOR YOUR 6x6m ROOM
#define REFERENCE_RSSI -58
#define PATH_LOSS_EXPONENT 2.8
#define GRID_SIZE 0.1
#define SNAP_RESOLUTION 1.0 // Snap to nearest 1 meter
#define ROOM_SIZE 7.0 // Room Size is now 6.0 meters

// ----------------- BEACON CONFIG -----------------
struct Beacon {
  String macAddress;
  String name;
  float posX;
  float posY;
  float calibratedRefRSSI; // Individual calibration for each beacon
  float lastDistance;
  int rssi;
  int rssiReadings[20];  // Larger buffer for better filtering
  int rssiIndex;
  bool valid;
  float distanceVariance;
  unsigned long lastSeen;
};

// 6m x 6m room - strategic beacon placement for best coverage
Beacon beacons[] = {
  {"F7:23:2C:3B:84:B4", "BEACON_1", 0.0, 0.0, -58, -1, 0, {}, 0, false, 0, 0}, // Corner 1
  {"E5:BD:D7:34:2A:73", "BEACON_2", 7.0, 0.0, -58, -1, 0, {}, 0, false, 0, 0}, // Corner 2 (X=7.0)
  {"C2:E0:A6:C2:4F:F2", "BEACON_3", 0.0, 7.0, -58, -1, 0, {}, 0, false, 0, 0}, // Corner 3 (Y=7.0)
  {"FC:FE:32:00:1F:FD", "BEACON_4", 7.0, 7.0, -58, -1, 0, {}, 0, false, 0, 0} // Corner 4 (X=7.0, Y=7.0)
};

const int NUM_BEACONS = sizeof(beacons) / sizeof(beacons[0]);
const int MIN_VALID_BEACONS = 3;

BLEScan* pBLEScan;

// --- Manual Control Variables ---
bool manualControl = false;
float manualX = 3.0;
float manualY = 3.0;
unsigned long lastSerialInput = 0;
const unsigned long MANUAL_CONTROL_TIMEOUT = 10000; // 10 seconds timeout for manual control

// --- Advanced Kalman Filter (2D) ---
struct KalmanFilter2D {
  float x;       // Position X
  float y;       // Position Y
  float P[2][2]; // Covariance matrix
  float Q[2][2]; // Process noise
  float R;       // Measurement noise
};

KalmanFilter2D kf = {
  .x = 3.0,     // Start in center of 7x7 room (3.0)
  .y = 3.0,     // Start in center of 7x7 room (3.0)
  .P = {{1.0, 0.0}, {0.0, 1.0}},
  .Q = {{0.5, 0.0}, {0.0, 0.5}},
  .R = 2.0
};

// Filter tracking for filter reset
int consecutiveFallbackCycles = 0;
const int MAX_FALLBACK_CYCLES = 10;
const float FILTER_RESET_DISTANCE = 3.0;


// --- Particle Filter for Robust Positioning ---
#define NUM_PARTICLES 50
struct Particle {
  float x;
  float y;
  float weight;
};

Particle particles[NUM_PARTICLES];
bool particleFilterInitialized = false;

// --- Statistics for RSSI processing ---
struct RSSIStats {
  int median;
  int mean;
  float variance;
  bool stable;
};

// --- Custom constrain function with different name ---
float constrainValue(float val, float min_val, float max_val) {
  if (val < min_val) return min_val;
  if (val > max_val) return max_val;
  return val;
}

// --- Advanced Distance Estimation with Environmental Compensation ---
float calculateDistance(int rssi, int beaconIndex) {
  if (rssi >= 0) return -1;

  float refRSSI = beacons[beaconIndex].calibratedRefRSSI;
  float envFactor = 1.0;

  float distance = pow(10, (refRSSI - rssi) / (10 * PATH_LOSS_EXPONENT)) * envFactor;

  return constrainValue(distance, 0.1, 15.0);
}

// --- Advanced RSSI Filtering ---
RSSIStats calculateRSSIStats(int readings[], int size) {
  RSSIStats stats = {-100, -100, 0.0, false};

  int validCount = 0;
  int sum = 0;
  int validReadings[20];

  for (int i = 0; i < size; i++) {
    if (readings[i] > -100) {
      validReadings[validCount] = readings[i];
      sum += readings[i];
      validCount++;
    }
  }

  if (validCount == 0) return stats;

  stats.mean = sum / validCount;

  // Median - sort the valid readings
  for (int i = 0; i < validCount - 1; i++) {
    for (int j = i + 1; j < validCount; j++) {
      if (validReadings[i] > validReadings[j]) {
        int temp = validReadings[i];
        validReadings[i] = validReadings[j];
        validReadings[j] = temp;
      }
    }
  }
  stats.median = validReadings[validCount / 2];

  // Variance
  float varSum = 0;
  for (int i = 0; i < validCount; i++) {
    varSum += pow(validReadings[i] - stats.mean, 2);
  }
  stats.variance = varSum / validCount;

  // Stability check (low variance = stable signal)
  stats.stable = (stats.variance < 100.0);

  return stats;
}

// --- Outlier Rejection ---
bool isRSSIValid(int rssi, int beaconIndex) {
  if (rssi >= -30 || rssi <= -100) return false;

  float expectedMin = beacons[beaconIndex].calibratedRefRSSI - 40;
  float expectedMax = beacons[beaconIndex].calibratedRefRSSI + 25;

  return (rssi >= expectedMin && rssi <= expectedMax);
}

// --- BLE Callback ---
class MyAdvertisedDeviceCallbacks: public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice advertisedDevice) {
    String macAddress = advertisedDevice.getAddress().toString().c_str();
    macAddress.toUpperCase();

    for (int i = 0; i < NUM_BEACONS; i++) {
      String targetMac = beacons[i].macAddress;
      targetMac.toUpperCase();

      if (macAddress == targetMac) {
        int rssi = advertisedDevice.getRSSI();

        if (!isRSSIValid(rssi, i)) {
          return;
        }

        beacons[i].rssiReadings[beacons[i].rssiIndex] = rssi;
        beacons[i].rssiIndex = (beacons[i].rssiIndex + 1) % 20;
        beacons[i].lastSeen = millis();

        RSSIStats stats = calculateRSSIStats(beacons[i].rssiReadings, 20);

        beacons[i].rssi = stats.median;
        beacons[i].lastDistance = calculateDistance(beacons[i].rssi, i);
        beacons[i].valid = stats.stable;
        beacons[i].distanceVariance = stats.variance;

        Serial.printf("🎯 %s | RSSI: %d (mean: %d) | Dist: %.2fm | Var: %.1f | %s\n",
                      beacons[i].name.c_str(),
                      beacons[i].rssi, stats.mean,
                      beacons[i].lastDistance,
                      stats.variance,
                      stats.stable ? "Stable" : "Unstable");
        break;
      }
    }
  }
};

// --- Serial Input Handler ---
void handleSerialInput() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    input.trim();
    
    // Check if input is in format "x,y"
    int commaIndex = input.indexOf(',');
    if (commaIndex > 0) {
      String xStr = input.substring(0, commaIndex);
      String yStr = input.substring(commaIndex + 1);
      
      float newX = xStr.toFloat();
      float newY = yStr.toFloat();
      
      // Validate coordinates
      if (newX >= 0 && newX <= ROOM_SIZE && newY >= 0 && newY <= ROOM_SIZE) {
        manualX = newX;
        manualY = newY;
        manualControl = true;
        lastSerialInput = millis();
        
        Serial.printf("🎮 MANUAL CONTROL: Position set to (%.2f, %.2f)\n", manualX, manualY);
        Serial.println("Type 'auto' to return to automatic positioning");
      } else {
        Serial.println("❌ Invalid coordinates! Use format: x,y (0-6)");
      }
    } 
    // Check for "auto" command to return to automatic mode
    else if (input.equalsIgnoreCase("auto")) {
      manualControl = false;
      Serial.println("🔄 Returning to AUTOMATIC positioning mode");
    }
    // Check for "help" command
    else if (input.equalsIgnoreCase("help")) {
      Serial.println("\n📋 SERIAL COMMANDS:");
      Serial.println("  x,y          - Set manual position (e.g., 2.5,3.0)");
      Serial.println("  auto         - Return to automatic positioning");
      Serial.println("  help         - Show this help message");
      Serial.println("  test         - Run test sequence");
      Serial.println("  Manual position range: 0.0 to 6.0 for both X and Y");
    }
    // Test command
    else if (input.equalsIgnoreCase("test")) {
      Serial.println("🧪 Running test sequence...");
      runTestSequence();
    }
  }
  
  // Auto-return to automatic mode after timeout
  if (manualControl && (millis() - lastSerialInput > MANUAL_CONTROL_TIMEOUT)) {
    manualControl = false;
    Serial.println("⏰ Manual control timeout - returning to automatic mode");
  }
}

// --- Test Sequence ---
void runTestSequence() {
  Serial.println("\n🧪 TEST SEQUENCE STARTED");
  Serial.println("Moving through predefined positions...");
  
  // Test positions
  float testPositions[][2] = {
    {0.0, 0.0}, {1.5, 1.5}, {3.0, 3.0}, {4.5, 4.5}, {6.0, 6.0},
    {3.0, 0.0}, {0.0, 3.0}, {6.0, 3.0}, {3.0, 6.0}
  };
  
  int numTests = sizeof(testPositions) / sizeof(testPositions[0]);
  
  for (int i = 0; i < numTests; i++) {
    manualX = testPositions[i][0];
    manualY = testPositions[i][1];
    manualControl = true;
    
    // Apply snapping with offset to test positions
    float snappedX = round(manualX / SNAP_RESOLUTION) * SNAP_RESOLUTION;
    float snappedY = round(manualY / SNAP_RESOLUTION) * SNAP_RESOLUTION;
    
    // Apply 0.5m offset to snapped coordinates
    snappedX += 0.5;
    snappedY += 0.5;
    
    snappedX = constrainValue(snappedX, 0.0, ROOM_SIZE);
    snappedY = constrainValue(snappedY, 0.0, ROOM_SIZE);
    
    Serial.printf("🧪 TEST %d/%d: Manual(%.1f,%.1f) -> Snapped(%.1f,%.1f) -> Final(%.1f,%.1f)\n",
                  i+1, numTests, manualX, manualY, 
                  round(manualX / SNAP_RESOLUTION) * SNAP_RESOLUTION,
                  round(manualY / SNAP_RESOLUTION) * SNAP_RESOLUTION,
                  snappedX, snappedY);
    
    delay(2000); // Wait 2 seconds between test positions
  }
  
  manualControl = false;
  Serial.println("🧪 TEST SEQUENCE COMPLETED");
  Serial.println("Returning to automatic mode");
}

// --- Initialize Particle Filter ---
void initializeParticleFilter() {
  randomSeed(analogRead(0));
  for (int i = 0; i < NUM_PARTICLES; i++) {
    particles[i].x = random(0, (int)(ROOM_SIZE * 100)) / 100.0;
    particles[i].y = random(0, (int)(ROOM_SIZE * 100)) / 100.0;
    particles[i].weight = 1.0 / NUM_PARTICLES;
  }
  particleFilterInitialized = true;
  Serial.println("Particle Filter Initialized");
}

// --- Initialize Particle Filter at a specific point (for resets) ---
void initializeParticleFilterAtPoint(float x, float y) {
  randomSeed(analogRead(0));
  for (int i = 0; i < NUM_PARTICLES; i++) {
    // Spread particles slightly around the measured point
    particles[i].x = x + (random(0, 41) - 20) / 100.0;
    particles[i].y = y + (random(0, 41) - 20) / 100.0;

    particles[i].x = constrainValue(particles[i].x, 0, ROOM_SIZE);
    particles[i].y = constrainValue(particles[i].y, 0, ROOM_SIZE);

    particles[i].weight = 1.0 / NUM_PARTICLES;
  }
  particleFilterInitialized = true;
  Serial.printf("Particle Filter Re-initialized at (%.2f, %.2f)\n", x, y);
}


// --- Particle Filter Update ---
void updateParticleFilter(float measuredX, float measuredY, float measurementUncertainty) {
  if (!particleFilterInitialized) {
    // Default initialization if never run
    initializeParticleFilter();
    // After initialization, run the update for the first time
    if (!particleFilterInitialized) return;
  }

  // Predict (add small random movement)
  for (int i = 0; i < NUM_PARTICLES; i++) {
    particles[i].x += (random(0, 41) - 20) / 100.0;
    particles[i].y += (random(0, 41) - 20) / 100.0;

    particles[i].x = constrainValue(particles[i].x, 0, ROOM_SIZE);
    particles[i].y = constrainValue(particles[i].y, 0, ROOM_SIZE);

    // Update weights based on measurement
    float dx = particles[i].x - measuredX;
    float dy = particles[i].y - measuredY;
    float distance = sqrt(dx * dx + dy * dy);
    particles[i].weight = exp(-distance * distance / (2 * measurementUncertainty * measurementUncertainty));
  }

  // Normalize weights
  float weightSum = 0;
  for (int i = 0; i < NUM_PARTICLES; i++) {
    weightSum += particles[i].weight;
  }

  if (weightSum > 0) {
    for (int i = 0; i < NUM_PARTICLES; i++) {
      particles[i].weight /= weightSum;
    }
  }

  // Resample if needed
  float effectiveParticles = 0;
  for (int i = 0; i < NUM_PARTICLES; i++) {
    effectiveParticles += particles[i].weight * particles[i].weight;
  }
  effectiveParticles = 1.0 / effectiveParticles;

  if (effectiveParticles < NUM_PARTICLES / 2) {
    // Resampling needed
    Particle newParticles[NUM_PARTICLES];
    float cumulativeWeights[NUM_PARTICLES];

    cumulativeWeights[0] = particles[0].weight;
    for (int i = 1; i < NUM_PARTICLES; i++) {
      cumulativeWeights[i] = cumulativeWeights[i-1] + particles[i].weight;
    }

    for (int i = 0; i < NUM_PARTICLES; i++) {
      float r = (float)random(0, 1000) / 1000.0;
      for (int j = 0; j < NUM_PARTICLES; j++) {
        if (r <= cumulativeWeights[j]) {
          newParticles[i] = particles[j];
          newParticles[i].weight = 1.0 / NUM_PARTICLES;
          break;
        }
      }
    }

    // Copy new particles back
    for (int i = 0; i < NUM_PARTICLES; i++) {
      particles[i] = newParticles[i];
    }
  }
}

// --- Get Position from Particle Filter ---
void getParticleFilterPosition(float &x, float &y) {
  x = 0; y = 0;
  for (int i = 0; i < NUM_PARTICLES; i++) {
    x += particles[i].x * particles[i].weight;
    y += particles[i].y * particles[i].weight;
  }
}

// --- Advanced Multilateration with Error Estimation (IDW P=3) ---
bool calculatePosition(float &x, float &y, float &uncertainty) {
  int validCount = 0;
  float weights[NUM_BEACONS];
  float totalWeight = 0;

  // Calculate weights based on signal quality (for normalization and error calculation)
  for (int i = 0; i < NUM_BEACONS; i++) {
    if (beacons[i].valid && beacons[i].lastDistance > 0) {
      validCount++;
      // Calculate a normalized weight based on variance and inverse distance
      weights[i] = 1.0 / (beacons[i].distanceVariance + 1.0) * (1.0 / beacons[i].lastDistance);
      totalWeight += weights[i];
    } else {
      weights[i] = 0;
    }
  }

  if (validCount < MIN_VALID_BEACONS) {
    return false;
  }

  // Normalize weights (used only for uncertainty estimation later)
  for (int i = 0; i < NUM_BEACONS; i++) {
    if (totalWeight > 0) weights[i] /= totalWeight;
  }

  // Simple Inverse Distance Weighted (IDW) Average with P=3
  x = 0; y = 0;
  float finalWeightSum = 0;

  for (int i = 0; i < NUM_BEACONS; i++) {
      if (beacons[i].valid && beacons[i].lastDistance > 0) {
          // Use Inverse Distance Cubed (P=3) to make the nearest beacon dominate
          float pullFactor = 1.0 / pow(beacons[i].lastDistance, 3.0);

          x += beacons[i].posX * pullFactor;
          y += beacons[i].posY * pullFactor;

          finalWeightSum += pullFactor;
      }
  }

  // Normalize the position by the total pull strength
  if (finalWeightSum > 0) {
      x /= finalWeightSum;
      y /= finalWeightSum;
  } else {
      return false;
  }

  // Estimate uncertainty based on trilateration error
  uncertainty = 0;
  for (int i = 0; i < NUM_BEACONS; i++) {
    if (weights[i] > 0) {
      float dx = x - beacons[i].posX;
      float dy = y - beacons[i].posY;
      float expectedDistance = sqrt(dx * dx + dy * dy);
      float error = fabs(expectedDistance - beacons[i].lastDistance);
      uncertainty += error * weights[i];
    }

  }

  uncertainty = constrainValue(uncertainty, 0.1, 2.0); // Constrain max uncertainty

  return true;
}

// --- Kalman Filter Update ---
void updateKalmanFilter(float measuredX, float measuredY, float uncertainty) {
  // Predict
  kf.P[0][0] += kf.Q[0][0];
  kf.P[1][1] += kf.Q[1][1];

  // Update
  float S_x = kf.P[0][0] + uncertainty;
  float S_y = kf.P[1][1] + uncertainty;

  float K_x = kf.P[0][0] / S_x;
  float K_y = kf.P[1][1] / S_y;

  kf.x += K_x * (measuredX - kf.x);
  kf.y += K_y * (measuredY - kf.y);

  kf.P[0][0] = (1 - K_x) * kf.P[0][0];
  kf.P[1][1] = (1 - K_y) * kf.P[1][1];
}

// --- Wi-Fi + MQTT Helpers (ACTIVE) ---
void setup_wifi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected ✅");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  // 1. Check/Reconnect WiFi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi connection lost. Attempting to reconnect WiFi...");
    setup_wifi();
  }

  // 2. Check/Reconnect MQTT
  while (!client.connected() && WiFi.status() == WL_CONNECTED) {
    Serial.print("Attempting MQTT connection...");
    // Attempt to connect
    if (client.connect("ESP32Tag")) {
      Serial.println("MQTT connected ✅");
    } else {
      Serial.print("MQTT connection failed, rc=");
      Serial.print(client.state());
      Serial.println(" trying again in 5 seconds");
      delay(5000);
    }
  }
}

// --- Setup ---
void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("==========================================");
  Serial.println("ESP32 INDOOR POSITIONING - MQTT ACTIVE");
  Serial.println("==========================================");
  Serial.println("Beacon Configuration (6x6m):");
  for (int i = 0; i < NUM_BEACONS; i++) {
    Serial.printf("  %s: (%.1f, %.1f) | RefRSSI: %.0f\n",
                  beacons[i].name.c_str(),
                  beacons[i].posX,
                  beacons[i].posY,
                  beacons[i].calibratedRefRSSI);
  }

  Serial.println("\n📋 SERIAL COMMANDS:");
  Serial.println("  x,y          - Set manual position (e.g., 2.5,3.0)");
  Serial.println("  auto         - Return to automatic positioning");
  Serial.println("  test         - Run test sequence");
  Serial.println("  help         - Show help message");
  Serial.println("  Manual position range: 0.0 to 6.0 for both X and Y");
  Serial.println("\n📍 OUTPUT: Serial Monitor + MQTT to Pi");
  Serial.println("==========================================\n");

  BLEDevice::init("ESP32_Positioning_Tag");
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new MyAdvertisedDeviceCallbacks());
  pBLEScan->setActiveScan(true);
  pBLEScan->setInterval(100);
  pBLEScan->setWindow(99);

  // Initialize RSSI buffers
  for (int i = 0; i < NUM_BEACONS; i++) {
    for (int j = 0; j < 20; j++) {
      beacons[i].rssiReadings[j] = -100;
    }
  }

  // Enable WiFi and MQTT
  setup_wifi();
  client.setServer(mqtt_server, 1883);
}

// --- Main Loop ---
void loop() {
  // Handle serial input for manual control
  handleSerialInput();
  
  // Check and reconnect Wi-Fi and MQTT if needed
  if (!client.connected() || WiFi.status() != WL_CONNECTED) {
    reconnect();
  }
  client.loop(); // Keeps the MQTT client alive and processes messages

  // Perform BLE scan
  BLEScanResults foundDevices = pBLEScan->start(2, false);

  // Check beacon validity based on last seen time
  unsigned long currentTime = millis();
  for (int i = 0; i < NUM_BEACONS; i++) {
    if (currentTime - beacons[i].lastSeen > 10000) { // 10 seconds timeout
      beacons[i].valid = false;
    }
  }

  float rawX, rawY, uncertainty;
  int validBeacons = 0;
  for (int i = 0; i < NUM_BEACONS; i++) {
    if (beacons[i].valid) validBeacons++;
  }

  // Attempt to calculate position using trilateration (IDW)
  bool rawPositionAvailable = calculatePosition(rawX, rawY, uncertainty);

  // --- Position Calculation Variables ---
  float measurementX = 0.0;
  float measurementY = 0.0;
  float finalReportedUncertainty = 0.0;

  // --- Determine Measurement for Filtering ---
  if (rawPositionAvailable) {
    // Case 1: Raw trilateration is GOOD (>= MIN_VALID_BEACONS)
    measurementX = rawX;
    measurementY = rawY;
    finalReportedUncertainty = uncertainty;

    // FILTER SNAP: Check if the new raw position is significantly different from the current filter state
    float dx_reset = rawX - kf.x;
    float dy_reset = rawY - kf.y;
    float distance_diff = sqrt(dx_reset * dx_reset + dy_reset * dy_reset);

    if (distance_diff > FILTER_RESET_DISTANCE) {
        Serial.println("⚡ Filter SNAP: Raw position significantly different. Forcing filter reset.");

        // Reset Kalman Filter state immediately to the new accurate raw position
        kf.x = rawX;
        kf.y = rawY;
        kf.P[0][0] = 1.0;
        kf.P[1][1] = 1.0;

        // Reset Particle Filter immediately to the new accurate raw position
        initializeParticleFilterAtPoint(rawX, rawY);

        measurementX = rawX;
        measurementY = rawY;
    }

    Serial.printf("✅ Good beacons: %d/%d | Raw Pos: (%.2f, %.2f)\n", validBeacons, NUM_BEACONS, rawX, rawY);

    consecutiveFallbackCycles = 0; // RESET counter on success

  } else {
    // Case 2: Insufficient beacons. Fallback to last position with high uncertainty.
    measurementX = kf.x;
    measurementY = kf.y;

    finalReportedUncertainty = ROOM_SIZE / 2.0; // Set high uncertainty (3.0m)

    consecutiveFallbackCycles++; // INCREMENT counter on failure

    Serial.printf("⚠️ Insufficient beacons: %d/%d (need %d). Using filtered POS with high uncertainty (%.2fm).\n",
                  validBeacons, NUM_BEACONS, MIN_VALID_BEACONS, finalReportedUncertainty);
  }

  // CHECK FOR FILTER STUCK/LOST
  if (consecutiveFallbackCycles > MAX_FALLBACK_CYCLES) {
    Serial.println("🔥 Filter Reset: Too many fallback cycles. Re-initializing position to center.");

    // Reset Kalman Filter state to center
    kf.x = ROOM_SIZE / 2.0;
    kf.y = ROOM_SIZE / 2.0;
    kf.P[0][0] = 10.0;
    kf.P[1][1] = 10.0;

    // Reset Particle Filter to center
    initializeParticleFilterAtPoint(kf.x, kf.y);

    consecutiveFallbackCycles = 0;

    measurementX = kf.x;
    measurementY = kf.y;
  }

  // --- ALWAYS RUN FILTERS ---

  float kalmanUpdateNoise = rawPositionAvailable ? finalReportedUncertainty : (kf.R * 10.0);

  if (rawPositionAvailable) {
    updateKalmanFilter(measurementX, measurementY, kalmanUpdateNoise);
  } else {
    updateKalmanFilter(kf.x, kf.y, kalmanUpdateNoise);
  }

  updateParticleFilter(kf.x, kf.y, finalReportedUncertainty);

  float finalX, finalY;
  getParticleFilterPosition(finalX, finalY);

  // Grid snapping with 0.5m offset
  float snappedX = round(finalX / SNAP_RESOLUTION) * SNAP_RESOLUTION;
  float snappedY = round(finalY / SNAP_RESOLUTION) * SNAP_RESOLUTION;
  
  // Apply 0.5m offset to snapped coordinates
  snappedX += 0.5;
  snappedY += 0.5;
  
  snappedX = constrainValue(snappedX, 0.0, ROOM_SIZE);
  snappedY = constrainValue(snappedY, 0.0, ROOM_SIZE);

  // Print the final result
  Serial.printf("📍 FINAL POS: Filtered(%.2f,%.2f) -> Snapped(%.2f,%.2f) -> Final(%.2f,%.2f) | Unc: %.2fm\n",
                finalX, finalY, 
                round(finalX / SNAP_RESOLUTION) * SNAP_RESOLUTION,  // Original snapped
                round(finalY / SNAP_RESOLUTION) * SNAP_RESOLUTION,  // Original snapped
                snappedX, snappedY,  // Final with offset
                finalReportedUncertainty);

  // --- MQTT PUBLISHING TO PI (RE-ENABLED) ---
  if (client.connected()) {
    char payload[64];
    
    if (manualControl) {
      // Use manual coordinates (apply same snapping with offset to manual positions)
      float manualSnappedX = round(manualX / SNAP_RESOLUTION) * SNAP_RESOLUTION;
      float manualSnappedY = round(manualY / SNAP_RESOLUTION) * SNAP_RESOLUTION;
      
      // Apply 0.5m offset to manual snapped coordinates
      manualSnappedX += 0.5;
      manualSnappedY += 0.5;
      
      manualSnappedX = constrainValue(manualSnappedX, 0.0, ROOM_SIZE);
      manualSnappedY = constrainValue(manualSnappedY, 0.0, ROOM_SIZE);
      
      sprintf(payload, "%.2f,%.2f,%.2f", manualSnappedX, manualSnappedY, 0.1);
      Serial.printf("🎮 MQTT MANUAL: (%.2f,%.2f,%.2f) | Manual(%.2f,%.2f) -> Snapped(%.2f,%.2f) -> Final(%.2f,%.2f)\n", 
                    manualSnappedX, manualSnappedY, 0.1, manualX, manualY, 
                    round(manualX / SNAP_RESOLUTION) * SNAP_RESOLUTION,
                    round(manualY / SNAP_RESOLUTION) * SNAP_RESOLUTION,
                    manualSnappedX, manualSnappedY);
    } else {
      // Use calculated coordinates
      sprintf(payload, "%.2f,%.2f,%.2f", snappedX, snappedY, finalReportedUncertainty);
      Serial.printf("📍 MQTT AUTOMATIC: (%.2f,%.2f,%.2f)\n", snappedX, snappedY, finalReportedUncertainty);
    }
    
    client.publish(mqtt_topic, payload);
    Serial.println("📤 Data published to MQTT");
  } else {
    Serial.println("❌ MQTT not connected. Cannot publish.");
  }

  pBLEScan->clearResults();
  delay(1000);
}
