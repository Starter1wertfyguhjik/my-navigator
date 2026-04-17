import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox
import time

# --- НАСТРОЙКИ СТРАНИЦЫ ---
st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

# Инициализация переменных в памяти, чтобы данные не пропадали
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор 2026 (Стабильная версия)")

# --- 1. ФУНКЦИЯ ПОИСКА (Photon - Бесплатно и быстро) ---
def address_search_provider(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    
    # Небольшая пауза, чтобы не спамить API при наборе каждой буквы
    time.sleep(0.3)
    
    url = "https://photon.komoot.io/api/"
    params = {"q": search_term, "limit": 8, "lang": "ru"}
    
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            features = r.json().get("features", [])
            results = []
            for f in features:
                p = f.get("properties", {})
                c = f.get("geometry", {}).get("coordinates") # [lon, lat]
                
                # Формируем читаемый адрес
                addr_label = ", ".join(filter(None, [p.get("city"), p.get("street"), p.get("housenumber")]))
                if not addr_label:
                    addr_label = p.get("name", "Неизвестный адрес")
                
                # Возвращаем кортеж: (что видит юзер, данные для кода)
                results.append((addr_label, {"lat": c[1], "lon": c[0], "name": addr_label}))
            return results
    except:
        pass
    return []

# --- 2. ЗАПРОС ДОРОГ (OSRM) ---
def get_osrm_route(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            dist_km = data["routes"][0]["distance"] / 1000.0
            duration_sec = data["routes"][0]["duration"]
            return dist_km, duration_sec / 3600.0
    except:
        pass
    return 0, 0.5 # Заглушка, если сервер дорог упал

# --- 3. ИНТЕРФЕЙС (SIDEBAR) ---
with st.sidebar:
    st.header("📍 Настройки")

    st.write("**Точка старта:**")
    start_res = st_searchbox(address_search_provider, key="start_box", placeholder="Откуда едем?")

    st.markdown("---")
    st.write("**Добавить остановку:**")
    point_res = st_searchbox(address_search_provider, key="point_box", placeholder="Куда заехать?")
    
    col1, col2 = st.columns(2)
    with col1: open_h = st.number_input("Открытие", 0, 23, 9)
    with col2: close_h = st.number_input("Закрытие", 0, 23, 21)
    
    if st.button("➕ Добавить в маршрут"):
        if point_res:
            st.session_state.points_list.append({
                "lat": point_res["lat"], "lon": point_res["lon"],
                "name": point_res["name"], "open": open_h, "close": close_h
            })
            st.toast(f"Добавлено: {point_res['name']}")
        else:
            st.warning("Выберите адрес из списка!")

    if st.session_state.points_list:
        st.write("**Ваш список:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['name']}")
        if st.button("🗑 Очистить"):
            st.session_state.points_list = []
            st.session_state.route_data = None
            st.rerun()

    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# --- 4. РАСЧЕТ И ОПТИМИЗАЦИЯ ---
if btn_calc:
    if not start_res or not st.session_state.points_list:
        st.error("Укажите старт и добавьте хотя бы одну точку!")
    else:
        with st.spinner("Оптимизируем маршрут по времени..."):
            tz = pytz.timezone('Europe/Moscow')
            curr_time = datetime.now(tz)
            curr_pos = (start_res["lat"], start_res["lon"])
            ordered = []
            temp = st.session_state.points_list[:]

            while temp:
                best_p, min_score, travel_h = None, float('inf'), 0
                for p in temp:
                    _, h = get_osrm_route(curr_pos, (p["lat"], p["lon"]))
                    arrival_h = (curr_time + timedelta(hours=h)).hour
                    
                    score = h * 60 # Время в пути
                    if arrival_h >= p["close"]: score += 10000 # Опоздали
                    elif arrival_h < p["open"]: score += (p["open"] - arrival_h) * 20 # Ждем открытия
                    
                    if score < min_score:
                        min_score, best_p, travel_h = score, p, h
                
                curr_time += timedelta(hours=travel_h)
                if curr_time.hour < best_p["open"]:
                    curr_time = curr_time.replace(hour=best_p["open"], minute=0)
                
                curr_pos = (best_p["lat"], best_p["lon"])
                ordered.append(best_p)
                temp.remove(best_p)

            st.session_state.route_data = {
                "start": start_res,
                "stops": ordered,
                "time_str": datetime.now(tz).strftime("%H:%M")
            }

# --- 5. ВЫВОД КАРТЫ И КНОПКИ ---
if st.session_state.route_data:
    rd = st.session_state.route_data
    st.info(f"🕒 Время выезда: {rd['time_str']} (МСК)")

    m = folium.Map(location=[rd['start']['lat'], rd['start']['lon']], zoom_start=11)
    folium.Marker([rd['start']['lat'], rd['start']['lon']], icon=folium.Icon(color='red', icon='home')).add_to(m)
    
    path = [[rd['start']['lat'], rd['start']['lon']]]
    for i, p in enumerate(rd['stops'], 1):
        folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=folium.Icon(color='blue')).add_to(m)
        path.append([p['lat'], p['lon']])
    path.append([rd['start']['lat'], rd['start']['lon']])
    
    folium.PolyLine(path, color="#2980b9", weight=4).add_to(m)
    st_folium(m, width="100%", height=500, key="main_map")

    # Кнопка Google Maps
    wp = "|".join([f"{p['lat']},{p['lon']}" for p in rd['stops']])
    g_url = f"https://www.google.com/maps/dir/?api=1&origin={rd['start']['lat']},{rd['start']['lon']}&destination={rd['start']['lat']},{rd['start']['lon']}&waypoints={wp}&travelmode=driving"
    
    st.markdown(f"""
        <a href="{g_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">
                🗺 ОТКРЫТЬ В GOOGLE MAPS (ПОЛНЫЙ ПУТЬ)
            </div>
        </a>
    """, unsafe_allow_html=True)
