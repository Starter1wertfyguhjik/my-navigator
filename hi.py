import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox
import time

# Настройка страницы
st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

# Инициализация хранилища данных
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор (Стабильная версия)")

# ---------------- ФУНКЦИЯ ПОИСКА (БЕЗ ОШИБКИ 429) ----------------
@st.cache_data(ttl=3600)
def search_photon_full(search_term):
    """Использует Photon API для мгновенного получения имен и координат"""
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
                
                # Собираем красивое название
                name_parts = [p.get("city"), p.get("street"), p.get("housenumber")]
                display_name = ", ".join([x for x in name_parts if x]) or p.get("name", "Неизвестное место")
                
                # Возвращаем кортеж (строка для списка, данные для кода)
                results.append((display_name, {
                    "lat": coords[1], 
                    "lon": coords[0], 
                    "name": display_name
                }))
            return results
        return []
    except:
        return []

def address_search_provider(search_term: str):
    time.sleep(0.1) # Защита от слишком частого спама
    return search_photon_full(search_term)

# ---------------- ЗАПРОС РЕАЛЬНЫХ ДОРОГ (OSRM) ----------------
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
    return 0, 0.5 # Заглушка, если сервер дорог временно лежит

# ---------------- ЛОГИКА ОПТИМИЗАЦИИ ----------------
def optimize_route(start_coords, points):
    tz = pytz.timezone('Europe/Moscow')
    curr_time = datetime.now(tz)
    curr_pos = (start_coords[0], start_coords[1])
    ordered = []
    temp = points[:]

    while temp:
        best_p, min_score, travel_h = None, float('inf'), 0
        for p in temp:
            dist, h = get_osrm_route(curr_pos, (p["lat"], p["lon"]))
            arr_time = curr_time + timedelta(hours=h)
            
            # Умный скоринг (учет времени работы)
            score = h * 60
            if arr_time.hour >= p["close"]: score += 10000 # Опоздали
            elif arr_time.hour < p["open"]: score += (p["open"] - arr_time.hour) * 20 # Рано приехали
            
            if score < min_score:
                min_score, best_p, travel_h = score, p, h
        
        curr_time += timedelta(hours=travel_h)
        if curr_time.hour < best_p["open"]:
            curr_time = curr_time.replace(hour=best_p["open"], minute=0)
            
        curr_pos = (best_p["lat"], best_p["lon"])
        ordered.append(best_p)
        temp.remove(best_p)
    return ordered, datetime.now(tz).strftime("%H:%M")

# ---------------- БОКОВАЯ ПАНЕЛЬ ----------------
with st.sidebar:
    st.header("📍 Маршрут")
    
    st.write("**Откуда едем?**")
    start_obj = st_searchbox(address_search_provider, key="start_search", placeholder="Введите адрес старта...")

    st.markdown("---")
    st.write("**Куда едем?**")
    new_point_obj = st_searchbox(address_search_provider, key="point_search", placeholder="Добавить точку...")
    
    c1, c2 = st.columns(2)
    with c1: open_h = st.number_input("Откр.", 0, 23, 9)
    with c2: close_h = st.number_input("Закр.", 0, 23, 21)
    
    if st.button("➕ Добавить в список"):
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
        st.write("---")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['addr'][:30]}...")
        if st.button("🗑 Очистить список"):
            st.session_state.points_list = []
            st.rerun()

    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# ---------------- ОСНОВНОЙ ЭКРАН ----------------
if btn_calc:
    if start_obj and st.session_state.points_list:
        with st.spinner("Рассчитываем кратчайший путь..."):
            ordered, msk_t = optimize_route((start_obj["lat"], start_obj["lon"]), st.session_state.points_list)
            st.session_state.route_data = {
                "start": start_obj, 
                "stops": ordered, 
                "time": msk_t
            }
    else:
        st.error("Выберите точку старта и добавьте хотя бы одну точку назначения!")

if st.session_state.route_data:
    rd = st.session_state.route_data
    st.success(f"Выезд запланирован на {rd['time']} (МСК)")

    # Карта Folium
    m = folium.Map(location=[rd['start']['lat'], rd['start']['lon']], zoom_start=11)
    
    # Рисуем точки
    folium.Marker([rd['start']['lat'], rd['start']['lon']], icon=folium.Icon(color='red', icon='star'), tooltip="СТАРТ").add_to(m)
    
    path = [[rd['start']['lat'], rd['start']['lon']]]
    for i, p in enumerate(rd['stops'], 1):
        folium.Marker([p['lat'], p['lon']], tooltip=f"{i}. {p['addr']}", icon=folium.Icon(color='blue')).add_to(m)
        path.append([p['lat'], p['lon']])
    
    path.append([rd['start']['lat'], rd['start']['lon']]) # Возврат
    folium.PolyLine(path, color="#2980b9", weight=4, opacity=0.8).add_to(m)
    
    st_folium(m, width="100%", height=500, key="map")

    # Кнопка для Google Maps
    wp = "|".join([f"{p['lat']},{p['lon']}" for p in rd['stops']])
    g_url = f"https://www.google.com/maps/dir/?api=1&origin={rd['start']['lat']},{rd['start']['lon']}&destination={rd['start']['lat']},{rd['start']['lon']}&waypoints={wp}&travelmode=driving"

    st.markdown(f"""
        <a href="{g_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;font-size:20px;">
                🚀 ОТКРЫТЬ МАРШРУТ В GOOGLE MAPS
            </div>
        </a>
    """, unsafe_allow_html=True)
