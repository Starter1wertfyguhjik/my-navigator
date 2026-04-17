import streamlit as st
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime, timedelta
import pytz
import time

# --- НАСТРОЙКИ ---
st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

# Инициализация состояний, чтобы данные не пропадали при обновлении страницы
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None
if "start_point" not in st.session_state:
    st.session_state.start_point = None

st.title("🚗 Умный Навигатор (Стабильная версия)")

# --- ФУНКЦИЯ ГЕОКОДИНГА (ПОИСК) ---
def fetch_location(query):
    """Ищет координаты через Photon API (OpenStreetMap)"""
    if not query or len(query) < 3:
        return None
    url = "https://photon.komoot.io/api/"
    params = {"q": query, "limit": 1, "lang": "ru"}
    try:
        r = requests.get(url, params=params, timeout=5)
        features = r.json().get("features", [])
        if features:
            f = features[0]
            p = f["properties"]
            c = f["geometry"]["coordinates"]
            # Собираем понятный адрес
            name = ", ".join(filter(None, [p.get("city"), p.get("street"), p.get("housenumber")])) or p.get("name", "Неизвестное место")
            return {"lat": c[1], "lon": c[0], "name": name}
    except Exception as e:
        st.error(f"Ошибка поиска: {e}")
    return None

# --- ЗАПРОС ДОРОГ (OSRM) ---
def get_osrm_route(start, end):
    url = f"http://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=false"
    try:
        r = requests.get(url, timeout=3)
        data = r.json()
        if data.get("code") == "Ok":
            return data["routes"][0]["distance"] / 1000.0, data["routes"][0]["duration"] / 3600.0
    except:
        pass
    return 0, 0.5 # Заглушка: 30 минут пути

# --- БОКОВАЯ ПАНЕЛЬ (ИНТЕРФЕЙС) ---
with st.sidebar:
    st.header("📍 Маршрут")
    
    # СЕКЦИЯ СТАРТА
    st.subheader("1. Откуда выезжаем?")
    start_input = st.text_input("Введите город, улицу", placeholder="Москва, Арбат...", key="input_start")
    if st.button("🚩 Установить старт"):
        res = fetch_location(start_input)
        if res:
            st.session_state.start_point = res
            st.success(f"Выбрано: {res['name']}")
        else:
            st.error("Адрес не найден. Попробуйте уточнить.")

    st.markdown("---")
    
    # СЕКЦИЯ ТОЧЕК
    st.subheader("2. Куда заедем?")
    point_input = st.text_input("Адрес остановки", placeholder="Тверская, 7...", key="input_point")
    
    c1, c2 = st.columns(2)
    with c1: open_h = st.number_input("Открытие (час)", 0, 23, 9)
    with c2: close_h = st.number_input("Закрытие (час)", 0, 23, 21)
    
    if st.button("➕ Добавить точку"):
        if point_input:
            res = fetch_location(point_input)
            if res:
                st.session_state.points_list.append({
                    **res, "open": open_h, "close": close_h
                })
                st.toast(f"Добавлено: {res['name']}")
            else:
                st.error("Адрес точки не найден")
        else:
            st.warning("Введите адрес!")

    # СПИСОК ДОБАВЛЕННЫХ
    if st.session_state.points_list:
        st.write("**Ваш список:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['name']} ({p['open']}-{p['close']})")
        
        if st.button("🗑 Очистить список"):
            st.session_state.points_list = []
            st.session_state.route_data = None
            st.rerun()

    st.markdown("---")
    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# --- ЛОГИКА ОПТИМИЗАЦИИ ---
if btn_calc:
    if not st.session_state.start_point or not st.session_state.points_list:
        st.error("Нужен адрес старта и хотя бы одна точка!")
    else:
        with st.spinner("Считаем лучший путь..."):
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
                        if arr_h >= p['close']: score += 10000 # Опоздали
                        elif arr_h < p['open']: score += (p['open'] - arr_h) * 20 # Ждем открытия
                        if score < min_score:
                            min_score, best_p, travel_h = score, p, h
                    
                    curr_time += timedelta(hours=travel_h)
                    if curr_time.hour < best_p['open']:
                        curr_time = curr_time.replace(hour=best_p['open'], minute=0)
                    curr_pos = (best_p['lat'], best_p['lon'])
                    ordered.append(best_p)
                    temp.remove(best_p)
                return ordered, datetime.now(tz).strftime("%H:%M")

            res_ordered, res_time = optimize(st.session_state.start_point, st.session_state.points_list)
            st.session_state.route_data = {"stops": res_ordered, "time": res_time}

# --- КАРТА И РЕЗУЛЬТАТЫ ---
if st.session_state.route_data:
    rd = st.session_state.route_data
    sp = st.session_state.start_point
    
    st.info(f"🕒 Время выезда: {rd['time']} (МСК)")

    m = folium.Map(location=[sp['lat'], sp['lon']], zoom_start=11)
    folium.Marker([sp['lat'], sp['lon']], icon=folium.Icon(color='red', icon='home'), tooltip="СТАРТ").add_to(m)
    
    path = [[sp['lat'], sp['lon']]]
    for i, p in enumerate(rd['stops'], 1):
        folium.Marker([p['lat'], p['lon']], tooltip=f"{i}. {p['name']}", icon=folium.Icon(color='blue')).add_to(m)
        path.append([p['lat'], p['lon']])
    path.append([sp['lat'], sp['lon']]) # Возврат
    
    folium.PolyLine(path, color="#2980b9", weight=4).add_to(m)
    st_folium(m, width="100%", height=500, key="main_map")

    # Ссылка в Google Maps
    wp = "|".join([f"{p['lat']},{p['lon']}" for p in rd['stops']])
    g_url = f"https://www.google.com/maps/dir/?api=1&origin={sp['lat']},{sp['lon']}&destination={sp['lat']},{sp['lon']}&waypoints={wp}&travelmode=driving"
    
    st.markdown(f"""
        <a href="{g_url}" target="_blank" style="text-decoration:none;">
            <div style="background:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;font-size:18px;">
                🗺 ОТКРЫТЬ МАРШРУТ В GOOGLE MAPS
            </div>
        </a>
    """, unsafe_allow_html=True)
