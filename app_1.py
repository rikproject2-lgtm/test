from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import datetime
import threading
import time
import random
import math
import os

app = FastAPI()
CAMPUS_CENTER = (22.0509, 88.0725)

# ------------------------------
# Blynk placeholders (optional)
# ------------------------------
BLYNK_TEMPLATE_ID = "TMPL3ZHnAAMIw"
BLYNK_AUTH_TOKEN = "hpOQDbsw9BUEWc5fsZYvnqqWhqouM102"

# ------------------------------
# Haversine Distance (meters)
# ------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

# ------------------------------
# Simulated Predictive Model
# ------------------------------
def predict_fill(bin_data):
    # Lightweight simulated model: small stochastic growth with time-of-day bias
    hour = datetime.datetime.now().hour
    base = 0.6 if 6 <= hour <= 20 else 0.2
    growth = random.uniform(base, base + 2.5)
    next_fill = min(100.0, float(bin_data.get("fill", 0)) + growth)
    return round(next_fill, 2)

# ------------------------------
# Core Data Structures
# ------------------------------
bins = [
    {"id": 1, "lat": 22.0513, "lng": 88.0721, "fill": 40.0, "status": "OK"},
    {"id": 2, "lat": 22.0506, "lng": 88.0712, "fill": 30.0, "status": "OK"},
    {"id": 3, "lat": 22.0498, "lng": 88.0728, "fill": 50.0, "status": "OK"},
    {"id": 4, "lat": 22.0492, "lng": 88.0705, "fill": 20.0, "status": "OK"},
    {"id": 5, "lat": 22.0509, "lng": 88.0698, "fill": 35.0, "status": "OK"},
]

vehicles = [
    {
        "id": i + 1,
        "lat": CAMPUS_CENTER[0] + random.uniform(-0.0008, 0.0008),
        "lng": CAMPUS_CENTER[1] + random.uniform(-0.0008, 0.0008),
        "status": "IDLE",
        "target_bin": None,
        "completed": 0,
        "total_distance": 0.0,
        # internal movement state
        "_moving": False,
        "_target_path": None,
        "_speed_m_s": 5.6  # 20 km/h default, can be adjusted per vehicle
    }
    for i in range(3)
]

assignments = []
comparison_stats = []
bin_alerts = []
auto_sim = {"running": False}
system_stats = {
    "completed": 0,
    "distance": 0.0,
    "avg_eta": 0.0,
    "ai_efficiency": 0.0,
    "trips_over_time": []  # for performance chart
}

# ------------------------------
# Utility helpers
# ------------------------------
def now_str():
    return datetime.datetime.now().strftime("%H:%M:%S")

def distance_m(p1, p2):
    return haversine(p1[0], p1[1], p2[0], p2[1])

def compute_eta_seconds(distance_meters, speed_m_s):
    if speed_m_s <= 0:
        return 0
    return distance_meters / speed_m_s

def record_comparison(rec):
    comparison_stats.append(rec)
    # keep recent 200 records for memory safety
    if len(comparison_stats) > 500:
        comparison_stats.pop(0)

# ------------------------------
# Read-only APIs
# ------------------------------
@app.get("/bins")
def get_bins():
    return bins

@app.get("/vehicles")
def get_vehicles():
    return vehicles

@app.get("/assignments")
def get_assignments():
    return assignments

@app.get("/comparisons")
def get_comparisons():
    return comparison_stats

@app.get("/alerts")
def get_alerts():
    return bin_alerts

@app.get("/stats")
def get_stats():
    return system_stats

# ------------------------------
# Predictive Bin Fill (AI Layer)
# ------------------------------
@app.post("/predict_fills")
def predict_fills():
    updated = []
    for b in bins:
        before = b["fill"]
        new_fill = predict_fill(b)
        b["fill"] = new_fill
        if new_fill >= 100 and b["status"] != "FULL":
            b["status"] = "FULL"
            bin_alerts.append({
                "time": now_str(),
                "msg": f"🔮 Predicted FULL Bin {b['id']} (AI Forecast)"
            })
        updated.append(b.copy())
    return {"ok": True, "bins": updated}

