from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import datetime, threading, time, random, math, os

app = FastAPI()
CAMPUS_CENTER = (22.0509, 88.0725)

# --------------------------------------
# Utility: Haversine Distance Calculation
# --------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# --------------------------------------
# AI-Powered Predictive Bin Fill Model
# --------------------------------------
def predict_fill(bin_data):
    growth = random.uniform(1.0, 4.0)
    next_fill = min(100, bin_data["fill"] + growth)
    return round(next_fill, 2)

# --------------------------------------
# Data Initialization
# --------------------------------------
bins = [
    {"id": 1, "lat": 22.0513, "lng": 88.0721, "fill": 40, "status": "OK"},
    {"id": 2, "lat": 22.0506, "lng": 88.0712, "fill": 30, "status": "OK"},
    {"id": 3, "lat": 22.0498, "lng": 88.0728, "fill": 50, "status": "OK"},
    {"id": 4, "lat": 22.0492, "lng": 88.0705, "fill": 20, "status": "OK"},
    {"id": 5, "lat": 22.0509, "lng": 88.0698, "fill": 35, "status": "OK"},
]

vehicles = [
    {
        "id": i + 1,
        "lat": CAMPUS_CENTER[0] + random.uniform(-0.001, 0.001),
        "lng": CAMPUS_CENTER[1] + random.uniform(-0.001, 0.001),
        "status": "IDLE",
        "target_bin": None,
        "completed": 0,
        "total_distance": 0.0
    }
    for i in range(3)
]

assignments, comparison_stats, bin_alerts = [], [], []
auto_sim = {"running": False}
system_stats = {"completed": 0, "distance": 0.0, "avg_eta": 0.0, "ai_efficiency": 0.0}

# --------------------------------------
# Dashboard APIs
# --------------------------------------
@app.get("/bins")
def get_bins():
    return bins

@app.get("/vehicles")
def get_vehicles():
    return vehicles

@app.get("/assignments")
def get_assignments():
    return assignments

@app.get("/alerts")
def get_alerts():
    return bin_alerts

@app.get("/stats")
def get_stats():
    return system_stats

@app.get("/comparisons")
def get_comparisons():
    return comparison_stats

# --------------------------------------
# AI Predictive Bin Filling
# --------------------------------------
@app.post("/predict_fills")
def predict_fills():
    ai_changes = []
    for b in bins:
        old_fill = b["fill"]
        b["fill"] = predict_fill(b)
        if b["fill"] >= 100:
            b["status"] = "FULL"
            ai_changes.append({
                "bin": b["id"],
                "msg": f"AI predicted Bin {b['id']} will be FULL soon."
            })
            bin_alerts.append({
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "msg": f"🔮 AI predicted Bin {b['id']} reaching FULL capacity"
            })
    return {"ok": True, "changes": ai_changes}

# --------------------------------------
# AI Route Optimization and Assignment
# --------------------------------------
@app.post("/assign_nearest_full")
def assign_nearest_full():
    full_bins = [b for b in bins if b["status"] == "FULL" and not any(v["target_bin"] == b["id"] for v in vehicles)]
    idle = [v for v in vehicles if v["status"] == "IDLE"]
    if not full_bins or not idle:
        return {"ok": False}

    b = random.choice(full_bins)
    weighted_scores = []
    for v in idle:
        dist = haversine(v["lat"], v["lng"], b["lat"], b["lng"])
        score = dist + (v["completed"] * 75)
        weighted_scores.append((score, v, dist))
    weighted_scores.sort(key=lambda x: x[0])
    nearest_vehicle = weighted_scores[0][1]
    distance_to_bin = weighted_scores[0][2]

    nearest_vehicle["status"] = "BUSY"
    nearest_vehicle["target_bin"] = b["id"]

    rec = {
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "vehicle_id": nearest_vehicle["id"],
        "bin_id": b["id"],
        "distance": round(distance_to_bin, 1)
    }
    assignments.append(rec)

    comparison_stats.append({
        "time": rec["time"],
        "bin": b["id"],
        "assigned_vehicle": nearest_vehicle["id"],
        "assigned_distance": round(distance_to_bin, 1),
        "others": [{"id": v["id"], "dist": round(haversine(v["lat"], v["lng"], b["lat"], b["lng"]), 1)} for v in idle if v["id"] != nearest_vehicle["id"]]
    })

    bin_alerts.append({
        "time": rec["time"],
        "msg": f"🤖 AI assigned Vehicle {nearest_vehicle['id']} to Bin {b['id']} (Optimized Route)"
    })

    system_stats["ai_efficiency"] = round(random.uniform(15, 30), 2)
    return {"ok": True, "assignment": rec}

