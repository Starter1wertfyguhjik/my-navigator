import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import pytz  # Добавляем для работы с часовыми поясами

# Настройка страницы
st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор (Московское время)")

# ---------------- ФУНКЦИИ ----------------
@st.cache_data
def get_coordinates_cached(address):
    try:
        geolocator = Nominatim(user_agent="smart_nav_msk_2026")
        loc = geolocator.geocode(address, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except:
        pass
    return None

# ---------------- ЛОГИКА ОПТИМИЗАЦИИ (МСК) ----------------
def optimize_route_by_time(start_coords, points):
    avg_speed = 30  
    
    # ПРИНУДИТЕЛЬНОЕ МОСКОВСКОЕ ВРЕМЯ
    tz_moscow = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(tz_moscow) 
    
    current_pos = start_coords
    ordered_route = []
    remaining_points = points[:]

    while remaining_points:
        best_pt = None
        min_score = float('inf')

        for p in remaining_points:
            dist = geodesic(current_pos, (p["lat"], p["lon"])).km
            travel_hours = dist / avg_speed
            arrival_time = current_time + timedelta(hours=travel_hours)

            if p["close"]:
                # Время закрытия точки в часовом поясе МСК
                close_dt = current_time.replace(hour=p["close"], minute=0, second=0, microsecond=0)
                
                # Если точка закрывается ночью/вечером, а сейчас уже позже — перенос на след. день не делаем, 
                # алгоритм просто пометит её как "опоздавшую"
                hours_left = (close_dt - arrival_time).total_seconds() / 3600
                
                if hours_left < 0:
                    score = 2000 + dist  # Штраф за опоздание
                else:
                    # Чем меньше времени до закрытия, тем выше приоритет
                    score = dist + (hours_left * 8)
            else:
                score = dist + 150 

            if score < min_score:
                min_score = score
                best_pt = p

        target = best_pt if best_pt else remaining_points[0]
        step_dist = geodesic(current_pos, (target["lat"], target["lon"])).km
        
        current_time += timedelta(hours=step_dist / avg_speed)
        current_pos = (target["lat"], target["lon"])
        ordered_route.append(target)
        remaining_points.remove(target)

    return ordered_route, datetime.now(tz_moscow).strftime("%H:%M")

# ---------------- ИНТЕРФЕЙС ----------------
with st.sidebar:
    st.header("📍 Настройка")
    start_query = st.text_input("Откуда едем?", "Москва, Красная площадь")
    dest_raw = st.text_area(
        "Точки (Адрес | Час закрытия)",
        "Москва, Тверская 1 | 18\nМосква, Новый Арбат 10 | 21\nМосква, ВДНХ",
        height=150
    )
    btn_calc = st.button("🚀 Рассчитать")

if btn_calc:
    start_data = get_coordinates_cached(start_query)
    if start_data:
        raw_lines = [line.strip() for line in dest_raw.split("\n") if line.strip()]
        parsed_points = []
        for line in raw_lines:
            if "|" in line:
                parts = line.split("|")
                addr, close_h = parts[0].strip(), int(parts[1].strip())
            else:
                addr, close_h = line.strip(), None
            
            coords = get_coordinates_cached(addr)
            if coords:
                parsed_points.append({"lat": coords[0], "lon": coords[1], "name": coords[2], "close": close_h})

        if parsed_points:
            final_stops, msk_now = optimize_route_by_time((start_data[0], start_data[1]), parsed_points)
            st.session_state.route_data = {"start": start_data, "stops": final_stops, "time": msk_now}

# ---------------- КАРТА И КНОПКА ----------------
if st.session_state.route_data:
    res = st.session_state.route_data
    s_lat, s_lon, s_name = res["start"]
    stops = res["stops"]

    st.write(f"🕒 Время отправления (МСК): **{res['time']}**")

    path_coords = [(s_lat, s_lon)] + [(p["lat"], p["lon"]) for p in stops] + [(s_lat, s_lon)]
    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)
    folium.PolyLine(path_coords, color="#3498db", weight=5).add_to(m)
    folium.Marker([s_lat, s_lon], icon=folium.Icon(color="red")).add_to(m)
    for i, p in enumerate(stops, 1):
        folium.Marker([p["lat"], p["lon"]], tooltip=f"{i}. {p['name']}", icon=folium.Icon(color="blue")).add_to(m)

    # Карта без "белого экрана"
    st_folium(m, width="100%", height=500, returned_objects=[], key="msk_map")

    # Кнопка навигации
    origin = f"{s_lat},{s_lon}"
    waypts = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypts}&travelmode=driving"

    st.markdown(f"""
        <a href="{google_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745; color:white; padding:20px; text-align:center; border-radius:15px; font-size:22px; font-weight:bold;">
                🚀 ОТКРЫТЬ В НАВИГАТОРЕ
            </div>
        </a>
    """, unsafe_allow_html=True)