# ------------------------------
# Random Fill for Simulation
# ------------------------------
@app.post("/fill_random")
def fill_random():
    b = random.choice(bins)
    b["fill"] = min(100.0, b["fill"] + random.randint(20, 40))
    if b["fill"] >= 100:
        b["fill"], b["status"] = 100.0, "FULL"
        bin_alerts.append({
            "time": now_str(),
            "msg": f"⚠️ Bin {b['id']} is FULL and sent an alert"
        })
    return {"ok": True, "bin": b}

# ------------------------------
# Assign Nearest Vehicle (Dynamic Optimization)
# ------------------------------
@app.post("/assign_nearest_full")
def assign_nearest_full():
    full_bins = [b for b in bins if b["status"] == "FULL" and not any(v["target_bin"] == b["id"] for v in vehicles)]
    idle = [v for v in vehicles if v["status"] == "IDLE"]
    if not full_bins or not idle:
        return {"ok": False}

    # Choose the most urgent bin (max fill) then optimize vehicle
    full_bins.sort(key=lambda x: (-x["fill"], x["id"]))
    b = full_bins[0]

    weighted_scores = []
    for v in idle:
        dist = haversine(v["lat"], v["lng"], b["lat"], b["lng"])
        score = dist + (v["completed"] * 50)  # bias toward less-worked vehicles
        weighted_scores.append((score, v, dist))
    weighted_scores.sort(key=lambda x: x[0])

    nearest_vehicle = weighted_scores[0][1]
    distance_to_bin = weighted_scores[0][2]

    nearest_vehicle["status"] = "BUSY"
    nearest_vehicle["target_bin"] = b["id"]
    # prepare internal path (straight-line; client-side routing can show realistic roads)
    nearest_vehicle["_moving"] = True
    nearest_vehicle["_target_path"] = [(nearest_vehicle["lat"], nearest_vehicle["lng"]), (b["lat"], b["lng"])]

    rec = {
        "time": now_str(),
        "vehicle_id": nearest_vehicle["id"],
        "bin_id": b["id"],
        "distance": round(distance_to_bin, 1)
    }
    assignments.append(rec)

    comp = {
        "time": rec["time"],
        "bin": b["id"],
        "assigned_vehicle": nearest_vehicle["id"],
        "assigned_distance": round(distance_to_bin, 1),
        "others": [{"id": v["id"], "dist": round(haversine(v["lat"], v["lng"], b["lat"], b["lng"]), 1)} for v in idle if v["id"] != nearest_vehicle["id"]]
    }
    record_comparison(comp)

    bin_alerts.append({
        "time": rec["time"],
        "msg": f"🚗 Vehicle {nearest_vehicle['id']} assigned to Bin {b['id']} dynamically (AI Route Optimization)"
    })

    return {"ok": True, "assignment": rec, "comparison": comp}

# ------------------------------
# Complete trip endpoint (called by internal loop or client)
# ------------------------------
@app.post("/complete_trip/{vid}/{bid}")
def complete_trip(vid: int, bid: int):
    v = next((x for x in vehicles if x["id"] == vid), None)
    b = next((x for x in bins if x["id"] == bid), None)
    if not v or not b:
        return JSONResponse({"ok": False, "msg": "vehicle or bin not found"}, status_code=404)

    # finalize vehicle and bin
    v["status"], v["target_bin"] = "IDLE", None
    v["_moving"] = False
    v["_target_path"] = None
    v["completed"] = v.get("completed", 0) + 1

    b["fill"], b["status"] = 0.0, "OK"

    system_stats["completed"] += 1
    # update trips_over_time for dashboard chart
    system_stats["trips_over_time"].append({"time": now_str(), "completed": system_stats["completed"]})
    # keep short history to avoid memory issues
    if len(system_stats["trips_over_time"]) > 200:
        system_stats["trips_over_time"].pop(0)

    bin_alerts.append({
        "time": now_str(),
        "msg": f"✅ Vehicle {vid} completed trip for Bin {bid}"
    })
    return {"ok": True}