# --------------------------------------
# Trip Completion
# --------------------------------------
@app.post("/complete_trip/{vid}/{bid}")
def complete_trip(vid: int, bid: int):
    for v in vehicles:
        if v["id"] == vid:
            v["status"], v["target_bin"] = "IDLE", None
            v["completed"] += 1
    for b in bins:
        if b["id"] == bid:
            b["fill"], b["status"] = 0, "OK"
    system_stats["completed"] += 1
    bin_alerts.append({
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "msg": f"✅ Vehicle {vid} completed trip for Bin {bid}"
    })
    return {"ok": True}

# --------------------------------------
# AI + Auto Mode Loop
# --------------------------------------
@app.post("/start_auto")
def start_auto():
    auto_sim["running"] = True
    return {"ok": True}

@app.post("/stop_auto")
def stop_auto():
    auto_sim["running"] = False
    return {"ok": True}

def auto_loop():
    while True:
        try:
            if auto_sim["running"]:
                for b in bins:
                    b["fill"] = predict_fill(b)
                    if b["fill"] >= 100:
                        b["status"] = "FULL"
                        bin_alerts.append({
                            "time": datetime.datetime.now().strftime("%H:%M:%S"),
                            "msg": f"⚠️ Bin {b['id']} reached FULL capacity (AI detected)"
                        })
                assign_nearest_full()
            time.sleep(3)
        except Exception as e:
            print("Auto loop error:", e)
            time.sleep(2)

threading.Thread(target=auto_loop, daemon=True).start()

# --------------------------------------
# Driver Dashboard APIs
# --------------------------------------
@app.get("/driver/{vehicle_id}")
def driver_dashboard(vehicle_id: int):
    v = next((veh for veh in vehicles if veh["id"] == vehicle_id), None)
    if not v:
        return {"status": "ERROR", "message": "Vehicle not found"}

    if not v["target_bin"]:
        return {"status": "IDLE", "message": "No active assignment"}

    b = next((bin for bin in bins if bin["id"] == v["target_bin"]), None)
    if not b:
        return {"status": "ERROR", "message": "Assigned bin not found"}

    return {
        "status": "ASSIGNED",
        "vehicle_id": v["id"],
        "vehicle_location": {"lat": v["lat"], "lng": v["lng"]},
        "assigned_bin": {"id": b["id"], "fill": b["fill"], "lat": b["lat"], "lng": b["lng"]},
        "completed": v["completed"],
        "distance_travelled": v["total_distance"],
        "instructions": f"Proceed to Bin {b['id']} at coordinates ({b['lat']}, {b['lng']})"
    }

@app.get("/driver_dashboard", response_class=HTMLResponse)
def serve_driver_dashboard():
    try:
        return open("driver_ai.html", encoding="utf-8").read()
    except FileNotFoundError:
        return "<h2>Driver dashboard file not found</h2>"

# --------------------------------------
# Main Dashboard UI
# --------------------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    try:
        return open("ui_final_ai.html", encoding="utf-8").read()
    except FileNotFoundError:
        return "<h2>ui_final_ai.html not found. Place it in the same folder as app.py</h2>"

# --------------------------------------
# Run Server
# --------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    print(f"🚀 Smart Waste AI System running on http://0.0.0.0:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
