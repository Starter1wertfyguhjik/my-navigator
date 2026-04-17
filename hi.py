import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime, timedelta
import pytz
import time

# Настройка
st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None
if "start_point" not in st.session_state:
    st.session_state.start_point = None

st.title("🚗 Умный Навигатор (Стабильная версия)")

# --- ФУНКЦИЯ ГЕОКОДИРОВАНИЯ (ПОИСКА) ---
def get_location_data(query):
    if not query: return None
    url = f"https://photon.komoot.io/api/?q={query}&limit=5&lang=ru"
    try:
        r = requests.get(url, timeout=5)
        features = r.json().get("features", [])
        if features:
            f = features[0]
            p = f["properties"]
            c = f["geometry"]["coordinates"]
            name = ", ".join(filter(None, [p.get("city"), p.get("street"), p.get("housenumber")])) or p.get("name", "Место")
            return {"lat": c[1], "lon": c[0], "name": name}
    except:
        st.error("Ошибка связи с сервером поиска")
    return None

# --- ЗАПРОС ДОРОГ (OSRM) ---
def get_osrm_route(start, end):
    url = f"http://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            route = data["routes"][0]
            return route["distance"] / 1000.0, route["duration"] / 3600.0
    except:
        pass
    return 0, 0.5

# --- SIDEBAR (ИНТЕРФЕЙС) ---
with st.sidebar:
    st.header("📍 Маршрут")
    
    # СТАРТ
    st.subheader("1. Точка старта")
    start_input = st.text_input("Введите адрес старта (напр. Москва, Арбат)", key="st_in")
    if st.button("✅ Подтвердить старт"):
        res = get_location_data(start_input)
        if res:
            st.session_state.start_point = res
            st.success(f"Старт установлен: {res['name']}")
        else:
            st.error("Адрес не найден")

    st.markdown("---")
    
    # ТОЧКИ НАЗНАЧЕНИЯ
    st.subheader("2. Добавить остановку")
    point_input = st.text_input("Адрес точки", key="pt_in")
    c1, c2 = st.columns(2)
    with c1: open_h = st.number_input("Откр.", 0, 23, 9)
    with c2: close_h = st.number_input("Закр.", 0, 23, 21)
    
    if st.button("➕ Добавить в список"):
        res = get_location_data(point_input)
        if res:
            st.session_state.points_list.append({
                **res, "open": open_h, "close": close_h
            })
            st.toast("Добавлено!")
        else:
            st.error("Не нашли адрес")

    # СПИСОК
    if st.session_state.points_list:
        st.write("**Ваш список:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['name']}")
        if st.button("🗑 Очистить"):
            st.session_state.points_list = []
            st.session_state.route_data = None
            st.rerun()

    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# --- ЛОГИКА РАСЧЕТА ---
if btn_calc:
    if not st.session_state.start_point or not st.session_state.points_list:
        st.error("Установите старт и добавьте хотя бы одну точку!")
    else:
        # (Логика оптимизации остается прежней, она работает хорошо)
        def optimize(start, pts):
            tz = pytz.timezone('Europe/Moscow')
            curr_time = datetime.now(tz)
            curr_pos = (start['lat'], start['lon'])
            ordered = []
            temp = pts[:]
            while temp:
                best_p, min_score, travel_h = None, float('inf'), 0
                for p in temp:
                    _, h = get_osrm_route(curr_pos, (p['lat'], p['lon']))
                    arr_h = (curr_time + timedelta(hours=h)).hour
                    score = h * 60
                    if arr_h >= p['close']: score += 5000
                    elif arr_h < p['open']: score += (p['open'] - arr_h) * 20
                    if score < min_score:
                        min_score, best_p, travel_h = score, p, h
                curr_time += timedelta(hours=travel_h)
                curr_pos = (best_p['lat'], best_p['lon'])
                ordered.append(best_p); temp.remove(best_p)
            return ordered, datetime.now(tz).strftime("%H:%M")

        ordered, t_start = optimize(st.session_state.start_point, st.session_state.points_list)
        st.session_state.route_data = {"stops": ordered, "time": t_start}

# --- КАРТА ---
if st.session_state.route_data:
    rd = st.session_state.route_data
    sp = st.session_state.start_point
    
    st.success(f"Маршрут готов! Время выезда: {rd['time']}")
    
    m = folium.Map(location=[sp['lat'], sp['lon']], zoom_start=11)
    folium.Marker([sp['lat'], sp['lon']], icon=folium.Icon(color='red', icon='home')).add_to(m)
    
    path = [[sp['lat'], sp['lon']]]
    for i, p in enumerate(rd['stops'], 1):
        folium.Marker([p['lat'], p['lon']], tooltip=p['name'], icon=folium.Icon(color='blue')).add_to(m)
        path.append([p['lat'], p['lon']])
    path.append([sp['lat'], sp['lon']])
    folium.PolyLine(path, color="blue", weight=3).add_to(m)
    
    st_folium(m, width=1000, height=500)

    # Google Maps
    wp = "|".join([f"{p['lat']},{p['lon']}" for p in rd['stops']])
    g_url = f"https://www.google.com/maps/dir/?api=1&origin={sp['lat']},{sp['lon']}&destination={sp['lat']},{sp['lon']}&waypoints={wp}&travelmode=driving"
    st.markdown(f'<a href="{g_url}" target="_blank"><div style="background:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">ОТКРЫТЬ В GOOGLE MAPS</div></a>', unsafe_allow_html=True)