# ------------------------------
# Reset operations
# ------------------------------
@app.post("/reset")
def reset_all():
    for v in vehicles:
        v.update({
            "status": "IDLE",
            "target_bin": None,
            "lat": CAMPUS_CENTER[0] + random.uniform(-0.0008, 0.0008),
            "lng": CAMPUS_CENTER[1] + random.uniform(-0.0008, 0.0008),
            "completed": 0,
            "total_distance": 0.0,
            "_moving": False,
            "_target_path": None
        })
    assignments.clear()
    comparison_stats.clear()
    bin_alerts.clear()
    system_stats["completed"] = 0
    system_stats["distance"] = 0.0
    system_stats["avg_eta"] = 0.0
    system_stats["trips_over_time"].clear()
    auto_sim["running"] = False
    return {"ok": True}

@app.post("/reset_vehicles")
def reset_vehicles():
    for v in vehicles:
        v.update({
            "status": "IDLE",
            "target_bin": None,
            "lat": CAMPUS_CENTER[0] + random.uniform(-0.0008, 0.0008),
            "lng": CAMPUS_CENTER[1] + random.uniform(-0.0008, 0.0008),
            "completed": 0,
            "total_distance": 0.0,
            "_moving": False,
            "_target_path": None
        })
    return {"ok": True}

# ------------------------------
# Auto mode toggles
# ------------------------------
@app.post("/start_auto")
def start_auto():
    auto_sim["running"] = True
    return {"ok": True}

@app.post("/stop_auto")
def stop_auto():
    auto_sim["running"] = False
    return {"ok": True}

# ------------------------------
# Background auto loop: predict fills and assign vehicles
# ------------------------------
def auto_loop():
    while True:
        try:
            if auto_sim["running"]:
                # Predictive fills (AI)
                for b in bins:
                    b["fill"] = predict_fill(b)
                    if b["fill"] >= 100:
                        b["status"] = "FULL"
                        bin_alerts.append({
                            "time": now_str(),
                            "msg": f"⚠️ Bin {b['id']} reached FULL capacity (AI detected)"
                        })
                # Assign vehicles to full bins
                assign_nearest_full()
            time.sleep(3.0)
        except Exception as e:
            # keep loop alive on errors
            print("Auto loop error:", e)
            time.sleep(1.0)

threading.Thread(target=auto_loop, daemon=True).start()

# ------------------------------
# Movement loop: move vehicles along straight-line path toward assigned bin
# This ensures server-side positions update so client dashboards and driver pages see live movement.
# ------------------------------
def movement_loop():
    tick = 0.5  # seconds per update
    while True:
        try:
            for v in vehicles:
                if v.get("_moving") and v.get("_target_path"):
                    path = v["_target_path"]
                    if len(path) >= 2:
                        start = path[0]
                        end = path[-1]
                        # compute vector and move a small step depending on speed
                        total_dist = haversine(start[0], start[1], end[0], end[1])  # meters
                        if total_dist <= 2.5:
                            # Teleport to destination if very close
                            v["lat"], v["lng"] = end[0], end[1]
                            moved = total_dist
                        else:
                            # fraction of the segment to move this tick
                            s = v.get("_speed_m_s", 5.6) * tick  # meters to move this tick
                            frac = min(1.0, s / total_dist)
                            new_lat = start[0] + (end[0] - start[0]) * frac
                            new_lng = start[1] + (end[1] - start[1]) * frac
                            # update vehicle position
                            prev = (v["lat"], v["lng"])
                            v["lat"], v["lng"] = new_lat, new_lng
                            moved = haversine(prev[0], prev[1], new_lat, new_lng)
                            # update start of path to current pos so next tick continues
                            v["_target_path"][0] = (new_lat, new_lng)
                        # accumulate stats
                        v["total_distance"] = round(v.get("total_distance", 0.0) + moved, 2)
                        system_stats["distance"] = round(system_stats.get("distance", 0.0) + moved, 2)
                        # check if reached destination (within 6 meters)
                        dist_to_target = haversine(v["lat"], v["lng"], end[0], end[1])
                        if dist_to_target <= 6.0:
                            # call complete_trip to finalize
                            try:
                                # call local function to finalize state rather than HTTP call
                                vid = v["id"]
                                bid = v["target_bin"]
                                # finalize details
                                for veh in vehicles:
                                    if veh["id"] == vid:
                                        veh["status"], veh["target_bin"] = "IDLE", None
                                        veh["_moving"] = False
                                        veh["_target_path"] = None
                                        veh["completed"] = veh.get("completed", 0) + 1
                                for b in bins:
                                    if b["id"] == bid:
                                        b["fill"], b["status"] = 0.0, "OK"
                                system_stats["completed"] += 1
                                system_stats["trips_over_time"].append({"time": now_str(), "completed": system_stats["completed"]})
                                bin_alerts.append({
                                    "time": now_str(),
                                    "msg": f"✅ Vehicle {vid} completed trip for Bin {bid} (auto)"
                                })
                            except Exception as e:
                                print("Error finalizing trip:", e)
            time.sleep(tick)
        except Exception as e:
            print("Movement loop error:", e)
            time.sleep(1.0)

