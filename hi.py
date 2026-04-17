import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox
import time

st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

# Инициализация состояний
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор (Без блокировок API)")

# ---------------- ФУНКЦИЯ ПОИСКА (Photon с координатами) ----------------
@st.cache_data(ttl=3600)
def search_photon_full(search_term):
    if not search_term or len(search_term) < 3:
        return []
    url = "https://photon.komoot.io/api/"
    params = {"q": search_term, "limit": 10, "lang": "ru"}
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            features = r.json().get("features", [])
            results = []
            for f in features:
                p = f.get("properties", {})
                coords = f.get("geometry", {}).get("coordinates") # [lon, lat]
                
                name_parts = [p.get("city"), p.get("street"), p.get("housenumber")]
                display_name = ", ".join([x for x in name_parts if x]) or p.get("name", "Неизвестно")
                
                # Сохраняем и имя, и координаты в кортеж для searchbox
                results.append((display_name, {"lat": coords[1], "lon": coords[0], "name": display_name}))
            return results
        return []
    except:
        return []

def address_search_provider(search_term: str):
    time.sleep(0.2) # Защита от спама
    return search_photon_full(search_term)

# ---------------- ЗАПРОС ДОРОГ (OSRM) ----------------
def get_osrm_route(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            route = data["routes"][0]
            return route["distance"] / 1000.0, route["duration"] / 3600.0
    except:
        pass
    from geopy.distance import geodesic
    dist = geodesic(start_coords, end_coords).km
    return dist, dist / 30.0

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("📍 Настройка")

    st.write("**Откуда едем?**")
    # Возвращает объект с координатами напрямую
    start_obj = st_searchbox(address_search_provider, key="start_search", placeholder="Старт...")
    
    st.markdown("---")
    st.write("**Куда едем?**")
    new_point_obj = st_searchbox(address_search_provider, key="point_search", placeholder="Адрес точки...")
    
    col_time1, col_time2 = st.columns(2)
    with col_time1: open_h = st.number_input("Открытие", 0, 23, 9)
    with col_time2: close_h = st.number_input("Закрытие", 0, 23, 21)
    
    if st.button("➕ Добавить"):
        if new_point_obj:
            st.session_state.points_list.append({
                "lat": new_point_obj["lat"],
                "lon": new_point_obj["lon"],
                "addr": new_point_obj["name"],
                "open": open_h,
                "close": close_h
            })
            st.toast("Точка добавлена")

    if st.session_state.points_list:
        if st.button("🗑 Очистить"):
            st.session_state.points_list = []
            st.rerun()

    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# ---------------- ОПТИМИЗАЦИЯ ----------------
def optimize_route(start_lat_lon, points):
    tz = pytz.timezone('Europe/Moscow')
    curr_time = datetime.now(tz)
    curr_pos = start_lat_lon
    ordered = []
    temp = points[:]

    while temp:
        best_p, min_score, travel_h = None, float('inf'), 0
        for p in temp:
            dist, h = get_osrm_route(curr_pos, (p["lat"], p["lon"]))
            arr_time = curr_time + timedelta(hours=h)
            
            # Упрощенный скоринг
            score = h * 60
            if arr_time.hour >= p["close"]: score += 10000
            elif arr_time.hour < p["open"]: score += (p["open"] - arr_time.hour) * 30
            
            if score < min_score:
                min_score, best_p, travel_h = score, p, h
        
        curr_time += timedelta(hours=travel_h)
        if curr_time.hour < best_p["open"]:
            curr_time = curr_time.replace(hour=best_p["open"], minute=0)
            
        curr_pos = (best_p["lat"], best_p["lon"])
        ordered.append(best_p)
        temp.remove(best_p)
    return ordered, datetime.now(tz).strftime("%H:%M")

# ---------------- ЛОГИКА ВЫВОДА ----------------
if btn_calc:
    if start_obj and st.session_state.points_list:
        with st.spinner("Считаем..."):
            ordered, msk_t = optimize_route((start_obj["lat"], start_obj["lon"]), st.session_state.points_list)
            st.session_state.route_data = {"start": start_obj, "stops": ordered, "time": msk_t}
    else:
        st.error("Выберите старт и добавьте точки!")

if st.session_state.route_data:
    rd = st.session_state.route_data
    st.info(f"🕒 Выезд в {rd['time']} (МСК)")
    
    # Карта
    m = folium.Map(location=[rd['start']['lat'], rd['start']['lon']], zoom_start=11)
    folium.Marker([rd['start']['lat'], rd['start']['lon']], icon=folium.Icon(color='red')).add_to(m)
    
    pts = [[rd['start']['lat'], rd['start']['lon']]]
    for i, p in enumerate(rd['stops'], 1):
        folium.Marker([p['lat'], p['lon']], tooltip=f"{i}. {p['addr']}", icon=folium.Icon(color='blue')).add_to(m)
        pts.append([p['lat'], p['lon']])
    pts.append([rd['start']['lat'], rd['start']['lon']])
    folium.PolyLine(pts, color="blue", weight=3).add_to(m)
    
    st_folium(m, width="100%", height=500, key="map")

    # Ссылка Google Maps (ИСПРАВЛЕННАЯ)
    wp = "|".join([f"{p['lat']},{p['lon']}" for p in rd['stops']])
    g_url = f"https://www.google.com/maps/dir/?api=1&origin={rd['start']['lat']},{rd['start']['lon']}&destination={rd['start']['lat']},{rd['start']['lon']}&waypoints={wp}&travelmode=driving"

    st.markdown(f'<a href="{g_url}" target="_blank"><div style="background:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">🚀 В GOOGLE MAPS</div></a>', unsafe_allow_html=True)