threading.Thread(target=movement_loop, daemon=True).start()

# ------------------------------
# Route recording endpoint used by client if needed
# ------------------------------
@app.post("/record_route_assignment")
async def record_route_assignment(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "msg": "invalid json"}

    rec = {
        "time": now_str(),
        "bin": data.get("bin_id"),
        "assigned_vehicle": data.get("vehicle_id"),
        "assigned_distance": round(float(data.get("distance", 0.0)), 1) if data.get("distance") is not None else None,
        "route_time": round(float(data.get("time", 0.0)), 1) if data.get("time") is not None else None,
        "others": data.get("others", [])
    }
    comparison_stats.append(rec)
    if rec.get("assigned_distance"):
        system_stats["distance"] = round(system_stats.get("distance", 0.0) + rec["assigned_distance"], 2)
    # recalc avg ETA roughly (distance / completed) as simple proxy
    if system_stats["completed"] > 0:
        try:
            system_stats["avg_eta"] = round(system_stats.get("distance", 0.0) / system_stats["completed"], 2)
        except Exception:
            pass
    return {"ok": True}

# ------------------------------
# Driver API and UI serving
# ------------------------------
@app.get("/driver/{vehicle_id}")
def driver_dashboard(vehicle_id: int):
    v = next((veh for veh in vehicles if veh["id"] == vehicle_id), None)
    if not v:
        return {"status": "ERROR", "message": "Vehicle not found"}
    if not v.get("target_bin"):
        return {"status": "IDLE", "message": "No active assignment", "vehicle_location": {"lat": v["lat"], "lng": v["lng"]}}
    b = next((bin for bin in bins if bin["id"] == v["target_bin"]), None)
    if not b:
        return {"status": "ERROR", "message": "Assigned bin not found", "vehicle_location": {"lat": v["lat"], "lng": v["lng"]}}
    # compute direct ETA based on vehicle speed
    dist = haversine(v["lat"], v["lng"], b["lat"], b["lng"])
    eta = compute_eta_seconds(dist, v.get("_speed_m_s", 5.6))
    return {
        "status": "ASSIGNED",
        "vehicle_id": v["id"],
        "vehicle_location": {"lat": v["lat"], "lng": v["lng"]},
        "assigned_bin": {"id": b["id"], "fill": b["fill"], "lat": b["lat"], "lng": b["lng"]},
        "completed": v.get("completed", 0),
        "distance_travelled": round(v.get("total_distance", 0.0), 2),
        "eta_seconds": int(eta),
        "instructions": f"Proceed to Bin {b['id']} at coordinates ({b['lat']}, {b['lng']})"
    }

@app.get("/driver_dashboard", response_class=HTMLResponse)
def serve_driver_dashboard():
    if os.path.exists("driver_ai_1.html"):
        return open("driver_ai_1.html", encoding="utf-8").read()
    return "<h2>Driver dashboard file not found</h2>"

# ------------------------------
# Serve main UI
# ------------------------------
@app.get("/", response_class=HTMLResponse)
def home():
    if os.path.exists("ui_final_ai_1.html"):
        return open("ui_final_ai_1.html", encoding="utf-8").read()
    return "<h2>ui_final_ai_1.html not found. Place it in the same folder as app.py</h2>"

# ------------------------------
# Helpful debug endpoint to list filesystem (only for local debugging)
# ------------------------------
@app.get("/_ls")
def list_files():
    try:
        files = os.listdir(".")
        return {"ok": True, "files": files}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------
# Run server
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Smart Waste AI Server running at http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
